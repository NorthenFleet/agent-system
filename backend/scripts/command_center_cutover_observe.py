#!/usr/bin/env python3
"""Observe the live 3021 cutover for a bounded post-restart window."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def observe(
    base_url: str,
    *,
    samples: int,
    interval_seconds: float,
    expected_connection_failures: int = 0,
    expected_reconnects: int = 0,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=5) as client:
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
                "Protected observation requires COMMAND_CENTER_SMOKE_TOKEN when login is enabled"
            )
        headers = {"Authorization": f"Bearer {token}"}
        for index in range(samples):
            if index:
                time.sleep(interval_seconds)
            try:
                public = client.get("/health")
                production = client.get(
                    "/api/v3/command-center/production-health",
                    headers=headers,
                )
                command = client.get(
                    "/api/v3/command-center/health",
                    headers=headers,
                )
                public.raise_for_status()
                production.raise_for_status()
                command.raise_for_status()
                prod = production.json()
                pool = (prod.get("storage_runtime") or {}).get("pool") or {}
                work_runs = prod.get("work_runs") or {}
                checkpoint = (
                    (prod.get("workflow_runtime") or {}).get("checkpoint_storage") or {}
                )
                workers = prod.get("workers") or {}
                observations.append(
                    {
                        "sample": index + 1,
                        "observed_at": _now(),
                        "public_status": public.json().get("status"),
                        "production_status": prod.get("status"),
                        "storage_backend": (prod.get("storage") or {}).get("backend"),
                        "pool_status": (prod.get("storage_runtime") or {}).get("status"),
                        "pool_in_use": pool.get("in_use"),
                        "pool_peak_in_use": pool.get("peak_in_use"),
                        "pool_acquire_timeouts": pool.get("acquire_timeouts_total"),
                        "pool_connection_failures": pool.get("connection_failures_total"),
                        "pool_stale_connections_discarded": pool.get(
                            "stale_connections_discarded_total"
                        ),
                        "pool_reconnects": pool.get("reconnects_total"),
                        "expired_active_leases": work_runs.get("expired_active_leases"),
                        "checkpoint_status": checkpoint.get("status"),
                        "workers_status": workers.get("status"),
                        "workers_live": workers.get("live"),
                        "workers_required": workers.get("required"),
                        "workers_stale": workers.get("stale"),
                        "mission_total": command.json().get("total"),
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "sample": str(index + 1),
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                )
    healthy_samples = [
        item
        for item in observations
        if item["public_status"] == "ok"
        and item["production_status"] == "ready"
        and item["storage_backend"] == "postgresql"
        and item["pool_status"] == "ready"
        and int(item["pool_acquire_timeouts"] or 0) == 0
        and int(item["pool_connection_failures"] or 0) == expected_connection_failures
        and int(item["pool_reconnects"] or 0) == expected_reconnects
        and int(item["expired_active_leases"] or 0) == 0
        and item["checkpoint_status"] == "ready"
        and item["workers_status"] == "ready"
        and int(item["workers_live"] or 0) >= int(item["workers_required"] or 1)
        and int(item["workers_stale"] or 0) == 0
    ]
    return {
        "schema_version": "command-center-cutover-observation.v2",
        "checked_at": _now(),
        "healthy": len(healthy_samples) == samples and not errors,
        "auth_mode": auth_mode,
        "requested_samples": samples,
        "successful_samples": len(observations),
        "healthy_samples": len(healthy_samples),
        "interval_seconds": interval_seconds,
        "expected_connection_failures": expected_connection_failures,
        "expected_reconnects": expected_reconnects,
        "errors": errors,
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3021")
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--interval-seconds", type=float, default=5)
    parser.add_argument("--expected-connection-failures", type=int, default=0)
    parser.add_argument("--expected-reconnects", type=int, default=0)
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    report = observe(
        args.base_url,
        samples=max(1, args.samples),
        interval_seconds=max(0, args.interval_seconds),
        expected_connection_failures=max(0, args.expected_connection_failures),
        expected_reconnects=max(0, args.expected_reconnects),
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
