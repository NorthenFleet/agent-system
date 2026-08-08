"""Add review-first invoice batch ingestion and OCR evidence tables.

Revision ID: 20260808_invoice_batch_ingestion
Revises: 20260807_payment_human_confirm
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_invoice_batch_ingestion"
down_revision = "20260807_payment_human_confirm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("intake_job_id", sa.String(length=36), nullable=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("source_channel", sa.String(length=24), nullable=False, server_default="web"),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_channel IN ('web','lark','watch_folder')",
            name="ck_invoice_batch_source_channel",
        ),
        sa.CheckConstraint(
            "status IN ('received','processing','review_required','completed','failed','cancelled')",
            name="ck_invoice_batch_status",
        ),
        sa.CheckConstraint(
            "total_count >= 0 AND processed_count >= 0 AND review_count >= 0 AND failed_count >= 0",
            name="ck_invoice_batch_counts",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["intake_job_id"], ["finance_intake_jobs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["finance_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref"),
    )
    op.create_index("ix_invoice_batches_project_id", "invoice_batches", ["project_id"])
    op.create_index("ix_invoice_batches_intake_job_id", "invoice_batches", ["intake_job_id"])
    op.create_index("ix_invoice_batches_period", "invoice_batches", ["period"])
    op.create_index("ix_invoice_batches_source_channel", "invoice_batches", ["source_channel"])
    op.create_index("ix_invoice_batches_status", "invoice_batches", ["status"])
    op.create_index("ix_invoice_batches_created_by", "invoice_batches", ["created_by"])
    op.create_index("ix_invoice_batches_created_at", "invoice_batches", ["created_at"])
    op.create_index("ix_invoice_batch_project_period", "invoice_batches", ["project_id", "period"])

    op.create_table(
        "invoice_ingest_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("formal_invoice_id", sa.String(length=36), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("preprocessed_object_key", sa.String(length=512), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("scan_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preprocessing_payload", sa.JSON(), nullable=False),
        sa.Column("extraction_payload", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_invoice_ingest_item_size"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_invoice_ingest_attempt_count"),
        sa.CheckConstraint(
            "status IN ('received','scanned','preprocessed','ocr_running','extracted',"
            "'needs_review','duplicate','failed','approved','committed')",
            name="ck_invoice_ingest_item_status",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["invoice_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["formal_invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("formal_invoice_id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("preprocessed_object_key"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_index("ix_invoice_ingest_items_batch_id", "invoice_ingest_items", ["batch_id"])
    op.create_index("ix_invoice_ingest_items_formal_invoice_id", "invoice_ingest_items", ["formal_invoice_id"])
    op.create_index("ix_invoice_ingest_items_sha256", "invoice_ingest_items", ["sha256"])
    op.create_index("ix_invoice_ingest_items_status", "invoice_ingest_items", ["status"])
    op.create_index("ix_invoice_ingest_items_created_at", "invoice_ingest_items", ["created_at"])
    op.create_index("ix_invoice_ingest_batch_status", "invoice_ingest_items", ["batch_id", "status"])

    op.create_table(
        "invoice_ocr_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("text_payload", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('success','failed','unavailable')", name="ck_invoice_ocr_run_status"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_invoice_ocr_run_duration"),
        sa.ForeignKeyConstraint(["item_id"], ["invoice_ingest_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "engine", name="uq_invoice_ocr_item_engine"),
    )
    op.create_index("ix_invoice_ocr_runs_item_id", "invoice_ocr_runs", ["item_id"])
    op.create_index("ix_invoice_ocr_runs_engine", "invoice_ocr_runs", ["engine"])
    op.create_index("ix_invoice_ocr_runs_status", "invoice_ocr_runs", ["status"])
    op.create_index("ix_invoice_ocr_runs_created_at", "invoice_ocr_runs", ["created_at"])

    op.create_table(
        "invoice_field_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("ocr_run_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0"),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("consensus_status", sa.String(length=24), nullable=False, server_default="single_source"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_invoice_field_confidence"),
        sa.CheckConstraint(
            "consensus_status IN ('agreed','single_source','conflict')",
            name="ck_invoice_field_consensus",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["invoice_ingest_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ocr_run_id"], ["invoice_ocr_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ocr_run_id", "field_name", name="uq_invoice_ocr_run_field"),
    )
    op.create_index("ix_invoice_field_candidates_item_id", "invoice_field_candidates", ["item_id"])
    op.create_index("ix_invoice_field_candidates_ocr_run_id", "invoice_field_candidates", ["ocr_run_id"])
    op.create_index("ix_invoice_field_candidates_field_name", "invoice_field_candidates", ["field_name"])
    op.create_index("ix_invoice_field_candidates_consensus_status", "invoice_field_candidates", ["consensus_status"])
    op.create_index("ix_invoice_field_item_name", "invoice_field_candidates", ["item_id", "field_name"])


def downgrade() -> None:
    op.drop_table("invoice_field_candidates")
    op.drop_table("invoice_ocr_runs")
    op.drop_table("invoice_ingest_items")
    op.drop_table("invoice_batches")
