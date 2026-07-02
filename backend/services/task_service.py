"""
TaskService — 任务业务逻辑
"""
from typing import Optional, List, Dict, Any
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

    def create_task(self, task_data: Dict[str, Any]) -> Task:
        obj = self.repository.create(self.db, task_data)
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
            # 记录状态变更历史
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
        return self._comment_repo.get_by_task(self.db, task_id, skip, limit)

    def get_history(self, task_id: str, skip: int = 0, limit: int = 50) -> List[Any]:
        return self._history_repo.get_by_task(self.db, task_id, skip, limit)
