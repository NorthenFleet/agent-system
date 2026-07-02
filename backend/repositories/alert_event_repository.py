"""
AlertEvent Repository — 告警事件表数据访问
"""
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from repositories.base import BaseRepository
from models.v2_models import AlertEvent


class AlertEventRepository(BaseRepository[AlertEvent]):
    def __init__(self):
        super().__init__(AlertEvent)

    def get_unacknowledged(self, db: Session, skip: int = 0, limit: int = 100) -> List[AlertEvent]:
        return (
            db.query(AlertEvent)
            .filter(AlertEvent.acknowledged == False)
            .order_by(AlertEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_agent(self, db: Session, agent_id: str, skip: int = 0, limit: int = 50) -> List[AlertEvent]:
        return (
            db.query(AlertEvent)
            .filter(AlertEvent.agent_id == agent_id)
            .order_by(AlertEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_severity(self, db: Session, severity: str, skip: int = 0, limit: int = 100) -> List[AlertEvent]:
        return (
            db.query(AlertEvent)
            .filter(AlertEvent.severity == severity)
            .order_by(AlertEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_unacknowledged(self, db: Session) -> int:
        return db.query(sql_func.count(AlertEvent.id)).filter(AlertEvent.acknowledged == False).scalar()
