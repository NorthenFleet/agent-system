"""Persist project work items in the shared V2 task ledger."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

V3_TO_V2_STATUS = {
    "todo": "pending",
    "pending": "pending",
    "planning": "pending",
    "assigned": "assigned",
    "claimed": "assigned",
    "in_progress": "in_progress",
    "active": "in_progress",
    "review": "review",
    "testing": "testing",
    "blocked": "pending",
    "done": "done",
    "completed": "done",
    "cancelled": "archived",
    "archived": "archived",
}

V3_TO_V2_PRIORITY = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
    "urgent": "critical",
}


def map_v3_status(status: str) -> str:
    return V3_TO_V2_STATUS.get(str(status or "").lower(), "pending")


def map_v3_priority(priority: str) -> str:
    return V3_TO_V2_PRIORITY.get(str(priority or "").lower(), "medium")


def determine_source(project_type: str) -> str:
    return "project-doc" if project_type == "document" else "project-dev"


def determine_type(project_type: str) -> str:
    return "document" if project_type == "document" else "development"


def external_task_id(project_id: str, entity: str, entity_id: str) -> str:
    """Build a deterministic ID that always fits the database's 64-char limit."""
    value = f"v3-{project_id}-{entity}-{entity_id}"
    if len(value) <= 64:
        return value
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"v3-{entity}-{digest}"


def _tags(project: dict[str, Any], entity: str, entity_id: str) -> list[str]:
    project_type = project.get("project_type", "software")
    return [
        "managed:project-ledger",
        f"project-id:{project.get('id', '')}",
        f"project:{project.get('name', '')}",
        f"project-type:{project_type}",
        f"entity:{entity}",
        f"entity-id:{entity_id}",
    ]


def build_project_task_records(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten project tasks and their executable points into ledger rows."""
    project_id = str(project.get("id", ""))
    project_type = str(project.get("project_type", "software"))
    source = determine_source(project_type)
    parent_type = determine_type(project_type)
    records: list[dict[str, Any]] = []

    for task in project.get("tasks", []) or []:
        task_id = str(task.get("id", ""))
        if not task_id:
            continue
        parent_id = external_task_id(project_id, "task", task_id)
        records.append({
            "task_id": parent_id,
            "title": task.get("title", ""),
            "description": task.get("description", ""),
            "type": parent_type,
            "status": map_v3_status(task.get("status", "todo")),
            "priority": map_v3_priority(task.get("priority", "medium")),
            "assignee": task.get("assignee_agent") or task.get("assignee_agent_id") or None,
            "progress": max(0, min(100, int(float(task.get("progress", 0) or 0)))),
            "source": source,
            "parent_task_id": None,
            "tags": _tags(project, "task", task_id),
        })

        for point in task.get("development_points", []) or []:
            point_id = str(point.get("id", ""))
            if not point_id:
                continue
            status = map_v3_status(point.get("status", "todo"))
            description = point.get("description", "")
            evidence = point.get("completion_evidence", "")
            if evidence:
                description = f"{description}\n\n完成反馈：{evidence}".strip()
            records.append({
                "task_id": external_task_id(project_id, "point", point_id),
                "title": point.get("title", ""),
                "description": description,
                "type": "writing-point" if project_type == "document" else "development-point",
                "status": status,
                "priority": map_v3_priority(task.get("priority", "medium")),
                "assignee": point.get("assigned_agent") or task.get("assignee_agent") or None,
                "progress": 100 if status == "done" else 0,
                "source": source,
                "parent_task_id": parent_id,
                "tags": _tags(project, "point", point_id) + [f"parent-entity-id:{task_id}"],
            })

    return records


def _sync_records(db: Session, records: Iterable[dict[str, Any]]) -> tuple[int, int, set[str]]:
    from services.task_service import TaskService

    service = TaskService(db)
    changed = 0
    failed = 0
    expected_ids: set[str] = set()
    for record in records:
        task_id = record["task_id"]
        expected_ids.add(task_id)
        payload = {key: value for key, value in record.items() if key != "task_id"}
        try:
            _, did_change = service.upsert_external_task(task_id, payload)
            changed += int(did_change)
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("项目任务写入总账失败: %s", task_id)
    return changed, failed, expected_ids


def reconcile_project_task_ledger(db: Optional[Session] = None) -> dict[str, int]:
    """Reconcile every project task and child point with the SQL task ledger."""
    from database import SessionLocal
    from models.v2_models import Task
    from project_manager import project_manager

    owns_session = db is None
    session = db or SessionLocal()
    try:
        records = [
            record
            for project in project_manager.list_projects()
            for record in build_project_task_records(project)
        ]
        changed, failed, expected_ids = _sync_records(session, records)

        stale = (
            session.query(Task)
            .filter(Task.source.in_(["project-dev", "project-doc"]))
            .all()
        )
        deleted = 0
        for task in stale:
            if "managed:project-ledger" in (task.tags or []) and task.task_id not in expected_ids:
                session.delete(task)
                deleted += 1
        if deleted:
            session.commit()
        return {
            "total": len(records),
            "changed": changed,
            "deleted": deleted,
            "failed": failed,
        }
    finally:
        if owns_session:
            session.close()


def sync_v3_task_to_v2(
    v3_task: dict[str, Any],
    project_id: str,
    project_name: str,
    project_type: str = "software",
) -> Optional[dict]:
    """Compatibility entry point for existing project routes."""
    project = {
        "id": project_id,
        "name": project_name,
        "project_type": project_type,
        "tasks": [v3_task],
    }
    from database import SessionLocal

    db = SessionLocal()
    try:
        records = build_project_task_records(project)
        _, failed, _ = _sync_records(db, records)
        if failed or not records:
            return None
        from services.task_service import TaskService
        task = TaskService(db).get_by_task_id(records[0]["task_id"])
        return task.to_dict() if task else None
    finally:
        db.close()


def sync_v3_task_status(
    v3_task_id: str,
    v3_status: str,
    v3_progress: Optional[float] = None,
    project_id: str = "",
) -> Optional[dict]:
    """Compatibility status updater for project routes."""
    if not project_id:
        return None
    from database import SessionLocal
    from services.task_service import TaskService

    db = SessionLocal()
    try:
        task_id = external_task_id(project_id, "task", v3_task_id)
        service = TaskService(db)
        updates: dict[str, Any] = {"status": map_v3_status(v3_status)}
        if v3_progress is not None:
            updates["progress"] = int(v3_progress or 0)
        task = service.update_task_by_task_id(task_id, updates, changed_by="system-sync")
        return task.to_dict() if task else None
    finally:
        db.close()


def sync_all_project_tasks(project_id: str, project_name: str, project_type: str, tasks: list[dict]) -> dict:
    project = {"id": project_id, "name": project_name, "project_type": project_type, "tasks": tasks}
    records = build_project_task_records(project)
    from database import SessionLocal

    db = SessionLocal()
    try:
        changed, failed, _ = _sync_records(db, records)
        return {"synced": len(records) - failed, "changed": changed, "failed": failed, "total": len(records)}
    finally:
        db.close()


def delete_v2_task(project_id: str, v3_task_id: str) -> bool:
    from database import SessionLocal
    from models.v2_models import Task

    db = SessionLocal()
    try:
        parent_id = external_task_id(project_id, "task", v3_task_id)
        deleted = db.query(Task).filter(
            (Task.task_id == parent_id) | (Task.parent_task_id == parent_id)
        ).delete(synchronize_session=False)
        db.commit()
        return bool(deleted)
    except Exception:
        db.rollback()
        logger.exception("删除项目任务总账记录失败: %s", v3_task_id)
        return False
    finally:
        db.close()


COMMAND_CENTER_TO_V2_STATUS = {
    "received": "pending",
    "planning": "pending",
    "awaiting_approval": "pending",
    "dispatching": "in_progress",
    "running": "in_progress",
    "waiting_feedback": "review",
    "evaluating": "testing",
    "completed": "done",
    "failed": "pending",
    "cancelled": "archived",
}

STEP_TO_V2_STATUS = {
    "draft": "pending",
    "ready": "pending",
    "running": "in_progress",
    "completed": "done",
    "failed": "pending",
    "cancelled": "archived",
}


def _tag_value(tags: list[str], prefix: str) -> str:
    return next((tag.split(":", 1)[1] for tag in tags if tag.startswith(prefix)), "")


def command_center_task_id(entity: str, entity_id: str) -> str:
    return external_task_id("command-center", entity, entity_id)


def _command_center_tags(mission: dict[str, Any], entity: str, entity_id: str) -> list[str]:
    context = mission.get("context") if isinstance(mission.get("context"), dict) else {}
    project_name = str(context.get("project_name") or mission.get("project_name") or "")
    tags = [
        "managed:command-center-ledger",
        f"mission-id:{mission.get('id', '')}",
        f"mission-type:{mission.get('mission_type') or 'software'}",
        f"entity:{entity}",
        f"entity-id:{entity_id}",
    ]
    project_id = str(mission.get("project_id") or "")
    if project_id:
        tags.append(f"project-id:{project_id}")
    if project_name:
        tags.append(f"project:{project_name}")
    return tags


def _mission_progress(mission: dict[str, Any]) -> int:
    status = str(mission.get("status") or "")
    if status == "completed":
        return 100
    steps = mission.get("steps") if isinstance(mission.get("steps"), list) else []
    if steps:
        completed = sum(1 for step in steps if str(step.get("status") or "") == "completed")
        running = sum(1 for step in steps if str(step.get("status") or "") == "running")
        return max(0, min(99, round((completed + running * 0.5) / len(steps) * 100)))
    defaults = {
        "received": 5,
        "planning": 12,
        "awaiting_approval": 25,
        "dispatching": 35,
        "running": 50,
        "waiting_feedback": 65,
        "evaluating": 85,
        "failed": 40,
        "cancelled": 0,
    }
    return defaults.get(status, 0)


def build_command_center_task_records(mission: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a command-center mission and current steps into the shared task ledger."""
    mission_id = str(mission.get("id") or "")
    if not mission_id:
        return []
    mission_type = str(mission.get("mission_type") or "software")
    mission_task_id = command_center_task_id("mission", mission_id)
    objective = str(mission.get("objective") or "")
    records: list[dict[str, Any]] = [{
        "task_id": mission_task_id,
        "title": mission.get("title") or mission_id,
        "description": objective,
        "type": "document" if mission_type == "document" else "development",
        "status": COMMAND_CENTER_TO_V2_STATUS.get(str(mission.get("status") or ""), "pending"),
        "priority": str(mission.get("priority") or "normal").replace("normal", "medium"),
        "assignee": "optimus",
        "progress": _mission_progress(mission),
        "source": "command-center",
        "parent_task_id": None,
        "tags": _command_center_tags(mission, "mission", mission_id),
    }]

    for step in mission.get("steps") or []:
        step_id = str(step.get("id") or "")
        if not step_id:
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        details = [str(step.get("description") or "").strip()]
        if step.get("work_run_id"):
            details.append(f"执行记录：{step.get('work_run_id')}")
        if result.get("output"):
            details.append(f"执行输出：{result.get('output')}")
        if result.get("error"):
            details.append(f"执行错误：{result.get('error')}")
        status = str(step.get("status") or "draft")
        records.append({
            "task_id": command_center_task_id("step", step_id),
            "title": step.get("title") or step_id,
            "description": "\n\n".join(item for item in details if item),
            "type": str(step.get("task_type") or "general"),
            "status": STEP_TO_V2_STATUS.get(status, "pending"),
            "priority": str(mission.get("priority") or "normal").replace("normal", "medium"),
            "assignee": step.get("agent_id") or "optimus",
            "progress": 100 if status == "completed" else 50 if status == "running" else 0,
            "source": "command-center",
            "parent_task_id": mission_task_id,
            "tags": _command_center_tags(mission, "step", step_id) + [f"parent-mission-id:{mission_id}"],
        })
    return records


def sync_command_center_mission_to_v2(mission: dict[str, Any]) -> dict[str, int]:
    """Upsert one mission and its active plan steps into the shared task ledger."""
    from database import SessionLocal
    from models.v2_models import Task

    records = build_command_center_task_records(mission)
    db = SessionLocal()
    try:
        try:
            from sqlalchemy import inspect
            if not inspect(db.bind).has_table("tasks"):
                return {"synced": 0, "changed": 0, "deleted": 0, "failed": 0, "total": len(records)}
        except Exception:
            return {"synced": 0, "changed": 0, "deleted": 0, "failed": 0, "total": len(records)}
        changed, failed, expected_ids = _sync_records(db, records)
        mission_id = str(mission.get("id") or "")
        stale = db.query(Task).filter(Task.source == "command-center").all()
        deleted = 0
        for task in stale:
            tags = task.tags or []
            if (
                "managed:command-center-ledger" in tags
                and _tag_value(tags, "mission-id:") == mission_id
                and task.task_id not in expected_ids
            ):
                db.delete(task)
                deleted += 1
        if deleted:
            db.commit()
        return {"synced": len(records) - failed, "changed": changed, "deleted": deleted, "failed": failed, "total": len(records)}
    finally:
        db.close()
