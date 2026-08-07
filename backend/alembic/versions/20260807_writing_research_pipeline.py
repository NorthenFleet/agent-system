"""Add evidence-aware writing and Jarvis run contracts.

Revision ID: 20260807_writing_research
Revises: 20260806_writing_collab
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_writing_research"
down_revision = "20260806_writing_collab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("writing_document_states", sa.Column("approved_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("writing_document_states", sa.Column("published_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("writing_document_versions", sa.Column("parent_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("writing_document_versions", sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="working"))
    op.create_index("ix_writing_document_versions_lifecycle_status", "writing_document_versions", ["lifecycle_status"])
    op.add_column("writing_ai_jobs", sa.Column("evidence_ref_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("writing_ai_jobs", sa.Column("risk_policy", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("writing_ai_proposals", sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"))
    op.add_column("writing_ai_proposals", sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("writing_ai_proposals", sa.Column("evidence_ref_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("writing_ai_proposals", sa.Column("concurrency_status", sa.String(length=16), nullable=False, server_default="unchanged"))
    op.create_index("ix_writing_ai_proposals_risk_level", "writing_ai_proposals", ["risk_level"])

    op.create_table(
        "writing_claims",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.String(length=128), nullable=False),
        sa.Column("block_id", sa.String(length=96), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("minimum_evidence_level", sa.String(length=16), nullable=False),
        sa.Column("evidence_status", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "document_id", "document_revision", "section_id", "block_id", "evidence_status", "status"):
        op.create_index(f"ix_writing_claims_{column}", "writing_claims", [column])

    op.create_table(
        "writing_evidence_refs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=48), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("perspective_scope", sa.String(length=64), nullable=False),
        sa.Column("evidence_level", sa.String(length=16), nullable=False),
        sa.Column("allowed_claim_scope", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_id", "source_system", "source_record_id", "artifact_sha256", name="uq_writing_evidence_identity"),
    )
    for column in ("project_id", "document_id", "evidence_level"):
        op.create_index(f"ix_writing_evidence_refs_{column}", "writing_evidence_refs", [column])

    op.create_table(
        "writing_evidence_bindings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("claim_id", sa.String(length=64), sa.ForeignKey("writing_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_ref_id", sa.String(length=64), sa.ForeignKey("writing_evidence_refs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("support_scope", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("claim_id", "evidence_ref_id", name="uq_writing_claim_evidence"),
    )
    op.create_index("ix_writing_evidence_bindings_claim_id", "writing_evidence_bindings", ["claim_id"])
    op.create_index("ix_writing_evidence_bindings_evidence_ref_id", "writing_evidence_bindings", ["evidence_ref_id"])

    op.create_table(
        "writing_evidence_gaps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("claim_id", sa.String(length=64), sa.ForeignKey("writing_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("required_level", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("research_matrix", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("dispatched_run_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("claim_id", "project_id", "document_id", "status"):
        op.create_index(f"ix_writing_evidence_gaps_{column}", "writing_evidence_gaps", [column])

    op.create_table(
        "writing_change_sets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("result_revision", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), sa.ForeignKey("writing_ai_proposals.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("evidence_ref_ids", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("approval_policy", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_id", "idempotency_key", name="uq_writing_changeset_idempotency"),
    )
    for column in ("project_id", "document_id", "risk_level", "status"):
        op.create_index(f"ix_writing_change_sets_{column}", "writing_change_sets", [column])

    op.create_table(
        "writing_word_imports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mapping_status", sa.String(length=24), nullable=False),
        sa.Column("change_set_id", sa.String(length=64), sa.ForeignKey("writing_change_sets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "document_id", "mapping_status"):
        op.create_index(f"ix_writing_word_imports_{column}", "writing_word_imports", [column])

    op.create_table(
        "writing_word_releases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("template_sha256", sa.String(length=64), nullable=False),
        sa.Column("docx_path", sa.Text(), nullable=False),
        sa.Column("docx_sha256", sa.String(length=64), nullable=False),
        sa.Column("pdf_path", sa.Text(), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("field_refresh_status", sa.String(length=24), nullable=False),
        sa.Column("page_check", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_id", "idempotency_key", name="uq_writing_release_idempotency"),
    )
    for column in ("project_id", "document_id", "document_revision", "status"):
        op.create_index(f"ix_writing_word_releases_{column}", "writing_word_releases", [column])

    op.create_table(
        "writing_jarvis_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("approval_reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_cursor", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "document_id", "idempotency_key", name="uq_writing_jarvis_run_idempotency"),
    )
    for column in ("project_id", "document_id", "run_type", "status", "lease_expires_at"):
        op.create_index(f"ix_writing_jarvis_runs_{column}", "writing_jarvis_runs", [column])

    op.create_table(
        "writing_jarvis_steps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("writing_jarvis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("compensation", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "step_key", name="uq_writing_jarvis_step"),
    )
    op.create_index("ix_writing_jarvis_steps_run_id", "writing_jarvis_steps", ["run_id"])
    op.create_index("ix_writing_jarvis_steps_status", "writing_jarvis_steps", ["status"])


def downgrade() -> None:
    op.drop_table("writing_jarvis_steps")
    op.drop_table("writing_jarvis_runs")
    op.drop_table("writing_word_releases")
    op.drop_table("writing_word_imports")
    op.drop_table("writing_change_sets")
    op.drop_table("writing_evidence_gaps")
    op.drop_table("writing_evidence_bindings")
    op.drop_table("writing_evidence_refs")
    op.drop_table("writing_claims")
    op.drop_index("ix_writing_ai_proposals_risk_level", table_name="writing_ai_proposals")
    op.drop_column("writing_ai_proposals", "concurrency_status")
    op.drop_column("writing_ai_proposals", "evidence_ref_ids")
    op.drop_column("writing_ai_proposals", "approval_required")
    op.drop_column("writing_ai_proposals", "risk_level")
    op.drop_column("writing_ai_jobs", "risk_policy")
    op.drop_column("writing_ai_jobs", "evidence_ref_ids")
    op.drop_index("ix_writing_document_versions_lifecycle_status", table_name="writing_document_versions")
    op.drop_column("writing_document_versions", "lifecycle_status")
    op.drop_column("writing_document_versions", "parent_revision")
    op.drop_column("writing_document_states", "published_revision")
    op.drop_column("writing_document_states", "approved_revision")
