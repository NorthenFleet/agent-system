"""Complete legacy feature-permission column compatibility."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260718_platform_compat2"
down_revision = "20260718_platform_compat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "user_feature_modules" not in sa.inspect(bind).get_table_names():
        return
    columns = {item["name"] for item in sa.inspect(bind).get_columns("user_feature_modules")}
    if "granted_by" not in columns:
        op.add_column("user_feature_modules", sa.Column("granted_by", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if "user_feature_modules" in sa.inspect(bind).get_table_names():
        columns = {item["name"] for item in sa.inspect(bind).get_columns("user_feature_modules")}
        if "granted_by" in columns:
            op.drop_column("user_feature_modules", "granted_by")
