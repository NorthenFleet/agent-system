#!/usr/bin/env python3
"""Pause one idle worker, verify degraded health, then always resume it."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(WORKSPACE_ROOT / ".env", override=False)

from services.command_center_service import command_center_service  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client(base_url: str) -> tuple[httpx.Client, dict[str, str]]:
    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=5)
    settings = client.get("/api/v2/auth/settings")
    settings.raise_for_status()
    token = os.getenv("COMMAND_CENTER_SMOKE_TOKEN", "").strip()
    if not token and not bool(settings.json().get("login_enabled")):
        session = client.post("/api/v2/auth/development-session")
        session.raise_for_status()
        token = str(session.json().get("access_token") or "")
    if not token:
        client.close()
        raise RuntimeError("COMMAND_CENTER_SMOKE_TOKEN is required when login is enabled")
    return client, {"Authorization": f"Bearer {token}"}


def _health(client: httpx.Client, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/api/v3/command-center/production-health", headers=headers)
    response.raise_for_status()
    payload = response.json()
    workers = payload.get("workers") or {}
    return {
        "status": payload.get("status"),
        "workers_status": workers.get("status"),
        "workers_live": workers.get("live"),
        "workers_required": workers.get("required"),
        "workers_stale": workers.get("stale"),
        "workers": workers.get("workers") or [],
    }


def _active_leases(worker_id: str) -> dict[str, int]:
    statements = {
        "steps": (
            "SELECT COUNT(*) AS count FROM mission_steps "
            "WHERE status='running' AND lease_owner=?"
        ),
        "workflows": (
            "SELECT COUNT(*) AS count FROM workflow_runs "
            "WHERE status IN ('pending','running','resume_pending') AND lease_owner=?"
        ),
        "compensations": (
            "SELECT COUNT(*) AS count FROM mission_compensations "
            "WHERE status='running' AND lease_owner=?"
        ),
        "outbox": (
            "SELECT COUNT(*) AS count FROM notification_outbox "
            "WHERE status='sending' AND lock_owner=?"
        ),
    }
    with command_center_service.connect() as connection:
        return {
            key: int(connection.execute(sql, (worker_id,)).fetchone()["count"] or 0)
            for key, sql in statements.items()
        }


def run(base_url: str, worker_id: str) -> dict[str, Any]:
    client, headers = _client(base_url)
    paused = False
    try:
        before = _health(client, headers)
        target = next(
            (item for item in before["workers"] if item.get("id") == worker_id),
            None,
        )
        if not target or not target.get("live"):
            raise RuntimeError(f"worker is not live: {worker_id}")
        pid = int((target.get("metadata") or {}).get("pid") or 0)
        if pid <= 1:
            raise RuntimeError(f"worker PID is invalid: {pid}")
        leases = _active_leases(worker_id)
        if any(leases.values()):
            raise RuntimeError(f"worker owns active leases: {leases}")

        os.kill(pid, signal.SIGSTOP)
        paused = True
        wait_seconds = int(
            max(
                7,
                int(os.getenv("COMMAND_CENTER_WORKER_STALE_SECONDS", "20")) + 2,
            )
        )
        time.sleep(wait_seconds)
        degraded = _health(client, headers)
    finally:
        if paused:
            os.kill(pid, signal.SIGCONT)

    recovered: dict[str, Any] = {}
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        time.sleep(1)
        recovered = _health(client, headers)
        if recovered.get("status") == "ready" and recovered.get("workers_stale") == 0:
            break
    client.close()
    healthy = bool(
        before.get("status") == "ready"
        and not any(leases.values())
        and degraded.get("status") == "degraded"
        and degraded.get("workers_status") == "degraded"
        and int(degraded.get("workers_live") or 0)
        < int(degraded.get("workers_required") or 1)
        and int(degraded.get("workers_stale") or 0) >= 1
        and recovered.get("status") == "ready"
        and recovered.get("workers_status") == "ready"
        and int(recovered.get("workers_stale") or 0) == 0
    )
    return {
        "schema_version": "command-center-worker-failover-drill.v1",
        "checked_at": _now(),
        "healthy": healthy,
        "target_worker": worker_id,
        "target_pid": pid,
        "active_leases_before_pause": leases,
        "before": before,
        "degraded": degraded,
        "recovered": recovered,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3021")
    parser.add_argument("--worker-id", default="command-center:worker-2")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    try:
        report = run(args.base_url, args.worker_id)
    except Exception as exc:
        report = {
            "schema_version": "command-center-worker-failover-drill.v1",
            "checked_at": _now(),
            "healthy": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    finally:
        command_center_service.repository.close()
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
