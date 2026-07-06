"""
AgentDispatch Repository — Agent 任务派发记录数据访问
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import AgentDispatch


class AgentDispatchRepository(BaseRepository[AgentDispatch]):
    def __init__(self):
        super().__init__(AgentDispatch)

    def create_dispatch(self, db: Session, dispatch_data: dict) -> AgentDispatch:
        """创建派发记录"""
        dispatch = AgentDispatch(**dispatch_data)
        db.add(dispatch)
        db.commit()
        db.refresh(dispatch)
        return dispatch

    def get_by_agent(self, db: Session, agent_id: str, skip: int = 0, limit: int = 50) -> List[AgentDispatch]:
        return (
            db.query(AgentDispatch)
            .filter(AgentDispatch.agent_id == agent_id)
            .order_by(AgentDispatch.dispatched_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_task(self, db: Session, task_id: str) -> Optional[AgentDispatch]:
        return (
            db.query(AgentDispatch)
            .filter(AgentDispatch.task_id == task_id)
            .order_by(AgentDispatch.dispatched_at.desc())
            .first()
        )

    def get_by_status(self, db: Session, status: str, skip: int = 0, limit: int = 50) -> List[AgentDispatch]:
        return (
            db.query(AgentDispatch)
            .filter(AgentDispatch.status == status)
            .order_by(AgentDispatch.dispatched_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
