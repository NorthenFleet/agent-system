"""
Analytics Router — 数据分析 API 端点 (S5 P5)

5 个 API 端点：
- GET /api/v2/analytics/team-efficiency
- GET /api/v2/analytics/throughput
- GET /api/v2/analytics/agent-productivity
- GET /api/v2/analytics/sprint-burndown
- GET /api/v2/analytics/task-trend

所有端点支持 days 查询参数 (7/14/30/90)，默认 14 天。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/api/v2/analytics",
    tags=["v2-analytics"],
    responses={
        400: {"description": "参数无效"},
        500: {"description": "服务器内部错误"},
    },
)


def _valid_days(days: Optional[int]) -> int:
    """Return the validated days value or None to let service use its default."""
    if days is None:
        return 14
    if days in {7, 14, 30, 90}:
        return days
    return 14


# ---------------------------------------------------------------------------
# 1. Team Efficiency
# ---------------------------------------------------------------------------

@router.get(
    "/team-efficiency",
    summary="团队效率指标",
    description="获取团队在指定时间范围内的效率指标，包括完成率、平均进度、按状态/优先级/负责人统计。",
)
def get_team_efficiency(
    days: Optional[int] = Query(14, ge=1, le=90, description="时间范围天数 (7/14/30/90)"),
    db: Session = Depends(get_db),
):
    """团队效率聚合端点。"""
    result = AnalyticsService.team_efficiency(db, days=days)
    return {"status": "success", "days": days, "metrics": result}


# ---------------------------------------------------------------------------
# 2. Throughput
# ---------------------------------------------------------------------------

@router.get(
    "/throughput",
    summary="任务吞吐量",
    description="获取每日任务创建/完成吞吐量数据及趋势。",
)
def get_throughput(
    days: Optional[int] = Query(14, ge=1, le=90, description="时间范围天数 (7/14/30/90)"),
    db: Session = Depends(get_db),
):
    """吞吐量聚合端点。"""
    result = AnalyticsService.throughput(db, days=days)
    return {"status": "success", "days": days, **result}


# ---------------------------------------------------------------------------
# 3. Agent Productivity
# ---------------------------------------------------------------------------

@router.get(
    "/agent-productivity",
    summary="Agent 产出率",
    description="获取每个 Agent 在指定时间范围内的任务完成率、平均进度等指标。",
)
def get_agent_productivity(
    days: Optional[int] = Query(14, ge=1, le=90, description="时间范围天数 (7/14/30/90)"),
    db: Session = Depends(get_db),
):
    """Agent 产出率聚合端点。"""
    result = AnalyticsService.agent_productivity(db, days=days)
    return {"status": "success", "days": days, **result}


# ---------------------------------------------------------------------------
# 4. Sprint Burndown
# ---------------------------------------------------------------------------

@router.get(
    "/sprint-burndown",
    summary="Sprint 燃尽图",
    description="获取 Sprint 燃尽数据，包括每日剩余/完成任务数和理想燃尽曲线。",
)
def get_sprint_burndown(
    days: Optional[int] = Query(14, ge=1, le=90, description="时间范围天数 (7/14/30/90)"),
    db: Session = Depends(get_db),
):
    """Sprint 燃尽聚合端点。"""
    result = AnalyticsService.sprint_burndown(db, days=days)
    return {"status": "success", **result}


# ---------------------------------------------------------------------------
# 5. Task Trend
# ---------------------------------------------------------------------------

@router.get(
    "/task-trend",
    summary="任务趋势",
    description="获取任务创建/完成的趋势数据。",
)
def get_task_trend(
    days: Optional[int] = Query(14, ge=1, le=90, description="时间范围天数 (7/14/30/90)"),
    db: Session = Depends(get_db),
):
    """任务趋势聚合端点。"""
    result = AnalyticsService.task_trend(db, days=days)
    return {"status": "success", "days": days, **result}
