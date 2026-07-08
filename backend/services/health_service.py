"""
Agent 健康度评分引擎 — 5 维评分计算

评分公式:
health_score =
  online_status_score   * 0.20 +   # 在线=100, 超时=50, 离线=0
  success_rate_score    * 0.30 +   # success_count / total * 100
  response_latency_score * 0.20 +  # 基于心跳间隔，越快越高
  backlog_score         * 0.15 +   # 待办任务越少越高
  confidence_trend_score * 0.15    # 评分变化率（上升加分，下降扣分）

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-08
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from models.v2_models import get_session
from models.v2_models import (
    Agent, AgentHeartbeat, AgentDispatch
)


# ──────────────────────────────────────────────
# 权重常量
# ──────────────────────────────────────────────
WEIGHT_STATUS = 0.20
WEIGHT_SUCCESS = 0.30
WEIGHT_LATENCY = 0.20
WEIGHT_BACKLOG = 0.15
WEIGHT_TREND = 0.15


class HealthService:
    """
    Agent 健康度 5 维评分引擎。

    所有数据从已有表聚合：
    - agents 表 → 在线状态
    - agent_dispatches / agent_heartbeats → 成功率
    - agent_heartbeats → 响应延迟
    - agent_dispatches → 待办任务
    - 历史评分 → 趋势
    """

    # 超时阈值（秒）：超过此间隔视为离线
    HEARTBEAT_TIMEOUT_SEC = 300  # 5 分钟
    # 心跳正常间隔阈值（秒）
    HEARTBEAT_NORMAL_SEC = 60  # 1 分钟

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._close_db = db is None

    def _get_session(self) -> Session:
        if self._db:
            return self._db
        return get_session()

    # ──────────────────────────────────────────
    # 1. 在线状态评分 (20%)
    # ──────────────────────────────────────────
    def _score_online_status(self, agent_id: str, session: Session) -> float:
        """
        在线状态评分。
        online  = 100
        timeout = 50  (最近一次心跳超时但非完全离线)
        offline = 0
        """
        agent = session.query(Agent).filter_by(name=agent_id).first()
        if agent is None:
            return 0.0

        if agent.status == "online":
            # 检查心跳是否真的在合理范围内
            latest_hb = session.query(AgentHeartbeat).filter_by(
                agent_id=agent_id
            ).order_by(
                AgentHeartbeat.heartbeat_at.desc()
            ).first()

            if latest_hb and latest_hb.heartbeat_at:
                now = datetime.now(timezone.utc)
                last_hb = latest_hb.heartbeat_at
                if last_hb.tzinfo is None:
                    last_hb = last_hb.replace(tzinfo=timezone.utc)
                delta = (now - last_hb).total_seconds()
                if delta > self.HEARTBEAT_TIMEOUT_SEC:
                    return 50.0  # 超时
            return 100.0
        elif agent.status == "timeout":
            return 50.0
        else:
            return 0.0

    # ──────────────────────────────────────────
    # 2. 成功率评分 (30%)
    # ──────────────────────────────────────────
    def _score_success_rate(self, agent_id: str, session: Session) -> float:
        """成功率 = success_count / total_count * 100"""
        total = session.query(AgentDispatch).filter_by(
            agent_id=agent_id
        ).count()

        if total == 0:
            return 50.0  # 无数据时中性评分

        success = session.query(AgentDispatch).filter_by(
            agent_id=agent_id, status="completed"
        ).count()

        failed = session.query(AgentDispatch).filter_by(
            agent_id=agent_id, status="failed"
        ).count()

        timeout_count = session.query(AgentDispatch).filter_by(
            agent_id=agent_id, status="timeout"
        ).count()

        # 完成率 = (completed) / total
        # 失败和超时扣分
        effective_total = success + failed + timeout_count
        if effective_total == 0:
            return 50.0

        success_rate = success / effective_total * 100.0
        return min(max(success_rate, 0.0), 100.0)

    # ──────────────────────────────────────────
    # 3. 响应延迟评分 (20%)
    # ──────────────────────────────────────────
    def _score_response_latency(
        self, agent_id: str, hours: int = 24, session: Optional[Session] = None
    ) -> float:
        """
        基于心跳平均间隔评分。
        每 60 秒扣 10 分：100 - (avg_interval / 60) * 10
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        heartbeats = session.query(AgentHeartbeat).filter(
            AgentHeartbeat.agent_id == agent_id,
            AgentHeartbeat.heartbeat_at >= cutoff,
        ).order_by(AgentHeartbeat.heartbeat_at.asc()).all()

        if len(heartbeats) < 2:
            return 50.0  # 数据不足

        # 计算相邻心跳的平均间隔
        intervals = []
        for i in range(1, len(heartbeats)):
            t1 = heartbeats[i - 1].heartbeat_at
            t2 = heartbeats[i].heartbeat_at
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=timezone.utc)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=timezone.utc)
            delta = (t2 - t1).total_seconds()
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            return 50.0

        avg_interval = sum(intervals) / len(intervals)
        score = max(0.0, 100.0 - (avg_interval / 60.0) * 10.0)
        return round(score, 2)

    # ──────────────────────────────────────────
    # 4. 待办任务评分 (15%)
    # ──────────────────────────────────────────
    def _score_backlog(self, agent_id: str, session: Session) -> float:
        """待办任务越少评分越高，每个待办扣 10 分。"""
        # 查找该 Agent 的待办任务
        pending_dispatches = session.query(AgentDispatch).filter_by(
            agent_id=agent_id,
        ).filter(
            AgentDispatch.status.in_(["pending", "dispatched", "running"])
        ).count()

        score = max(0.0, 100.0 - pending_dispatches * 10.0)
        return score

    # ──────────────────────────────────────────
    # 5. 趋势评分 (15%)
    # ──────────────────────────────────────────
    def _score_confidence_trend(
        self, agent_id: str, hours: int = 24, session: Optional[Session] = None
    ) -> float:
        """
        基于当前评分与 N 小时前评分的变化。
        上升 > 50, 下降 < 50, 不变 = 50
        """
        # 估算 N 小时前评分（通过历史心跳统计近似）
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        earlier_cutoff = cutoff - timedelta(hours=hours)

        # 当前窗口
        current_dispatches = session.query(AgentDispatch).filter(
            AgentDispatch.agent_id == agent_id,
            AgentDispatch.dispatched_at >= cutoff,
        ).all()

        # 前一窗口
        earlier_dispatches = session.query(AgentDispatch).filter(
            AgentDispatch.agent_id == agent_id,
            AgentDispatch.dispatched_at >= earlier_cutoff,
            AgentDispatch.dispatched_at < cutoff,
        ).all()

        def _window_rate(dispatches):
            if not dispatches:
                return 0.5
            success = sum(1 for d in dispatches if d.status == "completed")
            fail = sum(1 for d in dispatches if d.status == "failed")
            total = success + fail
            if total == 0:
                return 0.5
            return success / total

        current_rate = _window_rate(current_dispatches)
        previous_rate = _window_rate(earlier_dispatches)

        # 趋势: 相对变化率
        if previous_rate > 0:
            trend_ratio = (current_rate - previous_rate) / previous_rate
        elif current_rate > 0:
            # 从 0% 改善到 >0%，视为显著改善
            trend_ratio = 0.5
        else:
            trend_ratio = 0.0

        # 映射到 0-100: 50 为中性
        trend_score = 50.0 + trend_ratio * 50.0
        return max(0.0, min(100.0, trend_score))

    # ──────────────────────────────────────────
    # 内部：原始评分计算（不含趋势，用于趋势计算）
    # ──────────────────────────────────────────
    def _calculate_raw_score(
        self, agent_id: str, session: Optional[Session] = None
    ) -> float:
        """仅计算 4 维评分（不含趋势），用于趋势比较。"""
        s = session or self._get_session()

        status_s = self._score_online_status(agent_id, s)
        success_s = self._score_success_rate(agent_id, s)
        latency_s = self._score_response_latency(agent_id, session=s)
        backlog_s = self._score_backlog(agent_id, s)

        raw = (
            status_s * WEIGHT_STATUS
            + success_s * WEIGHT_SUCCESS
            + latency_s * WEIGHT_LATENCY
            + backlog_s * WEIGHT_BACKLOG
        ) / (WEIGHT_STATUS + WEIGHT_SUCCESS + WEIGHT_LATENCY + WEIGHT_BACKLOG)

        return round(raw, 2)

    # ──────────────────────────────────────────
    # 公共方法
    # ──────────────────────────────────────────

    def calculate_health(
        self, agent_id: str
    ) -> Dict[str, Any]:
        """
        计算单个 Agent 的健康度。

        Returns:
            {
                "agent_id": "...",
                "score": int (0-100),
                "components": {
                    "online_status": float,
                    "success_rate": float,
                    "response_latency": float,
                    "backlog": float,
                    "confidence_trend": float,
                },
                "trend": "up" | "down" | "stable",
            }
        """
        session = self._get_session()

        status_s = self._score_online_status(agent_id, session)
        success_s = self._score_success_rate(agent_id, session)
        latency_s = self._score_response_latency(agent_id, session=session)
        backlog_s = self._score_backlog(agent_id, session)
        trend_s = self._score_confidence_trend(agent_id, session=session)

        final = (
            status_s * WEIGHT_STATUS
            + success_s * WEIGHT_SUCCESS
            + latency_s * WEIGHT_LATENCY
            + backlog_s * WEIGHT_BACKLOG
            + trend_s * WEIGHT_TREND
        )

        final = int(round(max(0.0, min(100.0, final))))

        # 判断趋势方向
        trend_label = "stable"
        if trend_s > 55:
            trend_label = "up"
        elif trend_s < 45:
            trend_label = "down"

        if self._close_db:
            session.close()

        return {
            "agent_id": agent_id,
            "score": final,
            "components": {
                "online_status": round(status_s, 2),
                "success_rate": round(success_s, 2),
                "response_latency": round(latency_s, 2),
                "backlog": round(backlog_s, 2),
                "confidence_trend": round(trend_s, 2),
            },
            "trend": trend_label,
        }

    def get_all_health(self) -> List[Dict[str, Any]]:
        """获取所有 Agent 的健康度。"""
        session = self._get_session()
        agents = session.query(Agent).all()
        results = []
        for agent in agents:
            health = self.calculate_health(agent.name)
            results.append(health)

        if self._close_db:
            session.close()

        return results

    def get_health_trend(
        self, agent_id: str, hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取 Agent 健康度趋势数据（时间序列）。

        通过采样历史心跳和派发记录生成近似时间序列。
        """
        session = self._get_session()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        heartbeats = session.query(AgentHeartbeat).filter(
            AgentHeartbeat.agent_id == agent_id,
            AgentHeartbeat.heartbeat_at >= cutoff,
        ).order_by(AgentHeartbeat.heartbeat_at.asc()).all()

        # 按小时分桶
        trend_data = []
        for i in range(hours, -1, -1):
            bucket_time = datetime.now(timezone.utc) - timedelta(hours=i)
            bucket_end = bucket_time + timedelta(hours=1)

            # 该时段心跳统计
            hb_in_bucket = [
                hb for hb in heartbeats
                if bucket_time <= (
                    hb.heartbeat_at.replace(tzinfo=timezone.utc)
                    if hb.heartbeat_at.tzinfo is None
                    else hb.heartbeat_at
                ) < bucket_end
            ]

            # 该时段派发统计
            dispatches = session.query(AgentDispatch).filter(
                AgentDispatch.agent_id == agent_id,
                AgentDispatch.dispatched_at >= bucket_time,
                AgentDispatch.dispatched_at < bucket_end,
            ).all()

            # 简单评分
            success = sum(1 for d in dispatches if d.status == "completed")
            total_dispatch = len(dispatches)
            rate = success / total_dispatch * 100 if total_dispatch > 0 else 50

            # 在线状态
            has_hb = len(hb_in_bucket) > 0
            status_score = 100 if has_hb else 0

            score = int(
                status_score * WEIGHT_STATUS
                + rate * WEIGHT_SUCCESS
                + 60 * WEIGHT_LATENCY  # 默认
                + max(0, 100 - total_dispatch * 10) * WEIGHT_BACKLOG
                + 50 * WEIGHT_TREND
            )

            trend_data.append({
                "time": bucket_time.isoformat(),
                "score": min(100, max(0, score)),
            })

        if self._close_db:
            session.close()

        return {
            "agent_id": agent_id,
            "hours": hours,
            "trend": trend_data,
        }

    def get_component_breakdown(self, agent_id: str) -> Dict[str, Any]:
        """获取 5 维详细分数分解。"""
        health = self.calculate_health(agent_id)
        return {
            "agent_id": agent_id,
            "score": health["score"],
            "components": health["components"],
            "weights": {
                "online_status": WEIGHT_STATUS,
                "success_rate": WEIGHT_SUCCESS,
                "response_latency": WEIGHT_LATENCY,
                "backlog": WEIGHT_BACKLOG,
                "confidence_trend": WEIGHT_TREND,
            },
        }

    def get_health_summary(self) -> Dict[str, Any]:
        """
        团队健康度概览。
        包含平均/最高/最低/分布。
        """
        all_health = self.get_all_health()
        if not all_health:
            return {
                "total_agents": 0,
                "average_score": 0,
                "highest_score": 0,
                "lowest_score": 0,
                "distribution": {"healthy": 0, "warning": 0, "critical": 0},
            }

        scores = [h["score"] for h in all_health]
        avg_score = round(sum(scores) / len(scores), 1)
        highest = max(scores)
        lowest = min(scores)

        distribution = {"healthy": 0, "warning": 0, "critical": 0}
        for s in scores:
            if s >= 80:
                distribution["healthy"] += 1
            elif s >= 50:
                distribution["warning"] += 1
            else:
                distribution["critical"] += 1

        return {
            "total_agents": len(all_health),
            "average_score": avg_score,
            "highest_score": highest,
            "lowest_score": lowest,
            "distribution": distribution,
            "agents": all_health,
        }

    def get_health_ranking(self) -> List[Dict[str, Any]]:
        """Agent 健康度排名。"""
        all_health = self.get_all_health()
        ranked = sorted(all_health, key=lambda h: h["score"], reverse=True)
        for i, h in enumerate(ranked):
            h["rank"] = i + 1
        return ranked
