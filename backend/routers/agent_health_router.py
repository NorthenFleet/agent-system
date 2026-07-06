"""
Agent 健康度 API 路由

GET    /api/v2/agents/health                 — 所有 Agent 健康度
GET    /api/v2/agents/{agent_id}/health      — 单个 Agent 健康度
GET    /api/v2/agents/{agent_id}/health/trend — 健康度历史趋势（?hours=24）

注意：system health 不在本路由中。

@author 🟥 拉斐尔
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session

from models.v2_models import get_session
from services.health_service import HealthService
from routers.auth_router import get_current_user

router = APIRouter(
    prefix="/api/v2/agents",
    tags=["v2-agent-health"],
    responses={
        401: {"description": "未登录或 Token 无效"},
        403: {"description": "权限不足"},
    },
)


def get_health_service(db: Session = Depends(get_session)) -> HealthService:
    return HealthService(db)


@router.get("/health")
def get_all_agent_health(
    current_user: dict = Depends(get_current_user),
    service: HealthService = Depends(get_health_service),
):
    """获取所有 Agent 的健康度。"""
    results = service.get_all_health()
    return {"agents": results, "count": len(results)}


@router.get("/{agent_id}/health")
def get_agent_health(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    service: HealthService = Depends(get_health_service),
):
    """获取单个 Agent 的健康度。"""
    health = service.get_health(agent_id)
    if not health:
        raise HTTPException(404, f"Agent {agent_id} 不存在")
    return health


@router.get("/{agent_id}/health/trend")
def get_agent_health_trend(
    agent_id: str,
    hours: int = Query(24, description="回溯小时数", ge=1, le=720),
    current_user: dict = Depends(get_current_user),
    service: HealthService = Depends(get_health_service),
):
    """获取 Agent 健康度历史趋势。"""
    trend = service.get_health_trend(agent_id, hours=hours)
    return {
        "agent_id": agent_id,
        "hours": hours,
        "data_points": trend,
        "count": len(trend),
    }
