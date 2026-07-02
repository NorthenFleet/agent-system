"""
Sprint Repository — Sprint 表数据访问
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import Sprint


class SprintRepository(BaseRepository[Sprint]):
    def __init__(self):
        super().__init__(Sprint)

    def get_by_name(self, db: Session, name: str) -> Optional[Sprint]:
        return db.query(Sprint).filter(Sprint.name == name).first()

    def get_active_sprints(self, db: Session) -> List[Sprint]:
        return db.query(Sprint).filter(Sprint.status == "active").all()

    def get_upcoming_sprints(self, db: Session, skip: int = 0, limit: int = 10) -> List[Sprint]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return (
            db.query(Sprint)
            .filter(Sprint.start_date > now)
            .order_by(Sprint.start_date.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
