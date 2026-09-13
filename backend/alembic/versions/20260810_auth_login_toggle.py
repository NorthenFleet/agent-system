"""Add database-backed login policy.

Revision ID: 20260810_auth_login_toggle
Revises: 20260810_gap_routing
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20260810_auth_login_toggle"
down_revision = "20260810_gap_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    settings = op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        settings,
        [{
            "key": "auth.login_enabled",
            "value": {"enabled": False},
            "description": "Whether dashboard users must authenticate before accessing modules",
            "updated_by": None,
            "created_at": now,
            "updated_at": now,
        }],
    )


def downgrade() -> None:
    op.drop_table("system_settings")
