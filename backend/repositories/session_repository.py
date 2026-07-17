from __future__ import annotations
"""
Session Repository — Agent Session 数据访问层
"""
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from models.v2_models import AgentSession
from repositories.base_repository import BaseRepository


class SessionRepository(BaseRepository[AgentSession]):
    model = AgentSession

    def __init__(self, db: Session):
        super().__init__(db)

    def get_by_agent_id(
        self, agent_id: str, status: Optional[str] = None
    ) -> Sequence[AgentSession]:
        query = self.db.query(AgentSession).filter(AgentSession.agent_id == agent_id)
        if status:
            query = query.filter(AgentSession.status == status)
        return query.order_by(AgentSession.started_at.desc()).all()

    def get_active_session(
        self, agent_id: str
    ) -> Optional[AgentSession]:
        return (
            self.db.query(AgentSession)
            .filter(
                AgentSession.agent_id == agent_id,
                AgentSession.status == "active",
            )
            .first()
        )
