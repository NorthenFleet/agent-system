"""Transactional application service for project finance."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import and_, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.finance_models import (
    ApprovalEvent,
    ApprovalInstance,
    ApprovalTask,
    ApprovalWorkflowDefinition,
    ApprovalWorkflowStep,
    BankStatementImport,
    BankTransaction,
    BudgetAdjustment,
    BudgetLine,
    BudgetReservation,
    BudgetVersion,
    ExpenseRecord,
    FinanceAuditEvent,
    FinanceProject,
    FinanceProjectMembership,
    FinanceUserRole,
    FundAllocation,
    IdempotencyRecord,
    ImportJob,
    Invoice,
    InvoiceAttachment,
    OutboxEvent,
    Payment,
    ReconciliationMatch,
    Reimbursement,
    ReimbursementItem,
)
from models.v2_models import User
from schemas.finance import (
    BudgetAdjustmentCreate,
    BudgetCreate,
    BudgetLinesReplace,
    FundAllocationCreate,
    InvoiceCreate,
    PaymentCreate,
    PaymentConfirm,
    ProjectCreate,
    ProjectUpdate,
    ReimbursementCreate,
    ReimbursementItemCreate,
    ReimbursementItemUpdate,
    ReimbursementUpdate,
    RoleGrant,
    WorkflowCreate,
)
from services.finance_adapters import (
    AttachmentScanner,
    LocalObjectStorage,
    object_storage,
    ocr_adapter,
    parse_statement,
    verification_adapter,
)


MONEY = Decimal("0.01")
FINANCE_ROLES = {"finance_admin", "project_manager", "applicant", "reviewer", "cashier", "auditor"}
WRITE_ROLES = {"finance_admin", "project_manager", "applicant", "reviewer", "cashier"}
_IDEMPOTENCY_LOCKS: dict[str, threading.Lock] = {}
_IDEMPOTENCY_LOCKS_GUARD = threading.Lock()


def now() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY)


def uid() -> str:
    return str(uuid.uuid4())


def serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    return value


def row_dict(row: Any, *, exclude: Iterable[str] = ()) -> dict[str, Any]:
    blocked = set(exclude)
    return {
        column.name: serial(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in blocked
    }


class FinanceError(Exception):
    status_code = 400

    def __init__(self, message: str, *, code: str = "finance_error", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class FinanceForbidden(FinanceError):
    status_code = 403


class FinanceNotFound(FinanceError):
    status_code = 404


class FinanceConflict(FinanceError):
    status_code = 409


class FinanceServiceV2:
    def __init__(self, db: Session, user: dict[str, Any], request_id: str = "", ip_address: str = ""):
        self.db = db
        self.user = user
        self.user_id = int(user["sub"])
        self.system_role = str(user.get("role") or "")
        self.request_id = request_id
        self.ip_address = ip_address

    # ---------- access and infrastructure ----------
    @property
    def roles(self) -> set[str]:
        if self.system_role == "admin":
            return set(FINANCE_ROLES)
        return {
            value for (value,) in self.db.query(FinanceUserRole.role)
            .filter(FinanceUserRole.user_id == self.user_id).all()
        }

    def require(self, *roles: str) -> None:
        if not self.roles.intersection(roles):
            raise FinanceForbidden("当前用户没有执行该财务操作的权限", code="finance_role_required")

    def require_project(self, project_id: str, *, write: bool = False) -> FinanceProject:
        project = self.db.get(FinanceProject, project_id)
        if not project or project.deleted_at:
            raise FinanceNotFound("项目不存在")
        roles = self.roles
        if "finance_admin" in roles or (not write and "auditor" in roles):
            return project
        membership = self.db.query(FinanceProjectMembership.id).filter(
            FinanceProjectMembership.project_id == project_id,
            FinanceProjectMembership.user_id == self.user_id,
        ).first()
        if project.owner_user_id != self.user_id and not membership:
            raise FinanceForbidden("无权访问该项目")
        if write and not roles.intersection(WRITE_ROLES):
            raise FinanceForbidden("当前角色对项目只有只读权限")
        return project

    def audit(self, action: str, entity: Any, before: dict[str, Any] | None = None) -> None:
        self.db.add(FinanceAuditEvent(
            actor_user_id=self.user_id,
            action=action,
            entity_type=entity.__tablename__,
            entity_id=str(entity.id),
            before_payload=serial(before),
            after_payload=row_dict(entity),
            request_id=self.request_id,
            ip_address=self.ip_address,
        ))
        self.db.add(OutboxEvent(
            topic=f"finance.{action}",
            aggregate_type=entity.__tablename__,
            aggregate_id=str(entity.id),
            payload={"actor_user_id": self.user_id, "after": row_dict(entity)},
        ))

    def commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise FinanceConflict("数据重复或违反财务数据约束", code="integrity_conflict") from exc

    def idempotent(self, endpoint: str, key: str, payload: dict[str, Any], callback) -> tuple[dict[str, Any], bool]:
        if not key or len(key) > 128:
            raise FinanceError("写操作必须提供有效的 Idempotency-Key", code="idempotency_key_required")
        digest = hashlib.sha256(json.dumps(serial(payload), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        scope = f"{self.user_id}:{endpoint}:{key}"
        if self.db.bind.dialect.name == "postgresql":
            # Session-level lock intentionally survives commits inside the
            # application service and closes the duplicate side-effect race.
            self.db.execute(text("SELECT pg_advisory_lock(hashtext(:scope))"), {"scope": scope})
            release = lambda: self.db.execute(text("SELECT pg_advisory_unlock(hashtext(:scope))"), {"scope": scope})
            lock = None
        else:
            with _IDEMPOTENCY_LOCKS_GUARD:
                lock = _IDEMPOTENCY_LOCKS.setdefault(scope, threading.Lock())
            lock.acquire()
            release = lock.release
        try:
            existing = self.db.query(IdempotencyRecord).filter(
                IdempotencyRecord.actor_user_id == self.user_id,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == key,
            ).first()
            if existing:
                if existing.request_hash != digest:
                    raise FinanceConflict("同一 Idempotency-Key 对应了不同请求", code="idempotency_mismatch")
                return dict(existing.response_payload), True
            result = callback()
            self.db.add(IdempotencyRecord(
                actor_user_id=self.user_id,
                endpoint=endpoint,
                idempotency_key=key,
                request_hash=digest,
                response_status=200,
                response_payload=serial(result),
                expires_at=now() + timedelta(days=7),
            ))
            self.commit()
            return result, False
        finally:
            release()

    # ---------- roles and projects ----------
    def grant_role(self, request: RoleGrant) -> dict[str, Any]:
        self.require("finance_admin")
        if not self.db.get(User, request.user_id):
            raise FinanceNotFound("用户不存在")
        role = self.db.query(FinanceUserRole).filter_by(user_id=request.user_id, role=request.role).first()
        if not role:
            role = FinanceUserRole(user_id=request.user_id, role=request.role, granted_by=self.user_id)
            self.db.add(role)
            self.db.flush()
        if request.project_id:
            self.require_project(request.project_id)
            membership = self.db.query(FinanceProjectMembership).filter_by(
                project_id=request.project_id, user_id=request.user_id, role=request.role,
            ).first()
            if not membership:
                self.db.add(FinanceProjectMembership(
                    project_id=request.project_id, user_id=request.user_id, role=request.role,
                ))
        self.audit("role.granted", role)
        self.commit()
        return row_dict(role)

    def list_projects(self) -> list[dict[str, Any]]:
        query = self.db.query(FinanceProject).filter(FinanceProject.deleted_at.is_(None))
        if "finance_admin" not in self.roles and "auditor" not in self.roles:
            project_ids = select(FinanceProjectMembership.project_id).where(FinanceProjectMembership.user_id == self.user_id)
            query = query.filter(or_(FinanceProject.owner_user_id == self.user_id, FinanceProject.id.in_(project_ids)))
        return [row_dict(row) for row in query.order_by(FinanceProject.created_at.desc()).all()]

    def create_project(self, request: ProjectCreate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager")
        project = FinanceProject(
            project_key=request.project_key,
            name=request.name,
            owner_user_id=request.owner_user_id or self.user_id,
            currency=request.currency,
            created_by=self.user_id,
        )
        self.db.add(project)
        self.db.flush()
        self.db.add(FinanceProjectMembership(project_id=project.id, user_id=project.owner_user_id, role="project_manager"))
        self.audit("project.created", project)
        self.commit()
        return row_dict(project)

    def update_project(self, project_id: str, request: ProjectUpdate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager")
        project = self.require_project(project_id, write=True)
        if project.version != request.version:
            raise FinanceConflict("项目已被其他用户修改", code="version_conflict", details={"version": project.version})
        before = row_dict(project)
        for field in ("name", "owner_user_id", "status"):
            value = getattr(request, field)
            if value is not None:
                setattr(project, field, value)
        project.version += 1
        project.updated_at = now()
        self.audit("project.updated", project, before)
        self.commit()
        return row_dict(project)

    def create_allocation(self, request: FundAllocationCreate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager")
        self.require_project(request.project_id, write=True)
        allocation = FundAllocation(**request.model_dump(), created_by=self.user_id)
        self.db.add(allocation)
        self.db.flush()
        self.audit("allocation.created", allocation)
        self.commit()
        return row_dict(allocation)

    def list_allocations(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = self.db.query(FundAllocation).filter(FundAllocation.deleted_at.is_(None))
        if project_id:
            self.require_project(project_id)
            query = query.filter(FundAllocation.project_id == project_id)
        return [row_dict(row) for row in query.order_by(FundAllocation.allocated_at.desc()).all()]

    # ---------- budgets ----------
    def list_budgets(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = self.db.query(BudgetVersion).filter(BudgetVersion.deleted_at.is_(None))
        if project_id:
            self.require_project(project_id)
            query = query.filter(BudgetVersion.project_id == project_id)
        budgets = query.order_by(BudgetVersion.created_at.desc()).all()
        result = []
        for budget in budgets:
            data = row_dict(budget)
            data["lines"] = [row_dict(line) for line in self.db.query(BudgetLine).filter_by(budget_version_id=budget.id).all()]
            result.append(data)
        return result

    def create_budget(self, request: BudgetCreate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager")
        self.require_project(request.project_id, write=True)
        allocated = money(self.db.query(func.coalesce(func.sum(FundAllocation.amount), 0)).filter(
            FundAllocation.project_id == request.project_id,
            FundAllocation.deleted_at.is_(None),
        ).scalar())
        if request.approved_amount > allocated:
            raise FinanceConflict("预算金额不能超过已拨付经费", code="budget_exceeds_allocation", details={"allocated": float(allocated)})
        next_version = int(self.db.query(func.coalesce(func.max(BudgetVersion.version_no), 0)).filter_by(project_id=request.project_id).scalar()) + 1
        budget = BudgetVersion(
            project_id=request.project_id,
            version_no=next_version,
            name=request.name,
            approved_amount=request.approved_amount,
            effective_from=request.effective_from,
            created_by=self.user_id,
        )
        self.db.add(budget)
        self.db.flush()
        self.audit("budget.created", budget)
        self.commit()
        return {**row_dict(budget), "lines": []}

    def replace_budget_lines(self, budget_id: str, request: BudgetLinesReplace) -> dict[str, Any]:
        self.require("finance_admin", "project_manager")
        budget = self.db.get(BudgetVersion, budget_id)
        if not budget or budget.deleted_at:
            raise FinanceNotFound("预算不存在")
        self.require_project(budget.project_id, write=True)
        if budget.status != "draft":
            raise FinanceConflict("只有草稿预算可以编辑")
        if budget.lock_version != request.version:
            raise FinanceConflict("预算已被其他用户修改", code="version_conflict", details={"version": budget.lock_version})
        total = sum((money(item.amount) for item in request.lines), Decimal("0"))
        if total > money(budget.approved_amount):
            raise FinanceConflict("预算科目合计超过预算批复金额", code="budget_lines_exceed_total")
        existing = {line.category: line for line in self.db.query(BudgetLine).filter_by(budget_version_id=budget.id).all()}
        incoming = {item.category.strip(): item for item in request.lines}
        for category, line in existing.items():
            if category not in incoming:
                if money(line.reserved_amount) or money(line.spent_amount):
                    raise FinanceConflict(f"科目 {category} 已发生业务，不能删除")
                self.db.delete(line)
        for category, item in incoming.items():
            line = existing.get(category)
            if line:
                if money(item.amount) < money(line.reserved_amount) + money(line.spent_amount):
                    raise FinanceConflict(f"科目 {category} 金额低于已占用和已支出")
                line.amount = item.amount
                line.note = item.note
                line.lock_version += 1
            else:
                self.db.add(BudgetLine(
                    budget_version_id=budget.id,
                    category=category,
                    amount=item.amount,
                    note=item.note,
                ))
        budget.lock_version += 1
        budget.updated_at = now()
        self.audit("budget.lines_replaced", budget)
        self.commit()
        return self.get_budget(budget.id)

    def approve_budget(self, budget_id: str, version: int) -> dict[str, Any]:
        self.require("finance_admin")
        budget = self.db.get(BudgetVersion, budget_id)
        if not budget:
            raise FinanceNotFound("预算不存在")
        if budget.lock_version != version:
            raise FinanceConflict("预算版本冲突", code="version_conflict", details={"version": budget.lock_version})
        if budget.status != "draft":
            raise FinanceConflict("预算已经审批或失效")
        line_total = money(self.db.query(func.coalesce(func.sum(BudgetLine.amount), 0)).filter_by(budget_version_id=budget.id).scalar())
        if line_total != money(budget.approved_amount):
            raise FinanceConflict("预算科目合计必须等于批复金额", details={"line_total": float(line_total)})
        self.db.query(BudgetVersion).filter(
            BudgetVersion.project_id == budget.project_id,
            BudgetVersion.status == "approved",
            BudgetVersion.id != budget.id,
        ).update({"status": "superseded"}, synchronize_session=False)
        budget.status = "approved"
        budget.approved_by = self.user_id
        budget.approved_at = now()
        budget.lock_version += 1
        self.audit("budget.approved", budget)
        self.commit()
        return self.get_budget(budget.id)

    def adjust_budget_line(self, line_id: str, request: BudgetAdjustmentCreate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager")
        line = self.db.get(BudgetLine, line_id)
        if not line:
            raise FinanceNotFound("预算科目不存在")
        budget = self.db.get(BudgetVersion, line.budget_version_id)
        self.require_project(budget.project_id, write=True)
        if line.lock_version != request.version:
            raise FinanceConflict("预算科目版本冲突", code="version_conflict", details={"version": line.lock_version})
        target = money(request.amount)
        if target < money(line.reserved_amount) + money(line.spent_amount):
            raise FinanceConflict("调整后金额不能低于已占用和已支出")
        other_total = money(self.db.query(func.coalesce(func.sum(BudgetLine.amount), 0)).filter(
            BudgetLine.budget_version_id == budget.id, BudgetLine.id != line.id,
        ).scalar())
        if other_total + target > money(budget.approved_amount):
            raise FinanceConflict("调整后预算科目合计超过批复金额")
        before = money(line.amount)
        adjustment = BudgetAdjustment(
            budget_line_id=line.id,
            before_amount=before,
            after_amount=target,
            delta_amount=target - before,
            reason=request.reason,
            created_by=self.user_id,
        )
        line.amount = target
        line.lock_version += 1
        self.db.add(adjustment)
        self.audit("budget.adjusted", adjustment)
        self.commit()
        return row_dict(line)

    def get_budget(self, budget_id: str) -> dict[str, Any]:
        budget = self.db.get(BudgetVersion, budget_id)
        if not budget:
            raise FinanceNotFound("预算不存在")
        self.require_project(budget.project_id)
        return {
            **row_dict(budget),
            "lines": [row_dict(line) for line in self.db.query(BudgetLine).filter_by(budget_version_id=budget.id).order_by(BudgetLine.category).all()],
        }

    # ---------- reimbursements and workflow ----------
    def list_reimbursements(self, status: str | None = None) -> list[dict[str, Any]]:
        query = self.db.query(Reimbursement).filter(Reimbursement.deleted_at.is_(None))
        if status:
            query = query.filter(Reimbursement.status == status)
        if "finance_admin" not in self.roles and "auditor" not in self.roles:
            project_ids = select(FinanceProjectMembership.project_id).where(FinanceProjectMembership.user_id == self.user_id)
            query = query.filter(or_(Reimbursement.project_id.in_(project_ids), Reimbursement.applicant_user_id == self.user_id))
        return [self.reimbursement_detail(row) for row in query.order_by(Reimbursement.created_at.desc()).all()]

    def create_reimbursement(self, request: ReimbursementCreate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager", "applicant")
        self.require_project(request.project_id, write=True)
        number = f"REIM-{now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        record = Reimbursement(
            reimbursement_no=number,
            project_id=request.project_id,
            applicant_user_id=self.user_id,
            title=request.title,
            description=request.description,
        )
        self.db.add(record)
        self.db.flush()
        self.audit("reimbursement.created", record)
        self.commit()
        return self.reimbursement_detail(record)

    def reimbursement_detail(self, record: Reimbursement) -> dict[str, Any]:
        data = row_dict(record)
        data["items"] = [row_dict(item) for item in self.db.query(ReimbursementItem).filter_by(reimbursement_id=record.id).all()]
        instance = self.db.query(ApprovalInstance).filter_by(reimbursement_id=record.id).order_by(ApprovalInstance.submission_no.desc()).first()
        data["approval"] = None
        if instance:
            data["approval"] = {
                **row_dict(instance),
                "tasks": [row_dict(task) for task in self.db.query(ApprovalTask).filter_by(approval_instance_id=instance.id).order_by(ApprovalTask.step_order).all()],
                "events": [row_dict(event) for event in self.db.query(ApprovalEvent).filter_by(approval_instance_id=instance.id).order_by(ApprovalEvent.created_at).all()],
            }
        return data

    def get_reimbursement(self, reimbursement_id: str) -> dict[str, Any]:
        record = self.db.get(Reimbursement, reimbursement_id)
        if not record or record.deleted_at:
            raise FinanceNotFound("报销单不存在")
        self.require_project(record.project_id)
        return self.reimbursement_detail(record)

    def update_reimbursement(self, reimbursement_id: str, request: ReimbursementUpdate) -> dict[str, Any]:
        record = self._editable_reimbursement(reimbursement_id, request.version)
        before = row_dict(record)
        if request.title is not None:
            record.title = request.title
        if request.description is not None:
            record.description = request.description
        record.lock_version += 1
        self.audit("reimbursement.updated", record, before)
        self.commit()
        return self.reimbursement_detail(record)

    def add_reimbursement_item(self, reimbursement_id: str, request: ReimbursementItemCreate) -> dict[str, Any]:
        record = self._editable_reimbursement(reimbursement_id)
        line = self.db.get(BudgetLine, request.budget_line_id)
        if not line:
            raise FinanceNotFound("预算科目不存在")
        budget = self.db.get(BudgetVersion, line.budget_version_id)
        if budget.project_id != record.project_id or budget.status != "approved":
            raise FinanceConflict("报销明细必须使用本项目已审批预算")
        if request.invoice_id:
            invoice = self.db.get(Invoice, request.invoice_id)
            if not invoice or invoice.deleted_at:
                raise FinanceNotFound("发票不存在")
            linked = self.db.query(ReimbursementItem.id).filter(
                ReimbursementItem.invoice_id == request.invoice_id,
                ReimbursementItem.reimbursement_id != reimbursement_id,
            ).first()
            if linked:
                raise FinanceConflict("发票已关联其他报销明细", code="invoice_already_linked")
        item = ReimbursementItem(reimbursement_id=record.id, **request.model_dump())
        self.db.add(item)
        self.db.flush()
        record.total_amount = money(record.total_amount) + money(item.amount)
        record.lock_version += 1
        self.audit("reimbursement.item_added", item)
        self.commit()
        return self.reimbursement_detail(record)

    def update_reimbursement_item(self, reimbursement_id: str, item_id: str, request: ReimbursementItemUpdate) -> dict[str, Any]:
        record = self._editable_reimbursement(reimbursement_id, request.version)
        item = self.db.get(ReimbursementItem, item_id)
        if not item or item.reimbursement_id != record.id:
            raise FinanceNotFound("报销明细不存在")
        before_amount = money(item.amount)
        for field in ("budget_line_id", "description", "vendor", "expense_date", "amount", "invoice_id"):
            value = getattr(request, field)
            if value is not None:
                setattr(item, field, value)
        record.total_amount = money(record.total_amount) - before_amount + money(item.amount)
        record.lock_version += 1
        self.audit("reimbursement.item_updated", item)
        self.commit()
        return self.reimbursement_detail(record)

    def delete_reimbursement_item(self, reimbursement_id: str, item_id: str, version: int) -> dict[str, Any]:
        record = self._editable_reimbursement(reimbursement_id, version)
        item = self.db.get(ReimbursementItem, item_id)
        if not item or item.reimbursement_id != record.id:
            raise FinanceNotFound("报销明细不存在")
        record.total_amount = money(record.total_amount) - money(item.amount)
        record.lock_version += 1
        self.db.delete(item)
        self.audit("reimbursement.item_deleted", record)
        self.commit()
        return self.reimbursement_detail(record)

    def _editable_reimbursement(self, reimbursement_id: str, version: int | None = None) -> Reimbursement:
        record = self.db.get(Reimbursement, reimbursement_id)
        if not record or record.deleted_at:
            raise FinanceNotFound("报销单不存在")
        if record.applicant_user_id != self.user_id and "finance_admin" not in self.roles:
            raise FinanceForbidden("只能编辑自己的报销单")
        if record.status not in {"draft", "returned"}:
            raise FinanceConflict("当前状态不允许编辑")
        if version is not None and record.lock_version != version:
            raise FinanceConflict("报销单已被其他用户修改", code="version_conflict", details={"version": record.lock_version})
        return record

    def create_workflow(self, request: WorkflowCreate) -> dict[str, Any]:
        self.require("finance_admin")
        workflow = ApprovalWorkflowDefinition(
            name=request.name,
            project_id=request.project_id,
            category=request.category,
            min_amount=request.min_amount,
            max_amount=request.max_amount,
            priority=request.priority,
            created_by=self.user_id,
        )
        self.db.add(workflow)
        self.db.flush()
        for index, item in enumerate(request.steps, start=1):
            self.db.add(ApprovalWorkflowStep(
                workflow_definition_id=workflow.id,
                step_order=index,
                name=item.name,
                assignee_role=item.assignee_role,
                assignee_user_id=item.assignee_user_id,
            ))
        self.audit("workflow.created", workflow)
        self.commit()
        return self.workflow_detail(workflow)

    def list_workflows(self) -> list[dict[str, Any]]:
        self.require("finance_admin", "auditor")
        return [self.workflow_detail(row) for row in self.db.query(ApprovalWorkflowDefinition).order_by(ApprovalWorkflowDefinition.priority).all()]

    def workflow_detail(self, workflow: ApprovalWorkflowDefinition) -> dict[str, Any]:
        return {
            **row_dict(workflow),
            "steps": [row_dict(step) for step in self.db.query(ApprovalWorkflowStep).filter_by(workflow_definition_id=workflow.id).order_by(ApprovalWorkflowStep.step_order).all()],
        }

    def submit_reimbursement(self, reimbursement_id: str, version: int) -> dict[str, Any]:
        record = self._editable_reimbursement(reimbursement_id, version)
        items = self.db.query(ReimbursementItem).filter_by(reimbursement_id=record.id).all()
        if not items or money(record.total_amount) <= 0:
            raise FinanceConflict("报销单至少需要一条有效明细")
        workflow = self._match_workflow(record)
        if not workflow:
            raise FinanceConflict("没有匹配的审批工作流", code="approval_workflow_missing")
        steps = self.db.query(ApprovalWorkflowStep).filter_by(workflow_definition_id=workflow.id).order_by(ApprovalWorkflowStep.step_order).all()
        if not steps:
            raise FinanceConflict("审批工作流没有步骤")
        for step in steps:
            if step.assignee_user_id == record.applicant_user_id:
                raise FinanceConflict("申请人不能审批自己的报销单", code="separation_of_duties")
        # Lock lines where supported; SQLite serializes writers and ignores FOR UPDATE.
        line_ids = sorted({item.budget_line_id for item in items})
        lines = {
            line.id: line for line in self.db.query(BudgetLine).filter(BudgetLine.id.in_(line_ids)).with_for_update().all()
        }
        required: dict[str, Decimal] = {}
        for item in items:
            required[item.budget_line_id] = required.get(item.budget_line_id, Decimal("0")) + money(item.amount)
        for line_id, amount_required in required.items():
            line = lines.get(line_id)
            if not line:
                raise FinanceNotFound("预算科目不存在")
            available = money(line.amount) - money(line.reserved_amount) - money(line.spent_amount)
            if amount_required > available:
                raise FinanceConflict("可用预算不足", code="insufficient_budget", details={"budget_line_id": line_id, "available": float(available)})
        for item in items:
            line = lines[item.budget_line_id]
            line.reserved_amount = money(line.reserved_amount) + money(item.amount)
            reservation = self.db.query(BudgetReservation).filter_by(reimbursement_item_id=item.id).first()
            if reservation:
                if reservation.status != "released":
                    raise FinanceConflict("报销明细已占用预算", code="duplicate_budget_reservation")
                reservation.status = "reserved"
                reservation.amount = item.amount
                reservation.budget_line_id = line.id
                reservation.reserved_at = now()
                reservation.released_at = None
                reservation.committed_at = None
            else:
                self.db.add(BudgetReservation(
                    reimbursement_item_id=item.id,
                    budget_line_id=line.id,
                    amount=item.amount,
                ))
        snapshot = [{
            "order": step.step_order,
            "name": step.name,
            "assignee_role": step.assignee_role,
            "assignee_user_id": step.assignee_user_id,
        } for step in steps]
        submission_no = int(self.db.query(func.coalesce(func.max(ApprovalInstance.submission_no), 0)).filter_by(reimbursement_id=record.id).scalar()) + 1
        instance = ApprovalInstance(
            reimbursement_id=record.id,
            submission_no=submission_no,
            workflow_definition_id=workflow.id,
            workflow_snapshot=snapshot,
        )
        self.db.add(instance)
        self.db.flush()
        first = steps[0]
        self.db.add(ApprovalTask(
            approval_instance_id=instance.id,
            step_order=1,
            assignee_role=first.assignee_role,
            assignee_user_id=first.assignee_user_id,
        ))
        record.status = "submitted"
        record.submitted_at = now()
        record.lock_version += 1
        self.audit("reimbursement.submitted", record)
        self.commit()
        return self.reimbursement_detail(record)

    def _match_workflow(self, record: Reimbursement) -> ApprovalWorkflowDefinition | None:
        amount = money(record.total_amount)
        return self.db.query(ApprovalWorkflowDefinition).filter(
            ApprovalWorkflowDefinition.is_active.is_(True),
            or_(ApprovalWorkflowDefinition.project_id.is_(None), ApprovalWorkflowDefinition.project_id == record.project_id),
            ApprovalWorkflowDefinition.min_amount <= amount,
            or_(ApprovalWorkflowDefinition.max_amount.is_(None), ApprovalWorkflowDefinition.max_amount >= amount),
        ).order_by(
            ApprovalWorkflowDefinition.project_id.is_(None).asc(),
            ApprovalWorkflowDefinition.priority.asc(),
        ).first()

    def list_my_approval_tasks(self) -> list[dict[str, Any]]:
        roles = self.roles
        query = self.db.query(ApprovalTask).filter(ApprovalTask.status == "pending").filter(
            or_(
                ApprovalTask.assignee_user_id == self.user_id,
                and_(ApprovalTask.assignee_user_id.is_(None), ApprovalTask.assignee_role.in_(roles or {"__none__"})),
            )
        )
        return [row_dict(task) for task in query.order_by(ApprovalTask.created_at).all()]

    def act_approval(self, task_id: str, action: str, comment: str = "") -> dict[str, Any]:
        if action not in {"approve", "return", "reject"}:
            raise FinanceError("未知审批动作")
        task = self.db.get(ApprovalTask, task_id)
        if not task or task.status != "pending":
            raise FinanceConflict("审批任务不存在或已处理")
        if task.assignee_user_id and task.assignee_user_id != self.user_id:
            raise FinanceForbidden("审批任务未分配给当前用户")
        if not task.assignee_user_id and task.assignee_role not in self.roles:
            raise FinanceForbidden("当前用户不具备该审批角色")
        instance = self.db.get(ApprovalInstance, task.approval_instance_id)
        record = self.db.get(Reimbursement, instance.reimbursement_id)
        if record.applicant_user_id == self.user_id:
            raise FinanceConflict("申请人不能审批自己的报销单", code="separation_of_duties")
        from_status = record.status
        task.status = {"approve": "approved", "return": "returned", "reject": "rejected"}[action]
        task.comment = comment
        task.acted_by = self.user_id
        task.acted_at = now()
        if action == "approve":
            snapshot = list(instance.workflow_snapshot)
            next_order = task.step_order + 1
            next_step = next((item for item in snapshot if int(item["order"]) == next_order), None)
            if next_step:
                self.db.add(ApprovalTask(
                    approval_instance_id=instance.id,
                    step_order=next_order,
                    assignee_role=next_step.get("assignee_role"),
                    assignee_user_id=next_step.get("assignee_user_id"),
                ))
                instance.current_step = next_order
                record.status = "in_review"
            else:
                instance.status = "approved"
                instance.completed_at = now()
                record.status = "approved"
                record.approved_at = now()
        else:
            instance.status = task.status
            instance.completed_at = now()
            record.status = task.status
            self._release_reservations(record.id)
        record.lock_version += 1
        self.db.add(ApprovalEvent(
            approval_instance_id=instance.id,
            task_id=task.id,
            action=action,
            from_status=from_status,
            to_status=record.status,
            actor_user_id=self.user_id,
            comment=comment,
        ))
        self.audit(f"approval.{action}", record)
        self.commit()
        return self.reimbursement_detail(record)

    def _release_reservations(self, reimbursement_id: str) -> None:
        reservations = self.db.query(BudgetReservation).join(
            ReimbursementItem, ReimbursementItem.id == BudgetReservation.reimbursement_item_id,
        ).filter(
            ReimbursementItem.reimbursement_id == reimbursement_id,
            BudgetReservation.status == "reserved",
        ).with_for_update().all()
        for reservation in reservations:
            line = self.db.get(BudgetLine, reservation.budget_line_id)
            line.reserved_amount = max(Decimal("0"), money(line.reserved_amount) - money(reservation.amount))
            reservation.status = "released"
            reservation.released_at = now()

    def return_to_draft(self, reimbursement_id: str, version: int) -> dict[str, Any]:
        record = self.db.get(Reimbursement, reimbursement_id)
        if not record or record.applicant_user_id != self.user_id:
            raise FinanceForbidden("只能修改自己的退回报销单")
        if record.status != "returned" or record.lock_version != version:
            raise FinanceConflict("报销单状态或版本不允许转为草稿")
        record.status = "draft"
        record.lock_version += 1
        self.audit("reimbursement.redrafted", record)
        self.commit()
        return self.reimbursement_detail(record)

    def archive_reimbursement(self, reimbursement_id: str, version: int) -> dict[str, Any]:
        self.require("finance_admin", "cashier")
        record = self.db.get(Reimbursement, reimbursement_id)
        if not record or record.status != "paid":
            raise FinanceConflict("只有已付款报销单可以归档")
        if record.lock_version != version:
            raise FinanceConflict("报销单版本冲突", code="version_conflict", details={"version": record.lock_version})
        record.status = "archived"
        record.archived_at = now()
        record.lock_version += 1
        self.audit("reimbursement.archived", record)
        self.commit()
        return self.reimbursement_detail(record)

    # ---------- invoices and attachments ----------
    def create_invoice(self, request: InvoiceCreate) -> dict[str, Any]:
        self.require("finance_admin", "project_manager", "applicant")
        self.require_project(request.project_id, write=True)
        invoice = Invoice(**request.model_dump(), created_by=self.user_id)
        self.db.add(invoice)
        self.db.flush()
        self.audit("invoice.created", invoice)
        self.commit()
        return self.invoice_detail(invoice)

    def list_invoices(self) -> list[dict[str, Any]]:
        query = self.db.query(Invoice).filter(Invoice.deleted_at.is_(None))
        if "finance_admin" not in self.roles and "auditor" not in self.roles:
            project_ids = select(FinanceProjectMembership.project_id).where(FinanceProjectMembership.user_id == self.user_id)
            query = query.filter(Invoice.project_id.in_(project_ids))
        return [self.invoice_detail(row) for row in query.order_by(Invoice.created_at.desc()).all()]

    def invoice_detail(self, invoice: Invoice) -> dict[str, Any]:
        return {
            **row_dict(invoice),
            "attachments": [row_dict(item) for item in self.db.query(InvoiceAttachment).filter_by(invoice_id=invoice.id).all()],
        }

    def attach_invoice(self, invoice_id: str, filename: str, content_type: str, content: bytes) -> dict[str, Any]:
        invoice = self.db.get(Invoice, invoice_id)
        if not invoice or invoice.deleted_at:
            raise FinanceNotFound("发票不存在")
        self.require_project(invoice.project_id, write=True)
        digest = hashlib.sha256(content).hexdigest()
        if self.db.query(InvoiceAttachment.id).filter_by(sha256=digest).first():
            raise FinanceConflict("附件内容已存在", code="duplicate_attachment")
        scan_status = AttachmentScanner().validate(filename, content_type, content)
        safe_suffix = Path(filename).suffix.lower()[:10]
        object_key = f"invoices/{invoice.id}/{uid()}{safe_suffix}"
        object_storage().put(object_key, content, content_type)
        attachment = InvoiceAttachment(
            invoice_id=invoice.id,
            object_key=object_key,
            original_name=Path(filename).name[:255],
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            scan_status=scan_status,
        )
        self.db.add(attachment)
        self.db.flush()
        self.audit("invoice.attachment_uploaded", attachment)
        self.commit()
        return row_dict(attachment)

    def attachment_url(self, attachment_id: str) -> dict[str, Any]:
        attachment = self.db.get(InvoiceAttachment, attachment_id)
        if not attachment:
            raise FinanceNotFound("附件不存在")
        invoice = self.db.get(Invoice, attachment.invoice_id)
        self.require_project(invoice.project_id)
        self.db.add(FinanceAuditEvent(
            actor_user_id=self.user_id,
            action="invoice.attachment_downloaded",
            entity_type="invoice_attachments",
            entity_id=attachment.id,
            request_id=self.request_id,
            ip_address=self.ip_address,
        ))
        self.commit()
        storage = object_storage()
        url = f"/api/finance/attachments/{attachment.id}/content" if isinstance(storage, LocalObjectStorage) else storage.signed_url(attachment.object_key, 300)
        return {"url": url, "expires_in": 300}

    def attachment_content(self, attachment_id: str) -> tuple[bytes, str, str]:
        attachment = self.db.get(InvoiceAttachment, attachment_id)
        if not attachment:
            raise FinanceNotFound("附件不存在")
        invoice = self.db.get(Invoice, attachment.invoice_id)
        self.require_project(invoice.project_id)
        storage = object_storage()
        if not isinstance(storage, LocalObjectStorage):
            raise FinanceConflict("对象存储附件必须通过签名 URL 下载")
        try:
            content = storage.read(attachment.object_key)
        except FileNotFoundError as exc:
            raise FinanceNotFound("附件文件不存在") from exc
        self.audit("invoice.attachment_downloaded", attachment)
        self.commit()
        return content, attachment.content_type, attachment.original_name

    def run_ocr(self, invoice_id: str) -> dict[str, Any]:
        invoice = self.db.get(Invoice, invoice_id)
        if not invoice:
            raise FinanceNotFound("发票不存在")
        self.require_project(invoice.project_id, write=True)
        attachment = self.db.query(InvoiceAttachment).filter_by(invoice_id=invoice.id).first()
        if not attachment:
            raise FinanceConflict("发票没有附件")
        # Providers normally download from object storage.  The null adapter
        # deliberately returns manual_review and never discards the attachment.
        result = ocr_adapter().extract(b"", attachment.content_type)
        invoice.ocr_payload = result
        invoice.status = "extracted" if result.get("status") == "success" else "manual_review"
        self.audit("invoice.ocr_completed", invoice)
        self.commit()
        return self.invoice_detail(invoice)

    def verify_invoice(self, invoice_id: str) -> dict[str, Any]:
        invoice = self.db.get(Invoice, invoice_id)
        if not invoice:
            raise FinanceNotFound("发票不存在")
        self.require_project(invoice.project_id, write=True)
        result = verification_adapter().verify(row_dict(invoice))
        invoice.verification_payload = result
        invoice.verification_status = result.get("status", "manual_review")
        invoice.status = "verified" if invoice.verification_status == "verified" else "manual_review"
        self.audit("invoice.verification_completed", invoice)
        self.commit()
        return self.invoice_detail(invoice)

    # ---------- payments and reconciliation ----------
    @staticmethod
    def _mask_account(value: str) -> str:
        raw = "".join(char for char in value if char.isdigit())
        return ("*" * max(0, len(raw) - 4) + raw[-4:]) if raw else ""

    def list_payments(self) -> list[dict[str, Any]]:
        query = self.db.query(Payment).join(Reimbursement)
        if "finance_admin" not in self.roles and "auditor" not in self.roles:
            project_ids = select(FinanceProjectMembership.project_id).where(FinanceProjectMembership.user_id == self.user_id)
            query = query.filter(Reimbursement.project_id.in_(project_ids))
        return [row_dict(row) for row in query.order_by(Payment.created_at.desc()).all()]

    def create_payment(self, request: PaymentCreate) -> dict[str, Any]:
        self.require("finance_admin", "cashier")
        record = self.db.get(Reimbursement, request.reimbursement_id)
        if not record or record.status != "approved":
            raise FinanceConflict("只有审批通过的报销单可以登记付款")
        self.require_project(record.project_id, write=True)
        if record.applicant_user_id == self.user_id:
            raise FinanceConflict("申请人不能为自己的报销单登记付款", code="separation_of_duties")
        approver = self.db.query(ApprovalTask.id).join(ApprovalInstance).filter(
            ApprovalInstance.reimbursement_id == record.id,
            ApprovalTask.acted_by == self.user_id,
        ).first()
        if approver:
            raise FinanceConflict("审批人不能为同一报销单登记付款", code="separation_of_duties")
        payment = Payment(
            payment_no=f"PAY-{now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
            reimbursement_id=record.id,
            amount=record.total_amount,
            payee_name=request.payee_name,
            payee_account_masked=self._mask_account(request.payee_account),
            scheduled_at=request.scheduled_at,
            cashier_user_id=self.user_id,
        )
        record.status = "payment_pending"
        record.lock_version += 1
        self.db.add(payment)
        self.db.flush()
        self.audit("payment.created", payment)
        self.commit()
        return row_dict(payment)

    def confirm_payment(self, payment_id: str, request: PaymentConfirm) -> dict[str, Any]:
        self.require("finance_admin", "cashier")
        payment = self.db.get(Payment, payment_id)
        if not payment or payment.status != "pending":
            raise FinanceConflict("付款记录不存在或已处理")
        if payment.lock_version != request.version:
            raise FinanceConflict("付款记录版本冲突", code="version_conflict", details={"version": payment.lock_version})
        record = self.db.get(Reimbursement, payment.reimbursement_id)
        self.require_project(record.project_id, write=True)
        if record.applicant_user_id == self.user_id:
            raise FinanceConflict("申请人不能确认自己的付款", code="separation_of_duties")
        reservations = self.db.query(BudgetReservation).join(ReimbursementItem).filter(
            ReimbursementItem.reimbursement_id == record.id,
            BudgetReservation.status == "reserved",
        ).with_for_update().all()
        for reservation in reservations:
            line = self.db.get(BudgetLine, reservation.budget_line_id)
            line.reserved_amount = money(line.reserved_amount) - money(reservation.amount)
            line.spent_amount = money(line.spent_amount) + money(reservation.amount)
            reservation.status = "committed"
            reservation.committed_at = now()
            item = self.db.get(ReimbursementItem, reservation.reimbursement_item_id)
            if not self.db.query(ExpenseRecord.id).filter_by(reimbursement_item_id=item.id).first():
                self.db.add(ExpenseRecord(
                    project_id=record.project_id,
                    reimbursement_item_id=item.id,
                    payment_id=payment.id,
                    budget_line_id=line.id,
                    amount=item.amount,
                    expense_date=request.paid_at.date(),
                ))
        payment.status = "paid"
        payment.bank_reference = request.bank_reference
        payment.paid_at = request.paid_at
        payment.lock_version += 1
        record.status = "paid"
        record.paid_at = request.paid_at
        record.lock_version += 1
        self.audit("payment.confirmed", payment)
        self.commit()
        return row_dict(payment)

    def import_statement(self, filename: str, content: bytes) -> dict[str, Any]:
        self.require("finance_admin", "cashier")
        digest = hashlib.sha256(content).hexdigest()
        if self.db.query(BankStatementImport.id).filter_by(file_sha256=digest).first():
            raise FinanceConflict("该银行流水文件已导入", code="duplicate_statement")
        rows = parse_statement(filename, content)
        job = BankStatementImport(
            file_name=Path(filename).name[:255],
            file_sha256=digest,
            status="processing",
            imported_by=self.user_id,
        )
        self.db.add(job)
        self.db.flush()
        for row in rows:
            transaction = BankTransaction(
                import_id=job.id,
                transaction_ref=row.transaction_ref,
                transaction_date=row.transaction_date,
                amount=row.amount,
                counterparty=row.counterparty,
                account_masked=row.account_masked,
                memo=row.memo,
                raw_payload=row.raw_payload,
            )
            self.db.add(transaction)
            self.db.flush()
            self._suggest_matches(transaction)
        job.status = "completed"
        job.row_count = len(rows)
        job.completed_at = now()
        self.audit("bank_statement.imported", job)
        self.commit()
        return row_dict(job)

    def _suggest_matches(self, transaction: BankTransaction) -> None:
        candidates = self.db.query(Payment).filter(
            Payment.status == "paid",
            Payment.amount == abs(transaction.amount),
        ).all()
        for payment in candidates:
            date_score = 0.4 if payment.paid_at and abs((payment.paid_at.date() - transaction.transaction_date).days) <= 3 else 0.1
            name_score = 0.4 if transaction.counterparty and transaction.counterparty in payment.payee_name else 0.1
            reference_score = 0.2 if payment.bank_reference == transaction.transaction_ref else 0
            self.db.add(ReconciliationMatch(
                bank_transaction_id=transaction.id,
                payment_id=payment.id,
                matched_amount=abs(transaction.amount),
                confidence=Decimal(str(date_score + name_score + reference_score)),
            ))

    def list_reconciliations(self) -> list[dict[str, Any]]:
        return [row_dict(row) for row in self.db.query(ReconciliationMatch).order_by(ReconciliationMatch.created_at.desc()).all()]

    def confirm_reconciliations(self, match_ids: list[str]) -> list[dict[str, Any]]:
        self.require("finance_admin", "cashier")
        matches = self.db.query(ReconciliationMatch).filter(ReconciliationMatch.id.in_(match_ids)).with_for_update().all()
        if len(matches) != len(set(match_ids)):
            raise FinanceNotFound("部分对账匹配不存在")
        transaction_totals: dict[str, Decimal] = {}
        payment_totals: dict[str, Decimal] = {}
        for match in matches:
            if match.status != "suggested":
                raise FinanceConflict("匹配已经处理")
            transaction_totals[match.bank_transaction_id] = transaction_totals.get(match.bank_transaction_id, Decimal("0")) + money(match.matched_amount)
            payment_totals[match.payment_id] = payment_totals.get(match.payment_id, Decimal("0")) + money(match.matched_amount)
        for transaction_id, total in transaction_totals.items():
            transaction = self.db.get(BankTransaction, transaction_id)
            existing = money(self.db.query(func.coalesce(func.sum(ReconciliationMatch.matched_amount), 0)).filter(
                ReconciliationMatch.bank_transaction_id == transaction_id,
                ReconciliationMatch.status == "confirmed",
            ).scalar())
            if existing + total > abs(money(transaction.amount)):
                raise FinanceConflict("对账金额超过银行流水金额")
        for payment_id, total in payment_totals.items():
            payment = self.db.get(Payment, payment_id)
            existing = money(self.db.query(func.coalesce(func.sum(ReconciliationMatch.matched_amount), 0)).filter(
                ReconciliationMatch.payment_id == payment_id,
                ReconciliationMatch.status == "confirmed",
            ).scalar())
            if existing + total > money(payment.amount):
                raise FinanceConflict("对账金额超过付款金额")
        for match in matches:
            match.status = "confirmed"
            match.confirmed_by = self.user_id
            match.confirmed_at = now()
            self.audit("reconciliation.confirmed", match)
        self.db.flush()
        for transaction_id in transaction_totals:
            transaction = self.db.get(BankTransaction, transaction_id)
            confirmed = money(self.db.query(func.coalesce(func.sum(ReconciliationMatch.matched_amount), 0)).filter(
                ReconciliationMatch.bank_transaction_id == transaction_id,
                ReconciliationMatch.status == "confirmed",
            ).scalar())
            transaction.status = "matched" if confirmed == abs(money(transaction.amount)) else "partially_matched"
        for payment_id in payment_totals:
            payment = self.db.get(Payment, payment_id)
            confirmed = money(self.db.query(func.coalesce(func.sum(ReconciliationMatch.matched_amount), 0)).filter(
                ReconciliationMatch.payment_id == payment_id,
                ReconciliationMatch.status == "confirmed",
            ).scalar())
            payment.status = "reconciled" if confirmed == money(payment.amount) else "paid"
        self.commit()
        return [row_dict(row) for row in matches]

    # ---------- reports, compatibility, health, imports ----------
    def dashboard(self) -> dict[str, Any]:
        budget = self.budget_execution_report()
        reimbursements = self.db.query(Reimbursement).filter(Reimbursement.deleted_at.is_(None)).all()
        invoices = self.db.query(Invoice).filter(Invoice.deleted_at.is_(None)).all()
        payments = self.db.query(Payment).all()
        return {
            "status": "ready",
            "generated_at": now().isoformat(),
            "summary": {
                "projects": self.db.query(FinanceProject).filter(FinanceProject.deleted_at.is_(None)).count(),
                "budget_amount": budget["totals"]["amount"],
                "reserved_amount": budget["totals"]["reserved_amount"],
                "spent_amount": budget["totals"]["spent_amount"],
                "available_amount": budget["totals"]["available_amount"],
                "reimbursements": len(reimbursements),
                "pending_approvals": self.db.query(ApprovalTask).filter_by(status="pending").count(),
                "invoices": len(invoices),
                "pending_payments": sum(1 for item in payments if item.status == "pending"),
                "unmatched_transactions": self.db.query(BankTransaction).filter_by(status="unmatched").count(),
            },
            "recent_reimbursements": [row_dict(row) for row in reimbursements[:20]],
        }

    def budget_execution_report(self) -> dict[str, Any]:
        lines = self.db.query(BudgetLine).join(BudgetVersion).filter(BudgetVersion.status == "approved").all()
        records = []
        for line in lines:
            budget = self.db.get(BudgetVersion, line.budget_version_id)
            project = self.db.get(FinanceProject, budget.project_id)
            amount_value = money(line.amount)
            reserved = money(line.reserved_amount)
            spent = money(line.spent_amount)
            records.append({
                "project_id": project.id,
                "project_key": project.project_key,
                "project_name": project.name,
                "budget_id": budget.id,
                "budget_line_id": line.id,
                "category": line.category,
                "amount": float(amount_value),
                "reserved_amount": float(reserved),
                "spent_amount": float(spent),
                "available_amount": float(amount_value - reserved - spent),
            })
        keys = ("amount", "reserved_amount", "spent_amount", "available_amount")
        return {"records": records, "totals": {key: round(sum(float(item[key]) for item in records), 2) for key in keys}}

    def expense_report(self) -> dict[str, Any]:
        return {"records": [row_dict(row) for row in self.db.query(ExpenseRecord).order_by(ExpenseRecord.expense_date.desc()).all()]}

    def payment_report(self) -> dict[str, Any]:
        return {"records": self.list_payments()}

    def audit_report(self, limit: int = 200) -> dict[str, Any]:
        self.require("finance_admin", "auditor")
        rows = self.db.query(FinanceAuditEvent).order_by(FinanceAuditEvent.created_at.desc()).limit(limit).all()
        return {"records": [row_dict(row) for row in rows]}

    def compatibility_summary(self) -> dict[str, Any]:
        report = self.budget_execution_report()
        projects = self.list_projects()
        project_rows = []
        category_rows = []
        for project in projects:
            related = [item for item in report["records"] if item["project_id"] == project["id"]]
            project_rows.append({
                "project_key": project["project_key"],
                "name": project["name"],
                "budget_amount": sum(item["amount"] for item in related),
                "spent_amount": sum(item["spent_amount"] for item in related),
                "remaining_amount": sum(item["available_amount"] for item in related),
                "status": project["status"],
            })
            category_rows.extend({
                "project_key": project["project_key"],
                "category": item["category"],
                "budget_amount": item["amount"],
                "spent_amount": item["spent_amount"],
                "remaining_amount": item["available_amount"],
            } for item in related)
        reimbursements = self.db.query(Reimbursement).filter(Reimbursement.deleted_at.is_(None)).order_by(Reimbursement.created_at.desc()).all()
        reim_rows = [{
            **row_dict(row),
            "reimbursement_key": row.reimbursement_no,
            "project_key": self.db.get(FinanceProject, row.project_id).project_key,
            "item_count": self.db.query(ReimbursementItem).filter_by(reimbursement_id=row.id).count(),
        } for row in reimbursements]
        return {
            "status": "ready",
            "source": "postgresql" if self.db.bind.dialect.name == "postgresql" else self.db.bind.dialect.name,
            "generated_at": now().isoformat(),
            "summary": {
                "records": self.db.query(ExpenseRecord).count(),
                "total_amount": report["totals"]["spent_amount"],
                "obsidian_total_amount": 0,
                "projects": len(projects),
                "categories": len({item["category"] for item in category_rows}),
                "latest_amount": sum(float(row.total_amount) for row in reimbursements[:2]),
                "data_quality": {"complete": 0, "needs_review": self.db.query(Invoice).filter_by(status="manual_review").count(), "missing_amount": 0, "missing_date": 0},
            },
            "openclaw": None,
            "latest_reimbursements": reim_rows[:2],
            "projects": [],
            "categories": [],
            "monthly": [],
            "records": [],
            "budget": {"summary": {
                "projects": len(projects),
                "budget_amount": report["totals"]["amount"],
                "spent_amount": report["totals"]["spent_amount"],
                "remaining_amount": report["totals"]["available_amount"],
                "execution_percent": round(report["totals"]["spent_amount"] / report["totals"]["amount"] * 100, 2) if report["totals"]["amount"] else 0,
            }, "projects": project_rows, "categories": category_rows},
            "reimbursements": {"summary": {
                "reimbursements": len(reimbursements),
                "items": self.db.query(ReimbursementItem).count(),
                "total_amount": round(sum(float(row.total_amount) for row in reimbursements), 2),
                "confirmed": sum(1 for row in reimbursements if row.status in {"approved", "payment_pending", "paid", "archived"}),
            }, "records": reim_rows, "items": [], "sources": [], "events": []},
        }

    def create_import_job(self, source_type: str, dry_run: bool = False) -> dict[str, Any]:
        self.require("finance_admin")
        job = ImportJob(source_type=source_type, requested_by=self.user_id, status="running")
        self.db.add(job)
        self.db.flush()
        try:
            if source_type == "legacy_sqlite":
                result = self._import_legacy_sqlite(dry_run=dry_run)
            elif source_type in {"obsidian", "openclaw_memory"}:
                result = {"status": "adapter_required", "source_type": source_type, "imported": 0}
            else:
                raise FinanceError("未知导入来源")
            job.status = "completed"
            job.result_payload = result
        except Exception as exc:
            job_id = job.id
            self.db.rollback()
            self.db.add(ImportJob(
                id=job_id, source_type=source_type, requested_by=self.user_id,
                status="failed", error_message=str(exc)[:2000], completed_at=now(),
            ))
            self.db.commit()
            raise
        job.completed_at = now()
        self.audit("import.completed", job)
        self.commit()
        return row_dict(job)

    def get_import_job(self, job_id: str) -> dict[str, Any]:
        self.require("finance_admin")
        job = self.db.get(ImportJob, job_id)
        if not job:
            raise FinanceNotFound("导入任务不存在")
        return row_dict(job)

    def _import_legacy_sqlite(self, dry_run: bool = False) -> dict[str, Any]:
        path = Path(os.getenv("FINANCE_LEGACY_DB_PATH", "data/finance.db")).resolve()
        if not path.is_file():
            raise FinanceNotFound(f"历史财务数据库不存在: {path}")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        counts: dict[str, int] = {}
        zero_expense_count = 0
        reimbursement_total_adjustments: list[dict[str, Any]] = []
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in tables if name.startswith("finance_")}
            if dry_run:
                sums = {}
                for table, column in (("finance_budget_projects", "budget_amount"), ("finance_reimbursements", "total_amount"), ("finance_reimbursement_items", "amount"), ("finance_expenses", "amount")):
                    if table in tables:
                        sums[table] = float(connection.execute(f"SELECT ROUND(COALESCE(SUM({column}),0),2) FROM {table}").fetchone()[0] or 0)
                return {"dry_run": True, "source": str(path), "source_counts": counts, "source_amounts": sums}

            def clean(value: Any, fallback: str = "") -> str:
                return str(value or fallback).strip()

            def as_date(value: Any, fallback: date | None = None) -> date:
                raw = clean(value)
                try:
                    return date.fromisoformat(raw[:10]) if raw else (fallback or now().date())
                except ValueError:
                    return fallback or now().date()

            project_lines: dict[tuple[str, str], BudgetLine] = {}

            def ensure_project_budget(key: str, name: str, approved: Decimal, spent: dict[str, Decimal], source_label: str) -> FinanceProject:
                project = self.db.query(FinanceProject).filter_by(project_key=key).first()
                if not project:
                    project = FinanceProject(project_key=key, name=name or key, owner_user_id=self.user_id, created_by=self.user_id)
                    self.db.add(project)
                    self.db.flush()
                budget = self.db.query(BudgetVersion).filter_by(project_id=project.id, version_no=1).first()
                if not budget:
                    approved = max(money(approved), sum((money(value) for value in spent.values()), Decimal("0.00")))
                    if approved > 0 and not self.db.query(FundAllocation.id).filter_by(reference_no=f"LEGACY-{key}").first():
                        self.db.add(FundAllocation(
                            project_id=project.id, reference_no=f"LEGACY-{key}"[:128], amount=approved,
                            allocated_at=now().date(), source=source_label, created_by=self.user_id,
                        ))
                    budget = BudgetVersion(
                        project_id=project.id, version_no=1, name="历史批复预算", status="approved",
                        approved_amount=approved, approved_by=self.user_id, approved_at=now(), created_by=self.user_id,
                    )
                    self.db.add(budget)
                    self.db.flush()
                    allocated = Decimal("0.00")
                    for category, spent_amount in spent.items():
                        value = money(spent_amount)
                        line = BudgetLine(
                            budget_version_id=budget.id, category=category or "未分类", amount=value,
                            spent_amount=value, note=f"由{source_label}迁移",
                        )
                        self.db.add(line)
                        self.db.flush()
                        project_lines[(project.id, line.category)] = line
                        allocated += value
                    remaining = money(approved) - allocated
                    if remaining > 0 or not spent:
                        line = BudgetLine(
                            budget_version_id=budget.id, category="未分配", amount=max(remaining, Decimal("0.00")),
                            note=f"由{source_label}迁移",
                        )
                        self.db.add(line)
                        self.db.flush()
                        project_lines[(project.id, "未分配")] = line
                else:
                    for line in self.db.query(BudgetLine).filter_by(budget_version_id=budget.id):
                        project_lines[(project.id, line.category)] = line
                return project

            budget_sources = {row["project_key"]: row for row in connection.execute("SELECT * FROM finance_budget_projects")} if "finance_budget_projects" in tables else {}
            category_sources: dict[str, dict[str, Decimal]] = {}
            if "finance_budget_categories" in tables:
                for row in connection.execute("SELECT * FROM finance_budget_categories"):
                    category_sources.setdefault(clean(row["project_key"]), {})[clean(row["category"], "未分类")] = money(row["spent_amount"])
            for key, row in budget_sources.items():
                ensure_project_budget(clean(key), clean(row["name"], clean(key)), money(row["budget_amount"]), category_sources.get(clean(key), {}), "legacy_sqlite")

            reimbursement_sources = list(connection.execute("SELECT * FROM finance_reimbursements")) if "finance_reimbursements" in tables else []
            fallback_total = sum((money(row["total_amount"] or row["amount"]) for row in reimbursement_sources if not clean(row["project_key"])), Decimal("0.00"))
            fallback_project = ensure_project_budget("legacy-reimbursements", "历史未归属报销", fallback_total, {}, "legacy_sqlite") if fallback_total else None
            item_rows = list(connection.execute("SELECT * FROM finance_reimbursement_items")) if "finance_reimbursement_items" in tables else []
            items_by_reimbursement: dict[str, list[sqlite3.Row]] = {}
            for row in item_rows:
                items_by_reimbursement.setdefault(clean(row["reimbursement_key"]), []).append(row)
            status_map = {"confirmed": "approved", "approved": "approved", "paid": "paid", "archived": "archived", "submitted": "submitted", "draft": "draft", "rejected": "rejected", "cancelled": "cancelled"}
            for source in reimbursement_sources:
                legacy_key = clean(source["reimbursement_key"])
                if self.db.query(Reimbursement.id).filter_by(legacy_key=legacy_key).first():
                    continue
                key = clean(source["project_key"])
                project = self.db.query(FinanceProject).filter_by(project_key=key).first() if key else fallback_project
                if not project:
                    project = ensure_project_budget(key or "legacy-reimbursements", clean(source["project_name"], key or "历史未归属报销"), money(source["total_amount"] or source["amount"]), {}, "legacy_sqlite")
                source_total = money(source["total_amount"] or source["amount"])
                rows = items_by_reimbursement.get(legacy_key, [])
                item_total = sum((money(row["amount"]) for row in rows), Decimal("0.00"))
                total = item_total if rows else source_total
                if rows and item_total != source_total:
                    reimbursement_total_adjustments.append({
                        "reimbursement_key": legacy_key,
                        "source_total": float(source_total),
                        "item_total": float(item_total),
                    })
                record = Reimbursement(
                    reimbursement_no=legacy_key if legacy_key.startswith("REIM-") else f"LEGACY-{legacy_key}",
                    legacy_key=legacy_key, project_id=project.id, applicant_user_id=self.user_id,
                    title=clean(source["title"], "历史报销单"),
                    description=clean(source["note"]) or (f"历史汇总金额 {source_total}，迁移按明细合计 {item_total}" if rows and item_total != source_total else None),
                    total_amount=total, status=status_map.get(clean(source["status"]), "returned"),
                    submitted_at=datetime.fromisoformat(source["submitted_at"]) if clean(source["submitted_at"]) else None,
                    paid_at=datetime.fromisoformat(source["paid_at"]) if clean(source["paid_at"]) else None,
                    archived_at=datetime.fromisoformat(source["archived_at"]) if clean(source["archived_at"]) else None,
                )
                self.db.add(record)
                self.db.flush()
                if not rows and total > 0:
                    rows = [{"item_key": "summary", "budget_category": "未分配", "vendor": None, "invoice_no": None, "expense_date": source["submitted_at"], "amount": total, "note": "历史汇总明细"}]
                for source_item in rows:
                    category = clean(source_item["budget_category"], "未分配")
                    line = project_lines.get((project.id, category)) or project_lines.get((project.id, "未分配"))
                    if not line:
                        budget = self.db.query(BudgetVersion).filter_by(project_id=project.id, version_no=1).first()
                        line = BudgetLine(budget_version_id=budget.id, category=category, amount=money(source_item["amount"]), note="历史补充科目")
                        self.db.add(line)
                        self.db.flush()
                        project_lines[(project.id, category)] = line
                    invoice = None
                    invoice_no = clean(source_item["invoice_no"])
                    if invoice_no:
                        invoice_code = f"LEGACY-{project.project_key}"[:64]
                        invoice = self.db.query(Invoice).filter_by(invoice_code=invoice_code, invoice_number=invoice_no).first()
                        if not invoice:
                            invoice = Invoice(
                                project_id=project.id, invoice_code=invoice_code, invoice_number=invoice_no,
                                amount=money(source_item["amount"]), status="manual_review", verification_status="manual_review",
                                verification_payload={"source": "legacy_sqlite", "item_key": clean(source_item["item_key"])}, created_by=self.user_id,
                            )
                            self.db.add(invoice)
                            self.db.flush()
                    self.db.add(ReimbursementItem(
                        reimbursement_id=record.id, budget_line_id=line.id,
                        description=clean(source_item["note"], clean(source_item["item_key"], "历史报销明细")),
                        vendor=clean(source_item["vendor"]) or None, expense_date=as_date(source_item["expense_date"]),
                        amount=money(source_item["amount"]), invoice_id=invoice.id if invoice else None,
                    ))

            if "finance_expenses" in tables:
                expense_rows = list(connection.execute("SELECT * FROM finance_expenses"))
                grouped: dict[str, list[sqlite3.Row]] = {}
                for row in expense_rows:
                    if money(row["amount"]) <= 0:
                        zero_expense_count += 1
                        legacy_id = f"legacy-zero-expense-{row['id']}"
                        if not self.db.query(FinanceAuditEvent.id).filter_by(entity_id=legacy_id).first():
                            self.db.add(FinanceAuditEvent(
                                actor_user_id=self.user_id, action="legacy.zero_expense_preserved",
                                entity_type="finance_expenses", entity_id=legacy_id,
                                after_payload={key: row[key] for key in row.keys()},
                            ))
                        continue
                    grouped.setdefault(clean(row["project_code"], "legacy-obsidian"), []).append(row)
                for key, rows in grouped.items():
                    legacy_key = f"EXPENSES-{key}"
                    if self.db.query(Reimbursement.id).filter_by(legacy_key=legacy_key).first():
                        continue
                    spent: dict[str, Decimal] = {}
                    for row in rows:
                        category = clean(row["category"], "未分类")
                        spent[category] = spent.get(category, Decimal("0.00")) + money(row["amount"])
                    total = sum(spent.values(), Decimal("0.00"))
                    project = ensure_project_budget(key, clean(rows[0]["project_name"], key), total, spent, "obsidian_archive")
                    record = Reimbursement(
                        reimbursement_no=f"LEGACY-{legacy_key}"[:64], legacy_key=legacy_key, project_id=project.id,
                        applicant_user_id=self.user_id, title="Obsidian 历史支出归档", total_amount=total,
                        status="archived", archived_at=now(),
                    )
                    self.db.add(record)
                    self.db.flush()
                    payment = Payment(
                        payment_no=f"LEGACY-PAY-{key}"[:64], reimbursement_id=record.id, amount=total,
                        payee_name="历史归档汇总", status="paid", cashier_user_id=self.user_id, paid_at=now(),
                    )
                    self.db.add(payment)
                    self.db.flush()
                    for row in rows:
                        category = clean(row["category"], "未分类")
                        line = project_lines[(project.id, category)]
                        item = ReimbursementItem(
                            reimbursement_id=record.id, budget_line_id=line.id,
                            description=clean(row["expense_key"], "历史归档支出"), vendor=clean(row["handler"]) or None,
                            expense_date=as_date(row["expense_date"]), amount=money(row["amount"]),
                        )
                        self.db.add(item)
                        self.db.flush()
                        self.db.add(ExpenseRecord(
                            project_id=project.id, reimbursement_item_id=item.id, payment_id=payment.id,
                            budget_line_id=line.id, amount=item.amount, expense_date=item.expense_date,
                        ))

            if "finance_audit_logs" in tables:
                for source in connection.execute("SELECT * FROM finance_audit_logs ORDER BY id"):
                    legacy_id = f"legacy-audit-{source['id']}"
                    if not self.db.query(FinanceAuditEvent.id).filter_by(entity_id=legacy_id).first():
                        self.db.add(FinanceAuditEvent(
                            actor_user_id=self.user_id, action=f"legacy.{clean(source['action'], 'event')}"[:64],
                            entity_type=clean(source["source"], "legacy_sqlite")[:64], entity_id=legacy_id,
                            after_payload={"target_key": source["target_key"], "detail": source["detail_json"], "legacy_created_at": source["created_at"]},
                        ))
            self.db.flush()
        finally:
            connection.close()
        imported = {
            "projects": self.db.query(FinanceProject).count(),
            "budgets": self.db.query(BudgetVersion).count(),
            "budget_lines": self.db.query(BudgetLine).count(),
            "reimbursements": self.db.query(Reimbursement).count(),
            "reimbursement_items": self.db.query(ReimbursementItem).count(),
            "invoices": self.db.query(Invoice).count(),
            "expenses": self.db.query(ExpenseRecord).count(),
        }
        orphan_items = self.db.query(ReimbursementItem.id).outerjoin(Reimbursement).filter(Reimbursement.id.is_(None)).count()
        return {
            "dry_run": False,
            "source": str(path),
            "source_counts": counts,
            "imported": imported,
            "checks": {
                "orphan_items": orphan_items,
                "zero_amount_expenses_preserved_as_audit": zero_expense_count,
                "reimbursement_total_adjustments": reimbursement_total_adjustments,
            },
        }

    @staticmethod
    def readiness(db: Session) -> dict[str, Any]:
        dialect = db.bind.dialect.name
        db.execute(select(1))
        tables = set(inspect(db.bind).get_table_names())
        required = {"finance_projects", "reimbursements", "finance_audit_events", "alembic_version"}
        missing = sorted(required - tables)
        storage_status = "ready"
        try:
            storage = object_storage()
            storage.health()
        except Exception as exc:
            storage_status = f"error:{type(exc).__name__}"
        migration_versions: list[str] = []
        if "alembic_version" in tables:
            migration_versions = list(db.execute(text("SELECT version_num FROM alembic_version")).scalars())
        migration_ready = "20260718_finance_prod" in migration_versions
        return {
            "status": "ready" if not missing and migration_ready and storage_status == "ready" else "not_ready",
            "database": {"dialect": dialect, "missing_tables": missing, "migration_versions": migration_versions},
            "object_storage": storage_status,
        }
