"""Validated request types for the finance API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Money = Decimal


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VersionedRequest(ApiModel):
    version: int = Field(ge=1)


class ProjectCreate(ApiModel):
    project_key: str = Field(min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]+$")
    name: str = Field(min_length=2, max_length=255)
    owner_user_id: int | None = None
    currency: Literal["CNY"] = "CNY"


class ProjectUpdate(VersionedRequest):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    owner_user_id: int | None = None
    status: Literal["active", "suspended", "closed"] | None = None


class RoleGrant(ApiModel):
    user_id: int
    role: Literal["finance_admin", "project_manager", "applicant", "reviewer", "cashier", "auditor"]
    project_id: str | None = None


class FundAllocationCreate(ApiModel):
    project_id: str
    reference_no: str = Field(min_length=1, max_length=128)
    amount: Money = Field(gt=0, max_digits=18, decimal_places=2)
    allocated_at: date
    source: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=2000)


class BudgetCreate(ApiModel):
    project_id: str
    name: str = Field(min_length=1, max_length=255)
    approved_amount: Money = Field(gt=0, max_digits=18, decimal_places=2)
    effective_from: date | None = None


class BudgetLineInput(ApiModel):
    category: str = Field(min_length=1, max_length=64)
    amount: Money = Field(ge=0, max_digits=18, decimal_places=2)
    note: str = Field(default="", max_length=2000)


class BudgetLinesReplace(VersionedRequest):
    lines: list[BudgetLineInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_categories(self):
        categories = [item.category.strip() for item in self.lines]
        if len(categories) != len(set(categories)):
            raise ValueError("预算科目不能重复")
        return self


class BudgetAdjustmentCreate(VersionedRequest):
    amount: Money = Field(ge=0, max_digits=18, decimal_places=2)
    reason: str = Field(min_length=2, max_length=2000)


class BudgetApprove(VersionedRequest):
    pass


class ReimbursementCreate(ApiModel):
    project_id: str
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(default="", max_length=5000)


class ReimbursementUpdate(VersionedRequest):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class ReimbursementItemCreate(ApiModel):
    budget_line_id: str
    description: str = Field(min_length=1, max_length=500)
    vendor: str = Field(default="", max_length=255)
    expense_date: date
    amount: Money = Field(gt=0, max_digits=18, decimal_places=2)
    invoice_id: str | None = None


class ReimbursementItemUpdate(VersionedRequest):
    budget_line_id: str | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    vendor: str | None = Field(default=None, max_length=255)
    expense_date: date | None = None
    amount: Money | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    invoice_id: str | None = None


class ReimbursementSubmit(VersionedRequest):
    pass


class WorkflowStepInput(ApiModel):
    name: str = Field(min_length=1, max_length=128)
    assignee_role: Literal["finance_admin", "project_manager", "reviewer"] | None = None
    assignee_user_id: int | None = None

    @model_validator(mode="after")
    def one_assignee(self):
        if bool(self.assignee_role) == bool(self.assignee_user_id):
            raise ValueError("审批步骤必须且只能指定角色或用户之一")
        return self


class WorkflowCreate(ApiModel):
    name: str = Field(min_length=2, max_length=255)
    project_id: str | None = None
    category: str | None = Field(default=None, max_length=64)
    min_amount: Money = Field(default=Decimal("0"), ge=0)
    max_amount: Money | None = Field(default=None, gt=0)
    priority: int = Field(default=100, ge=1, le=10000)
    steps: list[WorkflowStepInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_range(self):
        if self.max_amount is not None and self.max_amount < self.min_amount:
            raise ValueError("审批金额上限不能小于下限")
        return self


class ApprovalAction(ApiModel):
    comment: str = Field(default="", max_length=2000)


class InvoiceCreate(ApiModel):
    project_id: str
    invoice_code: str = Field(default="", max_length=64)
    invoice_number: str = Field(default="", max_length=128)
    invoice_date: date | None = None
    amount: Money | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    tax_amount: Money | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    seller_name: str = Field(default="", max_length=255)
    buyer_name: str = Field(default="", max_length=255)


class InvoiceBatchCreate(ApiModel):
    project_id: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    source_channel: Literal["web", "lark", "watch_folder"] = "web"
    intake_job_id: str | None = None
    external_ref: str | None = Field(default=None, max_length=255)
    note: str = Field(default="", max_length=2000)


class PaymentCreate(ApiModel):
    reimbursement_id: str
    payee_name: str = Field(min_length=1, max_length=255)
    payee_account: str = Field(default="", max_length=128)
    scheduled_at: datetime | None = None


class PaymentConfirm(VersionedRequest):
    bank_reference: str = Field(min_length=1, max_length=128)
    paid_at: datetime
    human_confirmed: Literal[True]
    confirmation_note: str = Field(min_length=2, max_length=500)


class ReconciliationConfirm(ApiModel):
    matches: list[str] = Field(min_length=1, max_length=100)
    human_confirmed: Literal[True]
    confirmation_note: str = Field(min_length=2, max_length=500)


class ImportRequest(ApiModel):
    source_type: Literal["legacy_sqlite", "obsidian", "openclaw_memory"]
    dry_run: bool = False


class Pagination(ApiModel):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
