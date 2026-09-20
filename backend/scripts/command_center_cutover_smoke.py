#!/usr/bin/env python3
"""Verify a live 3021 PostgreSQL cutover without leaving business canary data."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
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


def _live_checks(base_url: str) -> dict[str, Any]:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=5) as client:
        public_health = client.get("/health")
        public_health.raise_for_status()
        settings = client.get("/api/v2/auth/settings")
        settings.raise_for_status()
        login_enabled = bool(settings.json().get("login_enabled"))
        token = os.getenv("COMMAND_CENTER_SMOKE_TOKEN", "").strip()
        auth_mode = "configured-token"
        if not token and not login_enabled:
            session = client.post("/api/v2/auth/development-session")
            session.raise_for_status()
            token = str(session.json().get("access_token") or "")
            auth_mode = "development-session"
        if not token:
            raise RuntimeError(
                "Protected live smoke requires COMMAND_CENTER_SMOKE_TOKEN when login is enabled"
            )
        headers = {"Authorization": f"Bearer {token}"}
        command_health = client.get("/api/v3/command-center/health", headers=headers)
        command_health.raise_for_status()
        production_health = client.get(
            "/api/v3/command-center/production-health",
            headers=headers,
        )
        production_health.raise_for_status()
        workflow = client.get(
            "/api/v3/command-center/workflow-runtime",
            headers=headers,
        )
        workflow.raise_for_status()
    command_payload = command_health.json()
    production_payload = production_health.json()
    workflow_payload = workflow.json()
    return {
        "public_health": public_health.json(),
        "auth_mode": auth_mode,
        "command_center": {
            "status": command_payload.get("status"),
            "storage_backend": (command_payload.get("storage") or {}).get("backend"),
            "mission_total": command_payload.get("total"),
            "active": command_payload.get("active"),
        },
        "production": {
            "status": production_payload.get("status"),
            "storage_backend": (production_payload.get("storage") or {}).get("backend"),
            "pool_status": (production_payload.get("storage_runtime") or {}).get("status"),
            "expired_active_leases": (production_payload.get("work_runs") or {}).get(
                "expired_active_leases"
            ),
            "checkpoint_status": (
                (production_payload.get("workflow_runtime") or {}).get(
                    "checkpoint_storage"
                )
                or {}
            ).get("status"),
            "workers": production_payload.get("workers") or {},
        },
        "workflow": {
            "checkpoint_backend": (workflow_payload.get("langgraph") or {}).get(
                "checkpoint_backend"
            ),
            "checkpoint_status": (workflow_payload.get("checkpoint_storage") or {}).get(
                "status"
            ),
        },
    }


def _transient_write_check() -> dict[str, Any]:
    canary_id = f"cutover-smoke-{uuid.uuid4().hex}"
    now = _now()
    with command_center_service.connect(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO work_runs
            (id, dispatch_id, status, attempt, idempotency_key, correlation_id,
             input_context, execution_result, metrics, created_at, updated_at)
            VALUES (?, ?, 'claimed', 1, ?, ?, '{}', '{}', '{}', ?, ?)
            """,
            (canary_id, canary_id, canary_id, canary_id, now, now),
        )
        inserted = connection.execute(
            "SELECT id FROM work_runs WHERE id=?",
            (canary_id,),
        ).fetchone()
        connection.execute("DELETE FROM work_runs WHERE id=?", (canary_id,))
    with command_center_service.connect() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS count FROM work_runs WHERE id=?",
            (canary_id,),
        ).fetchone()
    return {
        "insert_observed": bool(inserted),
        "cleanup_verified": int(remaining["count"] or 0) == 0,
        "canary_persisted": False,
    }


def run(base_url: str) -> dict[str, Any]:
    live = _live_checks(base_url)
    write = _transient_write_check()
    checks = {
        "public_health_ok": live["public_health"].get("status") == "ok",
        "live_storage_postgresql": live["command_center"]["storage_backend"]
        == "postgresql",
        "production_health_ready": live["production"]["status"] == "ready",
        "pool_ready": live["production"]["pool_status"] == "ready",
        "expired_leases_zero": live["production"]["expired_active_leases"] == 0,
        "checkpoint_ready": live["production"]["checkpoint_status"] == "ready",
        "workflow_checkpoint_postgresql": live["workflow"]["checkpoint_backend"]
        == "postgresql",
        "required_workers_live": int(
            live["production"]["workers"].get("live") or 0
        )
        >= int(live["production"]["workers"].get("required") or 1),
        "stale_workers_zero": int(
            live["production"]["workers"].get("stale") or 0
        )
        == 0,
        "transient_write_succeeded": write["insert_observed"] is True,
        "transient_write_cleaned": write["cleanup_verified"] is True,
    }
    return {
        "schema_version": "command-center-cutover-smoke.v1",
        "checked_at": _now(),
        "healthy": all(checks.values()),
        "checks": checks,
        "live": live,
        "write": write,
        "storage_runtime": command_center_service.storage_runtime_metrics(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3021")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    try:
        report = run(args.base_url)
    except Exception as exc:
        report = {
            "schema_version": "command-center-cutover-smoke.v1",
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
