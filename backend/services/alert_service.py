"""
AlertService — 告警业务逻辑
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from services.base import BaseService, Cache
from repositories.alert_rule_repository import AlertRuleRepository
from repositories.alert_event_repository import AlertEventRepository
from models.v2_models import AlertRule, AlertEvent


class AlertService(BaseService[AlertRule, AlertRuleRepository]):
    """告警规则 + 告警事件的组合 Service"""
    repository: AlertRuleRepository
    cache_prefix: str = "alert"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = AlertRuleRepository()
        self._event_repo = AlertEventRepository()

    # ─── AlertRule ───

    def get_enabled_rules(self) -> List[AlertRule]:
        return self.repository.get_enabled_rules(self.db)

    def get_rules_for_agent(self, agent_id: str) -> List[AlertRule]:
        return self.repository.get_rules_for_agent(self.db, agent_id)

    def get_by_severity(self, severity: str, skip: int = 0, limit: int = 100) -> List[AlertRule]:
        return self.repository.get_by_severity(self.db, severity, skip, limit)

    def create_rule(self, rule_data: dict) -> AlertRule:
        obj = self.repository.create(self.db, rule_data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def toggle_rule(self, rule_id: int, enabled: bool) -> Optional[AlertRule]:
        return self.update(rule_id, {"enabled": enabled})

    def get_rule_by_id(self, rule_id: int) -> Optional[AlertRule]:
        """根据 ID 获取规则"""
        return self.repository.get_by_id(self.db, rule_id)

    def list_rules(self, skip: int = 0, limit: int = 100) -> List[AlertRule]:
        """获取规则列表"""
        return self.repository.get_all(self.db, skip=skip, limit=limit, order_by="created_at")

    # ─── AlertEvent ───

    def get_unacknowledged(self, skip: int = 0, limit: int = 100) -> List[AlertEvent]:
        return self._event_repo.get_unacknowledged(self.db, skip, limit)

    def get_by_agent(self, agent_id: str, skip: int = 0, limit: int = 50) -> List[AlertEvent]:
        return self._event_repo.get_by_agent(self.db, agent_id, skip, limit)

    def get_by_severity(self, severity: str, skip: int = 0, limit: int = 100) -> List[AlertEvent]:
        return self._event_repo.get_by_severity(self.db, severity, skip, limit)

    def count_unacknowledged(self) -> int:
        return self._event_repo.count_unacknowledged(self.db)

    def create_alert_event(self, event_data: dict) -> AlertEvent:
        obj = self._event_repo.create(self.db, event_data)
        self.db.commit()
        self._cache_invalidate_prefix("unack")
        return obj

    def acknowledge_event(self, event_id: int, acknowledged_by: str) -> Optional[AlertEvent]:
        obj = self._event_repo.update(self.db, event_id, {
            "acknowledged": True,
            "acknowledged_by": acknowledged_by,
            "acknowledged_at": datetime.now(timezone.utc),
        })
        if obj:
            self.db.commit()
            self._cache_invalidate_prefix("unack")
        return obj

    def acknowledge_all(self, agent_id: Optional[str] = None, acknowledged_by: str = "") -> int:
        now = datetime.now(timezone.utc)
        if agent_id:
            events = self._event_repo.get_by_agent(self.db, agent_id)
        else:
            events = self._event_repo.get_unacknowledged(self.db)
        count = 0
        for e in events:
            if not e.acknowledged:
                self._event_repo.update(self.db, e.id, {
                    "acknowledged": True,
                    "acknowledged_by": acknowledged_by,
                    "acknowledged_at": now,
                })
                count += 1
        if count:
            self.db.commit()
            self._cache_invalidate_prefix("unack")
        return count

    def get_event_by_id(self, event_id: int) -> Optional[AlertEvent]:
        """根据 ID 获取事件"""
        return self._event_repo.get_by_id(self.db, event_id)

    def get_event_stats(self) -> Dict[str, Any]:
        """获取告警统计"""
        total = self._event_repo.count(self.db)
        active = self._event_repo.count_unacknowledged(self.db)
        critical = self._event_repo.count(self.db, filters={"severity": "critical", "acknowledged": False})
        return {
            "total": total or 0,
            "active": active or 0,
            "critical": critical or 0,
        }

    def list_events(self, skip: int = 0, limit: int = 100) -> List[AlertEvent]:
        """获取事件列表"""
        return self._event_repo.get_all(self.db, skip=skip, limit=limit, order_by="created_at")
