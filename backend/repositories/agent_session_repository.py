"""
AgentSession Repository — Agent 会话表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import AgentSession


class AgentSessionRepository(BaseRepository[AgentSession]):
    def __init__(self):
        super().__init__(AgentSession)

    def get_by_agent(self, db: Session, agent_id: str, skip: int = 0, limit: int = 50) -> List[AgentSession]:
        return (
            db.query(AgentSession)
            .filter(AgentSession.agent_id == agent_id)
            .order_by(AgentSession.started_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_sessions(self, db: Session) -> List[AgentSession]:
        return db.query(AgentSession).filter(AgentSession.ended_at.is_(None)).all()

    def get_by_session_id(self, db: Session, session_id: str):
        return db.query(AgentSession).filter(AgentSession.session_id == session_id).first()

    def get_by_task(self, db: Session, task_id: str, skip: int = 0, limit: int = 50) -> List[AgentSession]:
        return (
            db.query(AgentSession)
            .filter(AgentSession.task_id == task_id)
            .order_by(AgentSession.started_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
