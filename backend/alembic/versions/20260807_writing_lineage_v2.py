"""Complete deployed writing revision lineage repair.

Revision ID: 20260807_writing_lineage_v2
Revises: 20260807_writing_lineage
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_writing_lineage_v2"
down_revision = "20260807_writing_lineage"
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
