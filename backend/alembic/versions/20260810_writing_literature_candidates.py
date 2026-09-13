"""Persist immutable literature candidate artifacts.

Revision ID: 20260810_writing_candidates
Revises: 20260810_writing_literature
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_writing_candidates"
down_revision = "20260810_writing_literature"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "writing_research_iterations",
        sa.Column("candidate_payload", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "writing_research_iterations",
        sa.Column("candidate_artifact_path", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("writing_research_iterations", "candidate_artifact_path")
    op.drop_column("writing_research_iterations", "candidate_payload")
