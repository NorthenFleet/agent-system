import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine


def test_sparse_revision_lineage_uses_previous_existing_revision():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260807_writing_lineage_v3.py"
    )
    spec = importlib.util.spec_from_file_location("writing_lineage_v3", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE writing_document_versions (
                project_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_revision INTEGER NOT NULL,
                parent_revision INTEGER NOT NULL
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO writing_document_versions VALUES
                ('project-1', 'document-1', 1, 0),
                ('project-1', 'document-1', 3, 2),
                ('project-1', 'document-1', 8, 7),
                ('project-1', 'document-2', 4, 3)
        """)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.exec_driver_sql("""
            SELECT document_id, document_revision, parent_revision
            FROM writing_document_versions
            ORDER BY document_id, document_revision
        """).all()

    assert rows == [
        ("document-1", 1, 0),
        ("document-1", 3, 1),
        ("document-1", 8, 3),
        ("document-2", 4, 0),
    ]
