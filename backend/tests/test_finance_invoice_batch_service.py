from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import pytest

from database import Base
from models.finance_models import (
    FinanceProject,
    Invoice,
    InvoiceBatch,
    InvoiceFieldCandidate,
    InvoiceIngestItem,
    InvoiceOcrRun,
)
from models.v2_models import User
from schemas.finance import InvoiceBatchCreate
from services.finance_invoice_batch_service import FinanceInvoiceBatchService, InvoiceBatchProcessor
from services.finance_v2_service import FinanceConflict, FinanceServiceV2


@pytest.fixture
def batch_context(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'invoice-batch.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    user = User(username="admin", password_hash="x", display_name="admin", role="admin", is_active=True)
    session.add(user)
    session.flush()
    project = FinanceProject(
        project_key="invoice-project",
        name="发票测试项目",
        owner_user_id=user.id,
        created_by=user.id,
    )
    session.add(project)
    session.commit()
    monkeypatch.setenv("FINANCE_OBJECT_ROOT", str(tmp_path / "objects"))
    finance = FinanceServiceV2(session, {"sub": str(user.id), "username": user.username, "role": "admin"})
    yield session, project, FinanceInvoiceBatchService(finance)
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _fake_ocr(_content: bytes, _content_type: str):
    def candidate(value: str, confidence: float):
        return {
            "raw_value": value,
            "normalized_value": value,
            "confidence": confidence,
            "evidence_text": value,
            "bounding_box": None,
        }

    runs = [
        {
            "engine": "apple_vision",
            "engine_version": "test",
            "status": "success",
            "text": "发票号码 12345678\n价税合计 88.00",
            "observations": [],
            "duration_ms": 10,
            "error": None,
            "fields": {
                "invoice_number": candidate("12345678", 0.98),
                "total_amount": candidate("88.00", 0.96),
            },
        },
        {
            "engine": "tesseract",
            "engine_version": "test",
            "status": "success",
            "text": "发票号码 12345678\n价税合计 88.00",
            "observations": [],
            "duration_ms": 15,
            "error": None,
            "fields": {
                "invoice_number": candidate("12345678", 0.90),
                "total_amount": candidate("88.00", 0.88),
            },
        },
    ]
    consensus_fields = {
        field: {
            "value": value,
            "status": "agreed",
            "confidence": 0.98,
            "sources": ["apple_vision", "tesseract"],
            "candidates": [],
        }
        for field, value in (("invoice_number", "12345678"), ("total_amount", "88.00"))
    }
    return {
        "status": "success",
        "preprocessed_content": b"derived-png",
        "preprocessing": {"status": "success", "derived_sha256": "test"},
        "runs": runs,
        "consensus": {"fields": consensus_fields, "conflicts": [], "requires_human_review": True},
    }


def test_batch_ocr_stays_in_staging_until_human_review(batch_context, monkeypatch):
    session, project, service = batch_context
    monkeypatch.setattr("services.finance_invoice_batch_service.run_local_invoice_ocr", _fake_ocr)
    batch = service.create_batch(InvoiceBatchCreate(project_id=project.id, period="2026-08"))
    item = service.add_file(batch["id"], "invoice.png", "image/png", b"safe-image-content")

    assert session.query(Invoice).count() == 0
    assert item["status"] == "scanned"
    assert service.start_batch(batch["id"])["queued"] is True
    processed = InvoiceBatchProcessor(session).process(batch["id"])

    assert processed["status"] == "review_required"
    assert processed["processed_count"] == 1
    assert processed["review_count"] == 1
    staged = session.get(InvoiceIngestItem, item["id"])
    assert staged.status == "needs_review"
    assert staged.extraction_payload["authority"] == "staging_only"
    assert staged.extraction_payload["formal_invoice_created"] is False
    assert session.query(Invoice).count() == 0
    assert session.query(InvoiceOcrRun).count() == 2
    assert session.query(InvoiceFieldCandidate).count() == 4
    assert {row.consensus_status for row in session.query(InvoiceFieldCandidate).all()} == {"agreed"}


def test_duplicate_file_is_rejected_across_batches(batch_context):
    session, project, service = batch_context
    first = service.create_batch(InvoiceBatchCreate(project_id=project.id, period="2026-08"))
    second = service.create_batch(InvoiceBatchCreate(project_id=project.id, period="2026-09"))
    service.add_file(first["id"], "invoice-a.png", "image/png", b"same-content")

    with pytest.raises(FinanceConflict) as error:
        service.add_file(second["id"], "invoice-b.png", "image/png", b"same-content")

    assert error.value.code == "duplicate_invoice_file"
    assert session.query(InvoiceIngestItem).count() == 1
    assert session.get(InvoiceBatch, second["id"]).total_count == 0


def test_failed_item_can_be_reset_for_retry(batch_context, monkeypatch):
    session, project, service = batch_context
    monkeypatch.setattr(
        "services.finance_invoice_batch_service.run_local_invoice_ocr",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("ocr failed")),
    )
    batch = service.create_batch(InvoiceBatchCreate(project_id=project.id, period="2026-08"))
    item = service.add_file(batch["id"], "broken.png", "image/png", b"broken-image")
    service.start_batch(batch["id"])
    processed = InvoiceBatchProcessor(session).process(batch["id"])
    assert processed["status"] == "failed"
    assert session.get(InvoiceIngestItem, item["id"]).status == "failed"

    retried = service.retry_failed(batch["id"])
    assert retried["status"] == "received"
    assert retried["items"][0]["status"] == "scanned"
