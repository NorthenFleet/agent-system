"""
Agent Repository — Agent 表数据访问
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import Agent


class AgentRepository(BaseRepository[Agent]):
    def __init__(self):
        super().__init__(Agent)

    def get_by_agent_id(self, db: Session, agent_id: str) -> Optional[Agent]:
        return db.query(Agent).filter(Agent.agent_id == agent_id).first()

    def get_by_name(self, db: Session, name: str) -> Optional[Agent]:
        return db.query(Agent).filter(Agent.name == name).first()

    def get_by_status(self, db: Session, status: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        return db.query(Agent).filter(Agent.status == status).offset(skip).limit(limit).all()

    def get_by_team(self, db: Session, team: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        return db.query(Agent).filter(Agent.team == team).offset(skip).limit(limit).all()

    def get_online_agents(self, db: Session) -> List[Agent]:
        return db.query(Agent).filter(Agent.status == "online").all()

    def search_by_name(self, db: Session, keyword: str, skip: int = 0, limit: int = 50) -> List[Agent]:
        return (
            db.query(Agent)
            .filter(Agent.name.ilike(f"%{keyword}%"))
            .offset(skip)
            .limit(limit)
            .all()
        )
