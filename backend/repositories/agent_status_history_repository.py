"""
AgentStatusHistory Repository — Agent 状态历史表数据访问
"""
from typing import List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

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

    def get_recent_status_changes(self, db: Session, minutes: int = 60, skip: int = 0, limit: int = 100) -> List[AgentStatusHistory]:
        """获取最近 N 分钟的状态变更"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - minutes * 60
        return (
            db.query(AgentStatusHistory)
            .filter(AgentStatusHistory.changed_at >= datetime.fromtimestamp(cutoff_time, timezone.utc))
            .order_by(AgentStatusHistory.changed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
