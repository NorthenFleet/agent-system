"""
TaskService — 任务业务逻辑
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.task_repository import TaskRepository
from repositories.task_comment_repository import TaskCommentRepository
from repositories.task_history_repository import TaskHistoryRepository
from models.v2_models import Task


class TaskService(BaseService[Task, TaskRepository]):
    repository: TaskRepository
    cache_prefix: str = "task"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = TaskRepository()
        self._comment_repo = TaskCommentRepository()
        self._history_repo = TaskHistoryRepository()

    def get_by_task_id(self, task_id: str) -> Optional[Task]:
        cached = self._cache_get("by_id", task_id)
        if cached is not None:
            return cached
        obj = self.repository.get_by_task_id(self.db, task_id)
        if obj:
            self._cache_set(obj.to_dict(), "by_id", task_id, ttl=120)
        return obj

    def get_by_assignee(self, assignee: str, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_by_assignee(self.db, assignee, skip, limit)

    def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_by_status(self.db, status, skip, limit)

    def get_by_sprint(self, sprint: int, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_by_sprint(self.db, sprint, skip, limit)

    def get_by_priority(self, priority: str, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_by_priority(self.db, priority, skip, limit)

    def get_overdue(self, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_overdue(self.db, skip, limit)

    def get_stats(self) -> Dict[str, Any]:
        cached = self._cache_get("stats")
        if cached is not None:
            return cached
        stats = self.repository.get_stats(self.db)
        self._cache_set(stats, "stats", ttl=60)
        return stats

    def get_full_stats(self) -> Dict[str, Any]:
        cached = self._cache_get("full_stats")
        if cached is not None:
            return cached
        stats = self.repository.get_full_stats(self.db)
        self._cache_set(stats, "full_stats", ttl=60)
        return stats

    def search_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        sprint: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        result = self.repository.search_tasks(
            self.db, status=status, priority=priority, assignee=assignee,
            sprint=sprint, search=search, page=page, page_size=page_size,
            sort_by=sort_by, sort_order=sort_order
        )
        return {
            "tasks": [t.to_dict() for t in result["tasks"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "total_pages": result["total_pages"],
        }

    def get_gantt_data(self, sprint: Optional[int] = None, assignee: Optional[str] = None) -> Dict[str, Any]:
        tasks = self.repository.get_gantt_data(self.db, sprint=sprint, assignee=assignee)

        parents = [t for t in tasks if not t.parent_task_id]
        children = [t for t in tasks if t.parent_task_id]

        result = []
        for p in parents:
            item = {
                "task_id": p.task_id,
                "title": p.title,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "due_date": p.due_date.isoformat() if p.due_date else None,
                "progress": p.progress,
                "assignee": p.assignee,
                "status": p.status,
                "subtasks": [],
            }
            for c in children:
                if c.parent_task_id == p.task_id:
                    item["subtasks"].append({
                        "task_id": c.task_id,
                        "title": c.title,
                        "assignee": c.assignee,
                        "status": c.status,
                        "start_date": c.start_date.isoformat() if c.start_date else None,
                        "due_date": c.due_date.isoformat() if c.due_date else None,
                    })
            result.append(item)

        parent_ids = {p.task_id for p in parents}
        for t in tasks:
            if t.parent_task_id and t.parent_task_id not in parent_ids:
                result.append({
                    "task_id": t.task_id,
                    "title": t.title,
                    "start_date": t.start_date.isoformat() if t.start_date else None,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "progress": t.progress,
                    "assignee": t.assignee,
                    "status": t.status,
                    "subtasks": [],
                })

        return {"tasks": result}

    def create_task(self, task_data: Dict[str, Any], created_by: Optional[str] = None) -> Task:
        task_id = self.repository.generate_task_id(self.db)
        now = datetime.now(timezone.utc)
        data = {
            **task_data,
            "task_id": task_id,
            "created_by": created_by,
            "start_date": task_data.get("start_date") or now,
        }
        if data.get("assignee"):
            data["status"] = "assigned"
        obj = self.repository.create(self.db, data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def update_status(self, task_id: str, new_status: str, changed_by: Optional[str] = None) -> Optional[Task]:
        """更新任务状态，自动记录历史"""
        task = self.repository.get_by_task_id(self.db, task_id)
        if not task:
            return None

        old_status = task.status
        obj = self.repository.update(self.db, task.id, {"status": new_status})
        if obj:
            self._history_repo.create(self.db, {
                "task_id": task.task_id,
                "field": "status",
                "old_value": old_status,
                "new_value": new_status,
                "changed_by": changed_by,
            })
            self.db.commit()
            self._cache_invalidate("by_id", task_id)
            self._cache_invalidate("stats")
        return obj

    def update_task_by_task_id(self, task_id: str, update_data: Dict[str, Any], changed_by: Optional[str] = None) -> Optional[Task]:
        """根据 task_id 更新任务，记录变更历史"""
        task = self.repository.get_by_task_id(self.db, task_id)
        if not task:
            return None

        fields = update_data.copy()
        for field, value in fields.items():
            old_val = getattr(task, field)
            if old_val != value:
                self._history_repo.create(self.db, {
                    "task_id": task_id,
                    "field": field,
                    "old_value": str(old_val) if old_val is not None else None,
                    "new_value": str(value) if value is not None else None,
                    "changed_by": changed_by,
                })

        if update_data.get("status") == "done" and not task.completed_at:
            update_data["completed_at"] = datetime.now(timezone.utc)
            update_data["progress"] = 100
            if changed_by:
                self._history_repo.create(self.db, {
                    "task_id": task_id,
                    "field": "progress",
                    "old_value": str(task.progress),
                    "new_value": "100",
                    "changed_by": changed_by,
                })
                self._history_repo.create(self.db, {
                    "task_id": task_id,
                    "field": "completed_at",
                    "old_value": None,
                    "new_value": str(update_data["completed_at"]),
                    "changed_by": changed_by,
                })

        update_data["updated_at"] = datetime.now(timezone.utc)
        obj = self.repository.update_by_task_id(self.db, task_id, update_data)
        if obj:
            self.db.commit()
            self._cache_invalidate("by_id", task_id)
            self._cache_invalidate("stats")
        return obj

    def delete_task_by_task_id(self, task_id: str) -> bool:
        """根据 task_id 删除任务"""
        result = self.repository.delete_by_task_id(self.db, task_id)
        if result:
            self.db.commit()
            self._cache_invalidate("by_id", task_id)
            self._cache_invalidate("stats")
        return result

    def assign_task(self, task_id: str, assignee: str, changed_by: Optional[str] = None) -> Optional[Task]:
        """分配任务"""
        task = self.repository.get_by_task_id(self.db, task_id)
        if not task:
            return None

        old_assignee = task.assignee
        old_status = task.status

        update_data = {"assignee": assignee}
        if task.status == "pending":
            update_data["status"] = "assigned"

        self._history_repo.create(self.db, {
            "task_id": task_id,
            "field": "assignee",
            "old_value": old_assignee,
            "new_value": assignee,
            "changed_by": changed_by,
        })
        if old_status != update_data.get("status", old_status):
            self._history_repo.create(self.db, {
                "task_id": task_id,
                "field": "status",
                "old_value": old_status,
                "new_value": update_data["status"],
                "changed_by": changed_by,
            })

        obj = self.repository.update_by_task_id(self.db, task_id, update_data)
        if obj:
            self.db.commit()
            self._cache_invalidate("by_id", task_id)
            self._cache_invalidate("stats")
        return obj

    def add_comment(self, task_id: str, user_id: Optional[int] = None,
                    agent_id: Optional[str] = None, content: str = "") -> Any:
        task = self.repository.get_by_task_id(self.db, task_id)
        if not task:
            return None
        comment = self._comment_repo.create(self.db, {
            "task_id": task.task_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "content": content,
        })
        self.db.commit()
        return comment

    def get_comments(self, task_id: str, skip: int = 0, limit: int = 100) -> List[Any]:
        comments = self._comment_repo.get_by_task(self.db, task_id, skip, limit)
        return [c.to_dict() for c in comments]

    def get_history(self, task_id: str, skip: int = 0, limit: int = 50) -> List[Any]:
        history = self._history_repo.get_by_task(self.db, task_id, skip, limit)
        return [h.to_dict() for h in history]
