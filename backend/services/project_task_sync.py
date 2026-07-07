"""
V3 项目任务 → V2 任务列表 同步服务

产品侧（程序开发 / 文档撰写）中创建的任务，自动同步到生产侧任务列表。
V2 tasks.source = 'project-dev' | 'project-doc' 区分来源。

@author: wheeljack (infra)
@updated: 2026-07-07
"""
from __future__ import annotations
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

# ---------- 状态映射 ----------

V3_TO_V2_STATUS = {
    "todo": "pending",
    "planning": "pending",
    "in_progress": "in_progress",
    "active": "in_progress",
    "review": "review",
    "testing": "testing",
    "blocked": "pending",
    "done": "done",
    "completed": "done",
    "cancelled": "archived",
}


def map_v3_status(v3_status: str) -> str:
    return V3_TO_V2_STATUS.get(v3_status, "pending")


# ---------- 优先级映射 ----------

V3_TO_V2_PRIORITY = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
    "urgent": "critical",
}


def map_v3_priority(v3_priority: str) -> str:
    return V3_TO_V2_PRIORITY.get(v3_priority, "medium")


# ---------- 来源标识 ----------

def determine_source(project_type: str) -> str:
    """根据项目类型决定 V2 source 值"""
    if project_type == "document":
        return "project-doc"
    return "project-dev"


def determine_type(project_type: str) -> str:
    """根据项目类型决定 V2 type 值"""
    if project_type == "document":
        return "document"
    return "development"


# ---------- 同步核心 ----------

def sync_v3_task_to_v2(
    v3_task: dict[str, Any],
    project_id: str,
    project_name: str,
    project_type: str = "software",
) -> Optional[dict]:
    """
    将单个 V3 项目任务同步到 V2 tasks 表。

    使用 `task_id` 作为唯一键，已存在则更新，不存在则创建。
    返回 V2 task 的 dict，失败返回 None。
    """
    try:
        from database import SessionLocal
        from services.task_service import TaskService

        source = determine_source(project_type)
        task_type = determine_type(project_type)
        v3_id = v3_task.get("id", "")
        # V2 task_id 使用 v3 前缀保证唯一性和可追溯
        v2_task_id = f"v3-{project_id}-{v3_id}"

        db = SessionLocal()
        try:
            service = TaskService(db)
            existing = service.get_by_task_id(v2_task_id)

            now_status = map_v3_status(v3_task.get("status", "todo"))
            now_priority = map_v3_priority(v3_task.get("priority", "medium"))
            progress_int = int(v3_task.get("progress", 0) or 0)

            v2_data = {
                "title": v3_task.get("title", ""),
                "description": v3_task.get("description", ""),
                "type": task_type,
                "status": now_status,
                "priority": now_priority,
                "assignee": v3_task.get("assignee_agent") or v3_task.get("assignee_agent_id", ""),
                "progress": progress_int,
                "source": source,
                "parent_task_id": None,
                "tags": [f"project:{project_name}", f"type:{task_type}", f"v3:{v3_id}"],
            }

            if existing:
                # 更新已有任务
                service.update_task_by_task_id(
                    v2_task_id,
                    v2_data,
                    changed_by="system-sync",
                )
                logger.info(f"V2 任务已更新: {v2_task_id} (来源: {source})")
                return service.get_by_task_id(v2_task_id).to_dict()
            else:
                # 创建新任务
                v2_data["task_id"] = v2_task_id
                new_task = service.create_task(v2_data, created_by="system-sync")
                logger.info(f"V2 任务已创建: {v2_task_id} (来源: {source})")
                return new_task.to_dict()
        finally:
            db.close()

    except Exception as exc:
        logger.error(f"V3→V2 同步失败 (task {v3_task.get('id', '?')}): {exc}", exc_info=True)
        return None


def sync_v3_task_status(
    v3_task_id: str,
    v3_status: str,
    v3_progress: Optional[float] = None,
    project_id: str = "",
) -> Optional[dict]:
    """仅同步状态/进度变更（轻量更新）"""
    try:
        from database import SessionLocal
        from services.task_service import TaskService

        v2_task_id = f"v3-{project_id}-{v3_task_id}" if project_id else None

        db = SessionLocal()
        try:
            service = TaskService(db)

            if v2_task_id:
                task = service.get_by_task_id(v2_task_id)
            else:
                # 尝试通过 tags 查找
                task = None  # 需要更复杂的查找，先跳过
                logger.warning(f"无 project_id，无法定位 V2 任务: {v3_task_id}")

            if not task:
                logger.warning(f"V2 任务未找到，跳过同步: {v2_task_id}")
                return None

            updates = {}
            updates["status"] = map_v3_status(v3_status)
            if v3_progress is not None:
                updates["progress"] = int(v3_progress or 0)

            service.update_task_by_task_id(v2_task_id, updates, changed_by="system-sync")
            return service.get_by_task_id(v2_task_id).to_dict()
        finally:
            db.close()

    except Exception as exc:
        logger.error(f"V3→V2 状态同步失败: {exc}", exc_info=True)
        return None


def sync_all_project_tasks(project_id: str, project_name: str, project_type: str, tasks: list[dict]) -> dict:
    """批量同步一个项目的所有任务到 V2"""
    synced = 0
    failed = 0
    for task in tasks:
        result = sync_v3_task_to_v2(task, project_id, project_name, project_type)
        if result:
            synced += 1
        else:
            failed += 1

    return {"synced": synced, "failed": failed, "total": len(tasks)}


def delete_v2_task(project_id: str, v3_task_id: str) -> bool:
    """删除对应的 V2 任务（当 V3 任务被删除时）"""
    try:
        from database import SessionLocal
        from services.task_service import TaskService

        v2_task_id = f"v3-{project_id}-{v3_task_id}"
        db = SessionLocal()
        try:
            service = TaskService(db)
            task = service.get_by_task_id(v2_task_id)
            if task:
                service.delete_task(v2_task_id)
                logger.info(f"V2 任务已删除: {v2_task_id}")
                return True
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"V2 任务删除失败: {exc}", exc_info=True)
        return False
