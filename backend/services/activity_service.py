"""
ActivityService — 活动日志业务逻辑
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.activity_log_repository import ActivityLogRepository
from models.v2_models import ActivityLog


class ActivityService(BaseService[ActivityLog, ActivityLogRepository]):
    repository: ActivityLogRepository
    cache_prefix: str = "activity"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = ActivityLogRepository()

    def get_by_agent(self, agent_id: str, skip: int = 0, limit: int = 100) -> List[ActivityLog]:
        return self.repository.get_by_agent(self.db, agent_id, skip, limit)

    def get_by_action(self, action: str, skip: int = 0, limit: int = 100) -> List[ActivityLog]:
        return self.repository.get_by_action(self.db, action, skip, limit)

    def get_by_resource(self, resource_type: str, resource_id: str,
                        skip: int = 0, limit: int = 100) -> List[ActivityLog]:
        return self.repository.get_by_resource(self.db, resource_type, resource_id, skip, limit)

    def log(self, agent_id: str, action: str, resource_type: str = None,
            resource_id: str = None, detail: dict = None) -> ActivityLog:
        obj = self.repository.create(self.db, {
            "agent_id": agent_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "detail": detail or {},
        })
        self.db.commit()
        return obj
