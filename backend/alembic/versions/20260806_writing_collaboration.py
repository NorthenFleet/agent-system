"""Add structured writing collaboration state.

Revision ID: 20260806_writing_collab
Revises: 20260731_agent_health
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_writing_collab"
down_revision = "20260731_agent_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_document_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_markdown_sha256", sa.String(length=64), nullable=False),
        sa.Column("projection_revision", sa.Integer(), nullable=False),
        sa.Column("projection_status", sa.String(length=24), nullable=False),
        sa.Column("projection_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_id", name="uq_writing_document_state"),
    )
    op.create_index("ix_writing_document_states_project_id", "writing_document_states", ["project_id"])
    op.create_index("ix_writing_document_states_document_id", "writing_document_states", ["document_id"])
    op.create_index(
        "ix_writing_document_state_projection",
        "writing_document_states",
        ["projection_status", "updated_at"],
    )

    op.create_table(
        "writing_document_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("markdown_snapshot", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            "document_revision",
            name="uq_writing_document_version_revision",
        ),
    )
    op.create_index("ix_writing_document_versions_project_id", "writing_document_versions", ["project_id"])
    op.create_index("ix_writing_document_versions_document_id", "writing_document_versions", ["document_id"])

    op.create_table(
        "writing_change_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("client_change_id", sa.String(length=96), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("before_sha256", sa.String(length=64), nullable=False),
        sa.Column("after_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            "client_change_id",
            name="uq_writing_change_client_id",
        ),
    )
    op.create_index("ix_writing_change_events_project_id", "writing_change_events", ["project_id"])
    op.create_index("ix_writing_change_events_document_id", "writing_change_events", ["document_id"])
    op.create_index("ix_writing_change_events_document_revision", "writing_change_events", ["document_revision"])

    op.create_table(
        "writing_ai_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("client_request_id", sa.String(length=96), nullable=False),
        sa.Column("section_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("base_document_revision", sa.Integer(), nullable=False),
        sa.Column("target_blocks", sa.JSON(), nullable=False),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            "client_request_id",
            name="uq_writing_ai_job_client_request",
        ),
    )
    op.create_index("ix_writing_ai_jobs_project_id", "writing_ai_jobs", ["project_id"])
    op.create_index("ix_writing_ai_jobs_document_id", "writing_ai_jobs", ["document_id"])
    op.create_index("ix_writing_ai_jobs_status", "writing_ai_jobs", ["status"])
    op.create_index("ix_writing_ai_jobs_lease_expires_at", "writing_ai_jobs", ["lease_expires_at"])

    op.create_table(
        "writing_ai_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("writing_ai_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("block_id", sa.String(length=96), nullable=False),
        sa.Column("operation_type", sa.String(length=24), nullable=False),
        sa.Column("base_block_revision", sa.Integer(), nullable=False),
        sa.Column("base_block_sha256", sa.String(length=64), nullable=False),
        sa.Column("replacement_markdown", sa.Text(), nullable=False),
        sa.Column("replacement_json", sa.JSON(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_writing_ai_proposals_job_id", "writing_ai_proposals", ["job_id"])
    op.create_index("ix_writing_ai_proposals_project_id", "writing_ai_proposals", ["project_id"])
    op.create_index("ix_writing_ai_proposals_document_id", "writing_ai_proposals", ["document_id"])
    op.create_index("ix_writing_ai_proposals_block_id", "writing_ai_proposals", ["block_id"])
    op.create_index("ix_writing_ai_proposals_status", "writing_ai_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("writing_ai_proposals")
    op.drop_table("writing_ai_jobs")
    op.drop_table("writing_change_events")
    op.drop_table("writing_document_versions")
    op.drop_table("writing_document_states")
