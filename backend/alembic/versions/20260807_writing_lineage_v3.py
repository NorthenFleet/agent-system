"""Repair writing revision lineage for sparse histories.

Revision ID: 20260807_writing_lineage_v3
Revises: 20260807_writing_lineage_v2
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_writing_lineage_v3"
down_revision = "20260807_writing_lineage_v2"
branch_labels = None
depends_on = None


def _repair_to_previous_existing_revision() -> None:
    op.execute(sa.text("""
        UPDATE writing_document_versions
        SET parent_revision = COALESCE((
            SELECT MAX(previous.document_revision)
            FROM writing_document_versions AS previous
            WHERE previous.project_id = writing_document_versions.project_id
              AND previous.document_id = writing_document_versions.document_id
              AND previous.document_revision < writing_document_versions.document_revision
        ), 0)
    """))


def upgrade() -> None:
    _repair_to_previous_existing_revision()


def downgrade() -> None:
    _repair_to_previous_existing_revision()
