"""Production finance domain models.

The finance domain uses the application's SQLAlchemy session.  Production is
expected to point ``DATABASE_URL`` at PostgreSQL; SQLite remains supported for
tests and one-way legacy imports.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FinanceProject(Base):
    __tablename__ = "finance_projects"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_key = Column(String(128), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False, default="CNY")
    status = Column(String(24), nullable=False, default="active", index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        CheckConstraint("status IN ('active','suspended','closed')", name="ck_fin_project_status"),
        CheckConstraint("currency = 'CNY'", name="ck_fin_project_currency_v1"),
    )


class FinanceUserRole(Base):
    __tablename__ = "finance_user_roles"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False, index=True)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_fin_user_role"),
        CheckConstraint(
            "role IN ('finance_admin','project_manager','applicant','reviewer','cashier','auditor')",
            name="ck_fin_user_role",
        ),
    )


class FinanceProjectMembership(Base):
    __tablename__ = "finance_project_memberships"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("finance_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (UniqueConstraint("project_id", "user_id", "role", name="uq_fin_project_member"),)


class FundAllocation(Base):
    __tablename__ = "fund_allocations"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=False, index=True)
    reference_no = Column(String(128), nullable=False, unique=True)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="CNY")
    allocated_at = Column(Date, nullable=False)
    source = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_fund_allocation_positive"),)


class BudgetVersion(Base):
    __tablename__ = "budget_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="draft", index=True)
    approved_amount = Column(Numeric(18, 2), nullable=False, default=0)
    effective_from = Column(Date, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    lock_version = Column(Integer, nullable=False, default=1)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "version_no", name="uq_budget_project_version"),
        CheckConstraint("status IN ('draft','approved','superseded','cancelled')", name="ck_budget_version_status"),
        CheckConstraint("approved_amount >= 0", name="ck_budget_approved_amount"),
    )


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id = Column(String(36), primary_key=True, default=_uuid)
    budget_version_id = Column(String(36), ForeignKey("budget_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(64), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    reserved_amount = Column(Numeric(18, 2), nullable=False, default=0)
    spent_amount = Column(Numeric(18, 2), nullable=False, default=0)
    note = Column(Text, nullable=True)
    lock_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("budget_version_id", "category", name="uq_budget_line_category"),
        CheckConstraint("amount >= 0 AND reserved_amount >= 0 AND spent_amount >= 0", name="ck_budget_line_amounts"),
        CheckConstraint("reserved_amount + spent_amount <= amount", name="ck_budget_line_available"),
    )


class BudgetAdjustment(Base):
    __tablename__ = "budget_adjustments"

    id = Column(String(36), primary_key=True, default=_uuid)
    budget_line_id = Column(String(36), ForeignKey("budget_lines.id"), nullable=False, index=True)
    before_amount = Column(Numeric(18, 2), nullable=False)
    after_amount = Column(Numeric(18, 2), nullable=False)
    delta_amount = Column(Numeric(18, 2), nullable=False)
    reason = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Reimbursement(Base):
    __tablename__ = "reimbursements"

    id = Column(String(36), primary_key=True, default=_uuid)
    reimbursement_no = Column(String(64), nullable=False, unique=True, index=True)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=False, index=True)
    applicant_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    total_amount = Column(Numeric(18, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="CNY")
    status = Column(String(32), nullable=False, default="draft", index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    lock_version = Column(Integer, nullable=False, default=1)
    legacy_key = Column(String(128), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_reimbursement_amount"),
        CheckConstraint(
            "status IN ('draft','submitted','in_review','returned','approved','payment_pending','paid','archived','rejected','cancelled')",
            name="ck_reimbursement_status",
        ),
    )


class ReimbursementItem(Base):
    __tablename__ = "reimbursement_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    reimbursement_id = Column(String(36), ForeignKey("reimbursements.id", ondelete="CASCADE"), nullable=False, index=True)
    budget_line_id = Column(String(36), ForeignKey("budget_lines.id"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    vendor = Column(String(255), nullable=True)
    expense_date = Column(Date, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    invoice_id = Column(String(36), ForeignKey("invoices.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_reimbursement_item_amount"),
        UniqueConstraint("invoice_id", name="uq_reimbursement_item_invoice"),
    )


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"

    id = Column(String(36), primary_key=True, default=_uuid)
    reimbursement_item_id = Column(String(36), ForeignKey("reimbursement_items.id"), nullable=False, unique=True)
    budget_line_id = Column(String(36), ForeignKey("budget_lines.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(24), nullable=False, default="reserved", index=True)
    reserved_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    released_at = Column(DateTime(timezone=True), nullable=True)
    committed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_budget_reservation_amount"),
        CheckConstraint("status IN ('reserved','released','committed')", name="ck_budget_reservation_status"),
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=False, index=True)
    invoice_code = Column(String(64), nullable=True, index=True)
    invoice_number = Column(String(128), nullable=True, index=True)
    invoice_date = Column(Date, nullable=True)
    amount = Column(Numeric(18, 2), nullable=True)
    tax_amount = Column(Numeric(18, 2), nullable=True)
    seller_name = Column(String(255), nullable=True)
    buyer_name = Column(String(255), nullable=True)
    status = Column(String(24), nullable=False, default="uploaded", index=True)
    verification_status = Column(String(24), nullable=False, default="pending")
    ocr_payload = Column(JSON, nullable=True)
    verification_payload = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("invoice_code", "invoice_number", name="uq_invoice_identity"),
        CheckConstraint("status IN ('uploaded','extracted','verified','manual_review','rejected','linked','archived')", name="ck_invoice_status"),
    )


class InvoiceAttachment(Base):
    __tablename__ = "invoice_attachments"

    id = Column(String(36), primary_key=True, default=_uuid)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    object_key = Column(String(512), nullable=False, unique=True)
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True, index=True)
    scan_status = Column(String(24), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (CheckConstraint("size_bytes > 0", name="ck_invoice_attachment_size"),)


class InvoiceBatch(Base):
    """A monthly, review-first invoice ingestion batch.

    Batch records are staging data.  They never become formal invoices until a
    later human approval explicitly commits an item to ``invoices``.
    """

    __tablename__ = "invoice_batches"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=False, index=True)
    intake_job_id = Column(String(36), ForeignKey("finance_intake_jobs.id"), nullable=True, index=True)
    period = Column(String(7), nullable=False, index=True)
    source_channel = Column(String(24), nullable=False, default="web", index=True)
    external_ref = Column(String(255), nullable=True, unique=True)
    note = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="received", index=True)
    total_count = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    review_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source_channel IN ('web','lark','watch_folder')",
            name="ck_invoice_batch_source_channel",
        ),
        CheckConstraint(
            "status IN ('received','processing','review_required','completed','failed','cancelled')",
            name="ck_invoice_batch_status",
        ),
        CheckConstraint(
            "total_count >= 0 AND processed_count >= 0 AND review_count >= 0 AND failed_count >= 0",
            name="ck_invoice_batch_counts",
        ),
        Index("ix_invoice_batch_project_period", "project_id", "period"),
    )


class InvoiceIngestItem(Base):
    __tablename__ = "invoice_ingest_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    batch_id = Column(String(36), ForeignKey("invoice_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    formal_invoice_id = Column(String(36), ForeignKey("invoices.id"), nullable=True, unique=True, index=True)
    object_key = Column(String(512), nullable=False, unique=True)
    preprocessed_object_key = Column(String(512), nullable=True, unique=True)
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True, index=True)
    scan_status = Column(String(24), nullable=False, default="pending")
    status = Column(String(32), nullable=False, default="received", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    preprocessing_payload = Column(JSON, nullable=False, default=dict)
    extraction_payload = Column(JSON, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_invoice_ingest_item_size"),
        CheckConstraint("attempt_count >= 0", name="ck_invoice_ingest_attempt_count"),
        CheckConstraint(
            "status IN ('received','scanned','preprocessed','ocr_running','extracted',"
            "'needs_review','duplicate','failed','approved','committed')",
            name="ck_invoice_ingest_item_status",
        ),
        Index("ix_invoice_ingest_batch_status", "batch_id", "status"),
    )


class InvoiceOcrRun(Base):
    __tablename__ = "invoice_ocr_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    item_id = Column(String(36), ForeignKey("invoice_ingest_items.id", ondelete="CASCADE"), nullable=False, index=True)
    engine = Column(String(64), nullable=False, index=True)
    engine_version = Column(String(128), nullable=True)
    status = Column(String(24), nullable=False, index=True)
    text_payload = Column(Text, nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    duration_ms = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    __table_args__ = (
        CheckConstraint("status IN ('success','failed','unavailable')", name="ck_invoice_ocr_run_status"),
        CheckConstraint("duration_ms >= 0", name="ck_invoice_ocr_run_duration"),
        UniqueConstraint("item_id", "engine", name="uq_invoice_ocr_item_engine"),
    )


class InvoiceFieldCandidate(Base):
    __tablename__ = "invoice_field_candidates"

    id = Column(String(36), primary_key=True, default=_uuid)
    item_id = Column(String(36), ForeignKey("invoice_ingest_items.id", ondelete="CASCADE"), nullable=False, index=True)
    ocr_run_id = Column(String(36), ForeignKey("invoice_ocr_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(64), nullable=False, index=True)
    raw_value = Column(Text, nullable=False)
    normalized_value = Column(Text, nullable=False)
    confidence = Column(Numeric(5, 4), nullable=False, default=0)
    evidence_text = Column(Text, nullable=True)
    bounding_box = Column(JSON, nullable=True)
    consensus_status = Column(String(24), nullable=False, default="single_source", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_invoice_field_confidence"),
        CheckConstraint(
            "consensus_status IN ('agreed','single_source','conflict')",
            name="ck_invoice_field_consensus",
        ),
        UniqueConstraint("ocr_run_id", "field_name", name="uq_invoice_ocr_run_field"),
        Index("ix_invoice_field_item_name", "item_id", "field_name"),
    )


class ExpenseRecord(Base):
    __tablename__ = "expense_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=False, index=True)
    reimbursement_item_id = Column(String(36), ForeignKey("reimbursement_items.id"), nullable=False, unique=True)
    payment_id = Column(String(36), ForeignKey("payments.id"), nullable=False, index=True)
    budget_line_id = Column(String(36), ForeignKey("budget_lines.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    expense_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class ApprovalWorkflowDefinition(Base):
    __tablename__ = "approval_workflow_definitions"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    project_id = Column(String(36), ForeignKey("finance_projects.id"), nullable=True, index=True)
    category = Column(String(64), nullable=True)
    min_amount = Column(Numeric(18, 2), nullable=False, default=0)
    max_amount = Column(Numeric(18, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    priority = Column(Integer, nullable=False, default=100)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ApprovalWorkflowStep(Base):
    __tablename__ = "approval_workflow_steps"

    id = Column(String(36), primary_key=True, default=_uuid)
    workflow_definition_id = Column(String(36), ForeignKey("approval_workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    assignee_role = Column(String(32), nullable=True)
    assignee_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("workflow_definition_id", "step_order", name="uq_workflow_step_order"),
        CheckConstraint("step_order > 0", name="ck_workflow_step_order"),
    )


class ApprovalInstance(Base):
    __tablename__ = "approval_instances"

    id = Column(String(36), primary_key=True, default=_uuid)
    reimbursement_id = Column(String(36), ForeignKey("reimbursements.id"), nullable=False, index=True)
    submission_no = Column(Integer, nullable=False, default=1)
    workflow_definition_id = Column(String(36), ForeignKey("approval_workflow_definitions.id"), nullable=False)
    workflow_snapshot = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="active", index=True)
    current_step = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("reimbursement_id", "submission_no", name="uq_approval_submission"),)


class ApprovalTask(Base):
    __tablename__ = "approval_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    approval_instance_id = Column(String(36), ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    assignee_role = Column(String(32), nullable=True, index=True)
    assignee_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    comment = Column(Text, nullable=True)
    acted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (UniqueConstraint("approval_instance_id", "step_order", name="uq_approval_task_step"),)


class ApprovalEvent(Base):
    __tablename__ = "approval_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    approval_instance_id = Column(String(36), ForeignKey("approval_instances.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("approval_tasks.id"), nullable=True)
    action = Column(String(32), nullable=False)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=_uuid)
    payment_no = Column(String(64), nullable=False, unique=True, index=True)
    reimbursement_id = Column(String(36), ForeignKey("reimbursements.id"), nullable=False, unique=True)
    amount = Column(Numeric(18, 2), nullable=False)
    payee_name = Column(String(255), nullable=False)
    payee_account_masked = Column(String(64), nullable=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    bank_reference = Column(String(128), nullable=True, unique=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    cashier_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmation_note = Column(Text, nullable=True)
    lock_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        CheckConstraint("status IN ('pending','paid','reconciled','cancelled')", name="ck_payment_status"),
    )


class BankStatementImport(Base):
    __tablename__ = "bank_statement_imports"

    id = Column(String(36), primary_key=True, default=_uuid)
    file_name = Column(String(255), nullable=False)
    file_sha256 = Column(String(64), nullable=False, unique=True)
    status = Column(String(24), nullable=False, default="processing", index=True)
    row_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    imported_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id = Column(String(36), primary_key=True, default=_uuid)
    import_id = Column(String(36), ForeignKey("bank_statement_imports.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_ref = Column(String(128), nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    counterparty = Column(String(255), nullable=True)
    account_masked = Column(String(64), nullable=True)
    memo = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="unmatched", index=True)
    raw_payload = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("import_id", "transaction_ref", name="uq_bank_transaction_import_ref"),
        CheckConstraint("amount != 0", name="ck_bank_transaction_amount"),
    )


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"

    id = Column(String(36), primary_key=True, default=_uuid)
    bank_transaction_id = Column(String(36), ForeignKey("bank_transactions.id"), nullable=False, index=True)
    payment_id = Column(String(36), ForeignKey("payments.id"), nullable=False, index=True)
    matched_amount = Column(Numeric(18, 2), nullable=False)
    confidence = Column(Numeric(5, 4), nullable=False, default=0)
    status = Column(String(24), nullable=False, default="suggested", index=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    confirmation_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("bank_transaction_id", "payment_id", name="uq_reconciliation_pair"),
        CheckConstraint("matched_amount > 0", name="ck_reconciliation_amount"),
    )


class FinanceAuditEvent(Base):
    __tablename__ = "finance_audit_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(128), nullable=False, index=True)
    before_payload = Column(JSON, nullable=True)
    after_payload = Column(JSON, nullable=True)
    request_id = Column(String(128), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)


class FinanceIntakeJob(Base):
    __tablename__ = "finance_intake_jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    command_message_id = Column(String(64), nullable=False, unique=True, index=True)
    external_message_id = Column(String(200), nullable=True, index=True)
    source_channel = Column(String(32), nullable=False, index=True)
    source_account_id = Column(String(64), nullable=False, default="soundwave", index=True)
    external_conversation_id = Column(String(255), nullable=False)
    external_user_id = Column(String(200), nullable=False)
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_agent_id = Column(String(64), nullable=False, default="soundwave", index=True)
    operation_type = Column(String(32), nullable=False, default="unknown", index=True)
    request_text = Column(Text, nullable=False)
    request_hash = Column(String(64), nullable=False)
    request_metadata = Column(JSON, nullable=False, default=dict)
    mode = Column(String(24), nullable=False, default="shadow", index=True)
    status = Column(String(32), nullable=False, default="received", index=True)
    normalized_payload = Column(JSON, nullable=False, default=dict)
    shadow_snapshot = Column(JSON, nullable=False, default=dict)
    validation_report = Column(JSON, nullable=False, default=dict)
    reviewer_report = Column(JSON, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    lock_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("mode IN ('shadow','controlled_write')", name="ck_fin_intake_mode"),
        CheckConstraint(
            "status IN ('received','shadow_read','awaiting_extraction','extracted',"
            "'needs_review','validated','approved','committed','rejected','failed','cancelled')",
            name="ck_fin_intake_status",
        ),
        CheckConstraint(
            "operation_type IN ('reimbursement','invoice','budget','payment',"
            "'reconciliation','query','unknown')",
            name="ck_fin_intake_operation",
        ),
    )


class FinanceIntakeEvent(Base):
    __tablename__ = "finance_intake_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(
        String(36),
        ForeignKey("finance_intake_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(64), nullable=False, index=True)
    actor_type = Column(String(24), nullable=False)
    actor_id = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user','agent','system')",
            name="ck_fin_intake_event_actor_type",
        ),
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_type = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False, default="pending", index=True)
    source_ref = Column(String(512), nullable=True)
    result_payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(String(255), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("actor_user_id", "endpoint", "idempotency_key", name="uq_idempotency_scope"),)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    topic = Column(String(128), nullable=False, index=True)
    aggregate_type = Column(String(64), nullable=False)
    aggregate_id = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


Index("ix_budget_line_version_category", BudgetLine.budget_version_id, BudgetLine.category)
Index("ix_reimbursement_project_status", Reimbursement.project_id, Reimbursement.status)
Index("ix_approval_task_assignee_status", ApprovalTask.assignee_user_id, ApprovalTask.status)
Index("ix_bank_transaction_match", BankTransaction.amount, BankTransaction.transaction_date, BankTransaction.status)
Index("ix_fin_intake_source_created", FinanceIntakeJob.source_channel, FinanceIntakeJob.created_at)
Index("ix_fin_intake_status_created", FinanceIntakeJob.status, FinanceIntakeJob.created_at)
Index("ix_fin_intake_event_job_created", FinanceIntakeEvent.job_id, FinanceIntakeEvent.created_at)
