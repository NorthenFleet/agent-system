"""
Q-Learning 智能任务路由 API

POST   /api/v2/tasks/recommend      — 获取 Agent 推荐
GET    /api/v2/tasks/q-table        — 查看 Q-Table
PUT    /api/v2/tasks/q-table        — 手动更新 Q-Table（管理员）
POST   /api/v2/tasks/{task_id}/complete — 任务完成回调

@author 🟥 拉斐尔
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

from services.q_learning_service import QLearningService
from routers.auth_router import get_current_user, require_role

router = APIRouter(
    prefix="/api/v2/tasks",
    tags=["v2-task-recommend"],
    responses={
        401: {"description": "未登录或 Token 无效"},
        403: {"description": "权限不足"},
    },
)

# ─── Service 初始化（模块级单例） ───
q_learning_service = QLearningService()


def get_q_service() -> QLearningService:
    return q_learning_service


# ─── Pydantic Models ───


class RecommendRequest(BaseModel):
    task_type: str = Field(..., description="任务类型，如 backend_task、frontend_task")
    priority: str = Field("medium", description="优先级: high|medium|low")
    tags: List[str] = Field([], description="标签列表")
    top_k: int = Field(3, description="返回推荐数量")


class CompleteTaskRequest(BaseModel):
    agent_id: str = Field(..., description="执行任务的 Agent ID")
    outcome: str = Field(..., description="结果: success|fail|timeout")


class QTableUpdateRequest(BaseModel):
    q_table: Dict[str, Dict[str, float]] = Field(..., description="完整的 Q-Table 数据")


# ─── Endpoints ───


@router.post("/recommend")
def recommend_agents(
    req: RecommendRequest,
    current_user: dict = Depends(get_current_user),
    service: QLearningService = Depends(get_q_service),
):
    """根据任务特征返回推荐 Agent 列表。"""
    recommendations = service.get_recommendation(
        task_type=req.task_type,
        priority=req.priority,
        tags=req.tags,
        top_k=req.top_k,
    )
    return {
        "task_type": req.task_type,
        "priority": req.priority,
        "tags": req.tags,
        "recommendations": recommendations,
    }


@router.get("/q-table")
def get_q_table(
    current_user: dict = Depends(get_current_user),
    service: QLearningService = Depends(get_q_service),
):
    """查看当前 Q-Table。"""
    return {"q_table": service.get_q_table()}


@router.put("/q-table")
def update_q_table(
    req: QTableUpdateRequest,
    current_user: dict = Depends(require_role("admin")),
    service: QLearningService = Depends(get_q_service),
):
    """手动更新 Q-Table（需要 admin 权限）。"""
    service.set_initial_q_table(req.q_table)
    return {"message": "Q-Table 更新成功", "q_table": service.get_q_table()}


@router.post("/{task_id}/complete")
def complete_task(
    task_id: str,
    req: CompleteTaskRequest,
    current_user: dict = Depends(get_current_user),
    service: QLearningService = Depends(get_q_service),
):
    """任务完成回调，自动更新 Q-Table。"""
    result = service.update_after_completion(
        task_id=task_id,
        agent_id=req.agent_id,
        outcome=req.outcome,
    )
    return {"message": "Q-Table 已更新", "result": result}
