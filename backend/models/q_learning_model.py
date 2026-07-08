"""
Q-Learning 智能任务路由 — Q-Table 数据模型

存储 Q(s,a) 值、Agent 统计数据和超参数于单行 JSON 表。

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-08
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy import Column, Integer, JSON, DateTime

from database import Base


class QTable(Base):
    """
    Q-Table 持久化模型 — 全表只有一行，存储所有 Q(s,a) 值和统计。

    state_action_values 格式:
    {
      "backend_task:raphael": 0.6,
      "backend_task:donatello": 0.3,
      "frontend_task:donatello": 0.8,
    }

    agent_stats 格式:
    {
      "raphael": {
        "success_count": 10,
        "fail_count": 1,
        "timeout_count": 0,
        "total_cost": 0.5
      },
      ...
    }

    meta 格式:
    {
      "learning_rate": 0.1,
      "discount_factor": 0.9,
      "epsilon": 0.1,
      "last_updated": "ISO-8601"
    }
    """
    __tablename__ = "q_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    state_action_values = Column(
        JSON, nullable=False, default=lambda: {}
    )
    agent_stats = Column(
        JSON, nullable=False, default=lambda: {}
    )
    meta = Column(
        JSON, nullable=False, default=lambda: {
            "learning_rate": 0.1,
            "discount_factor": 0.9,
            "epsilon": 0.1,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    )
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "state_action_values": self.state_action_values or {},
            "agent_stats": self.agent_stats or {},
            "meta": self.meta or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
