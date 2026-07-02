"""
V3 project/task/development-point API for agent-driven development iteration.
"""

import os
import json
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from data_manager import data_manager
from project_manager import project_manager
from knowledge_manager import knowledge_manager
from openclaw_integration import openclaw_integration
from unified_data_manager import unified_data_manager
import skill_manager


router = APIRouter(prefix="/api/v3", tags=["projects-v3"])

BASE_DIR = Path(__file__).resolve().parents[1]
AGENT_ORGANIZATION_FILE = BASE_DIR / "data" / "agent_organization.json"
AGENT_TEMPLATES_FILE = BASE_DIR / "data" / "agent_templates.json"
AGENT_INSTANCES_FILE = BASE_DIR / "data" / "agent_instances.json"
AGENT_RUNNER_FILE = BASE_DIR / "data" / "agent_runner.json"
OPENCLAW_WORKSPACE = Path.home() / ".openclaw" / "workspace"
OPENCLAW_AGENTS_DIR = OPENCLAW_WORKSPACE / "agents"
NINJA_TURTLES_QUEUE_FILE = OPENCLAW_AGENTS_DIR / "ninja-turtles" / "dev-loop" / "queue.json"


class DesignDocument(BaseModel):
    id: Optional[str] = None
    project_id: Optional[str] = None
    version: int = 1
    status: str = "draft"
    summary: str = ""
    usage_requirements: list[Any] = Field(default_factory=list)
    data_structure: dict[str, Any] = Field(default_factory=dict)
    system_architecture: dict[str, Any] = Field(default_factory=dict)
    system_functions: list[Any] = Field(default_factory=list)
    api_interfaces: list[Any] = Field(default_factory=list)
    task_breakdown_guidance: list[Any] = Field(default_factory=list)
    parallel_tasks: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    changelog: list[Any] = Field(default_factory=list)
    author_agent: str = "project-manager"
    approved_by: str = ""
    approved_at: Optional[str] = None
    change_summary: Optional[str] = None


class DesignDocumentUpdate(BaseModel):
    status: Optional[str] = None
    summary: Optional[str] = None
    usage_requirements: Optional[list[Any]] = None
    data_structure: Optional[dict[str, Any]] = None
    system_architecture: Optional[dict[str, Any]] = None
    system_functions: Optional[list[Any]] = None
    api_interfaces: Optional[list[Any]] = None
    task_breakdown_guidance: Optional[list[Any]] = None
    parallel_tasks: Optional[list[Any]] = None
    risks: Optional[list[Any]] = None
    author_agent: Optional[str] = None
    change_summary: Optional[str] = None


class DesignDocumentRevise(BaseModel):
    agent_id: str = "project-manager"
    change_summary: str = "项目设计文档修订"
    status: str = "draft"
    updates: dict[str, Any] = Field(default_factory=dict)


class ApproveDesignDocumentRequest(BaseModel):
    agent_id: str = "project-manager"


class ProjectCreate(BaseModel):
    id: Optional[str] = None
    name: str
    project_type: str = "software"
    type: Optional[str] = None
    description: str = ""
    status: str = "planning"
    priority: str = "medium"
    owner_agent: str = "optimus"
    progress: float = 0
    current_phase: str = "planning"
    context: dict[str, Any] = Field(default_factory=dict)
    design_doc: Optional[DesignDocument] = None
    document_spec: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    project_type: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner_agent: Optional[str] = None
    progress: Optional[float] = None
    current_phase: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    document_spec: Optional[dict[str, Any]] = None


class DevelopmentPointCreate(BaseModel):
    id: Optional[str] = None
    task_id: Optional[str] = None
    title: str
    description: str = ""
    status: str = "todo"
    weight: float = 1
    completion_evidence: str = ""
    checklist: list[str] = Field(default_factory=list)
    assigned_agent: str = ""


class DevelopmentPointUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    weight: Optional[float] = None
    completion_evidence: Optional[str] = None
    checklist: Optional[list[str]] = None
    assigned_agent: Optional[str] = None


class TaskCreate(BaseModel):
    id: Optional[str] = None
    type: str = "development"
    title: str
    description: str = ""
    assignee_agent: str = ""
    assignee_agent_id: str = ""
    status: str = "todo"
    progress: float = 0
    priority: str = "medium"
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    development_points: list[DevelopmentPointCreate] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_agent: Optional[str] = None
    assignee_agent_id: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = None
    priority: Optional[str] = None
    dependencies: Optional[list[str]] = None
    acceptance_criteria: Optional[list[str]] = None
    context: Optional[dict[str, Any]] = None
    result_summary: Optional[str] = None



class AgentSkillsUpdate(BaseModel):
    skill_ids: list[str] = Field(default_factory=list)


class AssignRequest(BaseModel):
    assignee_agent: str


class LogCreate(BaseModel):
    task_id: Optional[str] = None
    agent_id: str = "system"
    action: str = "note"
    content: str


class ProjectChatRequest(BaseModel):
    agent_id: str = "optimus"
    message: str
    intent: str = "chat"
    task_id: str = ""
    chapter_id: str = ""
    role: str = "user"
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ProjectAgentActionRequest(BaseModel):
    agent_id: str = "optimus"
    action_type: str = "note"
    instruction: str = ""
    task_id: str = ""
    chapter_id: str = ""
    task_title: str = ""
    task_type: str = ""
    assignee_agent: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class SoftwareSpecUpdate(BaseModel):
    requirements: Optional[list[Any]] = None
    design_doc: Optional[dict[str, Any]] = None
    architecture: Optional[dict[str, Any]] = None
    database_design: Optional[dict[str, Any]] = None
    api_design: Optional[list[Any]] = None
    frontend_design: Optional[dict[str, Any]] = None
    test_plan: Optional[list[Any]] = None
    deployment_plan: Optional[list[Any]] = None
    agent_id: str = "project-manager"


class DocumentSectionCreate(BaseModel):
    id: Optional[str] = None
    parent_id: str = ""
    title: str
    summary: str = ""
    main_content: str = ""
    content_brief: str = ""
    key_points: list[str] = Field(default_factory=list)
    images: list[Any] = Field(default_factory=list)
    status: str = "planning"
    assigned_agent: str = ""
    assigned_agent_id: str = ""
    order_index: Optional[int] = None
    agent_id: str = "project-manager"


class DocumentSectionUpdate(BaseModel):
    parent_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    main_content: Optional[str] = None
    content_brief: Optional[str] = None
    key_points: Optional[list[str]] = None
    images: Optional[list[Any]] = None
    status: Optional[str] = None
    assigned_agent: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    order_index: Optional[int] = None
    agent_id: str = "project-manager"


class DocumentAssetCreate(BaseModel):
    id: Optional[str] = None
    chapter_id: str = ""
    section_id: str = ""
    chapter_title: str = ""
    type: str = "image"
    title: str
    description: str = ""
    file_path: str = ""
    status: str = "planned"
    order_index: Optional[int] = None
    agent_id: str = "project-manager"


class DocumentAssetUpdate(BaseModel):
    chapter_id: Optional[str] = None
    section_id: Optional[str] = None
    chapter_title: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    file_path: Optional[str] = None
    status: Optional[str] = None
    order_index: Optional[int] = None
    agent_id: str = "project-manager"


class DecomposeRequest(BaseModel):
    reasoning_summary: str = ""
    agent_id: str = "project-manager"
    new_tasks: list[TaskCreate] = Field(default_factory=list)
    updated_tasks: list[dict[str, Any]] = Field(default_factory=list)
    project_updates: dict[str, Any] = Field(default_factory=dict)
    new_development_points: list[DevelopmentPointCreate] = Field(default_factory=list)
    updated_development_points: list[dict[str, Any]] = Field(default_factory=list)


class CompletePointRequest(BaseModel):
    agent_id: str
    completion_evidence: str = ""
    result_summary: str = ""


class PointTransitionRequest(BaseModel):
    agent_id: str = ""
    reason: str = ""
    completion_evidence: str = ""
    result_summary: str = ""


class KnowledgeLinkRequest(BaseModel):
    node_id: str
    title: str = ""
    type: str = ""
    path: str = ""
    relation: str = "related"
    reason: str = ""
    confirmed_by: str = "project-manager"


class AgentSpawnRequest(BaseModel):
    requested_by: str
    base_agent_id: str
    project_id: str = ""
    task_id: str = ""
    development_point_id: str = ""
    reason: str = ""
    release_policy: str = "task_completed"
    instance_id: Optional[str] = None


class AgentReleaseRequest(BaseModel):
    released_by: str = "scheduler"
    reason: str = "manual_release"


class AgentCompleteRequest(BaseModel):
    completed_by: str = "scheduler"
    result_summary: str = ""
    memory_summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class AgentRunnerTickRequest(BaseModel):
    instance_id: Optional[str] = None
    execute: bool = False
    max_seconds: int = Field(default=600, ge=10, le=3600)


def _model_dict(model: BaseModel, exclude_unset: bool = False) -> dict:
    return model.model_dump(exclude_unset=exclude_unset)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value).strip().lower()).strip("-")


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON data in {path.name}: {exc}") from exc


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_agent_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": "leonardo",
            "name": "李奥纳多",
            "role": "架构师 / 开发负责人",
            "team": "ninja_turtles",
            "spawnable": True,
            "capabilities": ["架构设计", "技术方案", "任务拆解", "代码评审"],
            "memory_policy": {"long_term_owner": "leonardo", "project_memory": True, "instance_short_memory": True},
            "default_release_policy": "task_completed",
        },
        {
            "id": "raphael",
            "name": "拉斐尔",
            "role": "后端开发",
            "team": "ninja_turtles",
            "spawnable": True,
            "capabilities": ["后端开发", "API 实现", "数据模型", "接口联调"],
            "memory_policy": {"long_term_owner": "raphael", "project_memory": True, "instance_short_memory": True},
            "default_release_policy": "task_completed",
        },
        {
            "id": "donatello",
            "name": "多纳泰罗",
            "role": "前端开发",
            "team": "ninja_turtles",
            "spawnable": True,
            "capabilities": ["前端开发", "页面实现", "组件集成", "交互联调"],
            "memory_policy": {"long_term_owner": "donatello", "project_memory": True, "instance_short_memory": True},
            "default_release_policy": "task_completed",
        },
        {
            "id": "michelangelo",
            "name": "米开朗基罗",
            "role": "测试工程",
            "team": "ninja_turtles",
            "spawnable": True,
            "capabilities": ["测试工程", "回归验证", "质量检查", "验收清单"],
            "memory_policy": {"long_term_owner": "michelangelo", "project_memory": True, "instance_short_memory": True},
            "default_release_policy": "task_completed",
        },
    ]


def _load_agent_templates() -> list[dict[str, Any]]:
    data = _read_json_file(AGENT_TEMPLATES_FILE, {"templates": _default_agent_templates()})
    templates = data.get("templates") if isinstance(data, dict) else data
    if not isinstance(templates, list) or not templates:
        templates = _default_agent_templates()
    return templates


def _template_by_id() -> dict[str, dict[str, Any]]:
    return {row.get("id"): row for row in _load_agent_templates() if row.get("id")}


def _bootstrap_agent_instances() -> list[dict[str, Any]]:
    templates = _template_by_id()
    defaults = [
        ("wheeljack-leonardo", "leonardo", "wheeljack"),
        ("wheeljack-raphael", "raphael", "wheeljack"),
        ("wheeljack-donatello", "donatello", "wheeljack"),
        ("wheeljack-michelangelo", "michelangelo", "wheeljack"),
    ]
    now = _now_utc()
    rows = []
    for instance_id, base_agent_id, requested_by in defaults:
        template = templates.get(base_agent_id, {})
        rows.append({
            "id": instance_id,
            "instance_id": instance_id,
            "type": "elastic",
            "status": "idle",
            "base_agent_id": base_agent_id,
            "base_agent_name": template.get("name", base_agent_id),
            "requested_by": requested_by,
            "project_id": "",
            "task_id": "",
            "development_point_id": "",
            "role": template.get("role", ""),
            "capabilities": template.get("capabilities", []),
            "reason": "bootstrap_registered_openclaw_instance",
            "release_policy": "task_completed",
            "created_at": now,
            "updated_at": now,
            "source": "agent-instance-registry",
        })
    return rows


def _load_agent_instance_store() -> dict[str, Any]:
    default = {"instances": _bootstrap_agent_instances(), "memory_commits": [], "updated_at": _now_utc()}
    data = _read_json_file(AGENT_INSTANCES_FILE, default)
    if not isinstance(data, dict):
        data = default
    if "instances" not in data or not isinstance(data["instances"], list):
        data["instances"] = _bootstrap_agent_instances()
    if "memory_commits" not in data or not isinstance(data["memory_commits"], list):
        data["memory_commits"] = []
    return data


def _save_agent_instance_store(store: dict[str, Any]) -> dict[str, Any]:
    store["updated_at"] = _now_utc()
    _write_json_file(AGENT_INSTANCES_FILE, store)
    return store


def _enrich_agent_instance(instance: dict[str, Any]) -> dict[str, Any]:
    templates = _template_by_id()
    row = dict(instance)
    template = templates.get(row.get("base_agent_id"), {})
    row.setdefault("base_agent_name", template.get("name", row.get("base_agent_id", "")))
    row.setdefault("role", template.get("role", ""))
    row.setdefault("capabilities", template.get("capabilities", []))
    row.setdefault("type", "elastic")
    row.setdefault("source", "agent-instance-registry")
    return row


def _find_project_task_context(project_id: str, task_id: str, point_id: str = "") -> dict[str, Any]:
    project = project_manager.get_project(project_id) if project_id else None
    task = None
    point = None
    if project:
        for item in project.get("tasks", []):
            if item.get("id") == task_id:
                task = item
                break
        if task:
            for item in task.get("development_points", []):
                if item.get("id") == point_id:
                    point = item
                    break
    return {"project": project, "task": task, "development_point": point}


def _agent_work_type(base_agent_id: str) -> str:
    return {
        "leonardo": "architecture",
        "raphael": "backend",
        "donatello": "frontend",
        "michelangelo": "testing",
    }.get(base_agent_id, "development")


def _instance_dispatch_id(instance: dict[str, Any]) -> str:
    task_id = instance.get("task_id") or "standby"
    return f"elastic-{instance.get('id')}-{task_id}"


def _ensure_instance_workspace(instance: dict[str, Any], template: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    instance_id = instance.get("id") or instance.get("instance_id")
    workspace = OPENCLAW_AGENTS_DIR / instance_id / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    project = context.get("project") or {}
    task = context.get("task") or {}
    point = context.get("development_point") or {}
    display_name = f"{instance.get('requested_by', '')}-{template.get('name', instance.get('base_agent_id', ''))}"
    identity = (
        f"# {display_name}\n\n"
        f"**Name**: {display_name}\n"
        f"**Role**: {template.get('role', instance.get('role', '弹性执行实例'))}\n"
        f"**Status**: {instance.get('status', 'running')}\n"
        f"**Base Agent**: {instance.get('base_agent_id', '')}\n"
        f"**Requested By**: {instance.get('requested_by', '')}\n"
    )
    agents_md = (
        "# 弹性智能体执行说明\n\n"
        "你是由项目经理按需创建的临时执行分身。\n\n"
        f"- 来源模板：{template.get('name', instance.get('base_agent_id', ''))}\n"
        f"- 职责：{template.get('role', instance.get('role', ''))}\n"
        f"- 能力：{', '.join(template.get('capabilities', []))}\n"
        f"- 请求方：{instance.get('requested_by', '')}\n"
        f"- 项目：{project.get('name', instance.get('project_id', ''))}\n"
        f"- 任务：{task.get('title', instance.get('task_id', ''))}\n"
        f"- 开发要点：{point.get('title', instance.get('development_point_id', '')) or '未指定'}\n\n"
        "执行完成后，需要输出结果摘要、关键决策、阻塞点和下一步建议，并回写项目记忆与基础智能体记忆。\n"
    )
    execution_context = {
        "instance": instance,
        "template": template,
        "project": project,
        "task": task,
        "development_point": point,
        "memory_policy": template.get("memory_policy", {}),
        "release_policy": instance.get("release_policy", "task_completed"),
        "updated_at": _now_utc(),
    }
    current_task = (
        f"# 当前执行任务\n\n"
        f"项目：{project.get('name', instance.get('project_id', ''))}\n\n"
        f"任务：{task.get('title', instance.get('task_id', ''))}\n\n"
        f"开发要点：{point.get('title', instance.get('development_point_id', '')) or '未指定'}\n\n"
        f"调用原因：{instance.get('reason', '')}\n"
    )
    for filename, content in {
        "IDENTITY.md": identity,
        "SOUL.md": identity,
        "AGENTS.md": agents_md,
        "CURRENT_TASK.md": current_task,
    }.items():
        path = workspace / filename
        if filename in {"IDENTITY.md", "SOUL.md", "AGENTS.md"} and path.exists():
            continue
        path.write_text(content, encoding="utf-8")
    _write_json_file(workspace / "EXECUTION_CONTEXT.json", execution_context)
    return {
        "workspace": str(workspace),
        "execution_context": str(workspace / "EXECUTION_CONTEXT.json"),
        "current_task": str(workspace / "CURRENT_TASK.md"),
    }


def _load_dispatch_queue() -> dict[str, Any]:
    default = {"version": "1.0", "sprint": 0, "status": "running", "loop_mode": "auto", "tasks": []}
    data = _read_json_file(NINJA_TURTLES_QUEUE_FILE, default)
    if not isinstance(data, dict):
        data = default
    if "tasks" not in data or not isinstance(data["tasks"], list):
        data["tasks"] = []
    return data


def _save_dispatch_queue(queue: dict[str, Any]) -> dict[str, Any]:
    queue["updated_at"] = _now_utc()
    _write_json_file(NINJA_TURTLES_QUEUE_FILE, queue)
    return queue


def _dispatch_instance_to_openclaw(instance: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    context = _find_project_task_context(instance.get("project_id", ""), instance.get("task_id", ""), instance.get("development_point_id", ""))
    workspace_files = _ensure_instance_workspace(instance, template, context)
    queue = _load_dispatch_queue()
    dispatch_id = _instance_dispatch_id(instance)
    project = context.get("project") or {}
    task = context.get("task") or {}
    point = context.get("development_point") or {}
    dispatch_task = {
        "id": dispatch_id,
        "title": task.get("title") or f"{instance.get('id')} 弹性执行任务",
        "type": _agent_work_type(instance.get("base_agent_id", "")),
        "status": "assigned",
        "priority": task.get("priority", "high"),
        "assignee": instance.get("id"),
        "base_agent_id": instance.get("base_agent_id"),
        "requested_by": instance.get("requested_by"),
        "project_id": instance.get("project_id", ""),
        "project_name": project.get("name", ""),
        "task_id": instance.get("task_id", ""),
        "development_point_id": instance.get("development_point_id", ""),
        "development_point_title": point.get("title", ""),
        "reason": instance.get("reason", ""),
        "release_policy": instance.get("release_policy", "task_completed"),
        "execution_context": workspace_files["execution_context"],
        "created": instance.get("created_at") or _now_utc(),
        "updated_at": _now_utc(),
    }
    existing = next((row for row in queue["tasks"] if row.get("id") == dispatch_id), None)
    if existing:
        existing.update(dispatch_task)
        action = "updated"
    else:
        queue["tasks"].append(dispatch_task)
        action = "queued"
    _save_dispatch_queue(queue)
    return {"action": action, "queue_task": dispatch_task, "workspace": workspace_files}


def _mark_dispatch_instance(instance: dict[str, Any], status: str, result: str = "") -> Optional[dict[str, Any]]:
    dispatch_id = _instance_dispatch_id(instance)
    queue = _load_dispatch_queue()
    row = next((item for item in queue.get("tasks", []) if item.get("id") == dispatch_id), None)
    if not row:
        return None
    row["status"] = status
    row["updated_at"] = _now_utc()
    if result:
        row["result_summary"] = result
    if status in {"done", "completed"}:
        row["completed_at"] = row["updated_at"]
    _save_dispatch_queue(queue)
    return row


def _load_runner_state() -> dict[str, Any]:
    data = _read_json_file(AGENT_RUNNER_FILE, {"runs": [], "updated_at": _now_utc()})
    if not isinstance(data, dict):
        data = {"runs": [], "updated_at": _now_utc()}
    if "runs" not in data or not isinstance(data["runs"], list):
        data["runs"] = []
    return data


def _save_runner_state(state: dict[str, Any]) -> dict[str, Any]:
    state["updated_at"] = _now_utc()
    _write_json_file(AGENT_RUNNER_FILE, state)
    return state


def _runner_executor_status() -> dict[str, Any]:
    configured = os.getenv("ELASTIC_AGENT_EXECUTOR_CMD", "").strip()
    first = shlex.split(configured)[0] if configured else ""
    return {
        "configured": bool(configured),
        "command": configured.split()[0] if configured else "",
        "available": bool(first and shutil.which(first)),
        "mode": "external-command" if configured else "claim-only",
    }


def _read_execution_context(queue_task: dict[str, Any]) -> dict[str, Any]:
    context_path = queue_task.get("execution_context")
    if not context_path:
        return {}
    path = Path(context_path)
    if not path.exists():
        return {}
    return _read_json_file(path, {})


def _workspace_for_queue_task(queue_task: dict[str, Any]) -> Path:
    context_path = queue_task.get("execution_context")
    if context_path:
        return Path(context_path).parent
    return OPENCLAW_AGENTS_DIR / queue_task.get("assignee", "unknown") / "workspace"


def _render_runner_prompt(queue_task: dict[str, Any], context: dict[str, Any]) -> str:
    instance = context.get("instance") or {}
    template = context.get("template") or {}
    project = context.get("project") or {}
    task = context.get("task") or {}
    point = context.get("development_point") or {}
    capabilities = ", ".join(template.get("capabilities", []) or instance.get("capabilities", []))
    return f"""# OpenClaw 弹性智能体执行任务

你是一个临时弹性执行分身。请按照基础智能体模板执行当前项目任务，并在完成后输出结构化结果摘要。

## 身份
- 实例：{queue_task.get('assignee', instance.get('id', ''))}
- 来源模板：{template.get('name', instance.get('base_agent_id', ''))}
- 职责：{template.get('role', instance.get('role', ''))}
- 能力：{capabilities}
- 请求方：{instance.get('requested_by', queue_task.get('requested_by', ''))}

## 项目任务
- 项目：{project.get('name', queue_task.get('project_name', ''))}
- 项目 ID：{queue_task.get('project_id', '')}
- 任务：{task.get('title', queue_task.get('title', ''))}
- 任务 ID：{queue_task.get('task_id', '')}
- 开发要点：{point.get('title', queue_task.get('development_point_title', '')) or '未指定'}
- 开发要点 ID：{queue_task.get('development_point_id', '')}
- 调用原因：{queue_task.get('reason', '')}

## 输入上下文
- 执行上下文 JSON：{queue_task.get('execution_context', '')}
- 释放策略：{queue_task.get('release_policy', 'task_completed')}

## 输出要求
请在结果中包含：
1. result_summary：完成了什么
2. decisions：关键技术决策
3. blockers：阻塞点
4. next_actions：下一步建议
5. memory_summary：需要回写到项目和基础智能体长期记忆的摘要
"""


def _update_instance_runtime_status(instance_id: str, status: str, extra: Optional[dict[str, Any]] = None) -> None:
    store = _load_agent_instance_store()
    row = next((item for item in store.get("instances", []) if item.get("id") == instance_id), None)
    if not row:
        return
    row["status"] = status
    row["updated_at"] = _now_utc()
    if extra:
        row.update(extra)
    _save_agent_instance_store(store)


def _claim_next_elastic_task(instance_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    queue = _load_dispatch_queue()
    candidates = []
    for row in queue.get("tasks", []):
        if not (str(row.get("id", "")).startswith("elastic-") or row.get("base_agent_id")):
            continue
        if row.get("status") != "assigned":
            continue
        if instance_id and row.get("assignee") != instance_id:
            continue
        candidates.append(row)
    if not candidates:
        return None
    task = candidates[0]
    now = _now_utc()
    task["status"] = "in_progress"
    task["started_at"] = task.get("started_at") or now
    task["updated_at"] = now
    _save_dispatch_queue(queue)
    _update_instance_runtime_status(task.get("assignee", ""), "running", {"runner_status": "claimed"})
    return task


def _run_external_executor(queue_task: dict[str, Any], prompt_path: Path, max_seconds: int) -> dict[str, Any]:
    configured = os.getenv("ELASTIC_AGENT_EXECUTOR_CMD", "").strip()
    if not configured:
        return {"status": "skipped", "reason": "ELASTIC_AGENT_EXECUTOR_CMD not configured"}
    workspace = _workspace_for_queue_task(queue_task)
    context_path = queue_task.get("execution_context", "")
    formatted = configured.format(
        prompt=str(prompt_path),
        context=context_path,
        workspace=str(workspace),
        instance_id=queue_task.get("assignee", ""),
    )
    args = shlex.split(formatted)
    if not args or not shutil.which(args[0]):
        return {"status": "blocked", "reason": "executor command not found", "command": args[0] if args else ""}
    result = subprocess.run(args, cwd=str(workspace), text=True, capture_output=True, timeout=max_seconds)
    output_path = workspace / "RUNNER_OUTPUT.log"
    output_path.write_text(
        f"$ {' '.join(args)}\n\n[stdout]\n{result.stdout}\n\n[stderr]\n{result.stderr}\n",
        encoding="utf-8",
    )
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "output": str(output_path),
    }


def _runner_tick(req: AgentRunnerTickRequest) -> dict[str, Any]:
    task = _claim_next_elastic_task(req.instance_id)
    if not task:
        return {"claimed": False, "reason": "no assigned elastic task", "executor": _runner_executor_status()}
    context = _read_execution_context(task)
    workspace = _workspace_for_queue_task(task)
    workspace.mkdir(parents=True, exist_ok=True)
    prompt_path = workspace / "RUNNER_PROMPT.md"
    prompt_path.write_text(_render_runner_prompt(task, context), encoding="utf-8")
    now = _now_utc()
    run = {
        "id": f"run-{task.get('id')}-{now}",
        "task_id": task.get("id"),
        "instance_id": task.get("assignee"),
        "status": "claimed",
        "execute_requested": req.execute,
        "prompt": str(prompt_path),
        "execution_context": task.get("execution_context", ""),
        "created_at": now,
        "updated_at": now,
    }
    if req.execute:
        execution = _run_external_executor(task, prompt_path, req.max_seconds)
        run["execution"] = execution
        run["status"] = execution.get("status", "unknown")
        if execution.get("status") == "completed":
            task["status"] = "review"
            task["updated_at"] = _now_utc()
            queue = _load_dispatch_queue()
            existing = next((row for row in queue.get("tasks", []) if row.get("id") == task.get("id")), None)
            if existing:
                existing.update(task)
                _save_dispatch_queue(queue)
    runner_status_path = workspace / "RUNNER_STATUS.json"
    runner_status_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    state = _load_runner_state()
    state.setdefault("runs", []).append(run)
    state["runs"] = state["runs"][-200:]
    _save_runner_state(state)
    return {"claimed": True, "queue_task": task, "run": run, "executor": _runner_executor_status()}


@router.get("/projects")
def list_projects():
    projects = project_manager.list_projects()
    return {"projects": projects, "total": len(projects)}


@router.post("/projects", status_code=201)
def create_project(req: ProjectCreate):
    return project_manager.create_project(_model_dict(req))


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/projects/{project_id}")
def update_project(project_id: str, req: ProjectUpdate):
    project = project_manager.update_project(project_id, _model_dict(req, exclude_unset=True))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    deleted = project_manager.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "deleted": True}


@router.get("/projects/{project_id}/design-doc")
def get_project_design_doc(project_id: str):
    design_doc = project_manager.get_design_doc(project_id)
    if not design_doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return design_doc


@router.put("/projects/{project_id}/design-doc")
def update_project_design_doc(project_id: str, req: DesignDocumentUpdate):
    payload = _model_dict(req, exclude_unset=True)
    agent_id = payload.get("author_agent") or "project-manager"
    design_doc = project_manager.update_design_doc(project_id, payload, agent_id)
    if not design_doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return design_doc


@router.post("/projects/{project_id}/design-doc/revise", status_code=201)
def revise_project_design_doc(project_id: str, req: DesignDocumentRevise):
    result = project_manager.revise_design_doc(project_id, _model_dict(req))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.post("/projects/{project_id}/design-doc/approve")
def approve_project_design_doc(project_id: str, req: ApproveDesignDocumentRequest):
    result = project_manager.approve_design_doc(project_id, req.agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.get("/projects/{project_id}/agent-context")
def get_project_agent_context(project_id: str, agent_id: Optional[str] = Query(None)):
    context = project_manager.get_agent_context(project_id, data_manager.get_agents(), agent_id)
    if not context:
        raise HTTPException(status_code=404, detail="Project not found")
    return context


@router.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: str):
    tasks = project_manager.list_tasks(project_id)
    if tasks is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "tasks": tasks, "total": len(tasks)}


@router.post("/projects/{project_id}/tasks", status_code=201)
def create_project_task(project_id: str, req: TaskCreate):
    task = project_manager.add_task(project_id, _model_dict(req))
    if not task:
        raise HTTPException(status_code=404, detail="Project not found")
    return task


@router.put("/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdate):
    task = project_manager.update_task(task_id, _model_dict(req, exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/assign")
def assign_task(task_id: str, req: AssignRequest):
    task = project_manager.assign_task(task_id, req.assignee_agent)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/points")
def list_task_points(task_id: str):
    points = project_manager.list_points(task_id)
    if points is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "points": points, "total": len(points)}


@router.post("/tasks/{task_id}/points", status_code=201)
def create_task_point(task_id: str, req: DevelopmentPointCreate):
    point = project_manager.add_point(task_id, _model_dict(req))
    if not point:
        raise HTTPException(status_code=404, detail="Task not found")
    return point


@router.put("/points/{point_id}")
def update_development_point(point_id: str, req: DevelopmentPointUpdate):
    point = project_manager.update_point(point_id, _model_dict(req, exclude_unset=True))
    if not point:
        raise HTTPException(status_code=404, detail="Development point not found")
    return point


@router.post("/points/{point_id}/complete")
def complete_development_point(point_id: str, req: CompletePointRequest):
    result = project_manager.complete_point(point_id, req.agent_id, req.completion_evidence, req.result_summary)
    if not result:
        raise HTTPException(status_code=404, detail="Development point not found")
    return result




def _transition_point(point_id: str, action: str, req: PointTransitionRequest):
    result = project_manager.transition_point(
        point_id,
        action,
        req.agent_id,
        req.reason,
        req.completion_evidence,
        req.result_summary,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Development point not found")
    return result


@router.post("/points/{point_id}/claim")
def claim_development_point(point_id: str, req: PointTransitionRequest):
    return _transition_point(point_id, "claim", req)


@router.post("/points/{point_id}/release")
def release_development_point(point_id: str, req: PointTransitionRequest):
    return _transition_point(point_id, "release", req)


@router.post("/points/{point_id}/block")
def block_development_point(point_id: str, req: PointTransitionRequest):
    return _transition_point(point_id, "block", req)


@router.post("/points/{point_id}/submit-review")
def submit_development_point_review(point_id: str, req: PointTransitionRequest):
    return _transition_point(point_id, "submit_review", req)

@router.post("/tasks/{task_id}/logs", status_code=201)
def create_task_log(task_id: str, req: LogCreate):
    project_id = None
    for project in project_manager.list_projects():
        if any(task.get("id") == task_id for task in project.get("tasks", [])):
            project_id = project["id"]
            break
    if not project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    log = project_manager.add_log(project_id, task_id, req.agent_id, req.action, req.content)
    return log


@router.get("/projects/{project_id}/logs")
def list_project_logs(project_id: str, limit: int = Query(50, ge=1, le=200)):
    if not project_manager.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "logs": project_manager.list_logs(project_id, limit)}


@router.get("/projects/{project_id}/conversation")
def list_project_conversation(project_id: str, limit: int = Query(80, ge=1, le=200)):
    messages = project_manager.list_conversation(project_id, limit)
    if messages is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "messages": messages, "total": len(messages)}


@router.get("/projects/{project_id}/chat-context")
def get_project_chat_context(project_id: str):
    context = project_manager.build_project_chat_context(project_id)
    if not context:
        raise HTTPException(status_code=404, detail="Project not found")
    return context


@router.post("/projects/{project_id}/chat", status_code=201)
def create_project_chat_message(project_id: str, req: ProjectChatRequest):
    payload = _model_dict(req)
    result = project_manager.add_conversation_message(project_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    context = project_manager.build_project_chat_context(project_id)
    project_type = (context or {}).get("project", {}).get("project_type", "software")
    if project_type == "document":
        next_actions = [
            "根据目录结构拆分章节写作任务",
            "补充章节主要内容和图片/图表计划",
            "把引用资料绑定到章节或写作任务",
        ]
    else:
        next_actions = [
            "根据设计文档拆分开发任务",
            "指派后端、前端、测试智能体并行推进",
            "把接口、数据结构和验收标准写入开发要点",
        ]
    return {
        **result,
        "context": context,
        "suggested_next_actions": next_actions,
        "dispatch_status": "recorded",
    }


@router.post("/projects/{project_id}/agent-actions", status_code=201)
def create_project_agent_action(project_id: str, req: ProjectAgentActionRequest):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project_type = project.get("project_type") or project.get("type") or project.get("context", {}).get("project_type") or "software"
    instruction = req.instruction or req.payload.get("instruction") or req.task_title or req.action_type
    chat = project_manager.add_conversation_message(project_id, {
        "agent_id": req.agent_id,
        "role": "system",
        "intent": "agent_action",
        "message": instruction,
        "task_id": req.task_id,
        "chapter_id": req.chapter_id,
    })
    created_task = None
    should_create_task = req.action_type in {"create_task", "assign_task", "writing_task", "development_task"} or bool(req.task_title)
    if should_create_task:
        task_type = req.task_type or req.payload.get("task_type") or ("writing" if project_type == "document" else "development")
        title = req.task_title or req.payload.get("title") or instruction
        created_task = project_manager.add_task(project_id, {
            "title": title,
            "description": instruction,
            "type": task_type,
            "assignee_agent": req.assignee_agent or req.agent_id,
            "assignee_agent_id": req.assignee_agent or req.agent_id,
            "status": "todo",
            "priority": req.payload.get("priority", "medium"),
            "context": {
                "created_from_agent_action": req.action_type,
                "chapter_id": req.chapter_id,
                "project_type": project_type,
            },
            "development_points": [{
                "title": req.payload.get("point_title") or (title + ("写作要点" if task_type == "writing" else "开发要点")),
                "status": "todo",
                "assigned_agent": req.assignee_agent or req.agent_id,
            }],
        })
    log = project_manager.add_log(project_id, req.task_id or (created_task or {}).get("id"), req.agent_id, "project_agent_action", instruction)
    return {
        "project_id": project_id,
        "action_type": req.action_type,
        "agent_id": req.agent_id,
        "chat": chat,
        "created_task": created_task,
        "log": log,
        "dispatch_status": "recorded",
    }


@router.put("/projects/{project_id}/software-spec")
def update_project_software_spec(project_id: str, req: SoftwareSpecUpdate):
    payload = _model_dict(req, exclude_unset=True)
    agent_id = payload.pop("agent_id", "project-manager")
    result = project_manager.update_software_spec(project_id, payload, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.post("/projects/{project_id}/document-sections", status_code=201)
def create_document_section(project_id: str, req: DocumentSectionCreate):
    payload = _model_dict(req, exclude_unset=True)
    agent_id = payload.pop("agent_id", "project-manager")
    result = project_manager.add_document_section(project_id, payload, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.put("/projects/{project_id}/document-sections/{section_id}")
def update_document_section(project_id: str, section_id: str, req: DocumentSectionUpdate):
    payload = _model_dict(req, exclude_unset=True)
    agent_id = payload.pop("agent_id", "project-manager")
    result = project_manager.update_document_section(project_id, section_id, payload, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project or section not found")
    return result


@router.delete("/projects/{project_id}/document-sections/{section_id}")
def delete_document_section(project_id: str, section_id: str, agent_id: str = Query("project-manager")):
    result = project_manager.delete_document_section(project_id, section_id, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project or section not found")
    return result


@router.post("/projects/{project_id}/document-assets", status_code=201)
def create_document_asset(project_id: str, req: DocumentAssetCreate):
    payload = _model_dict(req, exclude_unset=True)
    agent_id = payload.pop("agent_id", "project-manager")
    result = project_manager.add_document_asset(project_id, payload, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.put("/projects/{project_id}/document-assets/{asset_id}")
def update_document_asset(project_id: str, asset_id: str, req: DocumentAssetUpdate):
    payload = _model_dict(req, exclude_unset=True)
    agent_id = payload.pop("agent_id", "project-manager")
    result = project_manager.update_document_asset(project_id, asset_id, payload, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project or asset not found")
    return result


@router.delete("/projects/{project_id}/document-assets/{asset_id}")
def delete_document_asset(project_id: str, asset_id: str, agent_id: str = Query("project-manager")):
    result = project_manager.delete_document_asset(project_id, asset_id, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project or asset not found")
    return result


@router.get("/projects/{project_id}/iteration-context")
def get_iteration_context(project_id: str):
    context = project_manager.get_iteration_context(project_id, data_manager.get_agents())
    if not context:
        raise HTTPException(status_code=404, detail="Project not found")
    context["knowledge_context"] = knowledge_manager.project_context(context["project"])
    return context


@router.get("/projects/{project_id}/knowledge-context")
def get_project_knowledge_context(project_id: str):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return knowledge_manager.project_context(project)


@router.post("/projects/{project_id}/knowledge-links", status_code=201)
def add_project_knowledge_link(project_id: str, req: KnowledgeLinkRequest):
    result = project_manager.add_knowledge_link("project", project_id, _model_dict(req))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found or invalid knowledge link")
    project = project_manager.get_project(project_id)
    result["knowledge_context"] = knowledge_manager.project_context(project) if project else None
    return result


@router.post("/tasks/{task_id}/knowledge-links", status_code=201)
def add_task_knowledge_link(task_id: str, req: KnowledgeLinkRequest):
    result = project_manager.add_knowledge_link("task", task_id, _model_dict(req))
    if not result:
        raise HTTPException(status_code=404, detail="Task not found or invalid knowledge link")
    return result


@router.post("/points/{point_id}/knowledge-links", status_code=201)
def add_point_knowledge_link(point_id: str, req: KnowledgeLinkRequest):
    result = project_manager.add_knowledge_link("point", point_id, _model_dict(req))
    if not result:
        raise HTTPException(status_code=404, detail="Development point not found or invalid knowledge link")
    return result


@router.delete("/knowledge-links")
def delete_knowledge_link(
    target_type: str = Query(..., pattern="^(project|task|point)$"),
    target_id: str = Query(..., min_length=1),
    node_id: str = Query(..., min_length=1),
    removed_by: str = Query("project-manager"),
):
    result = project_manager.remove_knowledge_link(target_type, target_id, node_id, removed_by)
    if not result:
        raise HTTPException(status_code=404, detail="Knowledge link not found")
    if target_type == "project":
        project = project_manager.get_project(target_id)
        result["knowledge_context"] = knowledge_manager.project_context(project) if project else None
    return result


@router.post("/projects/{project_id}/decompose", status_code=201)
def decompose_project(project_id: str, req: DecomposeRequest):
    result = project_manager.decompose_project(project_id, _model_dict(req))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result

# Agent status projection backed by V3 project tasks.
def _now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _merge_agent_sources(openclaw_agents, local_agents):
    merged = {}
    for agent in local_agents:
        aid = agent.get("id")
        if not aid:
            continue
        row = dict(agent)
        row["_dashboard_source"] = "local-data-manager"
        merged[aid] = row

    # Fields that OpenClaw runtime can provide (status, last_seen)
    # All other fields (name, role, team, memory, config, etc.) stay from local agents.json
    runtime_fields = {"status", "current_task", "last_seen", "last_heartbeat",
                      "cpu_usage", "memory_usage", "task_queue_len", "metadata",
                      "updated_at", "agent_name"}

    for agent in openclaw_agents:
        aid = agent.get("id")
        if not aid:
            continue
        if aid in merged:
            # Local data exists → only overlay runtime fields, keep local profile data
            for key in runtime_fields:
                if key in agent and agent[key] is not None:
                    merged[aid][key] = agent[key]
            merged[aid]["_dashboard_source"] = "openclaw-workspace+local-data-manager"
        else:
            # No local data → use OpenClaw data as-is (new/unknown agents)
            row = dict(agent)
            row["_dashboard_source"] = "openclaw-workspace"
            merged[aid] = row
    return list(merged.values())


def _load_agent_sources():
    observed_at = _now_utc()
    local_agents = [
        agent for agent in data_manager.get_agents()
        if agent.get("enabled", True)
    ]
    try:
        openclaw_agents = openclaw_integration.sync_agents()
    except Exception:
        openclaw_agents = []

    if openclaw_agents:
        return _merge_agent_sources(openclaw_agents, local_agents), "mixed", observed_at

    agents = []
    for agent in local_agents:
        row = dict(agent)
        row["_dashboard_source"] = "local-data-manager"
        agents.append(row)
    return agents, "local-data-manager", observed_at


def _agent_rows(agents: Optional[list[dict[str, Any]]] = None):
    projects = project_manager.list_projects()
    agents = agents if agents is not None else data_manager.get_agents()
    rows = []
    done = {"done", "completed"}
    for agent in agents:
        aid = agent.get("id", "")
        row = {
            "agent_id": aid,
            "agent_name": agent.get("name", aid),
            "role": agent.get("role", ""),
            "team": agent.get("team", ""),
            "status": agent.get("status", "idle"),
            "legacy_current_task": agent.get("current_task", ""),
            "current_project_id": None,
            "current_project_name": None,
            "current_task_id": None,
            "current_task_title": None,
            "current_development_point_id": None,
            "current_development_point_title": None,
            "task_progress": 0,
            "project_progress": 0,
            "source": "projects-v3",
        }
        for project in projects:
            for task in project.get("tasks", []):
                task_agent = task.get("assignee_agent")
                if task_agent == aid and task.get("status") not in done:
                    row.update({"current_project_id": project.get("id"), "current_project_name": project.get("name"), "current_task_id": task.get("id"), "current_task_title": task.get("title"), "task_progress": task.get("progress", 0), "project_progress": project.get("progress", 0), "status": "busy"})
                for point in task.get("development_points", []):
                    point_agent = point.get("assigned_agent") or task_agent
                    if point_agent == aid and point.get("status") not in done:
                        row.update({"current_project_id": project.get("id"), "current_project_name": project.get("name"), "current_task_id": task.get("id"), "current_task_title": task.get("title"), "current_development_point_id": point.get("id"), "current_development_point_title": point.get("title"), "task_progress": task.get("progress", 0), "project_progress": project.get("progress", 0), "status": "busy"})
                        break
                if row["current_development_point_id"]:
                    break
            if row["current_development_point_id"]:
                break
        rows.append(row)
    return rows



@router.get("/skills")
def list_skills(query: str = "", category: str = "", source: str = "", status: str = ""):
    rows = skill_manager.list_skills(query=query, category=category, source=source, status=status)
    return {
        "skills": rows,
        "total": len(rows),
        "categories": sorted({row.get("category", "") for row in rows if row.get("category")}),
        "sources": sorted({row.get("source", "") for row in rows if row.get("source")}),
        "source": "skill-registry",
        "updated_at": _now_utc(),
    }


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str):
    skill = skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.get("/agents/{agent_id}/skills")
def get_agent_skills(agent_id: str):
    rows = skill_manager.get_agent_skills(agent_id)
    return {"agent_id": agent_id, "skills": rows, "total": len(rows)}


@router.put("/agents/{agent_id}/skills")
def update_agent_skills(agent_id: str, req: AgentSkillsUpdate):
    rows = skill_manager.set_agent_skills(agent_id, req.skill_ids)
    return {"agent_id": agent_id, "skills": rows, "total": len(rows)}


@router.get("/agents/templates")
def list_agent_templates():
    templates = _load_agent_templates()
    return {
        "templates": templates,
        "total": len(templates),
        "source": "agent-template-registry",
        "updated_at": _now_utc(),
    }


@router.get("/agents/instances")
def list_agent_instances(status: str = ""):
    store = _load_agent_instance_store()
    rows = [_enrich_agent_instance(row) for row in store.get("instances", [])]
    if status:
        wanted = {item.strip() for item in status.split(",") if item.strip()}
        rows = [row for row in rows if row.get("status") in wanted]
    return {
        "instances": rows,
        "total": len(rows),
        "memory_commits": store.get("memory_commits", []),
        "source": "agent-instance-registry",
        "updated_at": store.get("updated_at") or _now_utc(),
    }


@router.get("/agents/dispatch-queue")
def get_agent_dispatch_queue():
    queue = _load_dispatch_queue()
    elastic_tasks = [
        row for row in queue.get("tasks", [])
        if str(row.get("id", "")).startswith("elastic-") or row.get("base_agent_id")
    ]
    return {
        "queue": queue,
        "elastic_tasks": elastic_tasks,
        "total": len(elastic_tasks),
        "source": "openclaw-dev-loop-queue",
        "updated_at": queue.get("updated_at") or _now_utc(),
    }


@router.get("/agents/runner/status")
def get_agent_runner_status():
    state = _load_runner_state()
    queue = _load_dispatch_queue()
    assigned = [
        row for row in queue.get("tasks", [])
        if (str(row.get("id", "")).startswith("elastic-") or row.get("base_agent_id"))
        and row.get("status") == "assigned"
    ]
    in_progress = [
        row for row in queue.get("tasks", [])
        if (str(row.get("id", "")).startswith("elastic-") or row.get("base_agent_id"))
        and row.get("status") == "in_progress"
    ]
    return {
        "runner": state,
        "executor": _runner_executor_status(),
        "queue": {
            "assigned": len(assigned),
            "in_progress": len(in_progress),
            "assigned_tasks": assigned,
            "in_progress_tasks": in_progress,
        },
        "updated_at": state.get("updated_at") or _now_utc(),
    }


@router.post("/agents/runner/tick")
def tick_agent_runner(req: AgentRunnerTickRequest = AgentRunnerTickRequest()):
    return _runner_tick(req)


@router.post("/agents/instances/{instance_id}/claim")
def claim_agent_instance(instance_id: str, execute: bool = False):
    return _runner_tick(AgentRunnerTickRequest(instance_id=instance_id, execute=execute))


@router.post("/agents/spawn", status_code=201)
def spawn_agent_instance(req: AgentSpawnRequest):
    templates = _template_by_id()
    base_agent_id = _safe_id(req.base_agent_id)
    requested_by = _safe_id(req.requested_by)
    template = templates.get(base_agent_id)
    if not template:
        raise HTTPException(status_code=404, detail="Agent template not found")
    if not template.get("spawnable", False):
        raise HTTPException(status_code=400, detail="Agent template is not spawnable")

    instance_id = _safe_id(req.instance_id or f"{requested_by}-{base_agent_id}")
    store = _load_agent_instance_store()
    now = _now_utc()
    existing = next((row for row in store["instances"] if row.get("id") == instance_id), None)
    payload = {
        "id": instance_id,
        "instance_id": instance_id,
        "type": "elastic",
        "status": "running" if req.task_id else "idle",
        "base_agent_id": base_agent_id,
        "base_agent_name": template.get("name", base_agent_id),
        "requested_by": requested_by,
        "project_id": req.project_id,
        "task_id": req.task_id,
        "development_point_id": req.development_point_id,
        "role": template.get("role", ""),
        "capabilities": template.get("capabilities", []),
        "reason": req.reason,
        "release_policy": req.release_policy or template.get("default_release_policy", "task_completed"),
        "updated_at": now,
        "source": "agent-instance-registry",
    }
    if existing:
        existing.update(payload)
        existing.setdefault("created_at", now)
        instance = existing
        action = "updated"
    else:
        payload["created_at"] = now
        store["instances"].append(payload)
        instance = payload
        action = "created"
    dispatch = None
    if instance.get("task_id"):
        dispatch = _dispatch_instance_to_openclaw(instance, template)
        instance["dispatch_status"] = dispatch["action"]
        instance["dispatch_task_id"] = dispatch["queue_task"]["id"]
        instance["workspace"] = dispatch["workspace"]
    _save_agent_instance_store(store)
    return {"action": action, "instance": _enrich_agent_instance(instance), "dispatch": dispatch}


@router.post("/agents/instances/{instance_id}/release")
def release_agent_instance(instance_id: str, req: AgentReleaseRequest):
    store = _load_agent_instance_store()
    row = next((item for item in store["instances"] if item.get("id") == instance_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Agent instance not found")
    row["status"] = "released"
    row["released_by"] = req.released_by
    row["release_reason"] = req.reason
    row["released_at"] = _now_utc()
    row["updated_at"] = row["released_at"]
    queue_task = _mark_dispatch_instance(row, "released", req.reason)
    _save_agent_instance_store(store)
    return {"instance": _enrich_agent_instance(row), "queue_task": queue_task}


@router.post("/agents/instances/{instance_id}/complete")
def complete_agent_instance(instance_id: str, req: AgentCompleteRequest):
    store = _load_agent_instance_store()
    row = next((item for item in store["instances"] if item.get("id") == instance_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Agent instance not found")
    now = _now_utc()
    row["status"] = "completed"
    row["completed_by"] = req.completed_by
    row["completed_at"] = now
    row["updated_at"] = now
    row["result_summary"] = req.result_summary
    queue_task = _mark_dispatch_instance(row, "done", req.result_summary)
    commit = {
        "id": f"mem-{instance_id}-{len(store.get('memory_commits', [])) + 1}",
        "instance_id": instance_id,
        "base_agent_id": row.get("base_agent_id", ""),
        "project_id": row.get("project_id", ""),
        "task_id": row.get("task_id", ""),
        "development_point_id": row.get("development_point_id", ""),
        "summary": req.memory_summary or req.result_summary,
        "decisions": req.decisions,
        "blockers": req.blockers,
        "next_actions": req.next_actions,
        "committed_by": req.completed_by,
        "created_at": now,
        "target_memory": ["project", "base_agent"],
    }
    store.setdefault("memory_commits", []).append(commit)
    _save_agent_instance_store(store)
    return {"instance": _enrich_agent_instance(row), "memory_commit": commit, "queue_task": queue_task}


@router.post("/agents/release")
def release_agent_instance_alias(instance_id: str = Query(..., min_length=1), req: AgentReleaseRequest = AgentReleaseRequest()):
    return release_agent_instance(instance_id, req)


@router.get("/agents/status")
def list_agent_project_status():
    rows = _agent_rows()
    return {"agents": rows, "total": len(rows), "source": "projects-v3"}


@router.get("/agents/dashboard")
def list_agent_dashboard():
    agents, aggregate_source, observed_at = _load_agent_sources()
    skill_summary = skill_manager.skill_summary_by_agent()
    work_rows = _agent_rows(agents)
    work_by_agent = {row.get("agent_id"): row for row in work_rows}
    dashboard = []

    for agent in agents:
        aid = agent.get("id", "")
        work = work_by_agent.get(aid, {})
        last_seen = agent.get("last_seen") or agent.get("last_heartbeat") or agent.get("updated_at")
        stale = not bool(last_seen)
        stale_reason = "" if last_seen else "missing-last-seen"
        current_work = None
        if work.get("current_task_id"):
            current_work = {
                "project_id": work.get("current_project_id"),
                "project_name": work.get("current_project_name"),
                "task_id": work.get("current_task_id"),
                "task_title": work.get("current_task_title"),
                "development_point_id": work.get("current_development_point_id"),
                "development_point_title": work.get("current_development_point_title"),
                "task_progress": work.get("task_progress", 0),
                "project_progress": work.get("project_progress", 0),
                "source": "projects-v3",
            }

        status = work.get("status") or agent.get("status", "unknown")
        profile_source = agent.get("_dashboard_source", aggregate_source)
        agent_skill_summary = skill_summary.get(aid, {"total": 0, "skills": [], "issues": 0})
        dashboard.append({
            "id": aid,
            "agent_id": aid,
            "name": agent.get("name", aid),
            "agent_name": agent.get("name", aid),
            "role": agent.get("role", ""),
            "team": agent.get("team", ""),
            "memory": agent.get("memory", []),
            "status": status,
            "current_task": work.get("current_task_title") or agent.get("current_task", ""),
            "legacy_current_task": agent.get("current_task", ""),
            "current_project_id": work.get("current_project_id"),
            "current_project_name": work.get("current_project_name"),
            "current_task_id": work.get("current_task_id"),
            "current_task_title": work.get("current_task_title"),
            "current_development_point_id": work.get("current_development_point_id"),
            "current_development_point_title": work.get("current_development_point_title"),
            "task_progress": work.get("task_progress", 0),
            "project_progress": work.get("project_progress", 0),
            "updated_at": observed_at,
            "last_seen": last_seen,
            "stale": stale,
            "stale_reason": stale_reason,
            "profile": {
                "id": aid,
                "name": agent.get("name", aid),
                "role": agent.get("role", ""),
                "team": agent.get("team", ""),
                "skills": agent.get("skills", []),
                "memory": agent.get("memory", []),
            },
            "runtime": {
                "status": status,
                "raw_status": agent.get("status", "unknown"),
                "current_task": agent.get("current_task", ""),
                "last_seen": last_seen,
                "updated_at": observed_at,
                "stale": stale,
                "stale_reason": stale_reason,
            },
            "current_work": current_work,
            "skill_summary": agent_skill_summary,
            "skills": agent_skill_summary.get("skills", []),
            "source": {
                "profile": profile_source,
                "runtime": profile_source,
                "work": "projects-v3" if current_work else "none",
                "skills": "skill-registry",
            },
        })

    return {
        "agents": dashboard,
        "total": len(dashboard),
        "source": "agents-dashboard",
        "agent_source": aggregate_source,
        "updated_at": observed_at,
    }


@router.get("/agents/organization")
def get_agent_organization():
    try:
        document = unified_data_manager.get_agent_organization_document()
        if document.get("root"):
            return document
    except Exception:
        pass
    if not AGENT_ORGANIZATION_FILE.exists():
        raise HTTPException(status_code=404, detail="Agent organization data not found")
    try:
        document = json.loads(AGENT_ORGANIZATION_FILE.read_text(encoding="utf-8"))
        document["source"] = "agent-organization-json"
        return document
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid agent organization data: {exc}") from exc


@router.get("/agents/{agent_id}/current-work")
def get_agent_current_work(agent_id: str):
    for row in _agent_rows():
        if row.get("agent_id") == agent_id:
            return row
    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/agents/{agent_id}/work-items")
def get_agent_work_items(agent_id: str):
    return project_manager.get_agent_work_items(agent_id)
