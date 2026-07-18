from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import Base
from models.finance_models import (
    ApprovalTask,
    ApprovalInstance,
    BankStatementImport,
    BankTransaction,
    BudgetLine,
    FinanceAuditEvent,
    FinanceProjectMembership,
    FinanceUserRole,
    Payment,
    ReconciliationMatch,
    Reimbursement,
)
from models.v2_models import User
from schemas.finance import (
    BudgetCreate,
    BudgetLineInput,
    BudgetLinesReplace,
    FundAllocationCreate,
    InvoiceCreate,
    PaymentConfirm,
    PaymentCreate,
    ProjectCreate,
    ReimbursementCreate,
    ReimbursementItemCreate,
    RoleGrant,
    WorkflowCreate,
    WorkflowStepInput,
)
from services.finance_v2_service import FinanceConflict, FinanceServiceV2


@pytest.fixture
def finance_context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'finance-test.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    users = {}
    for username, role in (("admin", "admin"), ("applicant", "viewer"), ("reviewer", "viewer"), ("cashier", "viewer")):
        user = User(username=username, password_hash="x", display_name=username, role=role, is_active=True)
        session.add(user)
        session.flush()
        users[username] = user
    session.commit()

    def svc(name: str) -> FinanceServiceV2:
        user = users[name]
        return FinanceServiceV2(session, {"sub": str(user.id), "username": user.username, "role": user.role})

    yield session, users, svc
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def prepare_approved_budget(finance_context, amount=Decimal("1000.00")):
    session, users, svc = finance_context
    admin = svc("admin")
    project = admin.create_project(ProjectCreate(project_key="project-a", name="项目 A"))
    admin.create_allocation(FundAllocationCreate(
        project_id=project["id"], reference_no="ALLOC-001", amount=amount,
        allocated_at=date(2026, 7, 18), source="测试拨付",
    ))
    budget = admin.create_budget(BudgetCreate(project_id=project["id"], name="2026预算", approved_amount=amount))
    budget = admin.replace_budget_lines(budget["id"], BudgetLinesReplace(
        version=budget["lock_version"],
        lines=[BudgetLineInput(category="差旅费", amount=amount)],
    ))
    budget = admin.approve_budget(budget["id"], budget["lock_version"])
    line = budget["lines"][0]
    for username, role in (("applicant", "applicant"), ("reviewer", "reviewer"), ("cashier", "cashier")):
        admin.grant_role(RoleGrant(user_id=users[username].id, role=role, project_id=project["id"]))
    admin.create_workflow(WorkflowCreate(
        name="项目审批",
        project_id=project["id"],
        steps=[WorkflowStepInput(name="财务复核", assignee_user_id=users["reviewer"].id)],
    ))
    return project, budget, line


def test_complete_budget_reimbursement_payment_and_archive_flow(finance_context):
    session, users, svc = finance_context
    project, _budget, line = prepare_approved_budget(finance_context)
    applicant = svc("applicant")
    reviewer = svc("reviewer")
    cashier = svc("cashier")

    reimbursement = applicant.create_reimbursement(ReimbursementCreate(project_id=project["id"], title="出差报销"))
    reimbursement = applicant.add_reimbursement_item(reimbursement["id"], ReimbursementItemCreate(
        budget_line_id=line["id"], description="项目差旅", vendor="铁路", expense_date=date(2026, 7, 10), amount=Decimal("300.00"),
    ))
    reimbursement = applicant.submit_reimbursement(reimbursement["id"], reimbursement["lock_version"])
    assert reimbursement["status"] == "submitted"
    budget_line = session.get(BudgetLine, line["id"])
    assert budget_line.reserved_amount == Decimal("300.00")

    task = reviewer.list_my_approval_tasks()[0]
    reimbursement = reviewer.act_approval(task["id"], "approve", "同意")
    assert reimbursement["status"] == "approved"

    payment = cashier.create_payment(PaymentCreate(
        reimbursement_id=reimbursement["id"], payee_name="申请人", payee_account="6222000012345678",
    ))
    assert payment["payee_account_masked"].endswith("5678")
    assert "62220000" not in payment["payee_account_masked"]
    payment = cashier.confirm_payment(payment["id"], PaymentConfirm(
        version=payment["lock_version"], bank_reference="BANK-001", paid_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    ))
    assert payment["status"] == "paid"
    session.refresh(budget_line)
    assert budget_line.reserved_amount == Decimal("0.00")
    assert budget_line.spent_amount == Decimal("300.00")

    record = cashier.get_reimbursement(reimbursement["id"])
    archived = cashier.archive_reimbursement(record["id"], record["lock_version"])
    assert archived["status"] == "archived"
    assert session.query(FinanceAuditEvent).count() >= 10


def test_return_releases_budget_and_allows_redraft(finance_context):
    session, _users, svc = finance_context
    project, _budget, line = prepare_approved_budget(finance_context)
    applicant = svc("applicant")
    reviewer = svc("reviewer")
    record = applicant.create_reimbursement(ReimbursementCreate(project_id=project["id"], title="需补材料"))
    record = applicant.add_reimbursement_item(record["id"], ReimbursementItemCreate(
        budget_line_id=line["id"], description="会议", expense_date=date(2026, 7, 11), amount=Decimal("100.00"),
    ))
    record = applicant.submit_reimbursement(record["id"], record["lock_version"])
    task = reviewer.list_my_approval_tasks()[0]
    record = reviewer.act_approval(task["id"], "return", "请补附件")
    assert record["status"] == "returned"
    assert session.get(BudgetLine, line["id"]).reserved_amount == Decimal("0.00")
    record = applicant.return_to_draft(record["id"], record["lock_version"])
    assert record["status"] == "draft"

    record = applicant.submit_reimbursement(record["id"], record["lock_version"])
    assert record["status"] == "submitted"
    assert record["approval"]["submission_no"] == 2
    assert session.get(BudgetLine, line["id"]).reserved_amount == Decimal("100.00")
    assert session.query(ApprovalInstance).filter_by(reimbursement_id=record["id"]).count() == 2


def test_insufficient_budget_is_atomic(finance_context):
    session, _users, svc = finance_context
    project, _budget, line = prepare_approved_budget(finance_context, Decimal("100.00"))
    applicant = svc("applicant")
    record = applicant.create_reimbursement(ReimbursementCreate(project_id=project["id"], title="超预算"))
    record = applicant.add_reimbursement_item(record["id"], ReimbursementItemCreate(
        budget_line_id=line["id"], description="大额支出", expense_date=date(2026, 7, 12), amount=Decimal("101.00"),
    ))
    with pytest.raises(FinanceConflict) as error:
        applicant.submit_reimbursement(record["id"], record["lock_version"])
    assert error.value.code == "insufficient_budget"
    assert session.get(BudgetLine, line["id"]).reserved_amount == Decimal("0.00")


def test_separation_of_duties_blocks_applicant_approval(finance_context):
    session, users, svc = finance_context
    project, _budget, line = prepare_approved_budget(finance_context)
    admin = svc("admin")
    applicant = svc("applicant")
    # A deliberately invalid workflow cannot be used to submit.
    workflow = admin.db.query(__import__("models.finance_models", fromlist=["ApprovalWorkflowDefinition"]).ApprovalWorkflowDefinition).first()
    step = admin.db.query(__import__("models.finance_models", fromlist=["ApprovalWorkflowStep"]).ApprovalWorkflowStep).filter_by(workflow_definition_id=workflow.id).first()
    step.assignee_user_id = users["applicant"].id
    session.commit()
    record = applicant.create_reimbursement(ReimbursementCreate(project_id=project["id"], title="本人审批"))
    record = applicant.add_reimbursement_item(record["id"], ReimbursementItemCreate(
        budget_line_id=line["id"], description="支出", expense_date=date(2026, 7, 12), amount=Decimal("10.00"),
    ))
    with pytest.raises(FinanceConflict) as error:
        applicant.submit_reimbursement(record["id"], record["lock_version"])
    assert error.value.code == "separation_of_duties"


def test_idempotency_replays_same_response_and_rejects_changed_payload(finance_context):
    _session, _users, svc = finance_context
    admin = svc("admin")
    payload = {"project_key": "idem", "name": "幂等项目"}
    first, replayed = admin.idempotent(
        "POST:/projects", "idem-1", payload,
        lambda: admin.create_project(ProjectCreate(**payload)),
    )
    second, replayed_second = admin.idempotent(
        "POST:/projects", "idem-1", payload,
        lambda: admin.create_project(ProjectCreate(**payload)),
    )
    assert not replayed
    assert replayed_second
    assert first == second
    with pytest.raises(FinanceConflict):
        admin.idempotent("POST:/projects", "idem-1", {**payload, "name": "不同"}, lambda: {})


def test_dashboard_get_path_does_not_write(finance_context):
    session, _users, svc = finance_context
    prepare_approved_budget(finance_context)
    before = session.query(FinanceAuditEvent).count()
    dashboard = svc("admin").dashboard()
    after = session.query(FinanceAuditEvent).count()
    assert dashboard["status"] == "ready"
    assert before == after


def test_invoice_attachment_is_private_deduplicated_and_downloadable(finance_context, tmp_path, monkeypatch):
    _session, _users, svc = finance_context
    monkeypatch.setenv("FINANCE_OBJECT_ROOT", str(tmp_path / "objects"))
    project, _budget, _line = prepare_approved_budget(finance_context)
    applicant = svc("applicant")
    invoice = applicant.create_invoice(InvoiceCreate(
        project_id=project["id"], invoice_code="1100", invoice_number="0001",
        invoice_date=date(2026, 7, 18), amount=Decimal("88.00"), tax_amount=Decimal("0.00"),
    ))
    content = b"%PDF-1.7\nfinance-test"
    attachment = applicant.attach_invoice(invoice["id"], "invoice.pdf", "application/pdf", content)
    download = applicant.attachment_url(attachment["id"])
    assert download["url"].endswith(f"/{attachment['id']}/content")
    body, content_type, filename = applicant.attachment_content(attachment["id"])
    assert body == content
    assert content_type == "application/pdf"
    assert filename == "invoice.pdf"
    with pytest.raises(FinanceConflict) as duplicate:
        applicant.attach_invoice(invoice["id"], "copy.pdf", "application/pdf", content)
    assert duplicate.value.code == "duplicate_attachment"


def test_partial_reconciliation_does_not_close_payment(finance_context):
    session, users, svc = finance_context
    project, _budget, _line = prepare_approved_budget(finance_context)
    reimbursement = Reimbursement(
        reimbursement_no="REIM-RECON", project_id=project["id"], applicant_user_id=users["applicant"].id,
        title="对账测试", total_amount=Decimal("300.00"), status="paid",
    )
    session.add(reimbursement)
    session.flush()
    payment = Payment(
        payment_no="PAY-RECON", reimbursement_id=reimbursement.id, amount=Decimal("300.00"),
        payee_name="测试收款方", cashier_user_id=users["cashier"].id, status="paid",
    )
    statement = BankStatementImport(
        file_name="statement.csv", file_sha256="a" * 64, status="completed",
        imported_by=users["cashier"].id,
    )
    session.add_all([payment, statement])
    session.flush()
    transaction = BankTransaction(
        import_id=statement.id, transaction_ref="TX-1", transaction_date=date(2026, 7, 18),
        amount=Decimal("-100.00"), counterparty="测试收款方",
    )
    session.add(transaction)
    session.flush()
    match = ReconciliationMatch(
        bank_transaction_id=transaction.id, payment_id=payment.id,
        matched_amount=Decimal("100.00"), confidence=Decimal("1.0000"),
    )
    session.add(match)
    session.commit()

    svc("cashier").confirm_reconciliations([match.id])
    session.refresh(transaction)
    session.refresh(payment)
    assert transaction.status == "matched"
    assert payment.status == "paid"
