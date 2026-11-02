"""Add the isolated, PostgreSQL-only second-brain authority (SB1)."""
from alembic import op
from models.knowledge_schema_v1 import metadata

revision = "20261006_knowledge_domain"
down_revision = "20260925_cluster_inventory"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Second-brain authority requires PostgreSQL")
    # Explicit migration only; partial/existing schemas fail instead of silently drifting.
    metadata.create_all(bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Knowledge data must be exported and reviewed before destructive removal")
