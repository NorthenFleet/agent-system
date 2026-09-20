"""Persistence boundary for Command Center state.

The business state machine intentionally depends on this narrow contract rather
than opening database connections itself. SQLite supports controlled single-node
deployments and PostgreSQL supplies row-level claim locking for multiple workers.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:  # pragma: no cover - exercised by deployment preflight
    psycopg2 = None
    RealDictCursor = None
    ThreadedConnectionPool = None


class UnsupportedCommandCenterBackend(RuntimeError):
    """Raised when configuration requests a backend that is not release-ready."""


class CommandCenterPoolExhausted(RuntimeError):
    """Raised when the bounded PostgreSQL pool cannot lease a connection in time."""


@dataclass(frozen=True)
class CommandCenterStorageCapabilities:
    durable: bool
    transactional_claims: bool
    multi_instance: bool
    runtime_schema_management: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


class CommandCenterRepository(ABC):
    """Transaction and schema-introspection contract used by the service."""

    backend: str
    source_of_truth: str
    capabilities: CommandCenterStorageCapabilities

    @abstractmethod
    def transaction(self, *, immediate: bool = False) -> Iterator[Any]:
        """Open a transaction and commit or roll it back atomically."""

    @abstractmethod
    def table_exists(self, connection: Any, table: str) -> bool:
        """Return whether a table exists in the current schema."""

    @abstractmethod
    def table_columns(self, connection: Any, table: str) -> set[str]:
        """Return the column names for a table in the current schema."""

    def claim_query(self, sql: str, *, table_alias: str | None = None) -> str:
        """Apply backend-specific row locking to a competing claim query."""
        return sql

    def lock_key(self, connection: Any, key: str) -> None:
        """Serialize creation for a logical idempotency key when required."""
        del connection, key

    def runtime_metrics(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "connection_mode": "direct",
        }

    def close(self) -> None:
        """Release backend resources; direct stores have nothing to close."""

    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "source_of_truth": self.source_of_truth,
            "capabilities": self.capabilities.as_dict(),
        }


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SQLiteCommandCenterRepository(CommandCenterRepository):
    """Durable single-node Command Center repository backed by SQLite."""

    backend = "sqlite"
    capabilities = CommandCenterStorageCapabilities(
        durable=True,
        transactional_claims=True,
        multi_instance=False,
        runtime_schema_management=True,
    )

    def __init__(self, db_path: str, *, busy_timeout_ms: int = 8000):
        if not str(db_path).strip():
            raise ValueError("Command Center SQLite path must not be empty")
        self.db_path = os.path.abspath(os.path.expanduser(str(db_path)))
        self.source_of_truth = self.db_path
        self.busy_timeout_ms = max(1, int(busy_timeout_ms))

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _validate_identifier(value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError(f"Unsafe SQL identifier: {value!r}")
        return value

    def table_exists(self, connection: sqlite3.Connection, table: str) -> bool:
        table = self._validate_identifier(table)
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            is not None
        )

    def table_columns(self, connection: sqlite3.Connection, table: str) -> set[str]:
        table = self._validate_identifier(table)
        return {
            str(row["name"])
            for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        }


def _postgres_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg2://", "postgresql://", 1)


def _redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.password:
        return database_url
    username = parsed.username or ""
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = f"{username}:***@" if username else ""
    return parsed._replace(netloc=f"{auth}{hostname}{port}").geturl()


def _postgres_placeholders(sql: str) -> str:
    """Translate qmark parameters while preserving question marks in literals."""
    output: list[str] = []
    quoted = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'":
            output.append(char)
            if quoted and index + 1 < len(sql) and sql[index + 1] == "'":
                output.append("'")
                index += 2
                continue
            quoted = not quoted
        elif char == "?" and not quoted:
            output.append("%s")
        else:
            output.append(char)
        index += 1
    return "".join(output)


def _postgres_sql(sql: str) -> str:
    statement = _postgres_placeholders(sql)
    match = re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", statement, re.IGNORECASE)
    if match:
        statement = statement[: match.start()] + "INSERT INTO" + statement[match.end() :]
        statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return statement


class _PostgresConnection:
    def __init__(self, connection: Any):
        self._connection = connection
        self._cursors: list[Any] = []

    def execute(self, sql: str, parameters: tuple[Any, ...] | list[Any] = ()) -> Any:
        cursor = self._connection.cursor(cursor_factory=RealDictCursor)
        self._cursors.append(cursor)
        cursor.execute(_postgres_sql(sql), parameters)
        return cursor

    def close(self) -> None:
        for cursor in self._cursors:
            try:
                cursor.close()
            except Exception:
                pass
        self._cursors.clear()


class PostgresCommandCenterRepository(CommandCenterRepository):
    """Multi-instance Command Center repository backed by PostgreSQL."""

    backend = "postgresql"
    capabilities = CommandCenterStorageCapabilities(
        durable=True,
        transactional_claims=True,
        multi_instance=True,
        runtime_schema_management=False,
    )

    def __init__(
        self,
        database_url: str,
        *,
        connect_timeout_seconds: int = 8,
        pool_min_size: int | None = None,
        pool_max_size: int | None = None,
        pool_acquire_timeout_seconds: float | None = None,
    ):
        if psycopg2 is None:
            raise UnsupportedCommandCenterBackend(
                "PostgreSQL requires psycopg2; install backend production dependencies"
            )
        self.database_url = database_url
        self.dsn = _postgres_dsn(database_url)
        self.source_of_truth = _redact_database_url(database_url)
        self.connect_timeout_seconds = max(1, int(connect_timeout_seconds))
        self.pool_min_size = max(
            1,
            int(pool_min_size or os.getenv("COMMAND_CENTER_DB_POOL_MIN", "1")),
        )
        self.pool_max_size = max(
            self.pool_min_size,
            int(pool_max_size or os.getenv("COMMAND_CENTER_DB_POOL_MAX", "10")),
        )
        self.pool_acquire_timeout_seconds = max(
            0.01,
            float(
                pool_acquire_timeout_seconds
                or os.getenv("COMMAND_CENTER_DB_POOL_ACQUIRE_TIMEOUT", "5")
            ),
        )
        self.pool_pre_ping = os.getenv(
            "COMMAND_CENTER_DB_POOL_PRE_PING",
            "true",
        ).strip().lower() not in {"0", "false", "no", "off"}
        self._pool: Any = None
        self._pool_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(self.pool_max_size)
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, float | int] = {
            "acquisitions_total": 0,
            "transactions_committed_total": 0,
            "transactions_rolled_back_total": 0,
            "acquire_timeouts_total": 0,
            "connection_failures_total": 0,
            "stale_connections_discarded_total": 0,
            "reconnects_total": 0,
            "in_use": 0,
            "peak_in_use": 0,
            "acquire_wait_ms_total": 0.0,
            "acquire_wait_ms_max": 0.0,
            "last_acquire_timeout_epoch": 0.0,
            "last_connection_failure_epoch": 0.0,
        }

    def _ensure_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is None:
                try:
                    self._pool = ThreadedConnectionPool(
                        self.pool_min_size,
                        self.pool_max_size,
                        self.dsn,
                        connect_timeout=self.connect_timeout_seconds,
                        application_name="agent-system-command-center",
                    )
                except Exception:
                    with self._metrics_lock:
                        self._metrics["connection_failures_total"] += 1
                        self._metrics["last_connection_failure_epoch"] = time.time()
                    raise
        return self._pool

    def _record_acquisition(self, wait_ms: float) -> None:
        with self._metrics_lock:
            self._metrics["acquisitions_total"] += 1
            self._metrics["in_use"] += 1
            self._metrics["peak_in_use"] = max(
                int(self._metrics["peak_in_use"]),
                int(self._metrics["in_use"]),
            )
            self._metrics["acquire_wait_ms_total"] += wait_ms
            self._metrics["acquire_wait_ms_max"] = max(
                float(self._metrics["acquire_wait_ms_max"]),
                wait_ms,
            )

    def _record_release(self) -> None:
        with self._metrics_lock:
            self._metrics["in_use"] = max(0, int(self._metrics["in_use"]) - 1)

    def _record_connection_failure(self, *, stale: bool = False) -> None:
        with self._metrics_lock:
            self._metrics["connection_failures_total"] += 1
            self._metrics["last_connection_failure_epoch"] = time.time()
            if stale:
                self._metrics["stale_connections_discarded_total"] += 1

    def _checkout_connection(self, pool: Any) -> Any:
        last_error: Exception | None = None
        discarded = False
        for _attempt in range(2):
            connection = None
            try:
                connection = pool.getconn()
                if bool(connection.closed):
                    raise RuntimeError("pooled PostgreSQL connection is closed")
                connection.autocommit = False
                if self.pool_pre_ping:
                    cursor = connection.cursor()
                    try:
                        cursor.execute("SELECT 1")
                    finally:
                        cursor.close()
                    connection.rollback()
                if discarded:
                    with self._metrics_lock:
                        self._metrics["reconnects_total"] += 1
                return connection
            except Exception as exc:
                last_error = exc
                discarded = True
                self._record_connection_failure(stale=True)
                if connection is not None:
                    try:
                        pool.putconn(connection, close=True)
                    except Exception:
                        try:
                            connection.close()
                        except Exception:
                            pass
        if last_error is not None:
            raise last_error
        raise RuntimeError("unable to checkout PostgreSQL connection")

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[_PostgresConnection]:
        del immediate  # Row-level claim locks replace SQLite's database write lock.
        started = time.monotonic()
        acquired = self._slots.acquire(timeout=self.pool_acquire_timeout_seconds)
        wait_ms = (time.monotonic() - started) * 1000
        if not acquired:
            with self._metrics_lock:
                self._metrics["acquire_timeouts_total"] += 1
                self._metrics["last_acquire_timeout_epoch"] = time.time()
                self._metrics["acquire_wait_ms_total"] += wait_ms
                self._metrics["acquire_wait_ms_max"] = max(
                    float(self._metrics["acquire_wait_ms_max"]),
                    wait_ms,
                )
            raise CommandCenterPoolExhausted(
                "PostgreSQL connection pool exhausted after "
                f"{self.pool_acquire_timeout_seconds:.2f}s"
            )
        connection = None
        adapter = None
        pool = None
        broken = False
        try:
            pool = self._ensure_pool()
            connection = self._checkout_connection(pool)
            self._record_acquisition(wait_ms)
            adapter = _PostgresConnection(connection)
            yield adapter
            connection.commit()
            with self._metrics_lock:
                self._metrics["transactions_committed_total"] += 1
        except Exception:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    broken = True
            with self._metrics_lock:
                if connection is not None:
                    self._metrics["transactions_rolled_back_total"] += 1
                if broken:
                    self._metrics["connection_failures_total"] += 1
                    self._metrics["last_connection_failure_epoch"] = time.time()
            raise
        finally:
            if adapter is not None:
                adapter.close()
            if connection is not None and pool is not None:
                pool.putconn(connection, close=broken or bool(connection.closed))
                self._record_release()
            self._slots.release()

    def runtime_metrics(self) -> dict[str, Any]:
        with self._metrics_lock:
            metrics = dict(self._metrics)
        acquisitions = int(metrics["acquisitions_total"])
        metrics["acquire_wait_ms_average"] = round(
            float(metrics["acquire_wait_ms_total"]) / acquisitions,
            3,
        ) if acquisitions else 0.0
        metrics["acquire_wait_ms_total"] = round(
            float(metrics["acquire_wait_ms_total"]),
            3,
        )
        metrics["acquire_wait_ms_max"] = round(
            float(metrics["acquire_wait_ms_max"]),
            3,
        )
        recent_cutoff = time.time() - 300
        recent_timeout = float(metrics["last_acquire_timeout_epoch"]) >= recent_cutoff
        recent_failure = float(metrics["last_connection_failure_epoch"]) >= recent_cutoff
        return {
            "backend": self.backend,
            "connection_mode": "threaded_pool",
            "pre_ping": self.pool_pre_ping,
            "status": "degraded" if recent_timeout or recent_failure else "ready",
            "health_window_seconds": 300,
            "pool": {
                "min_size": self.pool_min_size,
                "max_size": self.pool_max_size,
                "acquire_timeout_seconds": self.pool_acquire_timeout_seconds,
                **metrics,
            },
        }

    def close(self) -> None:
        with self._pool_lock:
            if self._pool is not None:
                self._pool.closeall()
                self._pool = None

    def table_exists(self, connection: _PostgresConnection, table: str) -> bool:
        table = SQLiteCommandCenterRepository._validate_identifier(table)
        return (
            connection.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema=current_schema() AND table_name=?
                """,
                (table,),
            ).fetchone()
            is not None
        )

    def table_columns(self, connection: _PostgresConnection, table: str) -> set[str]:
        table = SQLiteCommandCenterRepository._validate_identifier(table)
        return {
            str(row["column_name"])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema=current_schema() AND table_name=?
                """,
                (table,),
            ).fetchall()
        }

    def claim_query(self, sql: str, *, table_alias: str | None = None) -> str:
        lock_target = f" OF {table_alias}" if table_alias else ""
        return f"{sql.rstrip().rstrip(';')} FOR UPDATE{lock_target} SKIP LOCKED"

    def lock_key(self, connection: _PostgresConnection, key: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
            (str(key),),
        )


def _sqlite_path_from_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError("not a SQLite URL")
    if parsed.netloc not in {"", "localhost"}:
        raise ValueError("SQLite URL must not contain a remote host")
    path = unquote(parsed.path)
    if path == "/:memory:":
        return ":memory:"
    # sqlite:///relative.db and sqlite:////absolute.db follow SQLAlchemy's
    # conventional spelling.  urlparse retains the leading slash for both.
    if database_url.startswith("sqlite:////"):
        return path[1:]
    return path.lstrip("/")


def create_command_center_repository(
    *,
    db_path: str | None = None,
    database_url: str | None = None,
) -> CommandCenterRepository:
    """Build the configured repository and fail closed for unknown stores."""

    configured_url = str(database_url or "").strip()
    if configured_url:
        scheme = urlparse(configured_url).scheme.lower()
        if scheme == "sqlite":
            return SQLiteCommandCenterRepository(_sqlite_path_from_url(configured_url))
        if scheme in {"postgresql", "postgresql+psycopg2", "postgres"}:
            return PostgresCommandCenterRepository(configured_url)
        raise UnsupportedCommandCenterBackend(
            "COMMAND_CENTER_DATABASE_URL requests "
            f"{scheme or 'an unknown backend'}; supported backends are SQLite and PostgreSQL."
        )
    if db_path is None:
        raise ValueError("db_path or database_url is required")
    return SQLiteCommandCenterRepository(db_path)
