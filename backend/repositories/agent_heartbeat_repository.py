"""
AgentHeartbeat Repository — Agent 心跳表数据访问
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

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

    def get_recent_heartbeats(self, db: Session, minutes: int = 60, skip: int = 0, limit: int = 100) -> List[AgentHeartbeat]:
        """获取最近 N 分钟的心跳记录"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - minutes * 60
        return (
            db.query(AgentHeartbeat)
            .filter(AgentHeartbeat.heartbeat_at >= datetime.fromtimestamp(cutoff_time, timezone.utc))
            .order_by(AgentHeartbeat.heartbeat_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_agents_within_timeframe(self, db: Session, minutes: int = 30) -> List[str]:
        """获取最近 N 分钟内有心跳的 agent_id 列表"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - minutes * 60
        result = db.query(AgentHeartbeat.agent_id).distinct().filter(
            AgentHeartbeat.heartbeat_at >= datetime.fromtimestamp(cutoff_time, timezone.utc)
        ).all()
        return [row[0] for row in result]
