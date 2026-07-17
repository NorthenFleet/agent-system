"""add performance indexes

Revision ID: add_perf_indexes
Revises: 96c71f1bc6c6
Create Date: 2026-07-09

Performance indexes for Sprint 5 P4 optimization.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_perf_indexes'
down_revision: Union[str, None] = '96c71f1bc6c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create performance indexes."""
    # tasks table indexes
    op.create_index('ix_tasks_assignee', 'tasks', ['assignee'], if_not_exists=True)
    op.create_index('ix_tasks_status', 'tasks', ['status'], if_not_exists=True)
    op.create_index('ix_tasks_sprint_status', 'tasks', ['sprint', 'status'], if_not_exists=True)
    op.create_index('ix_tasks_created_at', 'tasks', ['created_at'], if_not_exists=True)

    # agent_heartbeats table indexes
    op.create_index('ix_heartbeats_agent_id', 'agent_heartbeats', ['agent_id'], if_not_exists=True)
    op.create_index('ix_heartbeats_agent_id_created', 'agent_heartbeats', ['agent_id', 'heartbeat_at'], if_not_exists=True)

    # activity_logs table indexes
    op.create_index('ix_activity_logs_agent_id', 'activity_logs', ['agent_id'], if_not_exists=True)
    op.create_index('ix_activity_logs_agent_id_created', 'activity_logs', ['agent_id', 'created_at'], if_not_exists=True)

    # Note: GIN index for title only applies to PostgreSQL
    # Check dialect before creating
    conn = op.get_bind()
    dialect_name = conn.dialect.name if hasattr(conn, 'dialect') else ''
    if dialect_name == 'postgresql':
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tasks_title_gin ON tasks USING gin(to_tsvector('english', title))"))


def downgrade() -> None:
    """Drop performance indexes."""
    op.drop_index('ix_tasks_assignee', table_name='tasks', if_exists=True)
    op.drop_index('ix_tasks_status', table_name='tasks', if_exists=True)
    op.drop_index('ix_tasks_sprint_status', table_name='tasks', if_exists=True)
    op.drop_index('ix_tasks_created_at', table_name='tasks', if_exists=True)

    op.drop_index('ix_heartbeats_agent_id', table_name='agent_heartbeats', if_exists=True)
    op.drop_index('ix_heartbeats_agent_id_created', table_name='agent_heartbeats', if_exists=True)

    op.drop_index('ix_activity_logs_agent_id', table_name='activity_logs', if_exists=True)
    op.drop_index('ix_activity_logs_agent_id_created', table_name='activity_logs', if_exists=True)

    conn = op.get_bind()
    dialect_name = conn.dialect.name if hasattr(conn, 'dialect') else ''
    if dialect_name == 'postgresql':
        op.execute(sa.text('DROP INDEX IF EXISTS ix_tasks_title_gin'))
