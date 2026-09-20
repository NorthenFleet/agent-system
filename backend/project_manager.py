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
from services.project_composition import (
    PROJECT_RELATION_TYPES,
    normalize_project_composition,
    project_relation_id,
)
from services.product_delivery_service import product_delivery_service
from services.product_service import product_registry_service
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
    if value in {"research", "study", "research_project"}:
        return "research"
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

    def _uses_unified_store(self) -> bool:
        return os.path.abspath(self.file_path) == os.path.abspath(PROJECTS_FILE)

    def _load_unlocked(self) -> dict:
        if self._uses_unified_store():
            data = unified_data_manager.load_projects_document()
        elif os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = self._default_data()
        data.setdefault("version", 1)
        data.setdefault("last_updated", _now_iso())
        data.setdefault("projects", [])
        data.setdefault("logs", [])
        return data

    def _save_unlocked(self, data: dict) -> None:
        data["last_updated"] = _now_iso()
        if self._uses_unified_store():
            unified_data_manager.save_projects_document(data)
        else:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

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
        normalize_project_composition(project)
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
            self._sync_task_progress_unlocked(task, touch=False)
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
            context = dict(_as_dict(payload.get("context")))
            context.pop("project_relations", None)
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
                "enabled_modules": _as_list(payload.get("enabled_modules")),
                "product_bindings": _as_list(payload.get("product_bindings")),
                "project_relations": [],
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
            for project in data["projects"]:
                normalize_project_composition(project)
                relations = [
                    relation for relation in _as_list(project.get("project_relations"))
                    if project_id not in {
                        relation.get("source_project_id"),
                        relation.get("target_project_id"),
                    }
                ]
                project["project_relations"] = relations
                project.setdefault("context", {})["project_relations"] = relations
            data["logs"] = [log for log in data.get("logs", []) if log.get("project_id") != project_id]
            return True

        return bool(self._with_data(mutate))

    def update_project(self, project_id: str, payload: dict) -> Optional[dict]:
        allowed = {
            "name", "description", "status", "priority", "owner_agent", "current_phase",
            "context", "progress", "project_type", "type", "document_spec",
            "enabled_modules", "product_bindings",
        }

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
                    elif key == "context":
                        next_context = dict(_as_dict(value))
                        next_context.pop("project_relations", None)
                        current_context = dict(_as_dict(project.get("context")))
                        current_context.update(next_context)
                        project["context"] = current_context
                    else:
                        project[key] = value
            project["updated_at"] = _now_iso()
            return project

        return self._with_data(mutate)

    def migrate_composition_model(self) -> int:
        """Persist idempotent module and product-binding migration for existing projects."""
        def mutate(data):
            changed = 0
            for project in data.get("projects", []):
                if normalize_project_composition(project):
                    changed += 1
            if changed:
                data["version"] = max(int(data.get("version") or 1), 3)
            return changed

        return int(self._with_data(mutate))

    def link_projects(
        self,
        source_project_id: str,
        target_project_id: str,
        *,
        relation_type: str = "course_implementation",
        purpose: str = "",
        source_role: str = "",
        target_role: str = "",
        context_policy: str = "bidirectional_summary",
        context_contract: Optional[dict] = None,
        actor_id: str = "project-manager",
    ) -> Optional[dict]:
        relation_type = str(relation_type or "course_implementation").strip()
        if relation_type not in PROJECT_RELATION_TYPES:
            raise ValueError(f"不支持的项目关系类型：{relation_type}")
        if not source_project_id or not target_project_id or source_project_id == target_project_id:
            raise ValueError("项目关系必须连接两个不同项目")
        now = _now_iso()

        def mutate(data):
            source = self._find_project_unlocked(data, source_project_id)
            target = self._find_project_unlocked(data, target_project_id)
            if not source or not target:
                return None
            normalize_project_composition(source)
            normalize_project_composition(target)
            source_type = _normalize_project_type(source.get("project_type"))
            target_type = _normalize_project_type(target.get("project_type"))
            if relation_type == "course_implementation" and (source_type != "document" or target_type != "software"):
                raise ValueError("course_implementation 必须从文档课程项目指向软件实现项目")
            relation = {
                "id": project_relation_id(source_project_id, target_project_id, relation_type),
                "source_project_id": source_project_id,
                "target_project_id": target_project_id,
                "relation_type": relation_type,
                "status": "active",
                "purpose": str(purpose or ""),
                "source_role": str(source_role or ("course_documentation" if source_type == "document" else "source")),
                "target_role": str(target_role or ("software_implementation" if target_type == "software" else "reference_document")),
                "context_policy": str(context_policy or "bidirectional_summary"),
                "context_contract": _as_dict(context_contract),
                "created_by": actor_id,
                "created_at": now,
                "updated_at": now,
            }
            for project in (source, target):
                relations = [
                    item for item in _as_list(project.get("project_relations"))
                    if item.get("id") != relation["id"]
                ]
                relations.append(copy.deepcopy(relation))
                project["project_relations"] = relations
                project.setdefault("context", {})["project_relations"] = relations
                project["updated_at"] = now
            self._append_log(
                data,
                source_project_id,
                None,
                actor_id,
                "project_relation_linked",
                f"关联项目：{source.get('name')} → {target.get('name')}（{relation_type}）",
            )
            self._append_log(
                data,
                target_project_id,
                None,
                actor_id,
                "project_relation_linked",
                f"关联项目：{source.get('name')} → {target.get('name')}（{relation_type}）",
            )
            return relation

        return self._with_data(mutate)

    def remove_project_relation(
        self,
        project_id: str,
        relation_id: str,
        actor_id: str = "project-manager",
    ) -> bool:
        def mutate(data):
            owner = self._find_project_unlocked(data, project_id)
            if not owner:
                return False
            normalize_project_composition(owner)
            relation = next(
                (item for item in _as_list(owner.get("project_relations")) if item.get("id") == relation_id),
                None,
            )
            if not relation:
                return False
            for project in data.get("projects", []):
                normalize_project_composition(project)
                relations = [
                    item for item in _as_list(project.get("project_relations"))
                    if item.get("id") != relation_id
                ]
                project["project_relations"] = relations
                project.setdefault("context", {})["project_relations"] = relations
            self._append_log(
                data,
                project_id,
                None,
                actor_id,
                "project_relation_removed",
                f"移除项目关系：{relation_id}",
            )
            return True

        return bool(self._with_data(mutate))

    def get_project_relationship_context(self, project_id: str) -> Optional[dict]:
        data = self._read()
        project = self._find_project_unlocked(data, project_id)
        if not project:
            return None
        return self._build_project_relationship_context(project, data.get("projects", []))

    @staticmethod
    def _relation_project_summary(project: dict) -> dict:
        project_type = _normalize_project_type(project.get("project_type"))
        context = _as_dict(project.get("context"))
        tasks = _as_list(project.get("tasks"))
        if project_type == "document":
            spec = _as_dict(project.get("document_spec"))
            work_object = {
                "document_type": spec.get("document_type", ""),
                "writing_goal": spec.get("writing_goal", ""),
                "target_audience": spec.get("target_audience", ""),
                "chapters": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "summary": item.get("summary") or item.get("main_content") or "",
                        "status": item.get("status"),
                    }
                    for item in _as_list(spec.get("chapters"))[:12]
                    if isinstance(item, dict)
                ],
                "next_step": context.get("next_step", ""),
            }
        else:
            design = _as_dict(project.get("design_doc"))
            work_object = {
                "summary": design.get("summary", ""),
                "usage_requirements": _as_list(design.get("usage_requirements"))[:12],
                "system_functions": _as_list(design.get("system_functions"))[:16],
                "api_interfaces": _as_list(design.get("api_interfaces"))[:12],
                "repository": context.get("repository") or context.get("repo") or context.get("workspace_path") or "",
            }
        return {
            "id": project.get("id"),
            "name": project.get("name"),
            "project_type": project_type,
            "description": project.get("description", ""),
            "goal": context.get("goal") or (
                _as_dict(project.get("document_spec")).get("writing_goal")
                if project_type == "document"
                else project.get("description", "")
            ),
            "status": project.get("status"),
            "progress": project.get("progress", 0),
            "current_phase": project.get("current_phase", ""),
            "task_summary": {
                "total": len(tasks),
                "open": len([task for task in tasks if not _is_done(str(task.get("status", "")))]),
                "recent": [
                    {
                        "id": task.get("id"),
                        "title": task.get("title"),
                        "status": task.get("status"),
                        "progress": task.get("progress", 0),
                    }
                    for task in tasks[:10]
                ],
            },
            "work_object": work_object,
        }

    def _build_project_relationship_context(self, project: dict, projects: list[dict]) -> dict:
        project_id = str(project.get("id") or "")
        project_type = _normalize_project_type(project.get("project_type"))
        project_map = {str(item.get("id")): item for item in projects if item.get("id")}
        resolved_relations: list[dict] = []
        implementation_project = None
        source_documents: list[dict] = []
        for relation in _as_list(project.get("project_relations")):
            if relation.get("status") != "active":
                continue
            is_source = relation.get("source_project_id") == project_id
            counterpart_id = (
                relation.get("target_project_id") if is_source else relation.get("source_project_id")
            )
            counterpart = project_map.get(str(counterpart_id or ""))
            counterpart_summary = self._relation_project_summary(counterpart) if counterpart else {
                "id": counterpart_id,
                "name": "关联项目已不存在",
                "project_type": "unknown",
                "status": "missing",
            }
            current_role = relation.get("source_role") if is_source else relation.get("target_role")
            counterpart_role = relation.get("target_role") if is_source else relation.get("source_role")
            resolved = {
                **relation,
                "direction": "outbound" if is_source else "inbound",
                "current_role": current_role,
                "counterpart_role": counterpart_role,
                "counterpart": counterpart_summary,
            }
            resolved_relations.append(resolved)
            if counterpart_summary.get("project_type") == "software" and implementation_project is None:
                implementation_project = counterpart_summary
            if counterpart_summary.get("project_type") == "document":
                source_documents.append(counterpart_summary)

        current_responsibility = (
            "维护课程体系、兵棋规则与教学文档，提供软件需求和验收依据，不直接执行代码开发。"
            if project_type == "document"
            else "实现水面舰艇作战软件与兵棋推演能力，只修改软件仓库，并用关联课程/规则文档作为需求与验收来源。"
        )
        related_summaries = [item["counterpart"] for item in resolved_relations]
        goals = [
            str(item.get("goal") or item.get("description") or "").strip()
            for item in [self._relation_project_summary(project), *related_summaries]
        ]
        return {
            "project_id": project_id,
            "operating_model": "课程文档项目负责教学与规则事实；软件项目负责代码、测试与运行交付；双方通过稳定项目 ID 共享摘要背景。",
            "current_project_role": "course_documentation" if project_type == "document" else "software_implementation",
            "current_project_responsibility": current_responsibility,
            "shared_goal": "；".join(dict.fromkeys(goal for goal in goals if goal))[:1200],
            "relations": resolved_relations,
            "implementation_project": implementation_project,
            "source_documents": source_documents,
            "boundaries": [
                "文档任务不得直接作为软件 Codex Job 执行。",
                "软件任务必须在 software 项目中生成计划并由管理员批准。",
                "智能体只读取关联项目摘要与关键验收信息，不无边界拼接全部历史。",
                "部署发布、权限扩大和高风险变更仍需单独审批。",
            ],
        }


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

        task = self._with_data(mutate)
        self._record_task_completion(task)
        return task

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

        task = self._with_data(mutate)
        self._record_task_completion(task)
        return task

    def delete_task(self, project_id: str, task_id: str) -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project:
                return None
            tasks = _as_list(project.get("tasks"))
            kept = [task for task in tasks if task.get("id") != task_id]
            if len(kept) == len(tasks):
                return None
            removed = next(task for task in tasks if task.get("id") == task_id)
            project["tasks"] = kept
            project["updated_at"] = _now_iso()
            self._append_log(data, project_id, task_id, "system", "task_deleted", f"任务删除：{removed.get('title', task_id)}")
            return removed

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
            self._sync_task_progress_unlocked(task)
            if project:
                self._append_log(data, project["id"], task_id, payload.get("assigned_agent") or "system", "point_created", f"开发要点创建：{point['title']}")
            return point

        return self._with_data(mutate)

    @staticmethod
    def _sync_task_progress_unlocked(task: dict, *, touch: bool = True) -> None:
        points = _as_list(task.get("development_points"))
        if not points:
            return
        total_weight = sum(max(float(point.get("weight", 1) or 1), 0.0) for point in points)
        if total_weight <= 0:
            total_weight = float(len(points))
        progress_factor = {
            "todo": 0.0,
            "ready": 0.0,
            "in_progress": 0.5,
            "running": 0.5,
            "blocked": 0.5,
            "review": 0.9,
            "done": 1.0,
            "completed": 1.0,
        }
        weighted_progress = sum(
            max(float(point.get("weight", 1) or 1), 0.0)
            * progress_factor.get(str(point.get("status") or "todo"), 0.0)
            for point in points
        )
        task["progress"] = round(min(100.0, weighted_progress / total_weight * 100.0), 1)
        statuses = {str(point.get("status") or "todo") for point in points}
        if statuses <= {"done", "completed"}:
            task["status"] = "done"
            task["progress"] = 100.0
        elif statuses & {"review"}:
            task["status"] = "review"
        elif statuses & {"in_progress", "running"}:
            task["status"] = "in_progress"
        elif statuses & {"blocked"}:
            task["status"] = "blocked"
        elif statuses & {"done", "completed"}:
            task["status"] = "in_progress"
        else:
            task["status"] = "todo"
        if touch:
            task["updated_at"] = _now_iso()

    def _record_task_completion_by_id(self, task_id: str) -> None:
        if not task_id:
            return
        data = self._read()
        project, task = self._find_task_unlocked(data, task_id)
        if project and task:
            self._record_task_completion(task, project)

    def _record_task_completion(self, task: Optional[dict], project: Optional[dict] = None) -> None:
        """Record product output after persistence; ledger failure never blocks task state."""
        if not task or not _is_done(str(task.get("status") or "")):
            return
        try:
            if project is None:
                project = self.get_project(str(task.get("project_id") or ""))
            if project:
                product_delivery_service.register_task_completion(project, task)
        except Exception:
            # The task manager is authoritative for work state. Product tracking
            # is an integration projection and must remain retryable.
            return

    def update_point(self, point_id: str, payload: dict) -> Optional[dict]:
        allowed = {
            "title",
            "description",
            "status",
            "weight",
            "completion_evidence",
            "checklist",
            "assigned_agent",
            "context",
        }

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
                self._sync_task_progress_unlocked(task)
                self._append_log(data, project["id"], task["id"], payload.get("assigned_agent") or "system", "point_updated", f"开发要点更新：{point['title']}")
            return point

        point = self._with_data(mutate)
        if point:
            self._record_task_completion_by_id(str(point.get("task_id") or ""))
        return point

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
            "reject_review": "todo",
            "retry": "todo",
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
            elif agent_id and action not in {"reject_review", "retry"}:
                point["assigned_agent"] = agent_id
            if completion_evidence:
                point["completion_evidence"] = completion_evidence
            elif reason and action in {"block", "submit_review", "reject_review", "retry"}:
                point["completion_evidence"] = reason
            if result_summary:
                task["result_summary"] = result_summary
            self._sync_task_progress_unlocked(task)
            project["updated_at"] = now
            action_name = {
                "claim": "point_claimed",
                "release": "point_released",
                "block": "point_blocked",
                "submit_review": "point_submitted_review",
                "reject_review": "point_review_rejected",
                "retry": "point_requeued",
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
            self._sync_task_progress_unlocked(task)
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

        result = self._with_data(mutate)
        if result:
            self._record_task_completion(result.get("task"), result.get("project"))
        return result

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
        relationship_context = self.get_project_relationship_context(project_id) or {
            "project_id": project_id,
            "relations": [],
            "boundaries": [],
        }
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
            "relationship_context": relationship_context,
            "background_context": relationship_context,
            "tasks": _as_list(project.get("tasks"))[:40],
            "recent_conversation": messages,
            "recent_logs": self.list_logs(project_id, 12),
        }

    def get_iteration_context(self, project_id: str, agents: Optional[list[dict]] = None) -> Optional[dict]:
        project = self.get_project(project_id)
        if not project:
            return None
        relationship_context = self.get_project_relationship_context(project_id) or {
            "project_id": project_id,
            "relations": [],
            "boundaries": [],
        }
        tasks = project.get("tasks", [])
        open_points = []
        blocked_items = []
        review_items = []
        all_points = []
        agent_workloads: dict[str, dict] = {}
        for task in tasks:
            task_status = str(task.get("status", ""))
            task_agent = task.get("assignee_agent") or ""
            task_points = list(task.get("development_points") or [])
            if task_agent:
                workload = agent_workloads.setdefault(task_agent, {"agent_id": task_agent, "open_tasks": 0, "open_points": 0})
                if not _is_done(task_status):
                    workload["open_tasks"] += 1
            if task_status == "blocked" and not any(
                str(point.get("status") or "") == "blocked"
                for point in task_points
            ):
                blocked_items.append({"type": "task", "task_id": task["id"], "title": task["title"], "assignee_agent": task_agent})
            if task_status == "review" and not any(
                str(point.get("status") or "") == "review"
                for point in task_points
            ):
                review_items.append({"type": "task", "task_id": task["id"], "title": task["title"], "assignee_agent": task_agent})
            for point in task_points:
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
        product_context = self._get_product_iteration_context(project)
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
        if product_context["summary"]["pending_deliverable_reviews"]:
            suggestions.append({
                "action": "review_product_deliverables",
                "reason": "product deliverables are waiting for acceptance",
                "count": product_context["summary"]["pending_deliverable_reviews"],
                "product_ids": product_context["summary"]["products_pending_review"],
            })
        if product_context["summary"]["accepted_unreleased_deliverables"]:
            suggestions.append({
                "action": "create_product_release",
                "reason": "accepted product deliverables have not entered a release",
                "count": product_context["summary"]["accepted_unreleased_deliverables"],
                "product_ids": product_context["summary"]["products_pending_release"],
            })
        if product_context["summary"]["runtime_issues"]:
            suggestions.append({
                "action": "investigate_product_runtime",
                "reason": "bound product runtime is degraded or offline",
                "count": product_context["summary"]["runtime_issues"],
                "product_ids": product_context["summary"]["products_with_runtime_issues"],
            })
        if open_points:
            suggestions.append({"action": "assign_open_points", "reason": "open development points are available", "count": len(open_points)})
        if not tasks:
            suggestions.append({"action": "decompose_initial_tasks", "reason": "project has no tasks yet", "count": 0})
        if not relationship_context.get("relations"):
            suggestions.append({
                "action": "link_project_background",
                "reason": "project has no related course, document, or implementation project",
                "count": 0,
            })
        return {
            "project": project,
            "progress": project.get("progress", 0),
            "current_phase": project.get("current_phase", ""),
            "status_summary": status_summary,
            "tasks": tasks,
            "open_points": open_points,
            "blocked_items": blocked_items,
            "review_items": review_items,
            "product_context": product_context,
            "relationship_context": relationship_context,
            "background_context": relationship_context,
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
                "product_context": product_context,
                "relationship_context": relationship_context,
                "background_context": relationship_context,
                "available_agents": available_agents,
                "recent_logs": recent_logs,
            },
            "project_manager_output_contract": project_manager_output_contract,
            "suggested_next_actions": suggestions,
        }

    @staticmethod
    def _get_product_iteration_context(project: dict) -> dict:
        """Project-manager read model over the product delivery ledger; never mutates it."""
        rows = []
        summary = {
            "bound_products": 0,
            "pending_deliverable_reviews": 0,
            "accepted_unreleased_deliverables": 0,
            "runtime_issues": 0,
            "products_pending_review": [],
            "products_pending_release": [],
            "products_with_runtime_issues": [],
        }
        bindings = _as_list(project.get("product_bindings"))
        for binding in bindings:
            if not isinstance(binding, dict) or str(binding.get("status") or "bound") != "bound":
                continue
            product_id = str(binding.get("product_id") or "")
            product = product_registry_service.get_product(product_id) if product_id else None
            if not product:
                continue
            deliverables = product_registry_service.list_deliverables(product_id, project_id=str(project.get("id") or ""), limit=500)
            accepted = [row for row in deliverables if row.get("status") == "accepted"]
            pending_review = [row for row in deliverables if row.get("status") == "draft"]
            releases = product_registry_service.list_releases(product_id, limit=500)
            released_sources = {str(row.get("source_deliverable_id") or "") for row in releases}
            accepted_unreleased = [row for row in accepted if str(row.get("id") or "") not in released_sources]
            runtime_issues = [
                row for row in product_registry_service.list_runtime_instances(product_id, limit=100)
                if row.get("state") in {"degraded", "offline", "failed"}
            ]
            rows.append({
                "product_id": product_id,
                "product_name": product.get("name", product_id),
                "binding_role": binding.get("role", "uses"),
                "pending_deliverable_reviews": len(pending_review),
                "accepted_unreleased_deliverables": len(accepted_unreleased),
                "runtime_issues": [{"id": row.get("id"), "name": row.get("name"), "state": row.get("state"), "summary": row.get("summary", "")} for row in runtime_issues],
            })
            summary["bound_products"] += 1
            summary["pending_deliverable_reviews"] += len(pending_review)
            summary["accepted_unreleased_deliverables"] += len(accepted_unreleased)
            summary["runtime_issues"] += len(runtime_issues)
            if pending_review:
                summary["products_pending_review"].append(product_id)
            if accepted_unreleased:
                summary["products_pending_release"].append(product_id)
            if runtime_issues:
                summary["products_with_runtime_issues"].append(product_id)
        return {"products": rows, "summary": summary}

    def update_software_spec(self, project_id: str, payload: dict, agent_id: str = "project-manager") -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "software":
                return None
            now = _now_iso()
            current = _as_dict(project.get("design_doc"))
            nested = _as_dict(payload.get("design_doc"))
            merged = {**current, **nested}
            field_map = {
                "requirements": "usage_requirements",
                "architecture": "system_architecture",
                "database_design": "data_structure",
                "api_design": "api_interfaces",
                "frontend_design": "frontend_design",
                "test_plan": "test_plan",
                "deployment_plan": "deployment_plan",
            }
            for source, target in field_map.items():
                if source in payload and payload[source] is not None:
                    merged[target] = payload[source]
            merged["version"] = max(int(current.get("version") or 1), int(merged.get("version") or 1)) + 1
            merged["author_agent"] = agent_id
            merged["updated_at"] = now
            project["design_doc"] = self._normalize_design_doc(
                merged,
                project_id,
                project.get("created_at") or now,
            )
            project["updated_at"] = now
            log = self._append_log(
                data,
                project_id,
                None,
                agent_id,
                "software_spec_updated",
                f"更新软件规格至版本 {project['design_doc']['version']}",
            )
            return {"project_id": project_id, "design_doc": project["design_doc"], "log": log}

        return self._with_data(mutate)

    def add_document_section(self, project_id: str, payload: dict, agent_id: str = "project-manager") -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "document":
                return None
            now = _now_iso()
            spec = _as_dict(project.get("document_spec"))
            chapters = list(_as_list(spec.get("chapters")))
            raw = dict(payload)
            raw.setdefault("id", _new_id("chapter"))
            raw.setdefault("project_id", project_id)
            raw.setdefault("order_index", len(chapters))
            normalized = self._normalize_document_spec(
                {**spec, "chapters": [raw]},
                project_id,
                project.get("created_at") or now,
            )["chapters"][0]
            chapters.append(normalized)
            project["document_spec"] = self._normalize_document_spec(
                {**spec, "chapters": chapters, "updated_at": now},
                project_id,
                project.get("created_at") or now,
            )
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "document_section_created", normalized["title"])
            return {"project_id": project_id, "section": normalized, "log": log}

        return self._with_data(mutate)

    def update_document_section(
        self,
        project_id: str,
        section_id: str,
        payload: dict,
        agent_id: str = "project-manager",
    ) -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "document":
                return None
            spec = _as_dict(project.get("document_spec"))
            chapters = list(_as_list(spec.get("chapters")))
            section = next((item for item in chapters if item.get("id") == section_id), None)
            if not section:
                return None
            aliases = {"content_brief": "main_content", "assigned_agent_id": "assigned_agent"}
            for key, value in payload.items():
                if value is not None and key not in {"id", "project_id"}:
                    section[aliases.get(key, key)] = value
            now = _now_iso()
            project["document_spec"] = self._normalize_document_spec(
                {**spec, "chapters": chapters, "updated_at": now},
                project_id,
                project.get("created_at") or now,
            )
            normalized = next(
                item for item in project["document_spec"]["chapters"]
                if item.get("id") == section_id
            )
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "document_section_updated", normalized["title"])
            return {"project_id": project_id, "section": normalized, "log": log}

        return self._with_data(mutate)

    def delete_document_section(
        self,
        project_id: str,
        section_id: str,
        agent_id: str = "project-manager",
    ) -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "document":
                return None
            spec = _as_dict(project.get("document_spec"))
            chapters = list(_as_list(spec.get("chapters")))
            removed = next((item for item in chapters if item.get("id") == section_id), None)
            if not removed:
                return None
            now = _now_iso()
            remaining = [item for item in chapters if item.get("id") != section_id]
            assets = [
                item for item in _as_list(spec.get("assets"))
                if item.get("chapter_id") != section_id
            ]
            project["document_spec"] = self._normalize_document_spec(
                {**spec, "chapters": remaining, "assets": assets, "updated_at": now},
                project_id,
                project.get("created_at") or now,
            )
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "document_section_deleted", removed.get("title", section_id))
            return {"project_id": project_id, "deleted_section_id": section_id, "log": log}

        return self._with_data(mutate)

    def add_document_asset(self, project_id: str, payload: dict, agent_id: str = "project-manager") -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "document":
                return None
            now = _now_iso()
            spec = _as_dict(project.get("document_spec"))
            assets = list(_as_list(spec.get("assets")))
            raw = dict(payload)
            raw.setdefault("id", _new_id("asset"))
            raw.setdefault("project_id", project_id)
            raw.setdefault("order_index", len(assets))
            normalized = self._normalize_document_spec(
                {**spec, "assets": [raw]},
                project_id,
                project.get("created_at") or now,
            )["assets"][0]
            assets.append(normalized)
            project["document_spec"] = self._normalize_document_spec(
                {**spec, "assets": assets, "updated_at": now},
                project_id,
                project.get("created_at") or now,
            )
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "document_asset_created", normalized["title"])
            return {"project_id": project_id, "asset": normalized, "log": log}

        return self._with_data(mutate)

    def update_document_asset(
        self,
        project_id: str,
        asset_id: str,
        payload: dict,
        agent_id: str = "project-manager",
    ) -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "document":
                return None
            spec = _as_dict(project.get("document_spec"))
            assets = list(_as_list(spec.get("assets")))
            asset = next((item for item in assets if item.get("id") == asset_id), None)
            if not asset:
                return None
            aliases = {"section_id": "chapter_id"}
            for key, value in payload.items():
                if value is not None and key not in {"id", "project_id"}:
                    asset[aliases.get(key, key)] = value
            now = _now_iso()
            project["document_spec"] = self._normalize_document_spec(
                {**spec, "assets": assets, "updated_at": now},
                project_id,
                project.get("created_at") or now,
            )
            normalized = next(
                item for item in project["document_spec"]["assets"]
                if item.get("id") == asset_id
            )
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "document_asset_updated", normalized["title"])
            return {"project_id": project_id, "asset": normalized, "log": log}

        return self._with_data(mutate)

    def delete_document_asset(
        self,
        project_id: str,
        asset_id: str,
        agent_id: str = "project-manager",
    ) -> Optional[dict]:
        def mutate(data):
            project = self._find_project_unlocked(data, project_id)
            if not project or _normalize_project_type(project.get("project_type")) != "document":
                return None
            spec = _as_dict(project.get("document_spec"))
            assets = list(_as_list(spec.get("assets")))
            removed = next((item for item in assets if item.get("id") == asset_id), None)
            if not removed:
                return None
            now = _now_iso()
            project["document_spec"] = self._normalize_document_spec(
                {
                    **spec,
                    "assets": [item for item in assets if item.get("id") != asset_id],
                    "updated_at": now,
                },
                project_id,
                project.get("created_at") or now,
            )
            project["updated_at"] = now
            log = self._append_log(data, project_id, None, agent_id, "document_asset_deleted", removed.get("title", asset_id))
            return {"project_id": project_id, "deleted_asset_id": asset_id, "log": log}

        return self._with_data(mutate)

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
            "frontend_design": _as_dict(payload.get("frontend_design")),
            "test_plan": _as_list(payload.get("test_plan")),
            "deployment_plan": _as_list(payload.get("deployment_plan")),
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
                "outline_items": _as_list(item.get("outline_items")),
                "subsections": _as_list(item.get("subsections")),
                "required_assets": _as_list(item.get("required_assets")),
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
            "course_profile": _as_dict(payload.get("course_profile")),
            "edition": payload.get("edition", ""),
            "current_edition_label": payload.get("current_edition_label", ""),
            "obsidian_edition_label": payload.get("obsidian_edition_label", ""),
            "publication_edition_label": payload.get("publication_edition_label", ""),
            "version_role_note": payload.get("version_role_note", ""),
            "expected_chapters": int(payload.get("expected_chapters") or 0),
            "outline": _as_list(payload.get("outline")),
            "chapters": chapters,
            "target_structure": _as_dict(payload.get("target_structure")),
            "assets": assets,
            "references": _as_list(payload.get("references") or payload.get("reference_plan")),
            "source_word": _as_dict(payload.get("source_word")),
            "working_markdown": _as_dict(payload.get("working_markdown")),
            "section_links": _as_list(payload.get("section_links")),
            "sync_status": _as_dict(payload.get("sync_status")),
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
