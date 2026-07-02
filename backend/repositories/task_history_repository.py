"""
TaskHistory Repository — 任务历史表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import TaskHistory


class TaskHistoryRepository(BaseRepository[TaskHistory]):
    def __init__(self):
        super().__init__(TaskHistory)

    def get_by_task(self, db: Session, task_id: str, skip: int = 0, limit: int = 50) -> List[TaskHistory]:
        return (
            db.query(TaskHistory)
            .filter(TaskHistory.task_id == task_id)
            .order_by(TaskHistory.changed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
