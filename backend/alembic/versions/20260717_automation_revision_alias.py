"""Bridge the deployed automation revision name to the repository lineage.

Revision ID: add_automation_s5p6
Revises: add_automation_tables_s5p6
"""

revision = "add_automation_s5p6"
down_revision = "add_automation_tables_s5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The deployed database already contains the automation tables.  This
    # revision only reconciles the historical revision identifier.
    pass


def downgrade() -> None:
    pass
