"""Repair historical writing revision parent lineage.

Revision ID: 20260807_writing_lineage
Revises: 20260807_writing_research
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_writing_lineage"
down_revision = "20260807_writing_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE writing_document_versions
        SET parent_revision = CASE
            WHEN document_revision > 1 THEN document_revision - 1
            ELSE 0
        END
    """))


def downgrade() -> None:
    op.execute(sa.text("UPDATE writing_document_versions SET parent_revision = 0"))
