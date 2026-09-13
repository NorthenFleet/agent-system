"""Add structured diagram workbench persistence.

Revision ID: 20260809_writing_diagram_workbench
Revises: 20260808_writing_workbench_v2
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_diagram_workbench"
down_revision = "20260808_writing_workbench_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_diagram_states",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("diagram_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("diagram_type", sa.String(48), nullable=False, server_default="flowchart"),
        sa.Column("theme_id", sa.String(48), nullable=False, server_default="academic"),
        sa.Column("page_settings", sa.JSON(), nullable=False),
        sa.Column("cells", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_id", name="uq_writing_diagram_state"),
    )
    op.create_index("ix_writing_diagram_states_project_id", "writing_diagram_states", ["project_id"])
    op.create_index("ix_writing_diagram_states_document_id", "writing_diagram_states", ["document_id"])

    op.create_table(
        "writing_diagram_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("diagram_revision", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(160), nullable=False, server_default=""),
        sa.Column("reason", sa.String(40), nullable=False, server_default="checkpoint"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False, server_default="human"),
        sa.Column("actor_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id", "document_id", "diagram_revision",
            name="uq_writing_diagram_version_revision",
        ),
    )
    op.create_index("ix_writing_diagram_versions_project_id", "writing_diagram_versions", ["project_id"])
    op.create_index("ix_writing_diagram_versions_document_id", "writing_diagram_versions", ["document_id"])

    op.create_table(
        "writing_diagram_ai_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(96), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False, server_default="ultra-magnus"),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("base_diagram_revision", sa.Integer(), nullable=False),
        sa.Column("target_cell_ids", sa.JSON(), nullable=False),
        sa.Column("target_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "project_id", "document_id", "client_request_id",
            name="uq_writing_diagram_ai_job_client_request",
        ),
    )
    op.create_index("ix_writing_diagram_ai_jobs_project_id", "writing_diagram_ai_jobs", ["project_id"])
    op.create_index("ix_writing_diagram_ai_jobs_document_id", "writing_diagram_ai_jobs", ["document_id"])
    op.create_index("ix_writing_diagram_ai_jobs_status", "writing_diagram_ai_jobs", ["status"])

    op.create_table(
        "writing_diagram_ai_proposals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("base_diagram_revision", sa.Integer(), nullable=False),
        sa.Column("base_cell_revisions", sa.JSON(), nullable=False),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["writing_diagram_ai_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_writing_diagram_ai_proposals_job_id", "writing_diagram_ai_proposals", ["job_id"])
    op.create_index("ix_writing_diagram_ai_proposals_project_id", "writing_diagram_ai_proposals", ["project_id"])
    op.create_index("ix_writing_diagram_ai_proposals_document_id", "writing_diagram_ai_proposals", ["document_id"])
    op.create_index("ix_writing_diagram_ai_proposals_status", "writing_diagram_ai_proposals", ["status"])
    op.create_index("ix_writing_diagram_ai_proposals_risk_level", "writing_diagram_ai_proposals", ["risk_level"])

    op.create_table(
        "writing_diagram_references",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("diagram_document_id", sa.String(64), nullable=False),
        sa.Column("diagram_revision", sa.Integer(), nullable=False),
        sa.Column("target_document_id", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(24), nullable=False),
        sa.Column("target_section_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("target_slide", sa.Integer(), nullable=True),
        sa.Column("export_format", sa.String(16), nullable=False, server_default="svg"),
        sa.Column("crop_or_viewbox", sa.JSON(), nullable=False),
        sa.Column("caption", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="current"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "diagram_document_id", "diagram_revision", "target_document_id",
            "target_section_id", "target_slide",
            name="uq_writing_diagram_reference_target",
        ),
    )
    op.create_index("ix_writing_diagram_references_project_id", "writing_diagram_references", ["project_id"])
    op.create_index("ix_writing_diagram_references_diagram_document_id", "writing_diagram_references", ["diagram_document_id"])
    op.create_index("ix_writing_diagram_references_target_document_id", "writing_diagram_references", ["target_document_id"])
    op.create_index("ix_writing_diagram_references_status", "writing_diagram_references", ["status"])


def downgrade() -> None:
    op.drop_table("writing_diagram_references")
    op.drop_table("writing_diagram_ai_proposals")
    op.drop_table("writing_diagram_ai_jobs")
    op.drop_table("writing_diagram_versions")
    op.drop_table("writing_diagram_states")
