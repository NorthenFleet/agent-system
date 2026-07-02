"""
ActivityLog Repository — 活动日志表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import ActivityLog


class ActivityLogRepository(BaseRepository[ActivityLog]):
    def __init__(self):
        super().__init__(ActivityLog)

    def get_by_agent(self, db: Session, agent_id: str, skip: int = 0, limit: int = 100) -> List[ActivityLog]:
        return (
            db.query(ActivityLog)
            .filter(ActivityLog.agent_id == agent_id)
            .order_by(ActivityLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_action(self, db: Session, action: str, skip: int = 0, limit: int = 100) -> List[ActivityLog]:
        return (
            db.query(ActivityLog)
            .filter(ActivityLog.action == action)
            .order_by(ActivityLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_resource(self, db: Session, resource_type: str, resource_id: str,
                        skip: int = 0, limit: int = 100) -> List[ActivityLog]:
        return (
            db.query(ActivityLog)
            .filter(ActivityLog.resource_type == resource_type, ActivityLog.resource_id == resource_id)
            .order_by(ActivityLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
