"""
AgentStatusHistory Repository — Agent 状态历史表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import AgentStatusHistory


class AgentStatusHistoryRepository(BaseRepository[AgentStatusHistory]):
    def __init__(self):
        super().__init__(AgentStatusHistory)

    def get_by_agent(self, db: Session, agent_id: str, skip: int = 0, limit: int = 50) -> List[AgentStatusHistory]:
        return (
            db.query(AgentStatusHistory)
            .filter(AgentStatusHistory.agent_id == agent_id)
            .order_by(AgentStatusHistory.changed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
