"""Durable projection leases and receipts, additive SB2 migration."""
from alembic import op
from models.knowledge_projection_v2 import metadata
revision = '20261006_knowledge_projection'
down_revision = '20261006_knowledge_domain'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        raise RuntimeError('Knowledge projection requires PostgreSQL')
    metadata.create_all(bind, checkfirst=False)


def downgrade():
    raise RuntimeError('Projection receipts must be preserved for reconciliation')
