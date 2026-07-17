"""
自动化规则引擎模型 — SQLAlchemy ORM

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-09 (Sprint 5 P6)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class AutomationRule(Base):
    """自动化规则定义"""
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    trigger = Column(JSON, nullable=False)  # {"type": "task_created", "conditions": {...}}
    actions = Column(JSON, nullable=False)  # [{"type": "assign", "params": {...}}, ...]
    priority = Column(Integer, nullable=False, default=10, index=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    executions = relationship("AutomationRuleExecution", back_populates="rule",
                              cascade="all, delete-orphan", order_by="AutomationRuleExecution.executed_at.desc()")

    def to_dict(self, include_executions: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "trigger": self.trigger or {},
            "actions": self.actions or [],
            "priority": self.priority,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_executions and self.executions:
            data["executions"] = [e.to_dict() for e in self.executions[:10]]
        return data


class AutomationRuleExecution(Base):
    """规则执行历史"""
    __tablename__ = "automation_rule_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_type = Column(String(32), nullable=False, index=True)
    trigger_payload = Column(JSON, nullable=True)
    action_results = Column(JSON, nullable=True)
    status = Column(String(16), nullable=False, default="success", index=True)  # success | failed | skipped
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    rule = relationship("AutomationRule", back_populates="executions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "trigger_type": self.trigger_type,
            "trigger_payload": self.trigger_payload,
            "action_results": self.action_results,
            "status": self.status,
            "error_message": self.error_message,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }
