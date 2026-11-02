"""Real PG, random schema, no application startup or production database access.

Run with --confcutdir=tests/knowledge to exclude legacy app-wide fixtures.
"""
import importlib.util
import os
from pathlib import Path
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from services.knowledge.service import KnowledgeService


def migration(name):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def svc(tmp_path):
    url = os.getenv("KNOWLEDGE_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("KNOWLEDGE_TEST_DATABASE_URL is required for the real PostgreSQL gate")
    parsed = sa.engine.make_url(url)
    assert "test" in (parsed.database or ""), "explicit test database required"
    admin = sa.create_engine(url)
    schema = "sb_test_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = sa.create_engine(parsed.update_query_dict({"options": f"-csearch_path={schema}"}))
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration("20261006_knowledge_domain.py").upgrade()
                migration("20261006_knowledge_projection.py").upgrade()
                migration("20261006_knowledge_context.py").upgrade()
                migration("20261006_knowledge_operations.py").upgrade()
        yield KnowledgeService(engine, tmp_path / "sources", project_check=lambda actor, pid: actor == "owner" and pid == "project-a")
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
