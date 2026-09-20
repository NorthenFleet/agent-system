import sqlite3

import pytest

from repositories.command_center_repository import (
    CommandCenterPoolExhausted,
    PostgresCommandCenterRepository,
    SQLiteCommandCenterRepository,
    _postgres_sql,
    create_command_center_repository,
)
from services.command_center_service import CommandCenterService


def test_sqlite_repository_owns_transactions_and_schema_introspection(tmp_path):
    repository = SQLiteCommandCenterRepository(str(tmp_path / "repository.db"))

    with repository.transaction(immediate=True) as connection:
        connection.execute("CREATE TABLE records (id TEXT PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO records (id, value) VALUES (?, ?)", ("1", "saved"))

    with repository.transaction() as connection:
        assert repository.table_exists(connection, "records") is True
        assert repository.table_columns(connection, "records") == {"id", "value"}
        assert connection.execute("SELECT value FROM records").fetchone()["value"] == "saved"

    with pytest.raises(RuntimeError, match="rollback"):
        with repository.transaction(immediate=True) as connection:
            connection.execute("INSERT INTO records (id, value) VALUES (?, ?)", ("2", "lost"))
            raise RuntimeError("rollback")

    with sqlite3.connect(repository.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1


def test_service_accepts_repository_and_survives_restart(tmp_path):
    repository = SQLiteCommandCenterRepository(str(tmp_path / "missions.db"))
    service = CommandCenterService(repository=repository)
    mission = service.create_mission(
        objective="验证 Repository 重启恢复",
        requested_by="admin",
    )

    restarted = CommandCenterService(
        repository=SQLiteCommandCenterRepository(repository.db_path)
    )

    assert restarted.get_mission(mission["id"])["objective"] == "验证 Repository 重启恢复"
    assert restarted.storage_info() == {
        "backend": "sqlite",
        "source_of_truth": repository.db_path,
        "capabilities": {
            "durable": True,
            "transactional_claims": True,
            "multi_instance": False,
            "runtime_schema_management": True,
        },
    }


def test_repository_factory_supports_explicit_sqlite_url(tmp_path):
    target = tmp_path / "factory.db"
    repository = create_command_center_repository(
        database_url=f"sqlite:////{str(target).lstrip('/')}"
    )

    assert isinstance(repository, SQLiteCommandCenterRepository)
    assert repository.db_path == str(target)


def test_repository_factory_builds_postgres_without_exposing_password():
    repository = create_command_center_repository(
        database_url="postgresql+psycopg2://agent:secret@db/command_center"
    )

    assert isinstance(repository, PostgresCommandCenterRepository)
    assert repository.source_of_truth == (
        "postgresql+psycopg2://agent:***@db/command_center"
    )
    assert repository.describe()["capabilities"]["multi_instance"] is True


def test_postgres_adapter_translates_parameters_idempotency_and_claim_locks():
    assert _postgres_sql("SELECT '?' AS literal, id FROM jobs WHERE id=?") == (
        "SELECT '?' AS literal, id FROM jobs WHERE id=%s"
    )
    assert _postgres_sql(
        "INSERT OR IGNORE INTO jobs (id, value) VALUES (?, ?)"
    ) == "INSERT INTO jobs (id, value) VALUES (%s, %s) ON CONFLICT DO NOTHING"

    repository = PostgresCommandCenterRepository(
        "postgresql+psycopg2:///command_center"
    )
    assert repository.claim_query(
        "SELECT s.* FROM mission_steps s WHERE status='ready'",
        table_alias="s",
    ).endswith("FOR UPDATE OF s SKIP LOCKED")


def test_service_rejects_ambiguous_storage_configuration(tmp_path):
    repository = SQLiteCommandCenterRepository(str(tmp_path / "repository.db"))

    with pytest.raises(ValueError, match="either db_path or repository"):
        CommandCenterService(str(tmp_path / "other.db"), repository=repository)


def test_postgres_pool_is_bounded_and_exports_sanitized_metrics(monkeypatch):
    import repositories.command_center_repository as repository_module

    class FakeConnection:
        def __init__(self, *, fail_ping=False):
            self.closed = 0
            self.autocommit = True
            self.fail_ping = fail_ping

        class Cursor:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, _sql):
                if self.connection.fail_ping:
                    self.connection.closed = 1
                    raise RuntimeError("connection terminated")

            def close(self):
                return None

        def cursor(self):
            return self.Cursor(self)

        def commit(self):
            return None

        def rollback(self):
            return None

    class FakePool:
        def __init__(self, minimum, maximum, dsn, **kwargs):
            self.minimum = minimum
            self.maximum = maximum
            self.dsn = dsn
            self.kwargs = kwargs
            self.connection = FakeConnection()
            self.closed = False

        def getconn(self):
            return self.connection

        def putconn(self, connection, close=False):
            assert connection is self.connection
            assert close is False

        def closeall(self):
            self.closed = True

    monkeypatch.setattr(repository_module, "ThreadedConnectionPool", FakePool)
    repository = PostgresCommandCenterRepository(
        "postgresql+psycopg2://agent:secret@db/command_center",
        pool_min_size=1,
        pool_max_size=1,
        pool_acquire_timeout_seconds=0.01,
    )

    with repository.transaction():
        with pytest.raises(CommandCenterPoolExhausted, match="pool exhausted"):
            with repository.transaction():
                pass

    metrics = repository.runtime_metrics()
    assert metrics["connection_mode"] == "threaded_pool"
    assert metrics["pre_ping"] is True
    assert metrics["status"] == "degraded"
    assert metrics["pool"]["max_size"] == 1
    assert metrics["pool"]["peak_in_use"] == 1
    assert metrics["pool"]["in_use"] == 0
    assert metrics["pool"]["acquisitions_total"] == 1
    assert metrics["pool"]["acquire_timeouts_total"] == 1
    assert "secret" not in str(metrics)

    repository.close()
    assert repository._pool is None


def test_postgres_pool_pre_ping_discards_stale_connection_and_reconnects(monkeypatch):
    import repositories.command_center_repository as repository_module

    class FakeConnection:
        def __init__(self, *, fail_ping=False):
            self.closed = 0
            self.autocommit = True
            self.fail_ping = fail_ping

        class Cursor:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, _sql):
                if self.connection.fail_ping:
                    self.connection.closed = 1
                    raise RuntimeError("connection terminated")

            def close(self):
                return None

        def cursor(self):
            return self.Cursor(self)

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            self.closed = 1

    class FakePool:
        def __init__(self, *_args, **_kwargs):
            self.connections = [
                FakeConnection(fail_ping=True),
                FakeConnection(fail_ping=False),
            ]
            self.returned = []

        def getconn(self):
            return self.connections.pop(0)

        def putconn(self, connection, close=False):
            self.returned.append((connection, close))

        def closeall(self):
            return None

    monkeypatch.setattr(repository_module, "ThreadedConnectionPool", FakePool)
    repository = PostgresCommandCenterRepository(
        "postgresql+psycopg2:///command_center",
        pool_min_size=1,
        pool_max_size=1,
    )

    with repository.transaction():
        pass

    metrics = repository.runtime_metrics()
    assert metrics["pool"]["stale_connections_discarded_total"] == 1
    assert metrics["pool"]["reconnects_total"] == 1
    assert metrics["pool"]["transactions_committed_total"] == 1
