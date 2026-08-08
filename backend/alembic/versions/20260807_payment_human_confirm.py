"""Add durable human confirmation evidence to payments and reconciliation.

Revision ID: 20260807_payment_human_confirm
Revises: 20260807_finance_intake_shadow
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_payment_human_confirm"
down_revision = "20260807_finance_intake_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("payments", sa.Column("confirmation_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_payments_confirmed_by_user_id_users",
        "payments",
        "users",
        ["confirmed_by_user_id"],
        ["id"],
    )
    op.add_column("reconciliation_matches", sa.Column("confirmation_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reconciliation_matches", "confirmation_note")
    op.drop_constraint("fk_payments_confirmed_by_user_id_users", "payments", type_="foreignkey")
    op.drop_column("payments", "confirmation_note")
    op.drop_column("payments", "confirmed_by_user_id")
