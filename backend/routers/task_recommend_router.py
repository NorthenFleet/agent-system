"""
Q-Learning 智能任务路由 — API 端点

POST /api/v2/tasks/recommend         — 推荐 Agent (带分数)
GET  /api/v2/tasks/q-table           — 查看 Q-Table (Admin)
PUT  /api/v2/tasks/q-table           — 更新参数 (Admin)

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-08
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db
from routers.auth_router import get_current_user
from services.q_learning_service import QLearningService

router = APIRouter(prefix="/api/v2/tasks", tags=["v2-tasks"])


def get_q_service(db=Depends(get_db)) -> QLearningService:
    return QLearningService(db)


# ──────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────

class RecommendRequest(BaseModel):
    type: Optional[str] = "general"
    priority: Optional[str] = "medium"
    tags: Optional[list] = None
    top_n: Optional[int] = 3
    use_exploration: Optional[bool] = True


class UpdateParamsRequest(BaseModel):
    learning_rate: Optional[float] = None
    discount_factor: Optional[float] = None
    epsilon: Optional[float] = None


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/recommend")
def recommend_agents(
    req: RecommendRequest,
    service: QLearningService = Depends(get_q_service),
):
    """
    输入任务信息，返回推荐 Agent 列表（带 Q-value 分数）。

    使用 Q-Learning + Thompson Sampling 进行智能任务路由。
    """
    task = {
        "type": req.type or "general",
        "priority": req.priority or "medium",
        "tags": req.tags or [],
    }
    top_n = min(req.top_n or 3, 10)

    recommendations = service.recommend_agents(
        task, top_n=top_n, use_exploration=req.use_exploration or True
    )

    return {
        "task": task,
        "recommendations": recommendations,
        "count": len(recommendations),
    }


@router.get("/q-table")
def get_q_table(
    _user: dict = Depends(get_current_user),
    service: QLearningService = Depends(get_q_service),
):
    """查看当前 Q-Table (Admin)。"""
    return service.get_q_table()


@router.put("/q-table")
def update_q_table_params(
    req: UpdateParamsRequest,
    _user: dict = Depends(get_current_user),
    service: QLearningService = Depends(get_q_service),
):
    """
    手动更新 Q-Table 超参数 (Admin)。

    可调整 learning_rate, discount_factor, epsilon。
    """
    # 参数验证
    if req.learning_rate is not None and not (0 <= req.learning_rate <= 1):
        raise HTTPException(400, "learning_rate 必须在 [0, 1] 范围内")
    if req.discount_factor is not None and not (0 <= req.discount_factor <= 1):
        raise HTTPException(400, "discount_factor 必须在 [0, 1] 范围内")
    if req.epsilon is not None and not (0 <= req.epsilon <= 1):
        raise HTTPException(400, "epsilon 必须在 [0, 1] 范围内")

    meta = service.update_parameters(
        learning_rate=req.learning_rate,
        discount_factor=req.discount_factor,
        epsilon=req.epsilon,
    )
    return {"meta": meta}
