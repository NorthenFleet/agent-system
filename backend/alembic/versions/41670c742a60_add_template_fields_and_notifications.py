"""add template fields and notifications table

Revision ID: 41670c742a60
Revises: 914b10264808
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = '41670c742a60'
down_revision = '914b10264808'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── TaskTemplate 增强字段 ──
    op.add_column('task_templates', sa.Column('category', sa.String(64), nullable=True))
    op.create_index(
        op.f('ix_task_templates_category'), 'task_templates', ['category'], unique=False
    )
    op.add_column('task_templates', sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('task_templates', sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('task_templates', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # ── Notifications 表 ──
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.String(32), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=True, server_default=''),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source_id', sa.String(128), nullable=True),
        sa.Column('link', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_notifications_type'), 'notifications', ['type'], unique=False)
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notifications_is_read'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_type'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')

    op.drop_column('task_templates', 'updated_at')
    op.drop_column('task_templates', 'usage_count')
    op.drop_column('task_templates', 'is_system')
    op.drop_index(op.f('ix_task_templates_category'), table_name='task_templates')
    op.drop_column('task_templates', 'category')
