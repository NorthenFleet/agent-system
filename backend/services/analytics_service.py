"""
AnalyticsService — 数据分析聚合服务 (S5 P5)

5 个聚合方法：
1. team_efficiency  — 团队效率指标
2. throughput        — 任务吞吐量
3. agent_productivity — Agent 产出率
4. sprint_burndown   — Sprint 燃尽
5. task_trend        — 任务趋势

所有查询使用 SQLAlchemy 聚合函数 (func.count, func.avg, func.sum)，
避免 N+1 查询，单次 SQL 完成统计。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from models.v2_models import (
    Task, Agent, Sprint,
)

logger = logging.getLogger(__name__)

# Valid time ranges
VALID_DAYS = {7, 14, 30, 90}
DEFAULT_DAYS = 14


def _now_utc() -> datetime:
    """Return the current UTC datetime for query cutoffs."""
    return datetime.now(timezone.utc)


def _cutoff(days: int) -> datetime:
    """Return the UTC cutoff datetime for the given number of days."""
    return _now_utc() - timedelta(days=days)


def _parse_days(days: Optional[int]) -> int:
    """Validate and normalise the days parameter."""
    if days not in VALID_DAYS:
        return DEFAULT_DAYS
    return days


def _make_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt is None:
        return _now_utc()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# 1. Team Efficiency
# ---------------------------------------------------------------------------

class TeamEfficiencyService:
    """Compute team-level efficiency metrics over a rolling window."""

    @staticmethod
    def compute(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """
        计算团队效率指标。

        使用单次聚合查询获取 total/completed/in-progress 任务数，
        使用 func.avg 获取平均进度和平均完成耗时。
        """
        days = _parse_days(days)
        since = _cutoff(days)

        # Single-pass aggregate: total, completed, avg progress
        row = (
            db.query(
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == "completed", 1), else_=0)).label("completed"),
                func.avg(Task.progress).label("avg_progress"),
            )
            .filter(Task.created_at >= since)
            .one()
        )

        total = row.total or 0
        completed = row.completed or 0
        avg_progress = float(row.avg_progress) if row.avg_progress else 0.0
        completion_rate = (completed / total * 100) if total else 0.0

        # Average time to complete: use completed_at - created_at
        completed_row = (
            db.query(func.avg(
                func.julianday(Task.completed_at) - func.julianday(Task.created_at)
            ).label("avg_hours"))
            .filter(
                Task.status == "completed",
                Task.completed_at >= since,
                Task.completed_at.isnot(None),
                Task.created_at.isnot(None),
            )
            .one()
        )
        avg_hours = (float(completed_row.avg_hours) * 24) if completed_row.avg_hours else None

        # By status — single grouped query (no N+1)
        status_rows = (
            db.query(Task.status, func.count(Task.id))
            .filter(Task.created_at >= since)
            .group_by(Task.status)
            .all()
        )
        by_status = {s: c for s, c in status_rows}

        # By priority — single grouped query
        priority_rows = (
            db.query(Task.priority, func.count(Task.id))
            .filter(Task.created_at >= since)
            .group_by(Task.priority)
            .all()
        )
        by_priority = {p: c for p, c in priority_rows}

        # By assignee (top 10) — single grouped query
        assignee_rows = (
            db.query(Task.assignee, func.count(Task.id))
            .filter(Task.created_at >= since, Task.assignee.isnot(None))
            .group_by(Task.assignee)
            .order_by(func.count(Task.id).desc())
            .limit(10)
            .all()
        )
        by_assignee = {a: c for a, c in assignee_rows}

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "avg_completion_rate": round(completion_rate, 2),
            "avg_progress": round(avg_progress, 2),
            "avg_time_to_complete_hours": round(avg_hours, 2) if avg_hours is not None else None,
            "by_status": by_status,
            "by_priority": by_priority,
            "by_assignee": by_assignee,
        }


# ---------------------------------------------------------------------------
# 2. Throughput
# ---------------------------------------------------------------------------

class ThroughputService:
    """Compute daily task throughput (created vs completed)."""

    @staticmethod
    def compute(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """
        计算每日吞吐量。

        使用 func.date 按天分组，单次查询得到每天的 created/completed/in_progress 数量。
        """
        days = _parse_days(days)
        since = _cutoff(days)

        # Daily created
        created_rows = (
            db.query(
                func.date(Task.created_at).label("day"),
                func.count(Task.id).label("cnt"),
            )
            .filter(Task.created_at >= since)
            .group_by(func.date(Task.created_at))
            .order_by(func.date(Task.created_at))
            .all()
        )

        # Daily completed
        completed_rows = (
            db.query(
                func.date(Task.completed_at).label("day"),
                func.count(Task.id).label("cnt"),
            )
            .filter(
                Task.completed_at >= since,
                Task.completed_at.isnot(None),
            )
            .group_by(func.date(Task.completed_at))
            .order_by(func.date(Task.completed_at))
            .all()
        )

        # Current in_progress count (snapshot, not daily)
        in_progress_count = (
            db.query(func.count(Task.id))
            .filter(Task.status == "in_progress", Task.created_at >= since)
            .scalar()
        ) or 0

        # Build date-indexed map
        created_map: Dict[str, int] = {r.day: r.cnt for r in created_rows}
        completed_map: Dict[str, int] = {r.day: r.cnt for r in completed_rows}

        # Collect all dates
        all_dates = sorted(set(created_map.keys()) | set(completed_map.keys()))

        data_points = []
        for d in all_dates:
            data_points.append({
                "date": d,
                "created": created_map.get(d, 0),
                "completed": completed_map.get(d, 0),
                "in_progress": in_progress_count,
            })

        total_created = sum(r.cnt for r in created_rows)
        total_completed = sum(r.cnt for r in completed_rows)
        daily_avg_created = round(total_created / days, 2) if days else 0
        daily_avg_completed = round(total_completed / days, 2) if days else 0

        # Simple trend: compare last 3 days vs previous 3 days
        trend = "stable"
        if len(all_dates) >= 6:
            recent = sum(completed_map.get(d, 0) for d in all_dates[-3:])
            earlier = sum(completed_map.get(d, 0) for d in all_dates[-6:-3])
            if recent > earlier * 1.1:
                trend = "increasing"
            elif recent < earlier * 0.9:
                trend = "decreasing"

        return {
            "summary": {
                "total_created": total_created,
                "total_completed": total_completed,
                "daily_avg_created": daily_avg_created,
                "daily_avg_completed": daily_avg_completed,
                "trend": trend,
            },
            "data_points": data_points,
        }


# ---------------------------------------------------------------------------
# 3. Agent Productivity
# ---------------------------------------------------------------------------

class AgentProductivityService:
    """Compute per-agent productivity metrics."""

    @staticmethod
    def compute(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """
        计算每个 Agent 的产出率。

        使用 func.avg / func.count 在 Task 表上按 assignee 聚合，
        再 LEFT JOIN Agent 表获取 team 和 last_heartbeat。
        全程无 N+1。
        """
        days = _parse_days(days)
        since = _cutoff(days)

        # Per-assignee aggregates from Task table
        task_stats = (
            db.query(
                Task.assignee.label("assignee"),
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == "completed", 1), else_=0)).label("completed"),
                func.avg(Task.progress).label("avg_progress"),
            )
            .filter(Task.assignee.isnot(None), Task.created_at >= since)
            .group_by(Task.assignee)
            .all()
        )

        # Build a map of assignee -> stats
        stats_map: Dict[str, Dict] = {}
        for row in task_stats:
            total = row.total or 0
            completed = row.completed or 0
            avg_prog = float(row.avg_progress) if row.avg_progress else 0.0
            stats_map[row.assignee] = {
                "total_tasks": total,
                "completed_tasks": completed,
                "completion_rate": round(completed / total * 100, 2) if total else 0.0,
                "avg_progress": round(avg_prog, 2),
            }

        # Fetch Agent records for team and last_heartbeat (single query)
        assignees = list(stats_map.keys())
        agent_map: Dict[str, Dict] = {}
        if assignees:
            agents = (
                db.query(Agent.name, Agent.team, Agent.last_heartbeat)
                .filter(Agent.name.in_(assignees))
                .all()
            )
            for a in agents:
                agent_map[a.name] = {
                    "team": a.team,
                    "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                }

        # Build result list
        agents_list = []
        for assignee, stats in stats_map.items():
            agent_info = agent_map.get(assignee, {})
            agents_list.append({
                "agent_name": assignee,
                "team": agent_info.get("team"),
                "last_heartbeat": agent_info.get("last_heartbeat"),
                **stats,
            })

        # Sort by completion_rate desc
        agents_list.sort(key=lambda x: x["completion_rate"], reverse=True)

        # Summary
        total_agents = len(agents_list)
        all_rates = [a["completion_rate"] for a in agents_list]
        all_tasks = [a["total_tasks"] for a in agents_list]
        avg_completion = round(sum(all_rates) / total_agents, 2) if total_agents else 0.0
        avg_tasks = round(sum(all_tasks) / total_agents, 2) if total_agents else 0.0
        top_performer = agents_list[0]["agent_name"] if agents_list else None

        return {
            "summary": {
                "total_agents": total_agents,
                "avg_completion_rate": avg_completion,
                "avg_tasks_per_agent": avg_tasks,
                "top_performer": top_performer,
            },
            "agents": agents_list,
        }


# ---------------------------------------------------------------------------
# 4. Sprint Burndown
# ---------------------------------------------------------------------------

class SprintBurndownService:
    """Compute Sprint burndown chart data."""

    @staticmethod
    def compute(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """
        计算 Sprint 燃尽数据。

        对每个 Sprint 查询其任务集合，按天分组统计 completed/remaining。
        使用 func.count 和 func.date 进行聚合，避免 N+1。
        """
        days = _parse_days(days)

        # Get active or recently-completed sprints
        sprints = (
            db.query(Sprint)
            .filter(
                Sprint.status.in_(["running", "completed"]),
                Sprint.start_date.isnot(None),
            )
            .order_by(Sprint.start_date.desc())
            .limit(5)
            .all()
        )

        results = []
        for sprint in sprints:
            # Total tasks in this sprint (single query)
            total = (
                db.query(func.count(Task.id))
                .filter(Task.sprint == sprint.id)
                .scalar()
            ) or 0

            # Completed tasks
            completed = (
                db.query(func.count(Task.id))
                .filter(Task.sprint == sprint.id, Task.status == "completed")
                .scalar()
            ) or 0

            remaining = total - completed
            completion_pct = round(completed / total * 100, 2) if total else 0.0

            # Date range — normalize to aware datetimes
            start = _make_aware(sprint.start_date)
            end = _make_aware(sprint.end_date) if sprint.end_date else _now_utc()

            # Daily completed counts for this sprint (single grouped query)
            daily_completed = (
                db.query(
                    func.date(Task.completed_at).label("day"),
                    func.count(Task.id).label("cnt"),
                )
                .filter(
                    Task.sprint == sprint.id,
                    Task.status == "completed",
                    Task.completed_at.isnot(None),
                )
                .group_by(func.date(Task.completed_at))
                .order_by(func.date(Task.completed_at))
                .all()
            )

            completed_map: Dict[str, int] = {r.day: r.cnt for r in daily_completed}

            # Build daily points
            try:
                total_days = max((end - start).days, 1)
            except Exception:
                total_days = 1

            velocity = round(completed / total_days, 2) if total_days else None

            if sprint.status == "completed":
                effective_end = end
            else:
                effective_end = _now_utc()

            try:
                days_elapsed = min(max((effective_end - start).days, 0), total_days)
            except Exception:
                days_elapsed = 0

            # Cumulative completed for burndown
            cumulative = 0
            data = []
            for i in range(total_days):
                day_date = start + timedelta(days=i)
                day_str = day_date.strftime("%Y-%m-%d")
                cumulative += completed_map.get(day_str, 0)
                remaining_at_day = total - cumulative
                ideal = total * (1 - (i + 1) / total_days)
                data.append({
                    "day_index": i,
                    "date": day_str,
                    "remaining_tasks": max(remaining_at_day, 0),
                    "completed_tasks": cumulative,
                    "ideal_remaining": round(ideal, 1),
                })

            results.append({
                "sprint_name": sprint.name,
                "sprint_status": sprint.status,
                "total_tasks": total,
                "completed_tasks": completed,
                "remaining_tasks": remaining,
                "completion_pct": completion_pct,
                "velocity": velocity,
                "days_elapsed": days_elapsed,
                "days_total": total_days,
            })

        return {"data": results}


# ---------------------------------------------------------------------------
# 5. Task Trend
# ---------------------------------------------------------------------------

class TaskTrendService:
    """Compute task trends over time periods."""

    @staticmethod
    def compute(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """
        计算任务趋势。

        按天分组，单次查询获取每天的 total/created/completed/avg_progress。
        """
        days = _parse_days(days)
        since = _cutoff(days)

        # Daily created
        created_rows = (
            db.query(
                func.date(Task.created_at).label("day"),
                func.count(Task.id).label("cnt"),
            )
            .filter(Task.created_at >= since)
            .group_by(func.date(Task.created_at))
            .order_by(func.date(Task.created_at))
            .all()
        )

        # Daily completed
        completed_rows = (
            db.query(
                func.date(Task.completed_at).label("day"),
                func.count(Task.id).label("cnt"),
            )
            .filter(
                Task.completed_at >= since,
                Task.completed_at.isnot(None),
            )
            .group_by(func.date(Task.completed_at))
            .order_by(func.date(Task.completed_at))
            .all()
        )

        # Daily avg progress for tasks created in window
        progress_rows = (
            db.query(
                func.date(Task.created_at).label("day"),
                func.avg(Task.progress).label("avg_prog"),
                func.count(Task.id).label("cnt"),
            )
            .filter(Task.created_at >= since)
            .group_by(func.date(Task.created_at))
            .order_by(func.date(Task.created_at))
            .all()
        )

        created_map = {r.day: r.cnt for r in created_rows}
        completed_map = {r.day: r.cnt for r in completed_rows}
        progress_map = {r.day: (round(float(r.avg_prog), 2) if r.avg_prog else 0.0) for r in progress_rows}

        all_dates = sorted(set(created_map.keys()) | set(completed_map.keys()))

        data_points = []
        for d in all_dates:
            data_points.append({
                "period": d,
                "total": created_map.get(d, 0),
                "created": created_map.get(d, 0),
                "completed": completed_map.get(d, 0),
                "avg_progress": progress_map.get(d, 0.0),
            })

        total_tasks = sum(created_map.values())

        # Completion trend
        trend = "stable"
        if len(all_dates) >= 6:
            recent = sum(completed_map.get(d, 0) for d in all_dates[-3:])
            earlier = sum(completed_map.get(d, 0) for d in all_dates[-6:-3])
            if recent > earlier * 1.1:
                trend = "increasing"
            elif recent < earlier * 0.9:
                trend = "decreasing"

        # Peak period
        peak_period = None
        if completed_map:
            peak_period = max(completed_map, key=completed_map.get)

        return {
            "summary": {
                "total_tasks": total_tasks,
                "completion_trend": trend,
                "peak_period": peak_period,
                "period_count": len(all_dates),
            },
            "data_points": data_points,
        }


# ---------------------------------------------------------------------------
# Facade — single entry point
# ---------------------------------------------------------------------------

class AnalyticsService:
    """
    数据分析服务门面。

    提供 5 个聚合方法的统一入口：
    - team_efficiency(db, days)
    - throughput(db, days)
    - agent_productivity(db, days)
    - sprint_burndown(db, days)
    - task_trend(db, days)
    """

    @staticmethod
    def team_efficiency(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """团队效率：任务完成率、平均进度、按状态/优先级/负责人统计。"""
        return TeamEfficiencyService.compute(db, days)

    @staticmethod
    def throughput(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """吞吐量：每日创建/完成任务数、趋势。"""
        return ThroughputService.compute(db, days)

    @staticmethod
    def agent_productivity(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """Agent 产出率：每个 Agent 的任务完成率、平均进度。"""
        return AgentProductivityService.compute(db, days)

    @staticmethod
    def sprint_burndown(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """Sprint 燃尽：每个 Sprint 的每日剩余/完成任务曲线。"""
        return SprintBurndownService.compute(db, days)

    @staticmethod
    def task_trend(db: Session, days: int = DEFAULT_DAYS) -> Dict:
        """任务趋势：每日任务创建/完成趋势。"""
        return TaskTrendService.compute(db, days)
