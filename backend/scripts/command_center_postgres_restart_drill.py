#!/usr/bin/env python3
"""Restart the local PostgreSQL service and verify Command Center recovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from command_center_database_fault_drill import (
    _active_leases,
    _auth_client,
    _dsn,
    _fact_snapshot,
    _now,
    _sample,
)


def _database_probe(database_url: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        connection = psycopg2.connect(
            database_url,
            connect_timeout=1,
            application_name="agent-system-postgres-restart-probe",
        )
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT pg_postmaster_start_time() AS postmaster_started_at"
                )
                value = cursor.fetchone()["postmaster_started_at"]
            return {
                "ready": True,
                "postmaster_started_at": value.isoformat(),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            }
        finally:
            connection.close()
    except Exception as exc:
        return {
            "ready": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }


def _connected_databases(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT datname, application_name, usename, state, COUNT(*) AS connections
        FROM pg_stat_activity
        WHERE backend_type='client backend' AND pid <> pg_backend_pid()
        GROUP BY datname, application_name, usename, state
        ORDER BY datname, application_name, usename, state
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def run(
    base_url: str,
    *,
    timeout_seconds: float,
    service_name: str,
) -> dict[str, Any]:
    database_url = _dsn()
    if not database_url.startswith("postgresql"):
        raise RuntimeError("COMMAND_CENTER_DATABASE_URL must be PostgreSQL")
    if service_name != "postgresql@17":
        raise RuntimeError("refusing to restart an unreviewed PostgreSQL service")

    control = psycopg2.connect(
        database_url,
        application_name="agent-system-postgres-restart-drill",
    )
    control.autocommit = True
    client, headers, auth_mode = _auth_client(base_url)
    try:
        with control.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT pg_postmaster_start_time() AS postmaster_started_at"
            )
            postmaster_before = cursor.fetchone()["postmaster_started_at"].isoformat()
            connections_before = _connected_databases(cursor)
            other_databases = sorted(
                {
                    str(row.get("datname"))
                    for row in connections_before
                    if row.get("datname") not in (None, "team_dashboard")
                }
            )
            if other_databases:
                raise RuntimeError(
                    f"other connected databases block restart drill: {other_databases}"
                )
            facts_before = _fact_snapshot(cursor)
            leases_before = _active_leases(cursor)
            if any(leases_before.values()):
                raise RuntimeError(f"active leases block restart drill: {leases_before}")
            baseline = _sample(client, headers)
            if not baseline["functional"] or baseline.get("production_status") != "ready":
                raise RuntimeError("baseline production health is not ready")

        injected_at = time.monotonic()
        restart = subprocess.run(
            ["brew", "services", "restart", service_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        observations: list[dict[str, Any]] = []
        consecutive_healthy = 0
        database_recovery_seconds: float | None = None
        functional_recovery_seconds: float | None = None
        postmaster_after: str | None = None
        deadline = injected_at + timeout_seconds
        while time.monotonic() < deadline:
            database = _database_probe(database_url)
            since_restart = round(time.monotonic() - injected_at, 3)
            if database["ready"]:
                postmaster_after = str(database["postmaster_started_at"])
                if database_recovery_seconds is None and postmaster_after != postmaster_before:
                    database_recovery_seconds = since_restart
            application = _sample(client, headers)
            observation = {
                "observed_at": _now(),
                "since_restart_seconds": since_restart,
                "database": database,
                "application": application,
            }
            observations.append(observation)
            recovered_generation = bool(
                database["ready"]
                and postmaster_after
                and postmaster_after != postmaster_before
            )
            if recovered_generation and application["functional"]:
                consecutive_healthy += 1
                if consecutive_healthy >= 3:
                    functional_recovery_seconds = since_restart
                    break
            else:
                consecutive_healthy = 0
            time.sleep(0.5)

        verification = psycopg2.connect(
            database_url,
            connect_timeout=3,
            application_name="agent-system-postgres-restart-verify",
        )
        try:
            with verification.cursor(cursor_factory=RealDictCursor) as cursor:
                facts_after = _fact_snapshot(cursor)
                leases_after = _active_leases(cursor)
                connections_after = _connected_databases(cursor)
                cursor.execute(
                    "SELECT pg_postmaster_start_time() AS postmaster_started_at"
                )
                postmaster_after = cursor.fetchone()[
                    "postmaster_started_at"
                ].isoformat()
        finally:
            verification.close()
    finally:
        client.close()
        control.close()

    final = observations[-1]["application"] if observations else {}
    rpo_zero = facts_before == facts_after
    generation_changed = postmaster_after != postmaster_before
    healthy = bool(
        restart.returncode == 0
        and generation_changed
        and database_recovery_seconds is not None
        and functional_recovery_seconds is not None
        and rpo_zero
        and not any(leases_after.values())
        and final.get("checkpoint_status") == "ready"
        and int(final.get("workers_live") or 0)
        >= int(final.get("workers_required") or 1)
    )
    return {
        "schema_version": "command-center-postgres-restart-drill.v1",
        "checked_at": _now(),
        "healthy": healthy,
        "scope": "homebrew-postgresql-service-restart",
        "service": service_name,
        "auth_mode": auth_mode,
        "restart_command": {
            "returncode": restart.returncode,
            "stdout": restart.stdout.strip()[:500],
            "stderr": restart.stderr.strip()[:500],
        },
        "postmaster_started_at_before": postmaster_before,
        "postmaster_started_at_after": postmaster_after,
        "postmaster_generation_changed": generation_changed,
        "database_recovery_seconds": database_recovery_seconds,
        "functional_recovery_seconds": functional_recovery_seconds,
        "rpo_zero": rpo_zero,
        "active_leases_before": leases_before,
        "active_leases_after": leases_after,
        "connections_before": connections_before,
        "connections_after": connections_after,
        "facts_before": facts_before,
        "facts_after": facts_after,
        "baseline": baseline,
        "final": final,
        "observations": observations,
        "note": (
            "production_status may remain degraded during the five-minute incident "
            "visibility window after functional recovery"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3021")
    parser.add_argument("--timeout-seconds", type=float, default=90)
    parser.add_argument("--service", default="postgresql@17")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    try:
        report = run(
            args.base_url,
            timeout_seconds=max(30, args.timeout_seconds),
            service_name=args.service,
        )
    except Exception as exc:
        report = {
            "schema_version": "command-center-postgres-restart-drill.v1",
            "checked_at": _now(),
            "healthy": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
