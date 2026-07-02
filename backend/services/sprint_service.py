"""
SprintService — Sprint 业务逻辑
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.sprint_repository import SprintRepository
from models.v2_models import Sprint


class SprintService(BaseService[Sprint, SprintRepository]):
    repository: SprintRepository
    cache_prefix: str = "sprint"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = SprintRepository()

    def get_by_name(self, name: str) -> Optional[Sprint]:
        return self.repository.get_by_name(self.db, name)

    def get_active_sprints(self) -> List[Sprint]:
        return self.repository.get_active_sprints(self.db)

    def get_upcoming_sprints(self, skip: int = 0, limit: int = 10) -> List[Sprint]:
        return self.repository.get_upcoming_sprints(self.db, skip, limit)

    def create_sprint(self, sprint_data: dict) -> Sprint:
        obj = self.repository.create(self.db, sprint_data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def start_sprint(self, sprint_id: int) -> Optional[Sprint]:
        return self.update(sprint_id, {"status": "active"})

    def close_sprint(self, sprint_id: int) -> Optional[Sprint]:
        return self.update(sprint_id, {"status": "closed"})
