"""
Agent 健康度计算引擎

评分维度（0-100）：
  - online_status (20%): 在线=100, timeout=50, 离线=0
  - success_rate (30%): 近 30 天成功任务 / 总任务 * 100
  - response_latency (20%): 基于心跳间隔（<60s=100, 60-300s=50, >300s=0）
  - backlog (15%): 1 - (pending_tasks / max(10, pending_tasks)) * 100
  - confidence_trend (15%): 最近 3 次评分的斜率，正斜率加分

@author 🟥 拉斐尔
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from models.v2_models import (
    AgentHealthScore, AgentHeartbeat, Agent, Task, get_session
)

logger = logging.getLogger(__name__)

# 权重
W_ONLINE = 0.20
W_SUCCESS = 0.30
W_LATENCY = 0.20
W_BACKLOG = 0.15
W_TREND = 0.15


class HealthService:
    """健康度计算引擎"""

    def __init__(self, db: Session):
        self.db = db

    def calculate_health(self, agent_id: str) -> Dict[str, Any]:
        """计算单个 Agent 的健康度，返回 0-100 的评分及各维度详情。"""
        # 1. online_status
        online_score = self._score_online_status(agent_id)

        # 2. success_rate
        success_score = self._score_success_rate(agent_id)

        # 3. response_latency
        latency_score = self._score_response_latency(agent_id)

        # 4. backlog
        backlog_score = self._score_backlog(agent_id)

        # 5. confidence_trend
        trend_score = self._score_confidence_trend(agent_id)

        total = (
            online_score * W_ONLINE +
            success_score * W_SUCCESS +
            latency_score * W_LATENCY +
            backlog_score * W_BACKLOG +
            trend_score * W_TREND
        )
        total = max(0.0, min(100.0, total))

        # 持久化评分
        record = self._save_health_record(agent_id, total, online_score, success_score,
                                          latency_score, backlog_score, trend_score)

        return {
            "agent_id": agent_id,
            "score": round(total, 2),
            "dimensions": {
                "online_status": {"score": round(online_score, 2), "weight": W_ONLINE},
                "success_rate": {"score": round(success_score, 2), "weight": W_SUCCESS},
                "response_latency": {"score": round(latency_score, 2), "weight": W_LATENCY},
                "backlog": {"score": round(backlog_score, 2), "weight": W_BACKLOG},
                "confidence_trend": {"score": round(trend_score, 2), "weight": W_TREND},
            },
            "calculated_at": record.calculated_at.isoformat(),
        }

    def get_health(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """返回单个 Agent 最新健康度。"""
        latest = (
            self.db.query(AgentHealthScore)
            .filter(AgentHealthScore.agent_id == agent_id)
            .order_by(desc(AgentHealthScore.calculated_at))
            .first()
        )
        if not latest:
            # 首次计算
            return self.calculate_health(agent_id)
        return latest.to_dict()

    def get_all_health(self) -> List[Dict[str, Any]]:
        """返回所有 Agent 健康度列表。"""
        agents = self.db.query(Agent).all()
        results = []
        for agent in agents:
            health = self.get_health(agent.agent_id)
            if health:
                health["agent_name"] = agent.name
                health["team"] = agent.team
                results.append(health)
        return results

    def get_health_trend(self, agent_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """返回历史趋势数据点。"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        records = (
            self.db.query(AgentHealthScore)
            .filter(
                and_(
                    AgentHealthScore.agent_id == agent_id,
                    AgentHealthScore.calculated_at >= cutoff,
                )
            )
            .order_by(AgentHealthScore.calculated_at.asc())
            .all()
        )
        return [r.to_dict() for r in records]

    # ─── 内部评分方法 ───

    def _score_online_status(self, agent_id: str) -> float:
        """在线状态评分：在线=100, timeout=50, 离线=0"""
        agent = self.db.query(Agent).filter(Agent.agent_id == agent_id).first()
        if not agent:
            return 0.0
        status_map = {
            "online": 100.0,
            "timeout": 50.0,
            "offline": 0.0,
            "busy": 100.0,
        }
        return status_map.get(agent.status, 0.0)

    def _score_success_rate(self, agent_id: str) -> float:
        """近 30 天任务成功率评分。"""
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        tasks = (
            self.db.query(Task)
            .filter(
                and_(
                    Task.assignee == agent_id,
                    Task.created_at >= thirty_days_ago,
                )
            )
            .all()
        )
        if not tasks:
            # 无历史任务，默认 50 分
            return 50.0
        completed = [t for t in tasks if t.status in ("completed", "done")]
        rate = len(completed) / len(tasks) * 100
        return max(0.0, min(100.0, rate))

    def _score_response_latency(self, agent_id: str) -> float:
        """基于心跳间隔评分：<60s=100, 60-300s=50, >300s=0"""
        agent = self.db.query(Agent).filter(Agent.agent_id == agent_id).first()
        if not agent or not agent.last_heartbeat_at:
            return 0.0

        now = datetime.now(timezone.utc)
        last_hb = agent.last_heartbeat_at
        if last_hb.tzinfo is None:
            last_hb = last_hb.replace(tzinfo=timezone.utc)

        interval_seconds = (now - last_hb).total_seconds()

        if interval_seconds < 60:
            return 100.0
        elif interval_seconds <= 300:
            # 线性插值: 60s→100, 300s→50
            return 100.0 - (interval_seconds - 60) / (300 - 60) * 50.0
        else:
            return 0.0

    def _score_backlog(self, agent_id: str) -> float:
        """积压评分：1 - (pending_tasks / max(10, pending_tasks)) * 100"""
        pending_count = (
            self.db.query(Task)
            .filter(
                and_(
                    Task.assignee == agent_id,
                    Task.status.in_(("pending", "in_progress", "doing")),
                )
            )
            .count()
        )
        max_val = max(10, pending_count)
        score = (1 - pending_count / max_val) * 100
        return max(0.0, min(100.0, score))

    def _score_confidence_trend(self, agent_id: str) -> float:
        """最近 3 次评分的斜率趋势，正斜率加分。"""
        records = (
            self.db.query(AgentHealthScore)
            .filter(AgentHealthScore.agent_id == agent_id)
            .order_by(desc(AgentHealthScore.calculated_at))
            .limit(3)
            .all()
        )
        if len(records) < 2:
            return 50.0  # 数据不足，默认中等

        scores = [r.score for r in reversed(records)]
        n = len(scores)
        # 简单线性回归斜率
        x_mean = (n - 1) / 2.0
        y_mean = sum(scores) / n
        numerator = sum((i - x_mean) * (scores[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0

        # 将斜率映射到 0-100: 负斜率→低分, 零→50, 正斜率→高分
        # 斜率范围大致在 -50 到 50 之间
        trend_score = 50.0 + slope * 10
        return max(0.0, min(100.0, trend_score))

    def _save_health_record(
        self, agent_id: str, total: float, online: float, success: float,
        latency: float, backlog: float, trend: float
    ) -> AgentHealthScore:
        """保存健康度记录到数据库。"""
        record = AgentHealthScore(
            agent_id=agent_id,
            score=total,
            online_status=self._get_agent_online_status(agent_id),
            success_rate=success,
            response_latency=latency,
            backlog_score=backlog,
            confidence_trend=trend,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _get_agent_online_status(self, agent_id: str) -> str:
        agent = self.db.query(Agent).filter(Agent.agent_id == agent_id).first()
        return agent.status if agent else "unknown"
