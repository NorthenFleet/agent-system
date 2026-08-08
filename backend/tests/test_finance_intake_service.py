from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.finance_models import (
    BankTransaction,
    BudgetVersion,
    ExpenseRecord,
    FinanceIntakeEvent,
    FinanceIntakeJob,
    FinanceProject,
    Invoice,
    Payment,
    Reimbursement,
)
from models.v2_models import User
from services.finance_intake_service import (
    FinanceIntakeConflict,
    FinanceIntakeForbidden,
    FinanceIntakeService,
)


@pytest.fixture
def intake_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'finance-intake.db'}")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            FinanceProject.__table__,
            BudgetVersion.__table__,
            Reimbursement.__table__,
            Invoice.__table__,
            ExpenseRecord.__table__,
            Payment.__table__,
            BankTransaction.__table__,
            FinanceIntakeJob.__table__,
            FinanceIntakeEvent.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(
        User(
            id=1,
            username="finance-owner",
            password_hash="not-used",
            display_name="财务申请人",
            role="viewer",
            is_active=True,
        )
    )
    session.add(
        FinanceProject(
            id="project-finance-1",
            project_key="finance-test",
            name="财务测试项目",
            owner_user_id=1,
            created_by=1,
            status="active",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _formal_counts(db):
    return {
        "projects": db.query(FinanceProject).count(),
        "budgets": db.query(BudgetVersion).count(),
        "reimbursements": db.query(Reimbursement).count(),
        "invoices": db.query(Invoice).count(),
        "expenses": db.query(ExpenseRecord).count(),
        "payments": db.query(Payment).count(),
        "transactions": db.query(BankTransaction).count(),
    }


def _payload(**overrides):
    payload = {
        "command_message_id": "msg-finance-1",
        "external_message_id": "om-finance-1",
        "source_channel": "feishu",
        "source_account_id": "soundwave",
        "external_conversation_id": "user:ou_finance",
        "external_user_id": "ou_finance",
        "requested_by_user_id": 1,
        "target_agent_id": "soundwave",
        "request_text": "请分析一笔100元差旅报销，不要写入正式财务账。",
        "request_metadata": {"phase": "shadow"},
    }
    payload.update(overrides)
    return payload


def test_stage_is_idempotent_and_keeps_formal_tables_read_only(intake_db):
    service = FinanceIntakeService(intake_db)
    before = _formal_counts(intake_db)

    created = service.stage(**_payload())
    replayed = service.stage(**_payload())

    assert created["replayed"] is False
    assert created["job"]["operation_type"] == "reimbursement"
    assert created["job"]["mode"] == "shadow"
    assert created["job"]["status"] == "shadow_read"
    assert replayed["replayed"] is True
    assert replayed["job"]["id"] == created["job"]["id"]
    assert intake_db.query(FinanceIntakeJob).count() == 1
    assert intake_db.query(FinanceIntakeEvent).count() == 2
    assert _formal_counts(intake_db) == before

    detail = service.get_job(created["job"]["id"], user_id=1, system_role="viewer")
    assert detail["shadow_snapshot"]["write_capability"] == "disabled"
    assert detail["shadow_snapshot"]["record_counts"]["reimbursements"] == 0
    assert [event["event_type"] for event in detail["events"]] == [
        "received",
        "formal_snapshot_captured",
    ]


def test_same_command_message_cannot_change_request_content(intake_db):
    service = FinanceIntakeService(intake_db)
    service.stage(**_payload())

    with pytest.raises(FinanceIntakeConflict):
        service.stage(**_payload(request_text="把同一消息改成另一笔付款"))


def test_extraction_requires_deterministic_validation_and_independent_review(intake_db):
    service = FinanceIntakeService(intake_db)
    before = _formal_counts(intake_db)
    job = service.stage(**_payload())["job"]
    extraction = service.submit_extraction(
        job["id"],
        agent_id="soundwave",
        payload={
            "project_id": "project-finance-1",
            "title": "差旅报销",
            "currency": "CNY",
            "total_amount": "100.00",
            "items": [
                {
                    "description": "车票",
                    "amount": "100.00",
                    "expense_date": date.today().isoformat(),
                }
            ],
        },
        evidence=["用户原始消息"],
        confidence=0.95,
        expected_version=1,
    )

    assert extraction["job"]["status"] == "needs_review"
    assert extraction["job"]["lock_version"] == 2
    assert extraction["validation"]["valid"] is True
    with pytest.raises(FinanceIntakeForbidden):
        service.submit_review(
            job["id"],
            reviewer_agent_id="soundwave",
            decision="approve",
            summary="不能自己复核",
            findings=[],
            confidence=1,
            expected_version=2,
        )

    reviewed = service.submit_review(
        job["id"],
        reviewer_agent_id="inspector",
        decision="approve",
        summary="金额、项目与明细一致",
        findings=[],
        confidence=0.93,
        expected_version=2,
    )
    assert reviewed["job"]["status"] == "validated"
    assert reviewed["review"]["independent_from"] == "soundwave"
    assert _formal_counts(intake_db) == before


def test_invalid_extraction_cannot_be_approved(intake_db):
    service = FinanceIntakeService(intake_db)
    job = service.stage(**_payload(command_message_id="msg-finance-invalid"))["job"]
    extraction = service.submit_extraction(
        job["id"],
        agent_id="soundwave",
        payload={"title": "缺少项目和金额", "items": []},
        evidence=[],
        confidence=0.5,
        expected_version=1,
    )
    assert extraction["validation"]["valid"] is False

    with pytest.raises(FinanceIntakeConflict):
        service.submit_review(
            job["id"],
            reviewer_agent_id="inspector",
            decision="approve",
            summary="错误批准",
            findings=[],
            confidence=0.5,
            expected_version=2,
        )
