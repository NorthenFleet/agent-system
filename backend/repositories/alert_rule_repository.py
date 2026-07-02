"""
AlertRule Repository — 告警规则表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import AlertRule


class AlertRuleRepository(BaseRepository[AlertRule]):
    def __init__(self):
        super().__init__(AlertRule)

    def get_enabled_rules(self, db: Session) -> List[AlertRule]:
        return db.query(AlertRule).filter(AlertRule.enabled == True).all()

    def get_rules_for_agent(self, db: Session, agent_id: str) -> List[AlertRule]:
        return (
            db.query(AlertRule)
            .filter(
                AlertRule.enabled == True,
                (AlertRule.agent_id == None) | (AlertRule.agent_id == agent_id)
            )
            .all()
        )

    def get_by_severity(self, db: Session, severity: str, skip: int = 0, limit: int = 100) -> List[AlertRule]:
        return (
            db.query(AlertRule)
            .filter(AlertRule.severity == severity, AlertRule.enabled == True)
            .offset(skip)
            .limit(limit)
            .all()
        )
