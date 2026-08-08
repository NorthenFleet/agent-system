"""Review-first invoice batch ingestion and local OCR orchestration."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import SessionLocal
from models.finance_models import (
    FinanceIntakeJob,
    FinanceProjectMembership,
    Invoice,
    InvoiceAttachment,
    InvoiceBatch,
    InvoiceFieldCandidate,
    InvoiceIngestItem,
    InvoiceOcrRun,
)
from schemas.finance import InvoiceBatchCreate
from services.finance_adapters import AttachmentScanner, object_storage
from services.finance_invoice_ocr import InvoiceOCRError, run_local_invoice_ocr
from services.finance_v2_service import (
    FinanceConflict,
    FinanceNotFound,
    FinanceServiceV2,
    now,
    row_dict,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _json_safe_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "engine": str(run.get("engine") or "unknown"),
        "engine_version": str(run.get("engine_version") or "")[:128],
        "status": str(run.get("status") or "failed"),
        "observations": list(run.get("observations") or []),
        "fields": dict(run.get("fields") or {}),
    }


class FinanceInvoiceBatchService:
    def __init__(self, finance: FinanceServiceV2):
        self.finance = finance
        self.db = finance.db

    def _batch(self, batch_id: str, *, write: bool = False) -> InvoiceBatch:
        batch = self.db.get(InvoiceBatch, batch_id)
        if not batch:
            raise FinanceNotFound("发票导入批次不存在")
        self.finance.require_project(batch.project_id, write=write)
        return batch

    def _detail(self, batch: InvoiceBatch, *, include_items: bool = True) -> dict[str, Any]:
        data = row_dict(batch)
        if not include_items:
            return data
        items = self.db.query(InvoiceIngestItem).filter_by(batch_id=batch.id).order_by(
            InvoiceIngestItem.created_at,
        ).all()
        data["items"] = []
        for item in items:
            item_data = row_dict(item)
            runs = self.db.query(InvoiceOcrRun).filter_by(item_id=item.id).order_by(
                InvoiceOcrRun.created_at,
            ).all()
            item_data["ocr_runs"] = [
                row_dict(run, exclude=("text_payload", "raw_payload"))
                for run in runs
            ]
            item_data["field_candidates"] = [
                row_dict(candidate)
                for candidate in self.db.query(InvoiceFieldCandidate).filter_by(item_id=item.id).order_by(
                    InvoiceFieldCandidate.field_name,
                    InvoiceFieldCandidate.created_at,
                ).all()
            ]
            data["items"].append(item_data)
        return data

    def create_batch(self, request: InvoiceBatchCreate) -> dict[str, Any]:
        self.finance.require("finance_admin", "project_manager", "applicant")
        self.finance.require_project(request.project_id, write=True)
        if request.intake_job_id:
            intake = self.db.get(FinanceIntakeJob, request.intake_job_id)
            if not intake or intake.operation_type != "invoice":
                raise FinanceConflict("关联的财务录入作业不存在或不是发票作业")
        batch = InvoiceBatch(
            project_id=request.project_id,
            intake_job_id=request.intake_job_id,
            period=request.period,
            source_channel=request.source_channel,
            external_ref=request.external_ref,
            note=request.note,
            created_by=self.finance.user_id,
        )
        self.db.add(batch)
        self.db.flush()
        self.finance.audit("invoice_batch.created", batch)
        self.finance.commit()
        return self._detail(batch)

    def list_batches(self, *, project_id: str = "", status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        query = self.db.query(InvoiceBatch)
        if project_id:
            self.finance.require_project(project_id)
            query = query.filter(InvoiceBatch.project_id == project_id)
        elif "finance_admin" not in self.finance.roles and "auditor" not in self.finance.roles:
            project_ids = select(FinanceProjectMembership.project_id).where(
                FinanceProjectMembership.user_id == self.finance.user_id,
            )
            query = query.filter(InvoiceBatch.project_id.in_(project_ids))
        if status:
            query = query.filter(InvoiceBatch.status == status)
        return [
            self._detail(batch, include_items=False)
            for batch in query.order_by(InvoiceBatch.created_at.desc()).limit(limit).all()
        ]

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        return self._detail(self._batch(batch_id))

    def add_file(self, batch_id: str, filename: str, content_type: str, content: bytes) -> dict[str, Any]:
        self.finance.require("finance_admin", "project_manager", "applicant")
        batch = self._batch(batch_id, write=True)
        if batch.status not in {"received", "review_required", "failed"}:
            raise FinanceConflict("当前批次状态不允许继续上传文件")
        digest = hashlib.sha256(content).hexdigest()
        if self.db.query(InvoiceIngestItem.id).filter_by(sha256=digest).first() or self.db.query(
            InvoiceAttachment.id,
        ).filter_by(sha256=digest).first():
            raise FinanceConflict("文件内容已存在于发票系统", code="duplicate_invoice_file")
        scan_status = AttachmentScanner().validate(filename, content_type, content)
        suffix = Path(filename).suffix.lower()[:10] or {
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/tiff": ".tiff",
        }.get(content_type, ".bin")
        item_id = _uid()
        object_key = f"invoice-ingest/{batch.id}/{item_id}/original{suffix}"
        object_storage().put(object_key, content, content_type)
        item = InvoiceIngestItem(
            id=item_id,
            batch_id=batch.id,
            object_key=object_key,
            original_name=Path(filename).name[:255],
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            scan_status=scan_status,
            status="scanned",
        )
        self.db.add(item)
        batch.total_count += 1
        batch.updated_at = now()
        self.db.flush()
        self.finance.audit("invoice_batch.file_received", item)
        self.finance.commit()
        return row_dict(item)

    def start_batch(self, batch_id: str) -> dict[str, Any]:
        self.finance.require("finance_admin", "project_manager", "applicant")
        batch = self._batch(batch_id, write=True)
        if batch.status == "processing":
            return {"batch": self._detail(batch, include_items=False), "queued": False}
        if batch.status in {"completed", "cancelled"}:
            raise FinanceConflict("当前批次已经结束，不能重新启动")
        pending = self.db.query(InvoiceIngestItem.id).filter(
            InvoiceIngestItem.batch_id == batch.id,
            InvoiceIngestItem.status.in_(("received", "scanned", "failed")),
        ).count()
        if not pending:
            raise FinanceConflict("批次中没有可处理的文件")
        before = row_dict(batch)
        batch.status = "processing"
        batch.started_at = now()
        batch.completed_at = None
        batch.updated_at = now()
        self.finance.audit("invoice_batch.processing_started", batch, before)
        self.finance.commit()
        return {"batch": self._detail(batch, include_items=False), "queued": True}

    def retry_failed(self, batch_id: str) -> dict[str, Any]:
        self.finance.require("finance_admin", "project_manager", "applicant")
        batch = self._batch(batch_id, write=True)
        if batch.status == "processing":
            raise FinanceConflict("批次正在处理，不能同时重试")
        failed = self.db.query(InvoiceIngestItem).filter_by(batch_id=batch.id, status="failed").all()
        if not failed:
            raise FinanceConflict("批次中没有失败文件")
        for item in failed:
            item.status = "scanned"
            item.last_error = None
            item.updated_at = now()
        batch.status = "received"
        batch.failed_count = 0
        batch.completed_at = None
        batch.updated_at = now()
        self.finance.audit("invoice_batch.retry_requested", batch)
        self.finance.commit()
        return self._detail(batch)


class InvoiceBatchProcessor:
    """A restart-safe processor; PostgreSQL rows are the durable queue."""

    def __init__(self, db: Session):
        self.db = db

    def _refresh_counts(self, batch: InvoiceBatch) -> None:
        items = self.db.query(InvoiceIngestItem).filter_by(batch_id=batch.id).all()
        batch.total_count = len(items)
        batch.processed_count = sum(
            item.status in {"extracted", "needs_review", "approved", "committed"}
            for item in items
        )
        batch.review_count = sum(item.status == "needs_review" for item in items)
        batch.failed_count = sum(item.status == "failed" for item in items)
        if batch.review_count:
            batch.status = "review_required"
        elif batch.failed_count:
            batch.status = "failed"
        elif items and batch.processed_count == len(items):
            batch.status = "completed"
        else:
            batch.status = "received"
        batch.completed_at = datetime.now(timezone.utc)
        batch.updated_at = datetime.now(timezone.utc)

    def _process_item(self, item: InvoiceIngestItem) -> None:
        item.status = "ocr_running"
        item.attempt_count += 1
        item.last_error = None
        item.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        try:
            content = object_storage().read(item.object_key)
            result = run_local_invoice_ocr(content, item.content_type)
            self.db.query(InvoiceFieldCandidate).filter_by(item_id=item.id).delete(synchronize_session=False)
            self.db.query(InvoiceOcrRun).filter_by(item_id=item.id).delete(synchronize_session=False)
            self.db.flush()
            if result.get("status") != "success":
                errors = [str(run.get("error") or "") for run in result.get("runs") or [] if run.get("error")]
                raise InvoiceOCRError("; ".join(errors) or "所有本地 OCR 引擎均失败")

            preprocessed = bytes(result.get("preprocessed_content") or b"")
            derived_key = f"invoice-ingest/{item.batch_id}/{item.id}/preprocessed.png"
            object_storage().put(derived_key, preprocessed, "image/png")
            item.preprocessed_object_key = derived_key
            item.preprocessing_payload = dict(result.get("preprocessing") or {})

            consensus = dict(result.get("consensus") or {})
            consensus_by_field = {
                name: str(data.get("status") or "single_source")
                for name, data in (consensus.get("fields") or {}).items()
            }
            for raw_run in result.get("runs") or []:
                run_data = _json_safe_run(raw_run)
                run = InvoiceOcrRun(
                    item_id=item.id,
                    engine=run_data["engine"],
                    engine_version=run_data["engine_version"],
                    status=run_data["status"],
                    text_payload=str(raw_run.get("text") or ""),
                    raw_payload=run_data,
                    duration_ms=max(0, int(raw_run.get("duration_ms") or 0)),
                    error_message=str(raw_run.get("error") or "")[:2000] or None,
                )
                self.db.add(run)
                self.db.flush()
                for field_name, candidate in (raw_run.get("fields") or {}).items():
                    self.db.add(InvoiceFieldCandidate(
                        item_id=item.id,
                        ocr_run_id=run.id,
                        field_name=field_name,
                        raw_value=str(candidate.get("raw_value") or ""),
                        normalized_value=str(candidate.get("normalized_value") or ""),
                        confidence=Decimal(str(candidate.get("confidence") or 0)).quantize(Decimal("0.0001")),
                        evidence_text=str(candidate.get("evidence_text") or "")[:4000] or None,
                        bounding_box=candidate.get("bounding_box"),
                        consensus_status=consensus_by_field.get(field_name, "single_source"),
                    ))
            item.extraction_payload = {
                "authority": "staging_only",
                "formal_invoice_created": False,
                "consensus": consensus,
                "engines": [
                    {
                        "engine": run.get("engine"),
                        "status": run.get("status"),
                        "duration_ms": run.get("duration_ms"),
                        "error": run.get("error"),
                    }
                    for run in result.get("runs") or []
                ],
            }
            item.status = "needs_review"
            item.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            item = self.db.get(InvoiceIngestItem, item.id)
            item.status = "failed"
            item.last_error = str(exc)[:4000]
            item.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def process(self, batch_id: str) -> dict[str, Any]:
        batch = self.db.get(InvoiceBatch, batch_id)
        if not batch:
            raise FinanceNotFound("发票导入批次不存在")
        if batch.status != "processing":
            return row_dict(batch)
        items = self.db.query(InvoiceIngestItem).filter(
            InvoiceIngestItem.batch_id == batch.id,
            InvoiceIngestItem.status.in_(("received", "scanned", "failed")),
        ).order_by(InvoiceIngestItem.created_at).all()
        for item in items:
            self._process_item(item)
        batch = self.db.get(InvoiceBatch, batch_id)
        self._refresh_counts(batch)
        self.db.commit()
        return row_dict(batch)


def process_invoice_batch_job(batch_id: str) -> None:
    db = SessionLocal()
    try:
        InvoiceBatchProcessor(db).process(batch_id)
    finally:
        db.close()
