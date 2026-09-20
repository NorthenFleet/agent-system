#!/usr/bin/env python3
"""Run a non-destructive PostgreSQL pool capacity and saturation gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repositories.command_center_repository import (  # noqa: E402
    CommandCenterPoolExhausted,
    PostgresCommandCenterRepository,
)
from services.workflow_runtime import (  # noqa: E402
    POSTGRES_CHECKPOINT_TABLES,
    postgres_checkpoint_required_version,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _database_snapshot(repository: PostgresCommandCenterRepository) -> dict[str, Any]:
    with repository.transaction() as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        counts = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM orchestration_missions) AS missions,
                (SELECT COUNT(*) FROM mission_steps) AS steps,
                (SELECT COUNT(*) FROM work_runs) AS work_runs,
                (SELECT COUNT(*) FROM work_run_events) AS work_run_events,
                (SELECT COUNT(*) FROM work_artifacts) AS work_artifacts
            """
        ).fetchone()
        missing = sorted(
            table
            for table in POSTGRES_CHECKPOINT_TABLES
            if not repository.table_exists(connection, table)
        )
        installed_checkpoint_version = -1
        if "checkpoint_migrations" not in missing:
            row = connection.execute(
                "SELECT MAX(v) AS version FROM checkpoint_migrations"
            ).fetchone()
            installed_checkpoint_version = (
                int(row["version"]) if row and row["version"] is not None else -1
            )
    return {
        "alembic_revision": str(version["version_num"]),
        "counts": {key: int(value) for key, value in dict(counts).items()},
        "checkpoint": {
            "missing_tables": missing,
            "installed_version": installed_checkpoint_version,
            "required_version": postgres_checkpoint_required_version(),
        },
    }


def _normal_load(
    database_url: str,
    *,
    pool_size: int,
    concurrency: int,
    requests: int,
    hold_ms: int,
) -> dict[str, Any]:
    repository = PostgresCommandCenterRepository(
        database_url,
        pool_min_size=1,
        pool_max_size=pool_size,
        pool_acquire_timeout_seconds=2,
    )

    def query(index: int) -> int:
        with repository.transaction() as connection:
            row = connection.execute(
                "SELECT ?::INTEGER AS request_id, pg_sleep(?::DOUBLE PRECISION)",
                (index, hold_ms / 1000),
            ).fetchone()
            return int(row["request_id"])

    started = time.monotonic()
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(query, index) for index in range(requests)]
        results: list[int] = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    metrics = repository.runtime_metrics()
    repository.close()
    return {
        "requests": requests,
        "completed": len(results),
        "unique_results": len(set(results)),
        "errors": errors,
        "elapsed_ms": elapsed_ms,
        "pool": metrics["pool"],
    }


def _saturation_gate(database_url: str) -> dict[str, Any]:
    repository = PostgresCommandCenterRepository(
        database_url,
        pool_min_size=1,
        pool_max_size=1,
        pool_acquire_timeout_seconds=0.05,
    )
    holder_started = threading.Event()
    release_holder = threading.Event()
    holder_error: list[str] = []

    def hold_connection() -> None:
        try:
            with repository.transaction() as connection:
                connection.execute("SELECT 1").fetchone()
                holder_started.set()
                release_holder.wait(timeout=2)
        except Exception as exc:
            holder_error.append(f"{type(exc).__name__}: {exc}")
            holder_started.set()

    thread = threading.Thread(target=hold_connection, name="pool-saturation-holder")
    thread.start()
    holder_started.wait(timeout=2)
    failed_closed = False
    error = ""
    try:
        with repository.transaction() as connection:
            connection.execute("SELECT 1").fetchone()
    except CommandCenterPoolExhausted as exc:
        failed_closed = True
        error = str(exc)
    finally:
        release_holder.set()
        thread.join(timeout=2)

    recovered = False
    if not holder_error:
        with repository.transaction() as connection:
            recovered = int(connection.execute("SELECT 1 AS ok").fetchone()["ok"]) == 1
    metrics = repository.runtime_metrics()
    repository.close()
    return {
        "failed_closed": failed_closed,
        "recovered": recovered,
        "error": error,
        "holder_errors": holder_error,
        "pool": metrics["pool"],
    }


def _unavailable_database_gate() -> dict[str, Any]:
    """Verify a refused local port fails quickly without exposing connection details."""
    repository = PostgresCommandCenterRepository(
        "postgresql://127.0.0.1:1/team_dashboard",
        connect_timeout_seconds=1,
        pool_min_size=1,
        pool_max_size=1,
        pool_acquire_timeout_seconds=1,
    )
    started = time.monotonic()
    failed_closed = False
    error_type = ""
    try:
        with repository.transaction() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        failed_closed = True
        error_type = type(exc).__name__
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    metrics = repository.runtime_metrics()
    repository.close()
    return {
        "failed_closed": failed_closed,
        "failed_within_limit": elapsed_ms < 3000,
        "elapsed_ms": elapsed_ms,
        "error_type": error_type,
        "connection_failures_total": metrics["pool"]["connection_failures_total"],
    }


def run_gate(
    database_url: str,
    *,
    pool_size: int,
    concurrency: int,
    requests: int,
    hold_ms: int,
) -> dict[str, Any]:
    probe = PostgresCommandCenterRepository(
        database_url,
        pool_min_size=1,
        pool_max_size=max(1, pool_size),
        pool_acquire_timeout_seconds=2,
    )
    try:
        database = _database_snapshot(probe)
    finally:
        probe.close()
    normal = _normal_load(
        database_url,
        pool_size=pool_size,
        concurrency=concurrency,
        requests=requests,
        hold_ms=hold_ms,
    )
    saturation = _saturation_gate(database_url)
    unavailable = _unavailable_database_gate()
    checkpoint = database["checkpoint"]
    checks = {
        "alembic_at_phase5_head": database["alembic_revision"]
        == "20260921_worker_registry",
        "checkpoint_schema_ready": (
            not checkpoint["missing_tables"]
            and checkpoint["installed_version"] >= checkpoint["required_version"] >= 0
        ),
        "normal_load_completed": normal["completed"] == requests and not normal["errors"],
        "pool_bound_respected": int(normal["pool"]["peak_in_use"]) <= pool_size,
        "no_normal_load_timeouts": int(normal["pool"]["acquire_timeouts_total"]) == 0,
        "saturation_failed_closed": saturation["failed_closed"] is True,
        "pool_recovered_after_saturation": saturation["recovered"] is True,
        "unavailable_database_failed_closed": (
            unavailable["failed_closed"] is True
            and unavailable["failed_within_limit"] is True
            and int(unavailable["connection_failures_total"]) >= 1
        ),
    }
    return {
        "schema_version": "command-center-postgres-capacity-gate.v1",
        "checked_at": _utc_now(),
        "healthy": all(checks.values()),
        "checks": checks,
        "database": database,
        "normal_load": normal,
        "saturation": saturation,
        "unavailable_database": unavailable,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("COMMAND_CENTER_DATABASE_URL", ""),
    )
    parser.add_argument("--pool-size", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--requests", type=int, default=24)
    parser.add_argument("--hold-ms", type=int, default=30)
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if not args.postgres_url:
        parser.error("--postgres-url or COMMAND_CENTER_DATABASE_URL is required")
    report = run_gate(
        args.postgres_url,
        pool_size=max(1, args.pool_size),
        concurrency=max(1, args.concurrency),
        requests=max(1, args.requests),
        hold_ms=max(0, args.hold_ms),
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
