"""add automation_rules and automation_rule_executions tables

Revision ID: add_automation_tables_s5p6
Revises: add_perf_indexes_s5p4
Create Date: 2026-07-09 14:17:00

Sprint 5 P6: Automation rule engine — tables for rule definitions and execution history.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_automation_tables_s5p6'
down_revision: Union[str, Sequence[str], None] = 'add_perf_indexes_s5p4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create automation_rules and automation_rule_executions tables."""
    op.create_table(
        'automation_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('trigger', sa.JSON(), nullable=False),
        sa.Column('actions', sa.JSON(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_automation_rules_is_active'), 'automation_rules', ['is_active'])
    op.create_index(op.f('ix_automation_rules_priority'), 'automation_rules', ['priority'])

    op.create_table(
        'automation_rule_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('trigger_type', sa.String(length=32), nullable=False),
        sa.Column('trigger_payload', sa.JSON(), nullable=True),
        sa.Column('action_results', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='success'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['rule_id'], ['automation_rules.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_automation_rule_executions_rule_id'), 'automation_rule_executions', ['rule_id'])
    op.create_index(op.f('ix_automation_rule_executions_trigger_type'), 'automation_rule_executions', ['trigger_type'])
    op.create_index(op.f('ix_automation_rule_executions_status'), 'automation_rule_executions', ['status'])
    op.create_index(op.f('ix_automation_rule_executions_executed_at'), 'automation_rule_executions', ['executed_at'])


def downgrade() -> None:
    """Drop automation_rule_executions and automation_rules tables."""
    op.drop_index(op.f('ix_automation_rule_executions_executed_at'), table_name='automation_rule_executions')
    op.drop_index(op.f('ix_automation_rule_executions_status'), table_name='automation_rule_executions')
    op.drop_index(op.f('ix_automation_rule_executions_trigger_type'), table_name='automation_rule_executions')
    op.drop_index(op.f('ix_automation_rule_executions_rule_id'), table_name='automation_rule_executions')
    op.drop_table('automation_rule_executions')
    op.drop_index(op.f('ix_automation_rules_priority'), table_name='automation_rules')
    op.drop_index(op.f('ix_automation_rules_is_active'), table_name='automation_rules')
    op.drop_table('automation_rules')
