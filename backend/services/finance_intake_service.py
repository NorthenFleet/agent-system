"""Audited finance intake staging with a formal-ledger read-only shadow."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from models.finance_models import (
    BankTransaction,
    BudgetVersion,
    ExpenseRecord,
    FinanceIntakeEvent,
    FinanceIntakeJob,
    FinanceProject,
    FinanceUserRole,
    Invoice,
    Payment,
    Reimbursement,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _business_today() -> date:
    return datetime.now(ZoneInfo(os.getenv("FINANCE_TIMEZONE", "Asia/Shanghai"))).date()


def _hash_request(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_operation(value: str) -> str:
    text = str(value or "").lower()
    marker_groups = (
        ("reimbursement", ("报销", "差旅", "垫付", "费用单")),
        ("invoice", ("发票", "票据", "税票")),
        ("budget", ("预算", "经费", "额度", "拨款")),
        ("reconciliation", ("对账", "银行流水", "流水核对")),
        ("payment", ("付款", "收款", "支付", "转账")),
    )
    for operation_type, markers in marker_groups:
        if any(marker in text for marker in markers):
            return operation_type
    if any(marker in text for marker in ("查询", "多少", "汇总", "分析", "情况")):
        return "query"
    return "unknown"


def _json_payload(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError) as exc:
        raise FinanceIntakeError("抽取结果不是有效的结构化 JSON") from exc


def _money(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount.quantize(Decimal("0.01"))


def _date_value(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


class FinanceIntakeError(Exception):
    status_code = 400


class FinanceIntakeConflict(FinanceIntakeError):
    status_code = 409


class FinanceIntakeNotFound(FinanceIntakeError):
    status_code = 404


class FinanceIntakeForbidden(FinanceIntakeError):
    status_code = 403


class FinanceIntakeService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _compact(job: FinanceIntakeJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "command_message_id": job.command_message_id,
            "source_channel": job.source_channel,
            "source_account_id": job.source_account_id,
            "requested_by_user_id": job.requested_by_user_id,
            "target_agent_id": job.target_agent_id,
            "operation_type": job.operation_type,
            "mode": job.mode,
            "status": job.status,
            "lock_version": job.lock_version,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    @classmethod
    def _detail(cls, job: FinanceIntakeJob, events: list[FinanceIntakeEvent]) -> dict[str, Any]:
        result = cls._compact(job)
        result.update(
            {
                "external_message_id": job.external_message_id,
                "external_conversation_id": job.external_conversation_id,
                "request_text": job.request_text,
                "request_metadata": job.request_metadata or {},
                "normalized_payload": job.normalized_payload or {},
                "shadow_snapshot": job.shadow_snapshot or {},
                "validation_report": job.validation_report or {},
                "reviewer_report": job.reviewer_report or {},
                "last_error": job.last_error,
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "actor_type": event.actor_type,
                        "actor_id": event.actor_id,
                        "payload": event.payload or {},
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                    for event in events
                ],
            }
        )
        return result

    def _formal_snapshot(self) -> dict[str, Any]:
        models = {
            "finance_projects": FinanceProject,
            "budget_versions": BudgetVersion,
            "reimbursements": Reimbursement,
            "invoices": Invoice,
            "expense_records": ExpenseRecord,
            "payments": Payment,
            "bank_transactions": BankTransaction,
        }
        return {
            "captured_at": _now().isoformat(),
            "authority": "formal_finance_tables_read_only",
            "write_capability": "disabled",
            "record_counts": {
                name: self.db.query(model).count()
                for name, model in models.items()
            },
        }

    @staticmethod
    def _issue(code: str, field: str, message: str) -> dict[str, str]:
        return {"code": code, "field": field, "message": message}

    def _validate_project(self, payload: dict[str, Any], errors: list[dict[str, str]]) -> None:
        project_id = str(payload.get("project_id") or "").strip()
        if not project_id:
            errors.append(self._issue("project_required", "project_id", "必须关联一个财务项目"))
            return
        project = self.db.get(FinanceProject, project_id)
        if not project or project.deleted_at or project.status != "active":
            errors.append(self._issue("project_unavailable", "project_id", "财务项目不存在或不可用"))

    def _validate_reimbursement(self, payload: dict[str, Any]) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        self._validate_project(payload, errors)
        if not str(payload.get("title") or "").strip():
            errors.append(self._issue("title_required", "title", "报销标题不能为空"))
        currency = str(payload.get("currency") or "CNY").upper()
        if currency != "CNY":
            errors.append(self._issue("currency_unsupported", "currency", "当前只支持人民币 CNY"))
        total = _money(payload.get("total_amount"))
        if total is None or total <= 0:
            errors.append(self._issue("total_amount_invalid", "total_amount", "报销总额必须大于 0"))

        items = payload.get("items")
        if not isinstance(items, list) or not items:
            errors.append(self._issue("items_required", "items", "至少需要一个报销明细"))
            items = []
        item_total = Decimal("0.00")
        today = _business_today()
        for index, item in enumerate(items):
            prefix = f"items.{index}"
            if not isinstance(item, dict):
                errors.append(self._issue("item_invalid", prefix, "报销明细必须是对象"))
                continue
            if not str(item.get("description") or "").strip():
                errors.append(self._issue("description_required", f"{prefix}.description", "明细说明不能为空"))
            amount = _money(item.get("amount"))
            if amount is None or amount <= 0:
                errors.append(self._issue("item_amount_invalid", f"{prefix}.amount", "明细金额必须大于 0"))
            else:
                item_total += amount
            expense_date = _date_value(item.get("expense_date"))
            if not expense_date:
                errors.append(self._issue("expense_date_invalid", f"{prefix}.expense_date", "费用日期必须是 YYYY-MM-DD"))
            elif expense_date > today:
                errors.append(self._issue("expense_date_future", f"{prefix}.expense_date", "费用日期不能晚于今天"))
        if total is not None and total > 0 and item_total != total:
            errors.append(
                self._issue(
                    "item_total_mismatch",
                    "total_amount",
                    f"明细合计 {item_total} 与报销总额 {total} 不一致",
                )
            )
        if not payload.get("invoice_numbers"):
            warnings.append(self._issue("invoice_reference_missing", "invoice_numbers", "尚未关联发票号码"))
        return {"errors": errors, "warnings": warnings}

    def _validate_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        self._validate_project(payload, errors)
        invoice_number = str(payload.get("invoice_number") or "").strip()
        invoice_code = str(payload.get("invoice_code") or "").strip()
        if not invoice_number:
            errors.append(self._issue("invoice_number_required", "invoice_number", "发票号码不能为空"))
        amount = _money(payload.get("amount"))
        if amount is None or amount <= 0:
            errors.append(self._issue("invoice_amount_invalid", "amount", "发票金额必须大于 0"))
        invoice_date = _date_value(payload.get("invoice_date"))
        if not invoice_date:
            errors.append(self._issue("invoice_date_invalid", "invoice_date", "发票日期必须是 YYYY-MM-DD"))
        elif invoice_date > _business_today():
            errors.append(self._issue("invoice_date_future", "invoice_date", "发票日期不能晚于今天"))
        if not str(payload.get("seller_name") or "").strip():
            errors.append(self._issue("seller_required", "seller_name", "销方名称不能为空"))
        if invoice_number:
            duplicate_query = self.db.query(Invoice.id).filter(
                Invoice.invoice_number == invoice_number,
                Invoice.deleted_at.is_(None),
            )
            if invoice_code:
                duplicate_query = duplicate_query.filter(Invoice.invoice_code == invoice_code)
            if duplicate_query.first():
                errors.append(self._issue("invoice_duplicate", "invoice_number", "正式财务库已存在相同发票"))
        if not invoice_code:
            warnings.append(self._issue("invoice_code_missing", "invoice_code", "发票代码尚未提取"))
        return {"errors": errors, "warnings": warnings}

    def validate_payload(self, operation_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation_type == "reimbursement":
            result = self._validate_reimbursement(payload)
        elif operation_type == "invoice":
            result = self._validate_invoice(payload)
        elif operation_type in {"query", "unknown"}:
            result = {
                "errors": [],
                "warnings": [self._issue("no_formal_write", "operation_type", "查询类请求不生成正式财务记录")],
            }
        else:
            result = {
                "errors": [self._issue("operation_not_supported", "operation_type", "该类型尚未开放结构化财务写入")],
                "warnings": [],
            }
        return {
            "validator": "finance-deterministic-v1",
            "validated_at": _now().isoformat(),
            "valid": not result["errors"],
            **result,
        }

    def stage(
        self,
        *,
        command_message_id: str,
        external_message_id: str,
        source_channel: str,
        source_account_id: str,
        external_conversation_id: str,
        external_user_id: str,
        requested_by_user_id: int,
        target_agent_id: str,
        request_text: str,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_message_id = str(command_message_id or "").strip()
        clean_text = str(request_text or "").strip()
        if not clean_message_id or not clean_text:
            raise FinanceIntakeError("财务暂存作业缺少消息标识或请求内容")
        request_hash = _hash_request(clean_text)
        existing = self.db.query(FinanceIntakeJob).filter(
            FinanceIntakeJob.command_message_id == clean_message_id
        ).first()
        if existing:
            if existing.request_hash != request_hash:
                raise FinanceIntakeConflict("同一消息标识对应了不同财务请求")
            return {"job": self._compact(existing), "replayed": True}

        now = _now()
        job = FinanceIntakeJob(
            command_message_id=clean_message_id,
            external_message_id=str(external_message_id or "").strip() or None,
            source_channel=str(source_channel or "").strip().lower(),
            source_account_id=str(source_account_id or "soundwave").strip(),
            external_conversation_id=str(external_conversation_id or "").strip(),
            external_user_id=str(external_user_id or "").strip(),
            requested_by_user_id=int(requested_by_user_id),
            target_agent_id=str(target_agent_id or "soundwave").strip(),
            operation_type=classify_operation(clean_text),
            request_text=clean_text,
            request_hash=request_hash,
            request_metadata=dict(request_metadata or {}),
            mode="shadow",
            status="received",
            normalized_payload={},
            shadow_snapshot={},
            validation_report={},
            reviewer_report={},
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        try:
            self.db.flush()
            self.db.add(
                FinanceIntakeEvent(
                    job_id=job.id,
                    event_type="received",
                    actor_type="agent",
                    actor_id=job.target_agent_id,
                    payload={"mode": "shadow", "request_hash": request_hash},
                )
            )
            job.shadow_snapshot = self._formal_snapshot()
            job.status = "shadow_read"
            job.updated_at = _now()
            self.db.add(
                FinanceIntakeEvent(
                    job_id=job.id,
                    event_type="formal_snapshot_captured",
                    actor_type="system",
                    actor_id="finance-intake",
                    payload=job.shadow_snapshot,
                )
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            existing = self.db.query(FinanceIntakeJob).filter(
                FinanceIntakeJob.command_message_id == clean_message_id
            ).first()
            if existing and existing.request_hash == request_hash:
                return {"job": self._compact(existing), "replayed": True}
            raise FinanceIntakeConflict("财务暂存作业标识冲突") from exc
        self.db.refresh(job)
        return {"job": self._compact(job), "replayed": False}

    def submit_extraction(
        self,
        job_id: str,
        *,
        agent_id: str,
        payload: dict[str, Any],
        evidence: list[str] | None,
        confidence: float,
        expected_version: int,
    ) -> dict[str, Any]:
        job = self.db.get(FinanceIntakeJob, job_id)
        if not job:
            raise FinanceIntakeNotFound("财务暂存作业不存在")
        clean_agent = str(agent_id or "").strip()
        if clean_agent != job.target_agent_id:
            raise FinanceIntakeForbidden("只有目标财务智能体可以提交抽取结果")
        normalized = _json_payload(payload)
        if job.status == "needs_review" and job.normalized_payload == normalized:
            return {"job": self._compact(job), "validation": job.validation_report, "replayed": True}
        if job.status not in {"shadow_read", "extracted"}:
            raise FinanceIntakeConflict(f"当前状态不允许重新抽取: {job.status}")
        if int(expected_version) != job.lock_version:
            raise FinanceIntakeConflict("财务暂存作业版本已变化，请重新读取后再提交")
        if confidence < 0 or confidence > 1:
            raise FinanceIntakeError("抽取置信度必须在 0 到 1 之间")

        validation = self.validate_payload(job.operation_type, normalized)
        job.normalized_payload = normalized
        job.validation_report = validation
        job.reviewer_report = {}
        job.status = "needs_review"
        job.lock_version += 1
        job.updated_at = _now()
        self.db.add(
            FinanceIntakeEvent(
                job_id=job.id,
                event_type="extraction_submitted",
                actor_type="agent",
                actor_id=clean_agent,
                payload={
                    "confidence": confidence,
                    "evidence": [str(item)[:500] for item in (evidence or [])[:50]],
                    "validation": validation,
                    "lock_version": job.lock_version,
                },
            )
        )
        self.db.commit()
        self.db.refresh(job)
        return {"job": self._compact(job), "validation": validation, "replayed": False}

    def submit_review(
        self,
        job_id: str,
        *,
        reviewer_agent_id: str,
        decision: str,
        summary: str,
        findings: list[dict[str, Any]] | None,
        confidence: float,
        expected_version: int,
    ) -> dict[str, Any]:
        job = self.db.get(FinanceIntakeJob, job_id)
        if not job:
            raise FinanceIntakeNotFound("财务暂存作业不存在")
        reviewer = str(reviewer_agent_id or "").strip()
        if not reviewer or reviewer == job.target_agent_id:
            raise FinanceIntakeForbidden("复核智能体必须与抽取智能体独立")
        clean_decision = str(decision or "").strip().lower()
        if clean_decision not in {"approve", "reject"}:
            raise FinanceIntakeError("复核结论必须是 approve 或 reject")
        if job.status == "validated" and clean_decision == "approve":
            return {"job": self._compact(job), "review": job.reviewer_report, "replayed": True}
        if job.status not in {"needs_review"}:
            raise FinanceIntakeConflict(f"当前状态不允许复核: {job.status}")
        if int(expected_version) != job.lock_version:
            raise FinanceIntakeConflict("财务暂存作业版本已变化，请重新读取后再复核")
        if confidence < 0 or confidence > 1:
            raise FinanceIntakeError("复核置信度必须在 0 到 1 之间")
        if clean_decision == "approve" and not bool((job.validation_report or {}).get("valid")):
            raise FinanceIntakeConflict("确定性校验未通过，不能批准")

        report = {
            "decision": clean_decision,
            "summary": str(summary or "").strip()[:4000],
            "findings": _json_payload({"items": findings or []})["items"][:100],
            "confidence": confidence,
            "reviewer_agent_id": reviewer,
            "reviewed_at": _now().isoformat(),
            "independent_from": job.target_agent_id,
        }
        job.reviewer_report = report
        job.status = "validated" if clean_decision == "approve" else "rejected"
        job.lock_version += 1
        job.updated_at = _now()
        self.db.add(
            FinanceIntakeEvent(
                job_id=job.id,
                event_type="independent_review_completed",
                actor_type="agent",
                actor_id=reviewer,
                payload={**report, "lock_version": job.lock_version},
            )
        )
        self.db.commit()
        self.db.refresh(job)
        return {"job": self._compact(job), "review": report, "replayed": False}

    def record_review_failure(self, job_id: str, *, error: str) -> dict[str, Any]:
        job = self.db.get(FinanceIntakeJob, job_id)
        if not job:
            raise FinanceIntakeNotFound("财务暂存作业不存在")
        if job.status != "needs_review":
            return self._compact(job)
        message = str(error or "独立复核失败").strip()[:2000]
        job.last_error = message
        job.updated_at = _now()
        self.db.add(
            FinanceIntakeEvent(
                job_id=job.id,
                event_type="independent_review_failed",
                actor_type="system",
                actor_id="finance-review-orchestrator",
                payload={"error": message},
            )
        )
        self.db.commit()
        self.db.refresh(job)
        return self._compact(job)

    def list_agent_jobs(
        self,
        *,
        agent_id: str,
        status: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clean_agent = str(agent_id or "").strip()
        query = self.db.query(FinanceIntakeJob)
        if clean_agent == "soundwave":
            query = query.filter(FinanceIntakeJob.target_agent_id == clean_agent)
        elif clean_agent == "inspector":
            query = query.filter(FinanceIntakeJob.status.in_(("needs_review", "validated", "rejected")))
        else:
            raise FinanceIntakeForbidden("该智能体没有财务作业访问权限")
        if status:
            query = query.filter(FinanceIntakeJob.status == status)
        jobs = query.order_by(FinanceIntakeJob.created_at.desc()).limit(limit).all()
        return [self._compact(job) for job in jobs]

    def get_agent_job(self, job_id: str, *, agent_id: str) -> dict[str, Any]:
        job = self.db.get(FinanceIntakeJob, job_id)
        if not job:
            raise FinanceIntakeNotFound("财务暂存作业不存在")
        clean_agent = str(agent_id or "").strip()
        if clean_agent not in {job.target_agent_id, "inspector"}:
            raise FinanceIntakeForbidden("该智能体没有财务作业访问权限")
        events = self.db.query(FinanceIntakeEvent).filter(
            FinanceIntakeEvent.job_id == job.id
        ).order_by(FinanceIntakeEvent.created_at.asc()).all()
        return self._detail(job, events)

    def _can_read_all(self, *, user_id: int, system_role: str) -> bool:
        if system_role == "admin":
            return True
        role = self.db.query(FinanceUserRole.id).filter(
            FinanceUserRole.user_id == user_id,
            FinanceUserRole.role.in_(("finance_admin", "auditor")),
        ).first()
        return role is not None

    def list_jobs(
        self,
        *,
        user_id: int,
        system_role: str,
        status: str = "",
        operation_type: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = self.db.query(FinanceIntakeJob)
        if not self._can_read_all(user_id=user_id, system_role=system_role):
            query = query.filter(FinanceIntakeJob.requested_by_user_id == user_id)
        if status:
            query = query.filter(FinanceIntakeJob.status == status)
        if operation_type:
            query = query.filter(FinanceIntakeJob.operation_type == operation_type)
        jobs = query.order_by(FinanceIntakeJob.created_at.desc()).limit(limit).all()
        return [self._compact(job) for job in jobs]

    def get_job(self, job_id: str, *, user_id: int, system_role: str) -> dict[str, Any]:
        job = self.db.get(FinanceIntakeJob, job_id)
        if not job:
            raise FinanceIntakeNotFound("财务暂存作业不存在")
        if (
            job.requested_by_user_id != user_id
            and not self._can_read_all(user_id=user_id, system_role=system_role)
        ):
            raise FinanceIntakeForbidden("无权查看该财务暂存作业")
        events = self.db.query(FinanceIntakeEvent).filter(
            FinanceIntakeEvent.job_id == job.id
        ).order_by(FinanceIntakeEvent.created_at.asc()).all()
        return self._detail(job, events)


class FinanceIntakeCoordinator:
    """Open a short PostgreSQL transaction for command-center ingestion."""

    def stage_command(self, **payload: Any) -> dict[str, Any]:
        with SessionLocal() as db:
            return FinanceIntakeService(db).stage(**payload)

    def submit_extraction(self, job_id: str, **payload: Any) -> dict[str, Any]:
        with SessionLocal() as db:
            return FinanceIntakeService(db).submit_extraction(job_id, **payload)

    def submit_review(self, job_id: str, **payload: Any) -> dict[str, Any]:
        with SessionLocal() as db:
            return FinanceIntakeService(db).submit_review(job_id, **payload)

    def list_agent_jobs(self, **filters: Any) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            return FinanceIntakeService(db).list_agent_jobs(**filters)

    def get_agent_job(self, job_id: str, *, agent_id: str) -> dict[str, Any]:
        with SessionLocal() as db:
            return FinanceIntakeService(db).get_agent_job(job_id, agent_id=agent_id)

    def record_review_failure(self, job_id: str, *, error: str) -> dict[str, Any]:
        with SessionLocal() as db:
            return FinanceIntakeService(db).record_review_failure(job_id, error=error)


finance_intake_coordinator = FinanceIntakeCoordinator()
