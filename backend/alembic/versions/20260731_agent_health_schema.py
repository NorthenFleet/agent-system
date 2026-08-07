"""Align the PostgreSQL agents table with the current health-service ORM."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260731_agent_health"
down_revision = "20260718_platform_compat3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agents" not in inspector.get_table_names():
        return

    columns = {item["name"] for item in inspector.get_columns("agents")}
    if "agent_id" not in columns:
        op.add_column("agents", sa.Column("agent_id", sa.String(length=64), nullable=True))
    if "current_task" not in columns:
        op.add_column("agents", sa.Column("current_task", sa.String(length=500), nullable=True))
    if "avatar_url" not in columns:
        op.add_column("agents", sa.Column("avatar_url", sa.String(length=500), nullable=True))
    if "last_heartbeat_at" not in columns:
        op.add_column("agents", sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True))

    op.execute(sa.text(
        "UPDATE agents SET agent_id = name "
        "WHERE agent_id IS NULL OR agent_id = ''"
    ))
    if "last_heartbeat" in columns:
        op.execute(sa.text(
            "UPDATE agents SET last_heartbeat_at = last_heartbeat "
            "WHERE last_heartbeat_at IS NULL AND last_heartbeat IS NOT NULL"
        ))

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("agents")}
    if "ix_agents_agent_id" not in indexes:
        op.create_index("ix_agents_agent_id", "agents", ["agent_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agents" not in inspector.get_table_names():
        return

    columns = {item["name"] for item in inspector.get_columns("agents")}
    indexes = {item["name"] for item in inspector.get_indexes("agents")}
    if "ix_agents_agent_id" in indexes:
        op.drop_index("ix_agents_agent_id", table_name="agents")
    for column in ["last_heartbeat_at", "avatar_url", "current_task", "agent_id"]:
        if column in columns:
            op.drop_column("agents", column)
