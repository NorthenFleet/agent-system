# V2 Models

# Import shared-Base model modules so SQLite development and Alembic metadata
# see the same collaboration tables as PostgreSQL production.
from models import writing_collaboration  # noqa: F401,E402
from models import cluster_inventory  # noqa: F401,E402
