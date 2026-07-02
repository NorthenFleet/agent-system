"""
Task Repository — 任务表数据访问
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from repositories.base import BaseRepository
from models.v2_models import Task


class TaskRepository(BaseRepository[Task]):
    def __init__(self):
        super().__init__(Task)

    def get_by_task_id(self, db: Session, task_id: str) -> Optional[Task]:
        """根据 task_id 获取"""
        return db.query(Task).filter(Task.task_id == task_id).first()

    def get_by_assignee(self, db: Session, assignee: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某人的任务"""
        return db.query(Task).filter(Task.assignee == assignee).offset(skip).limit(limit).all()

    def get_by_status(self, db: Session, status: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某状态的任务"""
        return db.query(Task).filter(Task.status == status).offset(skip).limit(limit).all()

    def get_by_sprint(self, db: Session, sprint: int, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某 Sprint 的任务"""
        return db.query(Task).filter(Task.sprint == sprint).offset(skip).limit(limit).all()

    def get_by_priority(self, db: Session, priority: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某优先级的任务"""
        return db.query(Task).filter(Task.priority == priority).offset(skip).limit(limit).all()

    def get_by_parent(self, db: Session, parent_task_id: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取子任务"""
        return db.query(Task).filter(Task.parent_task_id == parent_task_id).offset(skip).limit(limit).all()

    def get_stats(self, db: Session) -> Dict[str, Any]:
        """获取任务统计"""
        result = db.query(Task.status, sql_func.count(Task.id)).group_by(Task.status).all()
        total = db.query(sql_func.count(Task.id)).scalar()
        return {
            "total": total or 0,
            "by_status": {status: count for status, count in result},
        }

    def get_overdue(self, db: Session, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取逾期任务"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return (
            db.query(Task)
            .filter(Task.due_date < now, Task.status.notin_(["completed", "cancelled"]))
            .order_by(Task.due_date.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
