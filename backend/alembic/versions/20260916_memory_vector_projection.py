"""Create the rebuildable approved-memory vector projection.

Revision ID: 20260916_memory_vector
Revises: 20260810_auth_login_toggle
"""

from alembic import op


revision = "20260916_memory_vector"
down_revision = "20260810_auth_login_toggle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS approved_memory_vectors (
            source_ref TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            user_id TEXT NOT NULL,
            project_id TEXT NOT NULL DEFAULT '',
            agent_id TEXT NOT NULL DEFAULT '',
            importance TEXT NOT NULL DEFAULT 'normal',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL DEFAULT 'active',
            content_hash TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_dimension INTEGER NOT NULL,
            embedding vector(768) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            memory_updated_at TIMESTAMPTZ,
            indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_approved_memory_vectors_scope
        ON approved_memory_vectors(user_id, project_id, agent_id, status)
        """
    )


def downgrade() -> None:
    # This table is a rebuildable projection. The vector extension can be shared
    # by other features, so downgrading must not remove the extension itself.
    op.execute("DROP TABLE IF EXISTS approved_memory_vectors")
