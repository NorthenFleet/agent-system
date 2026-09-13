"""Route evidence gaps by literature and experiment type.

Revision ID: 20260810_gap_routing
Revises: 20260810_writing_candidates
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_gap_routing"
down_revision = "20260810_writing_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "writing_evidence_gaps",
        sa.Column("gap_type", sa.String(length=16), nullable=False, server_default="experiment"),
    )
    op.create_index(
        "ix_writing_evidence_gaps_gap_type",
        "writing_evidence_gaps",
        ["gap_type"],
    )
    op.execute(
        """
        UPDATE writing_evidence_gaps
        SET gap_type = 'literature'
        WHERE CAST(research_matrix AS TEXT) LIKE '%writing.literature%'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_writing_evidence_gaps_gap_type", table_name="writing_evidence_gaps")
    op.drop_column("writing_evidence_gaps", "gap_type")
