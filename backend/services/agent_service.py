"""
AgentService — Agent 业务逻辑
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.agent_repository import AgentRepository
from repositories.agent_heartbeat_repository import AgentHeartbeatRepository
from repositories.agent_status_history_repository import AgentStatusHistoryRepository
from models.v2_models import Agent


class AgentService(BaseService[Agent, AgentRepository]):
    repository: AgentRepository
    cache_prefix: str = "agent"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = AgentRepository()
        self._heartbeat_repo = AgentHeartbeatRepository()
        self._status_history_repo = AgentStatusHistoryRepository()

    def get_by_agent_id(self, agent_id: str) -> Optional[Agent]:
        cached = self._cache_get("by_id", agent_id)
        if cached is not None:
            return cached
        obj = self.repository.get_by_agent_id(self.db, agent_id)
        if obj:
            self._cache_set(obj.to_dict(), "by_id", agent_id, ttl=60)
        return obj

    def get_by_name(self, name: str) -> Optional[Agent]:
        return self.repository.get_by_name(self.db, name)

    def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        return self.repository.get_by_status(self.db, status, skip, limit)

    def get_by_team(self, team: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        return self.repository.get_by_team(self.db, team, skip, limit)

    def get_online_agents(self) -> List[Agent]:
        return self.repository.get_online_agents(self.db)

    def search_by_name(self, keyword: str, skip: int = 0, limit: int = 50) -> List[Agent]:
        return self.repository.search_by_name(self.db, keyword, skip, limit)

    def register_agent(self, agent_data: Dict[str, Any]) -> Agent:
        obj = self.repository.create(self.db, agent_data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def update_status(self, agent_id: str, new_status: str,
                      current_task: Optional[str] = None,
                      triggered_by: Optional[str] = None) -> Optional[Agent]:
        agent = self.repository.get_by_agent_id(self.db, agent_id)
        if not agent:
            return None

        old_status = agent.status
        update_data = {"status": new_status, "updated_at": datetime.now(timezone.utc)}
        if current_task:
            update_data["current_task"] = current_task

        obj = self.repository.update(self.db, agent.id, update_data)
        if obj:
            self._status_history_repo.create(self.db, {
                "agent_id": agent_id,
                "from_status": old_status,
                "to_status": new_status,
                "current_task": current_task,
                "triggered_by": triggered_by,
            })
            self.db.commit()
            self._cache_invalidate("by_id", agent_id)
        return obj

    def record_heartbeat(self, heartbeat_data: Dict[str, Any]) -> Any:
        hb = self._heartbeat_repo.create(self.db, heartbeat_data)
        self.db.commit()
        agent_id = heartbeat_data.get("agent_id")
        if agent_id:
            agent = self.repository.get_by_agent_id(self.db, agent_id)
            if agent:
                self.repository.update(self.db, agent.id, {
                    "last_heartbeat_at": datetime.now(timezone.utc),
                    "status": heartbeat_data.get("status", agent.status),
                    "current_task": heartbeat_data.get("current_task", agent.current_task),
                })
                self.db.commit()
                self._cache_invalidate("by_id", agent_id)
        return hb

    def get_latest_heartbeat(self, agent_id: str) -> Optional[Any]:
        hbs = self._heartbeat_repo.get_latest_by_agent(self.db, agent_id, limit=1)
        return hbs[0] if hbs else None

    def get_status_history(self, agent_id: str, skip: int = 0, limit: int = 50) -> List[Any]:
        history = self._status_history_repo.get_by_agent(self.db, agent_id, skip, limit)
        return [h.to_dict() for h in history]

    def get_recent_heartbeats(self, minutes: int = 60, skip: int = 0, limit: int = 100) -> List[Any]:
        hbs = self._heartbeat_repo.get_recent_heartbeats(self.db, minutes, skip, limit)
        return [hb.to_dict() for hb in hbs]

    def get_recent_status_changes(self, minutes: int = 60, skip: int = 0, limit: int = 100) -> List[Any]:
        changes = self._status_history_repo.get_recent_status_changes(self.db, minutes, skip, limit)
        return [c.to_dict() for c in changes]
