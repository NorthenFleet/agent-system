"""Isolated PostgreSQL regression gate for cluster at-most-once WorkRuns."""

from __future__ import annotations

import importlib.util
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from repositories.command_center_repository import (
    PostgresCommandCenterRepository,
    _postgres_dsn,
)
from services.work_run_service import WorkRunIdempotencyConflict, WorkRunService

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:  # pragma: no cover - exercised only in environments without PG extras
    psycopg2 = None
    sql = None


POSTGRES_URL = os.getenv("WORK_RUN_POSTGRES_TEST_URL", "").strip()
SCHEMA_ISOLATION_CONFIRMED = (
    os.getenv("WORK_RUN_POSTGRES_TEST_ISOLATED_SCHEMA", "").strip().lower()
    in {"1", "true", "yes", "on"}
)


def _database_name(database_url: str) -> str:
    return urlsplit(database_url).path.strip("/").lower()


def _is_explicit_test_database(database_url: str) -> bool:
    name = _database_name(database_url)
    return any(token in name for token in ("test", "ci", "integration"))


pytestmark = pytest.mark.skipif(
    not POSTGRES_URL
    or not SCHEMA_ISOLATION_CONFIRMED
    or not _is_explicit_test_database(POSTGRES_URL)
    or psycopg2 is None,
    reason=(
        "requires an explicitly confirmed isolated PostgreSQL test database and "
        "WORK_RUN_POSTGRES_TEST_ISOLATED_SCHEMA=true"
    ),
)


def _load_work_run_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260919_work_run_postgres.py"
    )
    spec = importlib.util.spec_from_file_location(
        "cluster_work_run_postgres_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _url_for_schema(database_url: str, schema_name: str) -> str:
    parsed = urlsplit(database_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema_name}"
    scoped = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(query)}"
    return f"{scoped}#{parsed.fragment}" if parsed.fragment else scoped


@pytest.fixture
def isolated_postgres_work_run_service():
    schema_name = f"cluster_wrun_{uuid.uuid4().hex}"
    admin_connection = psycopg2.connect(_postgres_dsn(POSTGRES_URL))
    admin_connection.autocommit = True
    service = None
    try:
        with admin_connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))

        scoped_url = _url_for_schema(POSTGRES_URL, schema_name)
        engine = create_engine(scoped_url)
        try:
            migration = _load_work_run_migration()
            with engine.begin() as connection:
                assert (
                    connection.exec_driver_sql("SELECT current_schema()").scalar_one()
                    == schema_name
                )
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
        finally:
            engine.dispose()

        repository = PostgresCommandCenterRepository(
            scoped_url,
            pool_min_size=1,
            pool_max_size=32,
            pool_acquire_timeout_seconds=20,
        )
        service = WorkRunService(repository=repository)
        yield service
    finally:
        if service is not None:
            service.repository.close()
        with admin_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema_name)
                )
            )
        admin_connection.close()


def test_postgres_at_most_once_is_atomic_and_cannot_be_bypassed(
    isolated_postgres_work_run_service,
):
    service = isolated_postgres_work_run_service
    callers = 32
    barrier = threading.Barrier(callers)
    idempotency_key = f"cluster-postgres:{uuid.uuid4().hex}"
    request_binding = {
        "schema_version": "cluster-operation.v1",
        "request_id": "postgres-request-001",
        "node_id": "node-1",
        "tailscale_id": "nPostgresTest",
        "operation": "host.info",
        "timeout_seconds": 10,
    }

    def claim(index: int):
        barrier.wait(timeout=20)
        return service.claim_at_most_once(
            dispatch_id="cluster-postgres-operation",
            idempotency_key=idempotency_key,
            request_binding=request_binding,
            agent_id=f"postgres-worker-{index}",
            executor="cluster-readonly-v1",
            lease_seconds=300,
        )

    with ThreadPoolExecutor(max_workers=callers) as pool:
        results = list(pool.map(claim, range(callers)))

    assert sum(created for _run, created in results) == 1
    assert len({run["id"] for run, _created in results}) == 1
    original = results[0][0]
    with service.connect() as connection:
        ledger = connection.execute(
            "SELECT COUNT(*) AS count, MAX(attempt) AS max_attempt "
            "FROM work_runs WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
    assert ledger["count"] == 1
    assert ledger["max_attempt"] == 1

    replay, created = service.claim_at_most_once(
        dispatch_id="cluster-postgres-operation",
        idempotency_key=idempotency_key,
        request_binding={
            "timeout_seconds": 10,
            "operation": "host.info",
            "tailscale_id": "nPostgresTest",
            "node_id": "node-1",
            "request_id": "postgres-request-001",
            "schema_version": "cluster-operation.v1",
        },
        agent_id="postgres-replay-worker",
        executor="cluster-readonly-v1",
    )
    assert created is False
    assert replay["id"] == original["id"]

    with pytest.raises(WorkRunIdempotencyConflict, match="request binding"):
        service.claim_at_most_once(
            dispatch_id="cluster-postgres-operation",
            idempotency_key=idempotency_key,
            request_binding={**request_binding, "node_id": "node-2"},
            agent_id="postgres-conflicting-worker",
            executor="cluster-readonly-v1",
        )

    with pytest.raises(WorkRunIdempotencyConflict, match="reserved"):
        service.claim(
            dispatch_id="cluster-postgres-operation",
            idempotency_key=idempotency_key,
            agent_id="ordinary-active-worker",
            executor="cluster-readonly-v1",
        )

    service.transition(original["id"], "failed", actor=original["lease_owner"])
    with pytest.raises(WorkRunIdempotencyConflict, match="reserved"):
        service.claim(
            dispatch_id="cluster-postgres-operation",
            idempotency_key=idempotency_key,
            agent_id="ordinary-terminal-worker",
            executor="cluster-readonly-v1",
        )

    with service.connect() as connection:
        final_ledger = connection.execute(
            "SELECT COUNT(*) AS count, MAX(attempt) AS max_attempt "
            "FROM work_runs WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
    assert final_ledger["count"] == 1
    assert final_ledger["max_attempt"] == 1
