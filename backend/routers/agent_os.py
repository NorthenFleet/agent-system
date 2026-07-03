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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from project_manager import project_manager
from unified_data_manager import unified_data_manager


router = APIRouter(prefix="/api/agent-os", tags=["agent-os"])

BASE_DIR = Path(__file__).resolve().parents[1]
AGENT_INSTANCES_FILE = BASE_DIR / "data" / "agent_instances.json"
AGENT_RUNNER_FILE = BASE_DIR / "data" / "agent_runner.json"


class IterationRequest(BaseModel):
    requested_by: str = "mobile-command"
    note: str = "移动端请求项目经理进入下一轮迭代"


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


def _role_template(agent_id: str, title: str = "") -> str:
    value = f"{agent_id} {title}".lower()
    if "donatello" in value or "前端" in title or "页面" in title:
        return "donatello"
    if "raphael" in value or "后端" in title or "api" in value:
        return "raphael"
    if "michelangelo" in value or "测试" in title or "验证" in title:
        return "michelangelo"
    return "leonardo"


def _attention_items(projects: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for project in projects:
        design_doc = project.get("design_doc") or {}
        if design_doc and design_doc.get("status") in {"draft", "review"}:
            rows.append(
                {
                    "kind": "design_doc",
                    "severity": "review",
                    "project_id": project.get("id", ""),
                    "project_name": project.get("name", ""),
                    "title": f"设计文档待确认：{project.get('name', '')}",
                    "description": design_doc.get("summary", "项目设计文档需要项目经理确认后继续拆解。"),
                    "href": f"/?view=tasks&project={project.get('id', '')}",
                }
            )
        for task in project.get("tasks") or []:
            status = str(task.get("status", "")).lower()
            if status == "blocked":
                rows.append(
                    {
                        "kind": "blocked_task",
                        "severity": "blocked",
                        "project_id": project.get("id", ""),
                        "project_name": project.get("name", ""),
                        "task_id": task.get("id", ""),
                        "title": task.get("title", "阻塞任务"),
                        "description": task.get("description", "任务阻塞，需要人工处理。"),
                        "href": f"/?view=tasks&project={project.get('id', '')}&task={task.get('id', '')}",
                    }
                )
            if status in {"todo", "pending", "assigned"} and not task.get("assignee_agent"):
                rows.append(
                    {
                        "kind": "unassigned_task",
                        "severity": "assign",
                        "project_id": project.get("id", ""),
                        "project_name": project.get("name", ""),
                        "task_id": task.get("id", ""),
                        "title": task.get("title", "待分配任务"),
                        "description": "任务尚未匹配执行智能体，可请求弹性分身或进入完整看板分配。",
                        "href": f"/?view=tasks&project={project.get('id', '')}&task={task.get('id', '')}",
                    }
                )
    rank = {"blocked": 0, "review": 1, "assign": 2}
    rows.sort(key=lambda item: (rank.get(item["severity"], 9), item.get("project_name", ""), item.get("title", "")))
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
    attention = _attention_items(projects)

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
        "attention": attention,
        "events": _recent_events(projects),
        "actions": [
            {
                "id": "request_iteration",
                "label": "请求下一轮迭代",
                "method": "POST",
                "endpoint": f"/api/agent-os/projects/{project_cards[0]['id']}/request-iteration" if project_cards else "",
                "disabled": not bool(project_cards),
            },
            {
                "id": "spawn_agent",
                "label": "请求弹性分身",
                "method": "POST",
                "endpoint": "/api/v3/agents/spawn",
                "body": {
                    "requested_by": "mobile-command",
                    "base_agent_id": _role_template((active_tasks[0].get("assignee_agent") if active_tasks else "") or "leonardo", active_tasks[0].get("title", "") if active_tasks else ""),
                    "project_id": active_tasks[0].get("project_id", "") if active_tasks else "",
                    "task_id": active_tasks[0].get("id", "") if active_tasks else "",
                    "reason": "移动端请求弹性智能体支援当前开放任务",
                },
                "disabled": not bool(active_tasks),
            },
            {"id": "review_open_projects", "label": "查看开放项目", "href": "/?view=tasks"},
            {"id": "inspect_agents", "label": "检查智能体", "href": "/?view=agents"},
            {"id": "open_full_console", "label": "打开完整控制台", "href": "/"},
        ],
    }


@router.get("/events")
def list_agent_os_events(limit: int = 30):
    limit = max(1, min(limit, 100))
    return {"events": _recent_events(project_manager.list_projects(), limit=limit)}


@router.get("/attention")
def list_attention_items(limit: int = 30):
    limit = max(1, min(limit, 100))
    return {"items": _attention_items(project_manager.list_projects(), limit=limit)}


@router.post("/projects/{project_id}/request-iteration", status_code=201)
def request_project_iteration(project_id: str, req: IterationRequest = IterationRequest()):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = project_manager.decompose_project(
        project_id,
        {
            "agent_id": req.requested_by,
            "reasoning_summary": req.note,
            "new_tasks": [],
            "updated_tasks": [],
            "new_development_points": [],
            "updated_development_points": [],
            "project_updates": {"context": {"mobile_iteration_requested_at": _now_iso()}},
        },
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to request iteration")
    return {"status": "recorded", "project_id": project_id, "result": result}
