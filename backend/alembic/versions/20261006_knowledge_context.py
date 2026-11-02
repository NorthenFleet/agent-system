"""SB3 shadow context snapshots in PostgreSQL."""
from alembic import op
from models.knowledge_context_v3 import metadata
revision = '20261006_knowledge_context'
down_revision = '20261006_knowledge_projection'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        raise RuntimeError('Knowledge contexts require PostgreSQL')
    metadata.create_all(bind, checkfirst=False)


def downgrade():
    raise RuntimeError('Context snapshots require an explicit retention/export decision')
