"""
AgentHeartbeat Repository — Agent 心跳表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import AgentHeartbeat


class AgentHeartbeatRepository(BaseRepository[AgentHeartbeat]):
    def __init__(self):
        super().__init__(AgentHeartbeat)

    def get_latest_by_agent(self, db: Session, agent_id: str, limit: int = 1) -> List[AgentHeartbeat]:
        return (
            db.query(AgentHeartbeat)
            .filter(AgentHeartbeat.agent_id == agent_id)
            .order_by(AgentHeartbeat.heartbeat_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_status(self, db: Session, status: str, skip: int = 0, limit: int = 100) -> List[AgentHeartbeat]:
        return (
            db.query(AgentHeartbeat)
            .filter(AgentHeartbeat.status == status)
            .order_by(AgentHeartbeat.heartbeat_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
