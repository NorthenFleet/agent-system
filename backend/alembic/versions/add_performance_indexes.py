"""add performance indexes

Revision ID: add_perf_indexes_s5p4
Revises: 41670c742a60
Create Date: 2026-07-09 12:00:00

Sprint 5 P4: Performance optimization — DB index additions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_perf_indexes_s5p4'
down_revision: Union[str, None] = '41670c742a60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes to hot-query columns."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    # ─── tasks 表 ───
    op.create_index('ix_tasks_assignee', 'tasks', ['assignee'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])
    op.create_index('ix_tasks_sprint', 'tasks', ['sprint'])
    op.create_index('ix_tasks_created_at', 'tasks', ['created_at'])
    op.create_index('ix_tasks_sprint_status', 'tasks', ['sprint', 'status'])

    # GIN index for full-text title search — PostgreSQL only
    if dialect == 'postgresql':
        op.execute(
            sa.text("CREATE INDEX ix_tasks_title_gin ON tasks USING gin(to_tsvector('simple', title))")
        )

    # ─── agent_heartbeats 表 ───
    op.create_index('ix_heartbeats_agent_id', 'agent_heartbeats', ['agent_id'])
    op.create_index('ix_heartbeats_agent_created', 'agent_heartbeats', ['agent_id', 'heartbeat_at'])

    # ─── activity_logs 表 ───
    op.create_index('ix_activity_logs_agent_id', 'activity_logs', ['agent_id'])
    op.create_index('ix_activity_logs_agent_created', 'activity_logs', ['agent_id', 'created_at'])


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    op.drop_index('ix_tasks_assignee', table_name='tasks')
    op.drop_index('ix_tasks_status', table_name='tasks')
    op.drop_index('ix_tasks_sprint', table_name='tasks')
    op.drop_index('ix_tasks_created_at', table_name='tasks')
    op.drop_index('ix_tasks_sprint_status', table_name='tasks')

    if dialect == 'postgresql':
        op.execute(sa.text('DROP INDEX IF EXISTS ix_tasks_title_gin'))

    op.drop_index('ix_heartbeats_agent_id', table_name='agent_heartbeats')
    op.drop_index('ix_heartbeats_agent_created', table_name='agent_heartbeats')

    op.drop_index('ix_activity_logs_agent_id', table_name='activity_logs')
    op.drop_index('ix_activity_logs_agent_created', table_name='activity_logs')
