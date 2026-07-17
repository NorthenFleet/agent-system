from __future__ import annotations
"""
Alert Repository — 告警数据访问层
"""
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from models.v2_models import AlertRule, AlertEvent
from repositories.base_repository import BaseRepository


class AlertRepository(BaseRepository[AlertRule]):
    model = AlertRule

    def __init__(self, db: Session):
        super().__init__(db)

    def list_events(
        self,
        status: str = "active",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[AlertEvent], int]:
        query = self.db.query(AlertEvent)
        if status == "active":
            query = query.filter(AlertEvent.acknowledged == False)
        total = query.count()
        events = (
            query.order_by(AlertEvent.triggered_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return events, total

    def acknowledge_event(self, event_id: int) -> Optional[AlertEvent]:
        from datetime import datetime, timezone

        event = self.db.query(AlertEvent).filter(AlertEvent.id == event_id).first()
        if event:
            event.acknowledged = True
            event.acknowledged_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(event)
        return event

    def get_events_for_target(
        self, target_type: str, target_id: str
    ) -> Sequence[AlertEvent]:
        return (
            self.db.query(AlertEvent)
            .filter(
                AlertEvent.target_type == target_type,
                AlertEvent.target_id == target_id,
            )
            .order_by(AlertEvent.triggered_at.desc())
            .all()
        )

    def create_event(self, event: AlertEvent) -> AlertEvent:
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
