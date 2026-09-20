#!/usr/bin/env python3
"""Terminate only agent-system PostgreSQL sessions and verify transparent recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(WORKSPACE_ROOT / ".env", override=False)

FACT_TABLES = (
    "orchestration_missions",
    "mission_steps",
    "mission_events",
    "workflow_runs",
    "work_runs",
    "work_run_events",
    "work_artifacts",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dsn() -> str:
    value = os.getenv("COMMAND_CENTER_DATABASE_URL", "").strip()
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if value.startswith(prefix):
            return "postgresql://" + value[len(prefix) :]
    return value


def _digest(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _fact_snapshot(cursor: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for table in FACT_TABLES:
        cursor.execute(f'SELECT id FROM "{table}"')
        ids = [str(row["id"]) for row in cursor.fetchall()]
        snapshot[table] = {"count": len(ids), "id_checksum": _digest(ids)}
    return snapshot


def _active_leases(cursor: Any) -> dict[str, int]:
    statements = {
        "steps": "SELECT COUNT(*) AS count FROM mission_steps WHERE status='running'",
        "workflows": (
            "SELECT COUNT(*) AS count FROM workflow_runs "
            "WHERE lease_owner IS NOT NULL AND status IN ('running','resume_pending')"
        ),
        "compensations": (
            "SELECT COUNT(*) AS count FROM mission_compensations WHERE status='running'"
        ),
        "outbox": "SELECT COUNT(*) AS count FROM notification_outbox WHERE status='sending'",
    }
    result: dict[str, int] = {}
    for name, statement in statements.items():
        cursor.execute(statement)
        result[name] = int(cursor.fetchone()["count"] or 0)
    return result


def _auth_client(base_url: str) -> tuple[httpx.Client, dict[str, str], str]:
    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=5)
    settings = client.get("/api/v2/auth/settings")
    settings.raise_for_status()
    token = os.getenv("COMMAND_CENTER_SMOKE_TOKEN", "").strip()
    auth_mode = "configured-token"
    if not token and not bool(settings.json().get("login_enabled")):
        session = client.post("/api/v2/auth/development-session")
        session.raise_for_status()
        token = str(session.json().get("access_token") or "")
        auth_mode = "development-session"
    if not token:
        client.close()
        raise RuntimeError("COMMAND_CENTER_SMOKE_TOKEN is required when login is enabled")
    return client, {"Authorization": f"Bearer {token}"}, auth_mode


def _sample(client: httpx.Client, headers: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    endpoints = {
        "public": ("/health", {}),
        "command": ("/api/v3/command-center/health", headers),
        "production": ("/api/v3/command-center/production-health", headers),
        "workflow": ("/api/v3/command-center/workflow-runtime", headers),
    }
    responses: dict[str, Any] = {}
    for name, (path, request_headers) in endpoints.items():
        try:
            response = client.get(path, headers=request_headers)
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            responses[name] = {"status_code": response.status_code, "payload": payload}
        except Exception as exc:
            responses[name] = {
                "status_code": 0,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            }
    production = responses.get("production", {}).get("payload") or {}
    command = responses.get("command", {}).get("payload") or {}
    workflow = responses.get("workflow", {}).get("payload") or {}
    workers = production.get("workers") or {}
    pool = (production.get("storage_runtime") or {}).get("pool") or {}
    work_runs = production.get("work_runs") or {}
    checkpoint = (production.get("workflow_runtime") or {}).get("checkpoint_storage") or {}
    functional = bool(
        all(item.get("status_code") == 200 for item in responses.values())
        and (command.get("storage") or {}).get("backend") == "postgresql"
        and (workflow.get("langgraph") or {}).get("checkpoint_backend") == "postgresql"
        and checkpoint.get("status") == "ready"
        and workers.get("status") == "ready"
        and int(workers.get("live") or 0) >= int(workers.get("required") or 1)
        and int(workers.get("stale") or 0) == 0
        and int(work_runs.get("expired_active_leases") or 0) == 0
    )
    return {
        "observed_at": _now(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "functional": functional,
        "http_status": {
            name: item.get("status_code") for name, item in responses.items()
        },
        "production_status": production.get("status"),
        "workers_live": workers.get("live"),
        "workers_required": workers.get("required"),
        "workers_stale": workers.get("stale"),
        "expired_active_leases": work_runs.get("expired_active_leases"),
        "checkpoint_status": checkpoint.get("status"),
        "mission_total": command.get("total"),
        "pool": {
            "pre_ping": (production.get("storage_runtime") or {}).get("pre_ping"),
            "connection_failures_total": pool.get("connection_failures_total"),
            "stale_connections_discarded_total": pool.get(
                "stale_connections_discarded_total"
            ),
            "reconnects_total": pool.get("reconnects_total"),
            "acquire_timeouts_total": pool.get("acquire_timeouts_total"),
        },
    }


def run(base_url: str, *, timeout_seconds: float) -> dict[str, Any]:
    database_url = _dsn()
    if not database_url.startswith("postgresql"):
        raise RuntimeError("COMMAND_CENTER_DATABASE_URL must be PostgreSQL")
    control = psycopg2.connect(
        database_url,
        application_name="agent-system-connection-fault-drill",
    )
    control.autocommit = True
    client, headers, auth_mode = _auth_client(base_url)
    try:
        with control.cursor(cursor_factory=RealDictCursor) as cursor:
            facts_before = _fact_snapshot(cursor)
            leases_before = _active_leases(cursor)
            if any(leases_before.values()):
                raise RuntimeError(f"active leases block fault drill: {leases_before}")
            baseline = _sample(client, headers)
            if not baseline["functional"]:
                raise RuntimeError("baseline production health is not functionally ready")

            cursor.execute(
                """
                SELECT pid, pg_terminate_backend(pid) AS terminated
                FROM pg_stat_activity
                WHERE datname=current_database()
                  AND application_name='agent-system-command-center'
                  AND pid <> pg_backend_pid()
                ORDER BY pid
                """
            )
            terminated_rows = [dict(row) for row in cursor.fetchall()]
            terminated = sum(1 for row in terminated_rows if row.get("terminated"))
            if terminated < 1:
                raise RuntimeError("no agent-system PostgreSQL sessions were terminated")

            injected_at = time.monotonic()
            observations: list[dict[str, Any]] = []
            consecutive_healthy = 0
            recovery_seconds: float | None = None
            deadline = injected_at + timeout_seconds
            while time.monotonic() < deadline:
                sample = _sample(client, headers)
                sample["since_injection_seconds"] = round(
                    time.monotonic() - injected_at,
                    3,
                )
                observations.append(sample)
                if sample["functional"]:
                    consecutive_healthy += 1
                    if consecutive_healthy >= 3:
                        recovery_seconds = sample["since_injection_seconds"]
                        break
                else:
                    consecutive_healthy = 0
                time.sleep(0.5)

            facts_after = _fact_snapshot(cursor)
            leases_after = _active_leases(cursor)
    finally:
        client.close()
        control.close()

    final = observations[-1] if observations else {}
    rpo_zero = facts_before == facts_after
    healthy = bool(
        recovery_seconds is not None
        and rpo_zero
        and not any(leases_after.values())
        and final.get("pool", {}).get("pre_ping") is True
        and int(final.get("pool", {}).get("reconnects_total") or 0) >= 1
    )
    return {
        "schema_version": "command-center-database-fault-drill.v1",
        "checked_at": _now(),
        "healthy": healthy,
        "scope": "agent-system-connections-only",
        "auth_mode": auth_mode,
        "terminated_connections": terminated,
        "terminated_pids": [int(row["pid"]) for row in terminated_rows],
        "functional_recovery_seconds": recovery_seconds,
        "rpo_zero": rpo_zero,
        "active_leases_before": leases_before,
        "active_leases_after": leases_after,
        "facts_before": facts_before,
        "facts_after": facts_after,
        "baseline": baseline,
        "final": final,
        "observations": observations,
        "note": (
            "production_status may remain degraded during the five-minute incident "
            "visibility window even after functional recovery"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3021")
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    try:
        report = run(args.base_url, timeout_seconds=max(10, args.timeout_seconds))
    except Exception as exc:
        report = {
            "schema_version": "command-center-database-fault-drill.v1",
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
