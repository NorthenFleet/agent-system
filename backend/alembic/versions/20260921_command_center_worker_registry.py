"""Add Command Center worker liveness registry.

Revision ID: 20260921_worker_registry
Revises: 20260920_langgraph_pg
"""

from alembic import op


revision = "20260921_worker_registry"
down_revision = "20260920_langgraph_pg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS command_center_workers (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL DEFAULT 'orchestrator',
            state TEXT NOT NULL DEFAULT 'running',
            started_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            stopped_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_command_center_workers_live "
        "ON command_center_workers(state, last_seen_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS command_center_workers")
