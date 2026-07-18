"""Align legacy PostgreSQL platform tables with the current ORM metadata."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260718_platform_compat"
down_revision = "20260718_finance_prod"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if "feature_modules" in sa.inspect(bind).get_table_names():
        columns = _columns("feature_modules")
        if "route_path" not in columns:
            op.add_column("feature_modules", sa.Column("route_path", sa.String(128), nullable=True))
            op.execute(sa.text("UPDATE feature_modules SET route_path = '/' || module_key WHERE route_path IS NULL"))
        if "updated_at" not in columns:
            op.add_column("feature_modules", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
            op.execute(sa.text("UPDATE feature_modules SET updated_at = created_at WHERE updated_at IS NULL"))
    if "user_feature_modules" in sa.inspect(bind).get_table_names():
        columns = _columns("user_feature_modules")
        if "can_manage" not in columns:
            op.add_column("user_feature_modules", sa.Column("can_manage", sa.Boolean(), nullable=True))
            if "can_edit" in columns:
                op.execute(sa.text("UPDATE user_feature_modules SET can_manage = can_edit WHERE can_manage IS NULL"))
            else:
                op.execute(sa.text("UPDATE user_feature_modules SET can_manage = false WHERE can_manage IS NULL"))
        if "updated_at" not in columns:
            op.add_column("user_feature_modules", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
            op.execute(sa.text("UPDATE user_feature_modules SET updated_at = created_at WHERE updated_at IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "user_feature_modules" in tables:
        columns = _columns("user_feature_modules")
        if "updated_at" in columns:
            op.drop_column("user_feature_modules", "updated_at")
        if "can_manage" in columns:
            op.drop_column("user_feature_modules", "can_manage")
    if "feature_modules" in tables:
        columns = _columns("feature_modules")
        if "updated_at" in columns:
            op.drop_column("feature_modules", "updated_at")
        if "route_path" in columns:
            op.drop_column("feature_modules", "route_path")
