"""
TaskComment Repository — 任务评论表数据访问
"""
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from repositories.base import BaseRepository
from models.v2_models import TaskComment


class TaskCommentRepository(BaseRepository[TaskComment]):
    def __init__(self):
        super().__init__(TaskComment)

    def get_by_task(self, db: Session, task_id: str, skip: int = 0, limit: int = 100) -> List[TaskComment]:
        return (
            db.query(TaskComment)
            .filter(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_task(self, db: Session, task_id: str) -> int:
        return db.query(sql_func.count(TaskComment.id)).filter(TaskComment.task_id == task_id).scalar()
