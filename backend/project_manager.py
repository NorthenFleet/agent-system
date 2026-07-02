"""
Project iteration manager for agent-driven development work.

Data model:
Project -> DesignDocument + Task -> DevelopmentPoint -> Logs
Progress is derived bottom-up from development point completion.
"""

import copy
import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from path_config import data_path
from unified_data_manager import unified_data_manager

PROJECTS_FILE = data_path("projects-v3.json")
CANONICAL_BOARD_PROJECT_ID = "proj-b098ac3dbf"
CANONICAL_BOARD_PROJECT_NAME = "OpenClaw 团队信息看板"
TASK_PROJECT_NAME_MAP = {
    "团队信息看板": "团队信息看板基础建设",
    "知识绑定项目": "知识绑定任务",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _is_done(status: str) -> bool:
    return status in {"done", "completed"}


def _normalize_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_project_type(value: Any) -> str:
    value = str(value or "").strip().lower()
    if value in {"document", "doc", "writing", "paper"}:
        return "document"
    return "software"


def _status_counts(items: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "unknown") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


class ProjectManager:
    def __init__(self, file_path: str = PROJECTS_FILE):
        self.file_path = file_path

    def _default_data(self) -> dict:
        return {"version": 2, "last_updated": _now_iso(), "projects": [], "logs": []}

    def _lock_path(self) -> str:
        return self.file_path + ".lock"

    def _load_unlocked(self) -> dict:
        data = unified_data_manager.load_projects_document()
        data.setdefault("version", 1)
        data.setdefault("last_updated", _now_iso())
        data.setdefault("projects", [])
        data.setdefault("logs", [])
        return data

    def _save_unlocked(self, data: dict) -> None:
        data["last_updated"] = _now_iso()
        unified_data_manager.save_projects_document(data)

    def _with_data(self, mutator):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                result = mutator(data)
                self._recalculate_all(data)
                self._save_unlocked(data)
                return result
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict:
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            try:
                data = self._load_unlocked()
                self._recalculate_all(data)
                return copy.deepcopy(data)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _recalculate_all(self, data: dict) -> None:
        for project in data.get("projects", []):
            self._recalculate_project(project)

    def _recalculate_project(self, project: dict) -> None:
        project_type = _normalize_project_type(project.get("project_type") or project.get("type") or _as_dict(project.get("context")).get("project_type"))
        project["project_type"] = project_type
        project["type"] = project_type
        project["document_spec"] = self._normalize_document_spec(project.get("document_spec"), project.get("id", ""), project.get("created_at") or _now_iso())
        if project.get("id"):
            project["design_doc"] = self._normalize_design_doc(
                project.get("design_doc"),
                project["id"],
                project.get("created_at") or _now_iso(),
            )
        tasks = _as_list(project.get("tasks"))
        for task in tasks:
            self._recalculate_task(task)
        if tasks:
            project["progress"] = round(sum(float(t.get("progress", 0)) for t in tasks) / len(tasks), 1)
            if project["progress"] >= 100:
                project["status"] = "done"
        else:
            project["progress"] = round(float(project.get("progress", 0) or 0), 1)
        project["updated_at"] = project.get("updated_at") or _now_iso()

    def _recalculate_task(self, task: dict) -> None:
        points = _as_list(task.get("development_points"))
        if points:
            total_weight = sum(max(float(p.get("weight", 1) or 1), 0) for p in points) or 1
            done_weight = sum(
                max(float(p.get("weight", 1) or 1), 0)
                for p in points
                if _is_done(str(p.get("status", "")))
            )
            task["progress"] = round(done_weight * 100 / total_weight, 1)
            if task["progress"] >= 100:
                task["status"] = "done"
            elif task.get("status") in {"todo", "pending"} and task["progress"] > 0:
                task["status"] = "in_progress"
        else:
            task["progress"] = round(float(task.get("progress", 0) or 0), 1)
        task["updated_at"] = task.get("updated_at") or _now_iso()

    def list_projects(self) -> list[dict]:
        data = self._read()
        return data["projects"]

    def get_project(self, project_id: str) -> Optional[dict]:
        data = self._read()
        for project in data["projects"]:
            if project["id"] == project_id:
                return project
        return None

    def create_project(self, payload: dict) -> dict:
        now = _now_iso()

        def mutate(data):
            requested_name = str(payload.get("name", "")).strip()
            for project in data.get("projects", []):
                if _normalize_name(project.get("name")) == _normalize_name(requested_name):
                    self._append_log(
                        data,
                        project["id"],
                        None,
                        payload.get("owner_agent", "system"),
                        "project_duplicate_reused",
                        f"复用已有项目，阻止重复创建：{requested_name}",
                    )
                    return project

            canonical = self._find_project_unlocked(data, CANONICAL_BOARD_PROJECT_ID)
            if not canonical:
                canonical = next(
                    (project for project in data.get("projects", []) if _normalize_name(project.get("name")) == _normalize_name(CANONICAL_BOARD_PROJECT_NAME)),
                    None,
                )
            if canonical and requested_name in TASK_PROJECT_NAME_MAP:
                task_title = TASK_PROJECT_NAME_MAP[requested_name]
                existing_task = next(
                    (task for task in canonical.get("tasks", []) if _normalize_name(task.get("title")) == _normalize_name(task_title)),
                    None,
                )
                if not existing_task:
                    task = {
                        "id": _new_id("task"),
                        "project_id": canonical["id"],
                        "title": task_title,
                        "description": payload.get("description", ""),
                        "assignee_agent": "",
                        "status": "todo",
                        "progress": 0,
                        "priority": payload.get("priority", "medium"),
                        "dependencies": [],
                        "acceptance_criteria": [],
                        "context": {
                            "created_from_project_request": requested_name,
                            "routed_at": now,
                        },
                        "result_summary": "",
                        "development_points": [],
                        "created_at": now,
                        "updated_at": now,
                    }
                    if requested_name == "知识绑定项目":
                        task["development_points"].append(self._make_point(task["id"], {"title": "绑定开发要点", "status": "todo"}, now))
                    canonical.setdefault("tasks", []).append(task)
                canonical["updated_at"] = now
                self._append_log(
                    data,
                    canonical["id"],
                    existing_task.get("id") if existing_task else canonical["tasks"][-1]["id"],
                    payload.get("owner_agent", "system"),
                    "project_request_routed_to_task",
                    f"将项目创建请求转为主项目任务：{requested_name}",
                )
                return canonical

            project_id = payload.get("id") or _new_id("proj")
            project_type = _normalize_project_type(payload.get("project_type") or payload.get("type"))
            context = _as_dict(payload.get("context"))
            context["project_type"] = project_type
            project = {
                "id": project_id,
                "name": payload["name"],
                "project_type": project_type,
                "type": project_type,
                "description": payload.get("description", ""),
                "status": payload.get("status", "planning"),
                "priority": payload.get("priority", "medium"),
                "owner_agent": payload.get("owner_agent", "optimus"),
                "progress": float(payload.get("progress", 0) or 0),
                "current_phase": payload.get("current_phase", "planning"),
                "context": context,
                "design_doc": self._normalize_design_doc(payload.get("design_doc"), project_id, now),
                "document_spec": self._normalize_document_spec(payload.get("document_spec"), project_id, now),
                "tasks": [],
                "created_at": now,
                "updated_at": now,
            }
            data["projects"].append(project)
            self._append_log(data, project["id"], None, payload.get("owner_agent", "system"), "project_created", f"项目创建：{project['name']}")
            return project

        return self._with_data(mutate)

    def delete_project(self, project_id: str) -> bool:
        def mutate(data):
            projects = data.get("projects", [])
            before = len(projects)
            data["projects"] = [project for project in projects if project.get("id") != project_id]
            if len(data["projects"]) == before:
                return False
            data["logs"] = [log for log in data.get("logs", []) if log.get("project_id") != project_id]
            return True

        return bool(self._with_data(mutate))

    def update_project(self, project_id: str, payload: dict) -> Optional[dict]:
        allowed = {"name", "description", "status", "priority", "owner_agent", "current_phase", "context", "progress", "project_type", "type", "document_spec"}

        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            for key, value in payload.items():
                if key in allowed and value is not None:
                    if key in {"project_type", "type"}:
                        project_type = _normalize_project_type(value)
                        project["project_type"] = project_type
                        project["type"] = project_type
                        project.setdefault("context", {})["project_type"] = project_type
                    elif key == "document_spec":
                        project["document_spec"] = self._normalize_document_spec(value, project_id, project.get("created_at") or _now_iso())
                    else:
                        project[key] = value
            project["updated_at"] = _now_iso()
            return project

        return self._with_data(mutate)


    def get_design_doc(self, project_id: str) -> Optional[dict]:
        project = self.get_project(project_id)
        if not project:
            return None
        return project.get("design_doc")

    def update_design_doc(self, project_id: str, payload: dict, agent_id: str = "project-manager") -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            current = self._normalize_design_doc(project.get("design_doc"), project_id, project.get("created_at") or _now_iso())
            merged = {**current, **payload}
            merged["id"] = current.get("id") or payload.get("id") or _new_id("design")
            merged["project_id"] = project_id
            merged["version"] = int(payload.get("version") or current.get("version") or 1)
            merged["updated_at"] = _now_iso()
            merged.setdefault("created_at", current.get("created_at") or merged["updated_at"])
            changelog = _as_list(merged.get("changelog"))
            if payload.get("change_summary"):
                changelog.append({
                    "version": merged["version"],
                    "agent_id": agent_id,
                    "summary": payload["change_summary"],
                    "created_at": merged["updated_at"],
                })
            merged["changelog"] = changelog[-50:]
            project["design_doc"] = self._normalize_design_doc(merged, project_id, merged.get("created_at") or _now_iso())
            project["updated_at"] = _now_iso()
            self._append_log(data, project_id, None, agent_id, "design_doc_updated", payload.get("change_summary") or "项目设计文档已更新")
            return project["design_doc"]

        return self._with_data(mutate)

    def revise_design_doc(self, project_id: str, payload: dict) -> Optional[dict]:
        agent_id = payload.get("agent_id", "project-manager")
        change_summary = payload.get("change_summary", "项目设计文档修订")

        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            current = self._normalize_design_doc(project.get("design_doc"), project_id, project.get("created_at") or _now_iso())
            version = int(current.get("version") or 1) + 1
            updates = _as_dict(payload.get("updates"))
            revised = {**current, **updates}
            revised["id"] = current.get("id") or _new_id("design")
            revised["project_id"] = project_id
            revised["version"] = version
            revised["status"] = payload.get("status") or "draft"
            revised["updated_at"] = _now_iso()
            revised["changelog"] = (_as_list(current.get("changelog")) + [{
                "version": version,
                "agent_id": agent_id,
                "summary": change_summary,
                "created_at": revised["updated_at"],
            }])[-50:]
            project["design_doc"] = self._normalize_design_doc(revised, project_id, current.get("created_at") or _now_iso())
            project["updated_at"] = _now_iso()
            log = self._append_log(data, project_id, None, agent_id, "design_doc_revised", change_summary)
            return {"design_doc": project["design_doc"], "log": log}

        return self._with_data(mutate)

    def approve_design_doc(self, project_id: str, agent_id: str = "project-manager") -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            doc = self._normalize_design_doc(project.get("design_doc"), project_id, project.get("created_at") or _now_iso())
            now = _now_iso()
            doc["status"] = "approved"
            doc["approved_by"] = agent_id
            doc["approved_at"] = now
            doc["updated_at"] = now
            doc["changelog"] = (_as_list(doc.get("changelog")) + [{
                "version": doc.get("version", 1),
                "agent_id": agent_id,
                "summary": "项目设计文档审批通过",
                "created_at": now,
            }])[-50:]
            project["design_doc"] = doc
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "design_doc_approved", "项目设计文档审批通过")
            return {"design_doc": doc, "log": log}

        return self._with_data(mutate)

    def get_agent_context(self, project_id: str, agents: Optional[list[dict]] = None, agent_id: Optional[str] = None) -> Optional[dict]:
        context = self.get_iteration_context(project_id, agents)
        if not context:
            return None
        project = context["project"]
        context["design_doc"] = project.get("design_doc")
        if agent_id:
            work = self.get_agent_work_items(agent_id)
            context["agent_id"] = agent_id
            context["agent_work"] = {
                "tasks": [item for item in work.get("tasks", []) if item.get("project_id") == project_id],
                "development_points": [item for item in work.get("development_points", []) if item.get("project_id") == project_id],
            }
        return context

    def add_task(self, project_id: str, payload: dict) -> Optional[dict]:
        now = _now_iso()

        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            task = {
                "id": payload.get("id") or _new_id("task"),
                "project_id": project_id,
                "type": payload.get("type") or _as_dict(payload.get("context")).get("task_type") or ("writing" if project.get("project_type") == "document" else "development"),
                "title": payload["title"],
                "description": payload.get("description", ""),
                "assignee_agent": payload.get("assignee_agent", ""),
                "assignee_agent_id": payload.get("assignee_agent_id") or payload.get("assignee_agent", ""),
                "status": payload.get("status", "todo"),
                "progress": float(payload.get("progress", 0) or 0),
                "priority": payload.get("priority", "medium"),
                "dependencies": _as_list(payload.get("dependencies")),
                "acceptance_criteria": _as_list(payload.get("acceptance_criteria")),
                "context": _as_dict(payload.get("context")),
                "result_summary": payload.get("result_summary", ""),
                "development_points": [],
                "created_at": now,
                "updated_at": now,
            }
            for point_payload in _as_list(payload.get("development_points")):
                task["development_points"].append(self._make_point(task["id"], point_payload, now))
            project.setdefault("tasks", []).append(task)
            self._append_log(data, project_id, task["id"], payload.get("assignee_agent") or "system", "task_created", f"任务创建：{task['title']}")
            return task

        return self._with_data(mutate)

    def update_task(self, task_id: str, payload: dict) -> Optional[dict]:
        allowed = {
            "title", "description", "type", "assignee_agent", "assignee_agent_id", "status", "progress", "priority",
            "dependencies", "acceptance_criteria", "context", "result_summary",
        }

        def mutate(data):
            project, task = self._find_task_unlocked(data, task_id)
            if not task:
                return None
            for key, value in payload.items():
                if key in allowed and value is not None:
                    task[key] = value
            task["updated_at"] = _now_iso()
            if project:
                self._append_log(data, project["id"], task_id, payload.get("assignee_agent") or "system", "task_updated", f"任务更新：{task['title']}")
            return task

        return self._with_data(mutate)

    def assign_task(self, task_id: str, assignee_agent: str) -> Optional[dict]:
        return self.update_task(task_id, {"assignee_agent": assignee_agent})

    def list_tasks(self, project_id: str) -> Optional[list[dict]]:
        project = self.get_project(project_id)
        if not project:
            return None
        return project.get("tasks", [])

    def add_point(self, task_id: str, payload: dict) -> Optional[dict]:
        now = _now_iso()

        def mutate(data):
            project, task = self._find_task_unlocked(data, task_id)
            if not task:
                return None
            point = self._make_point(task_id, payload, now)
            task.setdefault("development_points", []).append(point)
            if project:
                self._append_log(data, project["id"], task_id, payload.get("assigned_agent") or "system", "point_created", f"开发要点创建：{point['title']}")
            return point

        return self._with_data(mutate)

    def update_point(self, point_id: str, payload: dict) -> Optional[dict]:
        allowed = {"title", "description", "status", "weight", "completion_evidence", "checklist", "assigned_agent"}

        def mutate(data):
            project, task, point = self._find_point_unlocked(data, point_id)
            if not point:
                return None
            for key, value in payload.items():
                if key in allowed and value is not None:
                    point[key] = value
            if _is_done(str(point.get("status", ""))) and not point.get("completed_at"):
                point["completed_at"] = _now_iso()
            elif not _is_done(str(point.get("status", ""))):
                point["completed_at"] = None
            if project and task:
                self._append_log(data, project["id"], task["id"], payload.get("assigned_agent") or "system", "point_updated", f"开发要点更新：{point['title']}")
            return point

        return self._with_data(mutate)

    def list_points(self, task_id: str) -> Optional[list[dict]]:
        data = self._read()
        _, task = self._find_task_unlocked(data, task_id)
        if not task:
            return None
        return task.get("development_points", [])

    def get_agent_work_items(self, agent_id: str) -> dict:
        data = self._read()
        done = {"done", "completed"}
        assigned_tasks = []
        assigned_points = []
        for project in data.get("projects", []):
            for task in project.get("tasks", []):
                task_agent = task.get("assignee_agent")
                task_open = task.get("status") not in done
                if task_agent == agent_id and task_open:
                    assigned_tasks.append({
                        "project_id": project.get("id"),
                        "project_name": project.get("name"),
                        "task": task,
                    })
                for point in task.get("development_points", []):
                    point_agent = point.get("assigned_agent") or task_agent
                    if point_agent == agent_id and point.get("status") not in done:
                        assigned_points.append({
                            "project_id": project.get("id"),
                            "project_name": project.get("name"),
                            "task_id": task.get("id"),
                            "task_title": task.get("title"),
                            "point": point,
                        })
        return {
            "agent_id": agent_id,
            "tasks": assigned_tasks,
            "development_points": assigned_points,
            "total_tasks": len(assigned_tasks),
            "total_development_points": len(assigned_points),
        }

    def transition_point(self, point_id: str, action: str, agent_id: str = "", reason: str = "", completion_evidence: str = "", result_summary: str = "") -> Optional[dict]:
        status_by_action = {
            "claim": "in_progress",
            "release": "todo",
            "block": "blocked",
            "submit_review": "review",
        }
        if action not in status_by_action:
            return None

        def mutate(data):
            project, task, point = self._find_point_unlocked(data, point_id)
            if not point:
                return None
            now = _now_iso()
            next_status = status_by_action[action]
            point["status"] = next_status
            point["updated_at"] = now
            point["completed_at"] = None
            if action == "release":
                point["assigned_agent"] = ""
            elif agent_id:
                point["assigned_agent"] = agent_id
            if completion_evidence:
                point["completion_evidence"] = completion_evidence
            elif reason and action in {"block", "submit_review"}:
                point["completion_evidence"] = reason
            if result_summary:
                task["result_summary"] = result_summary
            task["updated_at"] = now
            project["updated_at"] = now
            action_name = {
                "claim": "point_claimed",
                "release": "point_released",
                "block": "point_blocked",
                "submit_review": "point_submitted_review",
            }[action]
            log = self._append_log(
                data,
                project["id"],
                task["id"],
                agent_id or point.get("assigned_agent") or "system",
                action_name,
                reason or completion_evidence or f"开发要点状态更新为 {next_status}：{point['title']}",
            )
            return {"project": project, "task": task, "point": point, "log": log}

        return self._with_data(mutate)

    def complete_point(self, point_id: str, agent_id: str, completion_evidence: str = "", result_summary: str = "") -> Optional[dict]:
        def mutate(data):
            project, task, point = self._find_point_unlocked(data, point_id)
            if not point:
                return None
            now = _now_iso()
            point["status"] = "done"
            point["completed_at"] = now
            point["updated_at"] = now
            if completion_evidence:
                point["completion_evidence"] = completion_evidence
            if agent_id:
                point["assigned_agent"] = point.get("assigned_agent") or agent_id
            if result_summary:
                task["result_summary"] = result_summary
            task["updated_at"] = now
            project["updated_at"] = now
            log = self._append_log(
                data,
                project["id"],
                task["id"],
                agent_id or point.get("assigned_agent") or "system",
                "point_completed",
                completion_evidence or f"开发要点完成：{point['title']}",
            )
            return {"project": project, "task": task, "point": point, "log": log}

        return self._with_data(mutate)

    def add_log(self, project_id: str, task_id: Optional[str], agent_id: str, action: str, content: str) -> Optional[dict]:
        def mutate(data):
            if not self._find_project_unlocked(data, project_id):
                return None
            return self._append_log(data, project_id, task_id, agent_id, action, content)

        return self._with_data(mutate)

    def list_logs(self, project_id: str, limit: int = 50) -> list[dict]:
        data = self._read()
        logs = [log for log in data.get("logs", []) if log.get("project_id") == project_id]
        return logs[-limit:]

    def list_conversation(self, project_id: str, limit: int = 80) -> Optional[list[dict]]:
        project = self.get_project(project_id)
        if not project:
            return None
        context = _as_dict(project.get("context"))
        messages = _as_list(context.get("conversations"))
        return messages[-limit:]

    def add_conversation_message(self, project_id: str, payload: dict) -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            now = _now_iso()
            context = _as_dict(project.get("context"))
            context["project_type"] = _normalize_project_type(project.get("project_type") or context.get("project_type"))
            messages = _as_list(context.get("conversations"))
            message = {
                "id": payload.get("id") or _new_id("chat"),
                "project_id": project_id,
                "agent_id": payload.get("agent_id") or "optimus",
                "role": payload.get("role") or "user",
                "message": str(payload.get("message") or payload.get("content") or "").strip(),
                "intent": payload.get("intent", "chat"),
                "project_type": context["project_type"],
                "task_id": payload.get("task_id", ""),
                "chapter_id": payload.get("chapter_id", ""),
                "created_at": payload.get("created_at") or now,
            }
            if payload.get("attachments") is not None:
                message["attachments"] = _as_list(payload.get("attachments"))
            messages.append(message)
            context["conversations"] = messages[-160:]
            project["context"] = context
            project["updated_at"] = now
            log = self._append_log(
                data,
                project_id,
                message.get("task_id") or None,
                message["agent_id"],
                "project_chat_message",
                message["message"],
            )
            return {"message": message, "conversation": context["conversations"], "log": log}

        return self._with_data(mutate)

    def build_project_chat_context(self, project_id: str, limit: int = 12) -> Optional[dict]:
        project = self.get_project(project_id)
        if not project:
            return None
        project_type = _normalize_project_type(project.get("project_type") or project.get("type") or _as_dict(project.get("context")).get("project_type"))
        messages = self.list_conversation(project_id, limit) or []
        if project_type == "document":
            spec = _as_dict(project.get("document_spec"))
            work_object = {
                "type": "document",
                "document_type": spec.get("document_type", ""),
                "writing_goal": spec.get("writing_goal", ""),
                "target_audience": spec.get("target_audience", ""),
                "outline": _as_list(spec.get("outline"))[:30],
                "chapters": _as_list(spec.get("chapters"))[:20],
                "assets": _as_list(spec.get("assets"))[:20],
                "references": _as_list(spec.get("references"))[:20],
            }
        else:
            design = _as_dict(project.get("design_doc"))
            work_object = {
                "type": "software",
                "summary": design.get("summary", ""),
                "usage_requirements": _as_list(design.get("usage_requirements"))[:20],
                "data_structure": _as_dict(design.get("data_structure")),
                "system_architecture": _as_dict(design.get("system_architecture")),
                "system_functions": _as_list(design.get("system_functions"))[:30],
                "api_interfaces": _as_list(design.get("api_interfaces"))[:30],
            }
        return {
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "project_type": project_type,
                "status": project.get("status"),
                "current_phase": project.get("current_phase"),
                "progress": project.get("progress", 0),
            },
            "work_object": work_object,
            "tasks": _as_list(project.get("tasks"))[:40],
            "recent_conversation": messages,
            "recent_logs": self.list_logs(project_id, 12),
        }

    def get_iteration_context(self, project_id: str, agents: Optional[list[dict]] = None) -> Optional[dict]:
        project = self.get_project(project_id)
        if not project:
            return None
        tasks = project.get("tasks", [])
        open_points = []
        blocked_items = []
        review_items = []
        all_points = []
        agent_workloads: dict[str, dict] = {}
        for task in tasks:
            task_status = str(task.get("status", ""))
            task_agent = task.get("assignee_agent") or ""
            if task_agent:
                workload = agent_workloads.setdefault(task_agent, {"agent_id": task_agent, "open_tasks": 0, "open_points": 0})
                if not _is_done(task_status):
                    workload["open_tasks"] += 1
            if task_status == "blocked":
                blocked_items.append({"type": "task", "task_id": task["id"], "title": task["title"], "assignee_agent": task_agent})
            if task_status == "review":
                review_items.append({"type": "task", "task_id": task["id"], "title": task["title"], "assignee_agent": task_agent})
            for point in task.get("development_points", []):
                all_points.append(point)
                point_status = str(point.get("status", ""))
                point_agent = point.get("assigned_agent") or task_agent
                if point_agent:
                    workload = agent_workloads.setdefault(point_agent, {"agent_id": point_agent, "open_tasks": 0, "open_points": 0})
                    if not _is_done(point_status):
                        workload["open_points"] += 1
                if not _is_done(point_status):
                    open_points.append({"task_id": task["id"], "task_title": task["title"], "task_assignee_agent": task_agent, **point})
                if point_status == "blocked":
                    blocked_items.append({"type": "point", "task_id": task["id"], "point_id": point["id"], "title": point["title"], "assigned_agent": point_agent})
                if point_status == "review":
                    review_items.append({"type": "point", "task_id": task["id"], "point_id": point["id"], "title": point["title"], "assigned_agent": point_agent})
        recent_logs = self.list_logs(project_id, 20)
        available_agents = [
            {"id": agent.get("id"), "name": agent.get("name"), "status": agent.get("status"), "current_task": agent.get("current_task")}
            for agent in (agents or [])
            if agent.get("status") in {"idle", "online"} or agent.get("current_task") in {"", "待分配", None}
        ]
        status_summary = {
            "tasks_by_status": _status_counts(tasks),
            "points_by_status": _status_counts(all_points),
            "total_tasks": len(tasks),
            "total_points": len(all_points),
            "open_points": len(open_points),
            "blocked_items": len(blocked_items),
            "review_items": len(review_items),
        }
        project_manager_output_contract = {
            "reasoning_summary": "short manager decision summary",
            "agent_id": "project-manager agent id",
            "project_updates": {"current_phase": "optional next phase", "context": {"optional": "mergeable project context"}},
            "new_tasks": ["TaskCreate fields including development_points"],
            "updated_tasks": ["task patch objects with id/task_id"],
            "new_development_points": ["point objects with task_id"],
            "updated_development_points": ["point patch objects with id/point_id"],
        }
        suggestions = []
        if blocked_items:
            suggestions.append({"action": "resolve_blockers", "reason": "blocked tasks or points exist", "count": len(blocked_items)})
        if review_items:
            suggestions.append({"action": "review_pending_work", "reason": "items are waiting for review", "count": len(review_items)})
        if open_points:
            suggestions.append({"action": "assign_open_points", "reason": "open development points are available", "count": len(open_points)})
        if not tasks:
            suggestions.append({"action": "decompose_initial_tasks", "reason": "project has no tasks yet", "count": 0})
        return {
            "project": project,
            "progress": project.get("progress", 0),
            "current_phase": project.get("current_phase", ""),
            "status_summary": status_summary,
            "tasks": tasks,
            "open_points": open_points,
            "blocked_items": blocked_items,
            "review_items": review_items,
            "recent_logs": recent_logs,
            "available_agents": available_agents,
            "agent_workloads": list(agent_workloads.values()),
            "project_manager_input": {
                "project_id": project_id,
                "project_name": project.get("name"),
                "goal": _as_dict(project.get("context")).get("goal", project.get("description", "")),
                "progress": project.get("progress", 0),
                "current_phase": project.get("current_phase", ""),
                "status_summary": status_summary,
                "open_points": open_points,
                "blocked_items": blocked_items,
                "review_items": review_items,
                "available_agents": available_agents,
                "recent_logs": recent_logs,
            },
            "project_manager_output_contract": project_manager_output_contract,
            "suggested_next_actions": suggestions,
        }

    def add_knowledge_link(self, target_type: str, target_id: str, payload: dict) -> Optional[dict]:
        def mutate(data):
            located = self._find_knowledge_target_unlocked(data, target_type, target_id)
            if not located:
                return None
            project, task, point, target = located
            now = _now_iso()
            link = self._normalize_knowledge_link(payload, now)
            if not link.get("node_id"):
                return None
            context = target.setdefault("context", {})
            if not isinstance(context, dict):
                context = {}
                target["context"] = context
            links = _as_list(context.get("knowledge_links"))
            links = [existing for existing in links if existing.get("node_id") != link["node_id"]]
            links.append(link)
            context["knowledge_links"] = links
            target["updated_at"] = now
            if task:
                task["updated_at"] = now
            if project:
                project["updated_at"] = now
            log = self._append_log(
                data,
                project["id"] if project else target_id,
                task.get("id") if task else None,
                link.get("confirmed_by") or "project-manager",
                "knowledge_link_added",
                f"知识节点关联：{link.get('title') or link['node_id']}",
            )
            return {
                "target_type": target_type,
                "target_id": target_id,
                "knowledge_link": link,
                "knowledge_links": links,
                "log": log,
            }

        return self._with_data(mutate)

    def remove_knowledge_link(self, target_type: str, target_id: str, node_id: str, removed_by: str = "project-manager") -> Optional[dict]:
        def mutate(data):
            located = self._find_knowledge_target_unlocked(data, target_type, target_id)
            if not located:
                return None
            project, task, point, target = located
            context = target.setdefault("context", {})
            if not isinstance(context, dict):
                context = {}
                target["context"] = context
            before = _as_list(context.get("knowledge_links"))
            after = [link for link in before if link.get("node_id") != node_id]
            if len(after) == len(before):
                return None
            now = _now_iso()
            context["knowledge_links"] = after
            target["updated_at"] = now
            if task:
                task["updated_at"] = now
            if project:
                project["updated_at"] = now
            log = self._append_log(
                data,
                project["id"] if project else target_id,
                task.get("id") if task else None,
                removed_by or "project-manager",
                "knowledge_link_removed",
                f"知识节点移除：{node_id}",
            )
            return {
                "target_type": target_type,
                "target_id": target_id,
                "node_id": node_id,
                "knowledge_links": after,
                "log": log,
            }

        return self._with_data(mutate)

    def decompose_project(self, project_id: str, payload: dict) -> Optional[dict]:
        reasoning = payload.get("reasoning_summary", "")
        agent_id = payload.get("agent_id", "project-manager")
        created_tasks = []
        updated_tasks = []
        created_points = []
        updated_points = []
        log = None

        def mutate(data):
            nonlocal log
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            project_updates = _as_dict(payload.get("project_updates"))
            for key in ("name", "description", "status", "priority", "owner_agent", "current_phase"):
                if key in project_updates and project_updates[key] is not None:
                    project[key] = project_updates[key]
            if isinstance(project_updates.get("context"), dict):
                merged_context = _as_dict(project.get("context")).copy()
                merged_context.update(project_updates["context"])
                project["context"] = merged_context
            for task_payload in _as_list(payload.get("new_tasks")):
                task_payload = dict(task_payload)
                task_payload.setdefault("assignee_agent", task_payload.get("assignee_agent", ""))
                task = {
                    "id": task_payload.get("id") or _new_id("task"),
                    "project_id": project_id,
                    "title": task_payload["title"],
                    "description": task_payload.get("description", ""),
                    "assignee_agent": task_payload.get("assignee_agent", ""),
                    "status": task_payload.get("status", "todo"),
                    "progress": float(task_payload.get("progress", 0) or 0),
                    "priority": task_payload.get("priority", "medium"),
                    "dependencies": _as_list(task_payload.get("dependencies")),
                    "acceptance_criteria": _as_list(task_payload.get("acceptance_criteria")),
                    "context": _as_dict(task_payload.get("context")),
                    "result_summary": task_payload.get("result_summary", ""),
                    "development_points": [],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
                for point_payload in _as_list(task_payload.get("development_points")):
                    task["development_points"].append(self._make_point(task["id"], point_payload, _now_iso()))
                project.setdefault("tasks", []).append(task)
                created_tasks.append(task)
            for task_payload in _as_list(payload.get("updated_tasks")):
                task_id = task_payload.get("id") or task_payload.get("task_id")
                _, task = self._find_task_unlocked(data, task_id)
                if not task:
                    continue
                for key in ("title", "description", "assignee_agent", "status", "priority", "dependencies", "acceptance_criteria", "context", "result_summary"):
                    if key in task_payload:
                        task[key] = task_payload[key]
                task["updated_at"] = _now_iso()
                updated_tasks.append(task)
            for point_payload in _as_list(payload.get("new_development_points")):
                task_id = point_payload.get("task_id")
                _, task = self._find_task_unlocked(data, task_id)
                if not task:
                    continue
                point = self._make_point(task_id, point_payload, _now_iso())
                task.setdefault("development_points", []).append(point)
                created_points.append(point)
            for point_payload in _as_list(payload.get("updated_development_points")):
                point_id = point_payload.get("id") or point_payload.get("point_id")
                _, task, point = self._find_point_unlocked(data, point_id)
                if not point:
                    continue
                for key in ("title", "description", "status", "weight", "completion_evidence", "checklist", "assigned_agent"):
                    if key in point_payload and point_payload[key] is not None:
                        point[key] = point_payload[key]
                if _is_done(str(point.get("status", ""))) and not point.get("completed_at"):
                    point["completed_at"] = _now_iso()
                elif not _is_done(str(point.get("status", ""))):
                    point["completed_at"] = None
                if task:
                    task["updated_at"] = _now_iso()
                updated_points.append(point)
            log = self._append_log(
                data,
                project_id,
                None,
                agent_id,
                "project_decomposed",
                reasoning or f"新增 {len(created_tasks)} 个任务，更新 {len(updated_tasks)} 个任务，新增 {len(created_points)} 个开发要点，更新 {len(updated_points)} 个开发要点",
            )
            return {
                "project_id": project_id,
                "created_tasks": created_tasks,
                "updated_tasks": updated_tasks,
                "created_development_points": created_points,
                "updated_development_points": updated_points,
                "log": log,
            }

        return self._with_data(mutate)


    def _normalize_knowledge_link(self, payload: dict, now: str) -> dict:
        return {
            "node_id": str(payload.get("node_id") or payload.get("id") or "").strip(),
            "title": payload.get("title", ""),
            "type": payload.get("type", ""),
            "path": payload.get("path", ""),
            "relation": payload.get("relation", "related"),
            "reason": payload.get("reason", ""),
            "confirmed_by": payload.get("confirmed_by") or payload.get("agent_id") or "project-manager",
            "confirmed_at": payload.get("confirmed_at") or now,
        }

    def _find_knowledge_target_unlocked(self, data: dict, target_type: str, target_id: str):
        if target_type == "project":
            project = self._find_project_unlocked(data, target_id)
            return (project, None, None, project) if project else None
        if target_type == "task":
            project, task = self._find_task_unlocked(data, target_id)
            return (project, task, None, task) if task else None
        if target_type == "point":
            project, task, point = self._find_point_unlocked(data, target_id)
            return (project, task, point, point) if point else None
        return None

    def _normalize_design_doc(self, payload: Any, project_id: str, now: str) -> dict:
        payload = _as_dict(payload)
        doc_id = payload.get("id") or _new_id("design")
        created_at = payload.get("created_at") or now
        updated_at = payload.get("updated_at") or now
        return {
            "id": doc_id,
            "project_id": project_id,
            "version": int(payload.get("version") or 1),
            "status": payload.get("status", "draft"),
            "summary": payload.get("summary", ""),
            "usage_requirements": _as_list(payload.get("usage_requirements") or payload.get("requirements")),
            "data_structure": _as_dict(payload.get("data_structure") or payload.get("data_model")) or {
                "entities": [],
                "relationships": [],
                "storage": [],
                "status_enums": [],
            },
            "system_architecture": _as_dict(payload.get("system_architecture") or payload.get("architecture")) or {
                "components": [],
                "data_flow": [],
                "agent_roles": [],
                "security_boundaries": [],
            },
            "system_functions": _as_list(payload.get("system_functions") or payload.get("features")),
            "api_interfaces": _as_list(payload.get("api_interfaces") or payload.get("api_contracts")),
            "task_breakdown_guidance": _as_list(payload.get("task_breakdown_guidance")),
            "parallel_tasks": _as_list(payload.get("parallel_tasks")),
            "risks": _as_list(payload.get("risks")),
            "changelog": _as_list(payload.get("changelog")),
            "author_agent": payload.get("author_agent", "project-manager"),
            "approved_by": payload.get("approved_by", ""),
            "approved_at": payload.get("approved_at"),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _normalize_document_spec(self, payload: Any, project_id: str, now: str) -> dict:
        payload = _as_dict(payload)
        chapters = []
        for index, item in enumerate(_as_list(payload.get("chapters") or payload.get("sections"))):
            item = _as_dict(item) if not isinstance(item, str) else {"title": item}
            chapters.append({
                "id": item.get("id") or _new_id("chapter"),
                "project_id": project_id,
                "parent_id": item.get("parent_id", ""),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "main_content": item.get("main_content") or item.get("content_brief", ""),
                "key_points": _as_list(item.get("key_points")),
                "images": _as_list(item.get("images")),
                "status": item.get("status", "planning"),
                "assigned_agent": item.get("assigned_agent", ""),
                "order_index": int(item.get("order_index") if item.get("order_index") is not None else index),
            })
        assets = []
        for index, item in enumerate(_as_list(payload.get("assets") or payload.get("image_plan"))):
            item = _as_dict(item) if not isinstance(item, str) else {"title": item}
            assets.append({
                "id": item.get("id") or _new_id("asset"),
                "project_id": project_id,
                "chapter_id": item.get("chapter_id") or item.get("section_id", ""),
                "type": item.get("type", "image"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "file_path": item.get("file_path", ""),
                "status": item.get("status", "planned"),
                "order_index": int(item.get("order_index") if item.get("order_index") is not None else index),
            })
        return {
            "document_type": payload.get("document_type", "报告"),
            "writing_goal": payload.get("writing_goal", ""),
            "target_audience": payload.get("target_audience", ""),
            "outline": _as_list(payload.get("outline")),
            "chapters": chapters,
            "assets": assets,
            "references": _as_list(payload.get("references") or payload.get("reference_plan")),
            "output_format": payload.get("output_format", "Markdown / Word / PDF"),
            "created_at": payload.get("created_at") or now,
            "updated_at": payload.get("updated_at") or now,
        }

    def _make_point(self, task_id: str, payload: dict, now: str) -> dict:
        status = payload.get("status", "todo")
        return {
            "id": payload.get("id") or _new_id("point"),
            "task_id": task_id,
            "title": payload["title"],
            "description": payload.get("description", ""),
            "status": status,
            "weight": float(payload.get("weight", 1) or 1),
            "completion_evidence": payload.get("completion_evidence", ""),
            "checklist": _as_list(payload.get("checklist")),
            "assigned_agent": payload.get("assigned_agent", ""),
            "context": _as_dict(payload.get("context")),
            "completed_at": now if _is_done(str(status)) else None,
            "created_at": now,
            "updated_at": now,
        }

    def _append_log(self, data: dict, project_id: str, task_id: Optional[str], agent_id: str, action: str, content: str) -> dict:
        log = {
            "id": _new_id("log"),
            "project_id": project_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "action": action,
            "content": content,
            "created_at": _now_iso(),
        }
        data.setdefault("logs", []).append(log)
        data["logs"] = data["logs"][-500:]
        return log

    def _find_project_unlocked(self, data: dict, project_id: str) -> Optional[dict]:
        for project in data.get("projects", []):
            if project.get("id") == project_id:
                return project
        return None

    def _find_task_unlocked(self, data: dict, task_id: str) -> tuple[Optional[dict], Optional[dict]]:
        for project in data.get("projects", []):
            for task in project.get("tasks", []):
                if task.get("id") == task_id:
                    return project, task
        return None, None

    def _find_point_unlocked(self, data: dict, point_id: str) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
        for project in data.get("projects", []):
            for task in project.get("tasks", []):
                for point in task.get("development_points", []):
                    if point.get("id") == point_id:
                        return project, task, point
        return None, None, None


project_manager = ProjectManager()
