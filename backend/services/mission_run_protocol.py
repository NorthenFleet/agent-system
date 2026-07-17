"""Project-owned mission run protocol shared by planning and simulation products."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


MAX_RUNS = 30
MAX_COMMANDS = 80
MAX_EVENTS = 120
MAX_ARTIFACTS = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def ensure_mission_protocol(
    project: dict[str, Any],
    integration: dict[str, Any],
    *,
    product_url: str,
) -> bool:
    """Create or migrate the project-owned mission and its product bindings."""
    changed = False
    project_id = str(project.get("id") or "")
    mission = integration.get("mission")
    if not isinstance(mission, dict):
        mission = {}
        changed = True

    defaults = {
        "id": _stable_id("mission", project_id),
        "project_id": project_id,
        "title": str(project.get("name") or "未命名任务"),
        "objective": str(project.get("description") or ""),
        "status": "bound" if integration.get("scenario_id") else "draft",
        "created_at": _now(),
    }
    for key, value in defaults.items():
        if not mission.get(key):
            mission[key] = value
            changed = True

    bindings = mission.get("bindings")
    if not isinstance(bindings, dict):
        bindings = {}
        changed = True
    expected = {
        "planning": {
            "product": "ai-planning",
            "name": "无人集群任务规划系统",
            "base_url": product_url,
            "scenario_id": integration.get("scenario_id") or "",
            "side": integration.get("side") or "red",
        },
        "simulation": {
            "product": "one-sim",
            "name": "无人集群仿真系统",
            "base_url": product_url,
            "mode": "embedded-planning-situation",
            "scenario_id": integration.get("scenario_id") or "",
        },
    }
    for binding_name, expected_binding in expected.items():
        current = bindings.get(binding_name)
        current = dict(current) if isinstance(current, dict) else {}
        for key, value in expected_binding.items():
            if current.get(key) != value:
                current[key] = value
                changed = True
        bindings[binding_name] = current
    mission["bindings"] = bindings
    integration["mission"] = mission
    if not isinstance(integration.get("runs"), list):
        integration["runs"] = []
        changed = True
    return changed


def update_binding(integration: dict[str, Any]) -> None:
    mission = integration.get("mission")
    if not isinstance(mission, dict):
        return
    mission["status"] = "bound"
    mission["updated_at"] = _now()
    bindings = mission.get("bindings") if isinstance(mission.get("bindings"), dict) else {}
    for name in ("planning", "simulation"):
        binding = bindings.get(name) if isinstance(bindings.get(name), dict) else {}
        binding.update({
            "scenario_id": integration.get("scenario_id") or "",
            "side": integration.get("side") or "red" if name == "planning" else binding.get("side"),
            "bound_at": integration.get("bound_at") or _now(),
        })
        if name == "simulation":
            binding.pop("side", None)
        bindings[name] = binding
    mission["bindings"] = bindings


def create_run(integration: dict[str, Any], *, actor: str) -> dict[str, Any]:
    mission = integration.get("mission") if isinstance(integration.get("mission"), dict) else {}
    run_id = f"mrun-{uuid.uuid4().hex[:12]}"
    run = {
        "id": run_id,
        "mission_id": mission.get("id"),
        "project_id": mission.get("project_id"),
        "correlation_id": f"corr-{uuid.uuid4().hex[:16]}",
        "scenario_id": integration.get("scenario_id"),
        "side": integration.get("side") or "red",
        "status": "starting",
        "created_at": _now(),
        "created_by": actor,
        "commands": [],
        "events": [],
        "artifacts": [],
    }
    runs = _rows(integration.get("runs"))
    runs.append(run)
    integration["runs"] = runs[-MAX_RUNS:]
    integration["current_run_id"] = run_id
    integration["run_id"] = run_id
    mission["status"] = "running"
    mission["current_run_id"] = run_id
    integration["mission"] = mission
    return run


def current_run(integration: dict[str, Any]) -> dict[str, Any] | None:
    run_id = integration.get("current_run_id") or integration.get("run_id")
    runs = integration.get("runs")
    if not isinstance(runs, list):
        return None
    return next((row for row in reversed(runs) if isinstance(row, dict) and row.get("id") == run_id), None)


def transition_run(integration: dict[str, Any], status: str, **updates: Any) -> dict[str, Any] | None:
    run = current_run(integration)
    if not run:
        return None
    run.update({"status": status, "updated_at": _now(), **updates})
    if status == "running" and not run.get("started_at"):
        run["started_at"] = _now()
    if status in {"stopped", "completed", "failed"} and not run.get("ended_at"):
        run["ended_at"] = _now()
    mission = integration.get("mission") if isinstance(integration.get("mission"), dict) else {}
    mission["status"] = status
    integration["mission"] = mission
    return run


def record_command(
    integration: dict[str, Any],
    name: str,
    *,
    status: str = "succeeded",
    target: str,
    detail: str = "",
) -> dict[str, Any] | None:
    run = current_run(integration)
    if not run:
        return None
    row = {
        "id": f"cmd-{uuid.uuid4().hex[:10]}",
        "name": name,
        "target": target,
        "status": status,
        "detail": detail[:500],
        "created_at": _now(),
        "correlation_id": run.get("correlation_id"),
    }
    commands = _rows(run.get("commands"))
    commands.append(row)
    run["commands"] = commands[-MAX_COMMANDS:]
    return row


def record_event(
    integration: dict[str, Any],
    event_type: str,
    *,
    source: str,
    summary: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    run = current_run(integration)
    if not run:
        return None
    compact_data = dict(data or {})
    fingerprint = hashlib.sha256(
        json.dumps([event_type, source, summary, compact_data], ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    events = _rows(run.get("events"))
    if events and events[-1].get("fingerprint") == fingerprint:
        events[-1]["observed_at"] = _now()
        events[-1]["observations"] = int(events[-1].get("observations") or 1) + 1
        run["events"] = events
        return events[-1]
    row = {
        "id": f"evt-{uuid.uuid4().hex[:10]}",
        "type": event_type,
        "source": source,
        "summary": summary[:500],
        "data": compact_data,
        "fingerprint": fingerprint,
        "created_at": _now(),
        "observations": 1,
        "correlation_id": run.get("correlation_id"),
    }
    events.append(row)
    run["events"] = events[-MAX_EVENTS:]
    return row


def record_artifact(
    integration: dict[str, Any],
    artifact_type: str,
    *,
    source: str,
    title: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    run = current_run(integration)
    if not run:
        return None
    row = {
        "id": f"artifact-{uuid.uuid4().hex[:10]}",
        "type": artifact_type,
        "source": source,
        "title": title[:200],
        "metadata": dict(metadata or {}),
        "created_at": _now(),
        "correlation_id": run.get("correlation_id"),
    }
    artifacts = _rows(run.get("artifacts"))
    if artifacts and artifacts[-1].get("type") == artifact_type and artifacts[-1].get("metadata") == row["metadata"]:
        artifacts[-1]["observed_at"] = _now()
        return artifacts[-1]
    artifacts.append(row)
    run["artifacts"] = artifacts[-MAX_ARTIFACTS:]
    return row


def protocol_summary(integration: dict[str, Any]) -> dict[str, Any]:
    run = current_run(integration)
    return {
        "mission": integration.get("mission") if isinstance(integration.get("mission"), dict) else {},
        "current_run": run or {},
        "run_count": len(_rows(integration.get("runs"))),
    }
