"""
健康检查 + Agent 健康度评分 API

系统健康:
  GET  /api/v2/system/health          — 系统健康检查
  GET  /api/v2/system/status          — 系统状态

Agent 健康度:
  GET  /api/v2/agents/health               — 所有 Agent 健康度
  GET  /api/v2/agents/health/summary       — 团队概览
  GET  /api/v2/agents/health/ranking       — 排名
  GET  /api/v2/agents/{id}/health          — 单个 Agent 健康度
  GET  /api/v2/agents/{id}/health/trend    — 趋势数据
  GET  /api/v2/agents/{id}/health/breakdown — 5 维详细分解

@author: 拉斐尔 (🐢 后端开发)
@updated: 2026-07-08
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db
from services.health_service import HealthService
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v2/system", tags=["v2-system"])

# Agent 健康度专用路由（/api/v2/agents/health 前缀）
health_router = APIRouter(prefix="/api/v2/agents", tags=["v2-agents-health"])


def get_health_service(db=Depends(get_db)) -> HealthService:
    return HealthService(db)


# ──────────────────────────────────────────────
# 系统健康检查（原有）
# ──────────────────────────────────────────────

@router.get("/health")
def health_check():
    return {"status": "ok", "port": 3020}


@router.get("/health/root")
def health_root():
    return {"status": "ok", "port": 3020}


@router.get("/status")
def system_status():
    return {
        "version": "3.0",
        "database": os.getenv("DATABASE_URL", "not configured")[:30] + "...",
        "timestamp": datetime.now().isoformat(),
    }


# ──────────────────────────────────────────────
# Agent 健康度评分 API（新增）
# ──────────────────────────────────────────────

@health_router.get("/health")
def get_all_agents_health(
    service: HealthService = Depends(get_health_service),
    _user: dict = Depends(get_current_user),
):
    """获取所有 Agent 的健康度评分。"""
    results = service.get_all_health()
    return {"agents": results, "total": len(results)}


@health_router.get("/health/summary")
def get_health_summary(
    service: HealthService = Depends(get_health_service),
    _user: dict = Depends(get_current_user),
):
    """团队健康度概览 (平均/最高/最低/分布)。"""
    return service.get_health_summary()


@health_router.get("/health/ranking")
def get_health_ranking(
    service: HealthService = Depends(get_health_service),
    _user: dict = Depends(get_current_user),
):
    """Agent 健康度排名。"""
    ranking = service.get_health_ranking()
    return {"ranking": ranking, "total": len(ranking)}


@health_router.get("/{agent_id}/health")
def get_agent_health(
    agent_id: str,
    service: HealthService = Depends(get_health_service),
    _user: dict = Depends(get_current_user),
):
    """获取单个 Agent 的健康度评分。"""
    health = service.calculate_health(agent_id)
    if health["score"] == 0 and health["components"]["online_status"] == 0:
        # Agent 不存在或完全离线
        return health
    return health


@health_router.get("/{agent_id}/health/trend")
def get_agent_health_trend(
    agent_id: str,
    hours: int = Query(24, ge=1, le=168, description="趋势时间范围（小时）"),
    service: HealthService = Depends(get_health_service),
    _user: dict = Depends(get_current_user),
):
    """获取 Agent 健康度趋势数据。"""
    return service.get_health_trend(agent_id, hours=hours)


@health_router.get("/{agent_id}/health/breakdown")
def get_agent_health_breakdown(
    agent_id: str,
    service: HealthService = Depends(get_health_service),
    _user: dict = Depends(get_current_user),
):
    """获取 Agent 5 维详细评分分解。"""
    return service.get_component_breakdown(agent_id)
