"""
Agent OS control-plane API.

This router exposes a compact, mobile-friendly view of the current agent
system without replacing the existing project/agent APIs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from project_manager import project_manager
from unified_data_manager import unified_data_manager


router = APIRouter(prefix="/api/agent-os", tags=["agent-os"])

BASE_DIR = Path(__file__).resolve().parents[1]
AGENT_INSTANCES_FILE = BASE_DIR / "data" / "agent_instances.json"
AGENT_RUNNER_FILE = BASE_DIR / "data" / "agent_runner.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def _done(status: Any) -> bool:
    return str(status or "").lower() in {"done", "completed", "complete"}


def _active(status: Any) -> bool:
    return str(status or "").lower() in {"active", "busy", "running", "in_progress"}


def _flatten_tasks(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for project in projects:
        for task in project.get("tasks") or []:
            row = dict(task)
            row["project_id"] = project.get("id", "")
            row["project_name"] = project.get("name", "")
            rows.append(row)
    return rows


def _development_points(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for task in tasks:
        for point in task.get("development_points") or []:
            row = dict(point)
            row["task_id"] = task.get("id", "")
            row["task_title"] = task.get("title", "")
            row["project_id"] = task.get("project_id", "")
            row["project_name"] = task.get("project_name", "")
            points.append(row)
    return points


def _agent_nodes() -> list[dict[str, Any]]:
    try:
        document = unified_data_manager.get_agent_organization_document()
        return [
            node
            for node in document.get("nodes", [])
            if node.get("node_type") == "agent" and not node.get("hidden")
        ]
    except Exception:
        return []


def _agent_instances() -> list[dict[str, Any]]:
    store = _load_json(AGENT_INSTANCES_FILE, {})
    if isinstance(store, dict):
        return list(store.get("instances") or [])
    if isinstance(store, list):
        return store
    return []


def _runner_status() -> dict[str, Any]:
    runner = _load_json(AGENT_RUNNER_FILE, {})
    return runner if isinstance(runner, dict) else {}


def _recent_events(projects: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for project in projects:
        for log in project.get("logs") or []:
            rows.append(
                {
                    "time": log.get("created_at") or log.get("timestamp") or project.get("updated_at", ""),
                    "project_id": project.get("id", ""),
                    "project": project.get("name", ""),
                    "agent": log.get("agent_id", "system"),
                    "action": log.get("action", "event"),
                    "content": log.get("content", ""),
                }
            )
    rows.sort(key=lambda item: str(item.get("time", "")), reverse=True)
    return rows[:limit]


def _schema() -> dict[str, Any]:
    return {
        "version": "agent-os-control-plane-v1",
        "entities": {
            "Project": ["id", "name", "status", "progress", "owner_agent", "tasks", "design_doc"],
            "Task": ["id", "project_id", "title", "status", "progress", "assignee_agent", "development_points"],
            "DevelopmentPoint": ["id", "task_id", "title", "status", "weight", "acceptance_criteria"],
            "AgentTemplate": ["id", "name", "role", "skills", "memory_policy", "spawn_policy"],
            "AgentInstance": ["id", "template_id", "status", "project_id", "task_id", "claimed_at", "released_at"],
            "Skill": ["id", "name", "version", "permissions", "assigned_agents", "enabled"],
            "Memory": ["agent_id", "scope", "kind", "summary", "source", "updated_at"],
            "Run": ["id", "project_id", "task_id", "agent_instance_id", "status", "artifacts", "review"],
            "Event": ["id", "type", "source", "target", "payload", "created_at"],
        },
        "control_loops": [
            "项目经理拆解任务",
            "调度器匹配模板和空闲实例",
            "分身加载技能与任务上下文",
            "执行结果回写任务、日志、记忆",
            "项目经理依据状态继续分解下一轮",
        ],
    }


@router.get("/schema")
def get_agent_os_schema():
    return _schema()


@router.get("/mobile-summary")
def get_mobile_summary():
    projects = project_manager.list_projects()
    tasks = _flatten_tasks(projects)
    points = _development_points(tasks)
    agents = _agent_nodes()
    instances = _agent_instances()
    runner = _runner_status()

    open_projects = [p for p in projects if not _done(p.get("status"))]
    active_tasks = [t for t in tasks if not _done(t.get("status"))]
    blocked_tasks = [t for t in tasks if str(t.get("status", "")).lower() == "blocked"]
    running_instances = [i for i in instances if _active(i.get("status"))]
    idle_instances = [i for i in instances if str(i.get("status", "")).lower() in {"idle", "available"}]

    project_cards = sorted(
        [
            {
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "status": p.get("status", "unknown"),
                "progress": p.get("progress", 0),
                "owner_agent": p.get("owner_agent", ""),
                "task_total": len(p.get("tasks") or []),
                "task_open": len([t for t in p.get("tasks") or [] if not _done(t.get("status"))]),
                "updated_at": p.get("updated_at", ""),
            }
            for p in open_projects
        ],
        key=lambda item: (float(item.get("progress") or 0), item.get("updated_at", "")),
    )[:6]

    agent_cards = [
        {
            "id": node.get("agent_id") or node.get("id", ""),
            "name": node.get("name", ""),
            "title": node.get("title", ""),
            "emoji": node.get("emoji", ""),
            "status": "running"
            if any((i.get("template_id") == (node.get("agent_id") or node.get("id"))) and _active(i.get("status")) for i in instances)
            else "idle",
        }
        for node in agents[:12]
    ]

    return {
        "updated_at": _now_iso(),
        "schema": _schema()["version"],
        "summary": {
            "projects": {"total": len(projects), "open": len(open_projects)},
            "tasks": {"total": len(tasks), "open": len(active_tasks), "blocked": len(blocked_tasks)},
            "development_points": {
                "total": len(points),
                "done": len([p for p in points if _done(p.get("status"))]),
            },
            "agents": {"templates": len(agents), "instances": len(instances), "running": len(running_instances), "idle": len(idle_instances)},
            "runner": {
                "mode": runner.get("mode", "claim-only"),
                "queue": len(runner.get("queue") or []),
                "in_progress": len(runner.get("in_progress") or []),
            },
        },
        "projects": project_cards,
        "agents": agent_cards,
        "events": _recent_events(projects),
        "actions": [
            {"id": "review_open_projects", "label": "查看开放项目", "href": "/?view=tasks"},
            {"id": "inspect_agents", "label": "检查智能体", "href": "/?view=agents"},
            {"id": "open_full_console", "label": "打开完整控制台", "href": "/"},
        ],
    }


@router.get("/events")
def list_agent_os_events(limit: int = 30):
    limit = max(1, min(limit, 100))
    return {"events": _recent_events(project_manager.list_projects(), limit=limit)}
