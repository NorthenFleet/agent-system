"""Add audited finance intake jobs in read-only shadow mode.

Revision ID: 20260807_finance_intake_shadow
Revises: 20260807_writing_lineage_v3
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_finance_intake_shadow"
down_revision = "20260807_writing_lineage_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_intake_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("command_message_id", sa.String(length=64), nullable=False),
        sa.Column("external_message_id", sa.String(length=200), nullable=True),
        sa.Column("source_channel", sa.String(length=32), nullable=False),
        sa.Column("source_account_id", sa.String(length=64), nullable=False, server_default="soundwave"),
        sa.Column("external_conversation_id", sa.String(length=255), nullable=False),
        sa.Column("external_user_id", sa.String(length=200), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("target_agent_id", sa.String(length=64), nullable=False, server_default="soundwave"),
        sa.Column("operation_type", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_metadata", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False, server_default="shadow"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("normalized_payload", sa.JSON(), nullable=False),
        sa.Column("shadow_snapshot", sa.JSON(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("reviewer_report", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('shadow','controlled_write')", name="ck_fin_intake_mode"),
        sa.CheckConstraint(
            "status IN ('received','shadow_read','awaiting_extraction','extracted',"
            "'needs_review','validated','approved','committed','rejected','failed','cancelled')",
            name="ck_fin_intake_status",
        ),
        sa.CheckConstraint(
            "operation_type IN ('reimbursement','invoice','budget','payment',"
            "'reconciliation','query','unknown')",
            name="ck_fin_intake_operation",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_intake_jobs_command_message_id", "finance_intake_jobs", ["command_message_id"], unique=True)
    op.create_index("ix_finance_intake_jobs_external_message_id", "finance_intake_jobs", ["external_message_id"])
    op.create_index("ix_finance_intake_jobs_source_channel", "finance_intake_jobs", ["source_channel"])
    op.create_index("ix_finance_intake_jobs_source_account_id", "finance_intake_jobs", ["source_account_id"])
    op.create_index("ix_finance_intake_jobs_requested_by_user_id", "finance_intake_jobs", ["requested_by_user_id"])
    op.create_index("ix_finance_intake_jobs_target_agent_id", "finance_intake_jobs", ["target_agent_id"])
    op.create_index("ix_finance_intake_jobs_operation_type", "finance_intake_jobs", ["operation_type"])
    op.create_index("ix_finance_intake_jobs_mode", "finance_intake_jobs", ["mode"])
    op.create_index("ix_finance_intake_jobs_status", "finance_intake_jobs", ["status"])
    op.create_index("ix_finance_intake_jobs_created_at", "finance_intake_jobs", ["created_at"])
    op.create_index("ix_fin_intake_source_created", "finance_intake_jobs", ["source_channel", "created_at"])
    op.create_index("ix_fin_intake_status_created", "finance_intake_jobs", ["status", "created_at"])

    op.create_table(
        "finance_intake_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user','agent','system')",
            name="ck_fin_intake_event_actor_type",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["finance_intake_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_intake_events_job_id", "finance_intake_events", ["job_id"])
    op.create_index("ix_finance_intake_events_event_type", "finance_intake_events", ["event_type"])
    op.create_index("ix_finance_intake_events_created_at", "finance_intake_events", ["created_at"])
    op.create_index("ix_fin_intake_event_job_created", "finance_intake_events", ["job_id", "created_at"])


def downgrade() -> None:
    op.drop_table("finance_intake_events")
    op.drop_table("finance_intake_jobs")
