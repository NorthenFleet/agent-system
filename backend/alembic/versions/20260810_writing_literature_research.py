"""Add evidence-aware literature research contracts.

Revision ID: 20260810_writing_literature
Revises: 20260809_diagram_workbench
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_writing_literature"
down_revision = "20260809_diagram_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("writing_claims", sa.Column("claim_key", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("writing_claims", sa.Column("claim_fingerprint", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("writing_claims", sa.Column("rhetorical_role", sa.String(length=24), nullable=False, server_default="fact"))
    op.add_column("writing_claims", sa.Column("evidence_policy", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("writing_claims", sa.Column("temporal_scope", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("writing_claims", sa.Column("geographic_scope", sa.String(length=24), nullable=False, server_default="global"))
    op.add_column(
        "writing_claims",
        sa.Column(
            "supersedes_claim_id",
            sa.String(length=64),
            sa.ForeignKey("writing_claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    for column in (
        "claim_key",
        "claim_fingerprint",
        "rhetorical_role",
        "geographic_scope",
        "supersedes_claim_id",
    ):
        op.create_index(f"ix_writing_claims_{column}", "writing_claims", [column])

    op.create_table(
        "writing_research_iterations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("writing_jarvis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_no", sa.Integer(), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("base_section_sha256", sa.String(length=64), nullable=False),
        sa.Column("candidate_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="baseline"),
        sa.Column(
            "parent_iteration_id",
            sa.String(length=64),
            sa.ForeignKey("writing_research_iterations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("change_set_id", sa.String(length=64), sa.ForeignKey("writing_change_sets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "iteration_no", name="uq_writing_research_iteration_run_no"),
    )
    for column in ("project_id", "document_id", "run_id", "status", "parent_iteration_id"):
        op.create_index(f"ix_writing_research_iterations_{column}", "writing_research_iterations", [column])

    op.create_table(
        "writing_retrieval_refs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("writing_jarvis_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("iteration_id", sa.String(length=64), sa.ForeignKey("writing_research_iterations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("provider_record_id", sa.String(length=200), nullable=False),
        sa.Column("query_id", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("query_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.Text(), nullable=False, server_default=""),
        sa.Column("doi", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("abstract_snapshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata_sha256", sa.String(length=64), nullable=False),
        sa.Column("access_status", sa.String(length=24), nullable=False, server_default="metadata_only"),
        sa.Column("screening_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("screening_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "canonical_ref_id",
            sa.String(length=64),
            sa.ForeignKey("writing_retrieval_refs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            "provider",
            "provider_record_id",
            "metadata_sha256",
            name="uq_writing_retrieval_identity",
        ),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            "idempotency_key",
            name="uq_writing_retrieval_idempotency",
        ),
    )
    for column in (
        "project_id",
        "document_id",
        "document_revision",
        "run_id",
        "iteration_id",
        "provider",
        "query_id",
        "year",
        "doi",
        "access_status",
        "screening_status",
        "canonical_ref_id",
    ):
        op.create_index(f"ix_writing_retrieval_refs_{column}", "writing_retrieval_refs", [column])

    evidence_columns = (
        sa.Column("evidence_kind", sa.String(length=24), nullable=False, server_default="simulation"),
        sa.Column("source_quality", sa.String(length=24), nullable=False, server_default="internal"),
        sa.Column("support_role", sa.String(length=24), nullable=False, server_default="supports"),
        sa.Column("directness", sa.String(length=24), nullable=False, server_default="direct"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("license_or_access", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "retrieval_ref_id",
            sa.String(length=64),
            sa.ForeignKey("writing_retrieval_refs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("locator", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("excerpt_sha256", sa.String(length=64), nullable=False, server_default=""),
    )
    for column in evidence_columns:
        op.add_column("writing_evidence_refs", column)
    for column in ("evidence_kind", "source_quality", "support_role", "directness", "retrieval_ref_id"):
        op.create_index(f"ix_writing_evidence_refs_{column}", "writing_evidence_refs", [column])

    op.create_table(
        "writing_research_run_scopes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("writing_jarvis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("claim_id", sa.String(length=64), sa.ForeignKey("writing_claims.id", ondelete="CASCADE"), nullable=True),
        sa.Column("gap_id", sa.String(length=64), sa.ForeignKey("writing_evidence_gaps.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scope_role", sa.String(length=24), nullable=False, server_default="target"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "section_id", "claim_id", "gap_id", name="uq_writing_research_run_scope"),
    )
    for column in ("run_id", "section_id", "claim_id", "gap_id", "scope_role"):
        op.create_index(f"ix_writing_research_run_scopes_{column}", "writing_research_run_scopes", [column])

    op.create_table(
        "writing_research_evaluations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("iteration_id", sa.String(length=64), sa.ForeignKey("writing_research_iterations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluator_version", sa.String(length=48), nullable=False),
        sa.Column("hard_gates", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("dimension_scores", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("total_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("baseline_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "iteration_id",
            "evaluator_version",
            "input_sha256",
            name="uq_writing_research_evaluation_input",
        ),
    )
    op.create_index("ix_writing_research_evaluations_iteration_id", "writing_research_evaluations", ["iteration_id"])
    op.create_index("ix_writing_research_evaluations_decision", "writing_research_evaluations", ["decision"])

    op.create_table(
        "writing_screening_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("retrieval_ref_id", sa.String(length=64), sa.ForeignKey("writing_retrieval_refs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("actor_type", sa.String(length=16), nullable=False, server_default="human"),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "retrieval_ref_id",
            "idempotency_key",
            name="uq_writing_screening_decision_idempotency",
        ),
    )
    op.create_index("ix_writing_screening_decisions_retrieval_ref_id", "writing_screening_decisions", ["retrieval_ref_id"])
    op.create_index("ix_writing_screening_decisions_decision", "writing_screening_decisions", ["decision"])


def downgrade() -> None:
    op.drop_table("writing_screening_decisions")
    op.drop_table("writing_research_evaluations")
    op.drop_table("writing_research_run_scopes")

    for column in ("evidence_kind", "source_quality", "support_role", "directness", "retrieval_ref_id"):
        op.drop_index(f"ix_writing_evidence_refs_{column}", table_name="writing_evidence_refs")
    for column in (
        "excerpt_sha256",
        "locator",
        "retrieval_ref_id",
        "license_or_access",
        "acquired_at",
        "published_at",
        "directness",
        "support_role",
        "source_quality",
        "evidence_kind",
    ):
        op.drop_column("writing_evidence_refs", column)

    op.drop_table("writing_retrieval_refs")
    op.drop_table("writing_research_iterations")

    for column in (
        "claim_key",
        "claim_fingerprint",
        "rhetorical_role",
        "geographic_scope",
        "supersedes_claim_id",
    ):
        op.drop_index(f"ix_writing_claims_{column}", table_name="writing_claims")
    for column in (
        "supersedes_claim_id",
        "geographic_scope",
        "temporal_scope",
        "evidence_policy",
        "rhetorical_role",
        "claim_fingerprint",
        "claim_key",
    ):
        op.drop_column("writing_claims", column)
