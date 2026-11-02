"""SB4 registered imports, memory proposals and maintenance receipts."""
from alembic import op
from models.knowledge_operations_v4 import metadata

revision = '20261006_knowledge_operations'
down_revision = '20261006_knowledge_context'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        raise RuntimeError('Knowledge operations require PostgreSQL')
    metadata.create_all(bind, checkfirst=False)


def downgrade():
    raise RuntimeError('Knowledge operations require an explicit retention/export decision')
