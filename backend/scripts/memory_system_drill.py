#!/usr/bin/env python3
"""Run non-destructive memory failure drills against production decision logic."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.v2_models import Base, Notification, User
from scripts.memory_system_gate import write_status
from services.memory_system_gate import (
    enforce_bridge_deployment,
    evaluate_memory_report,
    execution_failure_status,
)
from services.memory_system_health_status import publish_memory_health_notification


DEFAULT_OUTPUT = BACKEND_ROOT / "data" / "memory-system-drill.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report() -> dict[str, Any]:
    return {
        "schema_version": "memory-introspection.v1",
        "status": "ready",
        "authority": {"system": "3021-unified-memory"},
        "scope": {"agent_id": "optimus", "user_scoped": True},
        "identity": {"channel": "feishu", "bound": True, "display_name": "演练用户"},
        "counts": {"profile": 1, "profile_facts": 1, "project_memories": 1, "agent_memories": 1},
        "remembered_items": [{"scope": "profile"}],
        "retrieval": {"citations": ["synthetic:citation"]},
        "channels": {
            "local_markdown": {"status": "ready"},
            "openclaw_lexical_index": {"status": "ready"},
            "approved_graph_projection": {"status": "ready"},
            "native_private_graph": {"status": "ready"},
        },
        "degraded_channels": [],
    }


def _contract() -> dict[str, Any]:
    return {
        "minimum_counts": {"profile": 1, "profile_facts": 1, "project_memories": 1, "agent_memories": 1},
        "minimum_remembered_items": 1,
        "required_channels": {
            "local_markdown": ["ready"],
            "openclaw_lexical_index": ["ready"],
            "approved_graph_projection": ["ready"],
            "native_private_graph": ["ready"],
        },
        "max_degraded_channels": 0,
    }


def _drill_3021_unavailable() -> dict[str, Any]:
    status = execution_failure_status(
        case_id="synthetic-3021-unavailable",
        error="memory endpoint unavailable: synthetic connection refused",
        attempt=2,
        attempts_configured=2,
        checked_at=_now(),
    )
    passed = (
        status["healthy"] is False
        and status["failures"][0]["check"] == "gate_execution"
        and "remembered_items" not in status
    )
    return {"passed": passed, "evidence": {"failure_check": status["failures"][0]["check"], "fail_closed": not status["healthy"]}}


def _drill_identity_unbound() -> dict[str, Any]:
    report = _report()
    report["identity"]["bound"] = False
    result = evaluate_memory_report(report, _contract())
    checks = [item["check"] for item in result["failures"]]
    return {"passed": result["healthy"] is False and "identity.bound" in checks, "evidence": {"failure_checks": checks}}


def _drill_bridge_mismatch() -> dict[str, Any]:
    status = {"healthy": True, "failures": [], "summary": {}}
    enforce_bridge_deployment(
        status,
        {
            "ready": False,
            "plugin_version": "synthetic-mismatch",
            "bridge_schema": "approved-projection.v1",
            "failed_checks": ["synthetic source hash mismatch"],
        },
    )
    checks = [item["check"] for item in status["failures"]]
    return {"passed": status["healthy"] is False and "bridge_deployment" in checks, "evidence": {"failure_checks": checks}}


def _drill_notification_recovery_dedupe() -> dict[str, Any]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add(User(username="drill-admin", password_hash="not-used", display_name="演练管理员", role="admin", is_active=True))
        session.commit()
        baseline = publish_memory_health_notification(session, {"healthy": True, "checked_at": _now(), "failures": []})
        alert = publish_memory_health_notification(
            session,
            {"healthy": False, "checked_at": _now(), "failures": [{"check": "synthetic.failure"}]},
        )
        duplicate = publish_memory_health_notification(
            session,
            {"healthy": False, "checked_at": _now(), "failures": [{"check": "synthetic.failure"}]},
        )
        recovery = publish_memory_health_notification(session, {"healthy": True, "checked_at": _now(), "failures": []})
        notification_count = session.query(Notification).count()
        passed = (
            baseline["notifications_created"] == 0
            and alert["notifications_created"] == 1
            and duplicate["notifications_created"] == 0
            and recovery["notifications_created"] == 1
            and notification_count == 2
        )
        return {
            "passed": passed,
            "evidence": {
                "baseline": baseline["status"],
                "alert": alert["status"],
                "duplicate": duplicate["status"],
                "recovery": recovery["status"],
                "temporary_notifications": notification_count,
            },
        }
    finally:
        session.close()
        engine.dispose()


def run_drills() -> dict[str, Any]:
    scenarios: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("3021_unavailable", _drill_3021_unavailable),
        ("identity_unbound", _drill_identity_unbound),
        ("bridge_version_mismatch", _drill_bridge_mismatch),
        ("notification_recovery_dedupe", _drill_notification_recovery_dedupe),
    ]
    results: list[dict[str, Any]] = []
    for name, drill in scenarios:
        try:
            result = drill()
            results.append({"name": name, "passed": result.get("passed") is True, "evidence": result.get("evidence") or {}})
        except Exception as exc:
            results.append({"name": name, "passed": False, "evidence": {"error": str(exc)[:500]}})
    failed = [item["name"] for item in results if not item["passed"]]
    return {
        "schema_version": "memory-system-drill.v1",
        "checked_at": _now(),
        "healthy": not failed,
        "summary": {
            "mode": "synthetic-non-destructive",
            "total_scenarios": len(results),
            "passed_scenarios": len(results) - len(failed),
            "failed_scenarios": failed,
        },
        "failures": [
            {"check": f"drill.{name}", "expected": "passed", "actual": "failed"}
            for name in failed
        ],
        "scenarios": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    status = run_drills()
    write_status(args.output, status)
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status["healthy"] else 2


if __name__ == "__main__":
    sys.exit(main())
