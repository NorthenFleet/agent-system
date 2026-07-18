"""Create the production project-finance domain.

Revision ID: 20260718_finance_prod
Revises: add_automation_s5p6, add_perf_indexes
"""
from __future__ import annotations

from alembic import op

from models.finance_models import Base


revision = "20260718_finance_prod"
down_revision = ("add_automation_s5p6", "add_perf_indexes")
branch_labels = None
depends_on = None


FINANCE_TABLES = (
    "finance_projects",
    "finance_user_roles",
    "finance_project_memberships",
    "fund_allocations",
    "budget_versions",
    "budget_lines",
    "budget_adjustments",
    "reimbursements",
    "invoices",
    "reimbursement_items",
    "budget_reservations",
    "invoice_attachments",
    "approval_workflow_definitions",
    "approval_workflow_steps",
    "approval_instances",
    "approval_tasks",
    "approval_events",
    "payments",
    "expense_records",
    "bank_statement_imports",
    "bank_transactions",
    "reconciliation_matches",
    "finance_audit_events",
    "import_jobs",
    "idempotency_records",
    "outbox_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in FINANCE_TABLES], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(FINANCE_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
