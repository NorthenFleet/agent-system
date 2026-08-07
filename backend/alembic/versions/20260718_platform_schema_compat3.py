"""Make legacy feature permission columns safe for current ORM writes."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260718_platform_compat3"
down_revision = "20260718_platform_compat2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "user_feature_modules" not in sa.inspect(bind).get_table_names():
        return

    columns = {item["name"] for item in sa.inspect(bind).get_columns("user_feature_modules")}
    if "can_manage" in columns:
        if "can_edit" in columns:
            op.execute(sa.text(
                "UPDATE user_feature_modules "
                "SET can_manage = COALESCE(can_manage, can_edit, false)"
            ))
        else:
            op.execute(sa.text(
                "UPDATE user_feature_modules SET can_manage = false WHERE can_manage IS NULL"
            ))
        op.alter_column(
            "user_feature_modules",
            "can_manage",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )

    if "can_edit" in columns:
        op.execute(sa.text(
            "UPDATE user_feature_modules "
            "SET can_edit = COALESCE(can_edit, can_manage, false)"
        ))
        op.alter_column(
            "user_feature_modules",
            "can_edit",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.false(),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "user_feature_modules" not in sa.inspect(bind).get_table_names():
        return

    columns = {item["name"] for item in sa.inspect(bind).get_columns("user_feature_modules")}
    if "can_edit" in columns:
        op.alter_column(
            "user_feature_modules",
            "can_edit",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=None,
        )
    if "can_manage" in columns:
        op.alter_column(
            "user_feature_modules",
            "can_manage",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
