"""
任务完成 Webhook 回调 — 自动更新 Q-Learning 奖励值

当任务完成/超时/失败时，自动调用 Q-Learning 更新 Q-Table：
  success → +1
  fail    → -1
  timeout → -0.5

新增端点:
  POST /api/v2/tasks/{id}/complete   — 标记任务完成并更新 Q-Table
  POST /api/v2/tasks/{id}/fail       — 标记任务失败并更新 Q-Table
  POST /api/v2/tasks/{id}/timeout    — 标记任务超时并更新 Q-Table

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-08
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.q_learning_service import QLearningService
from services.task_service import TaskService
from models.v2_models import Task
from routers.auth_router import get_current_user

router = APIRouter(prefix="/api/v2/tasks", tags=["v2-tasks-webhook"])


def get_q_service(db=Depends(get_db)) -> QLearningService:
    return QLearningService(db)


def get_task_service(db=Depends(get_db)) -> TaskService:
    return TaskService(db)


# ──────────────────────────────────────────────
# Request Schema
# ──────────────────────────────────────────────

class TaskOutcomeRequest(BaseModel):
    agent_id: Optional[str] = None
    notes: Optional[str] = None


# ──────────────────────────────────────────────
# Internal helper
# ──────────────────────────────────────────────

def _lookup_task_and_agent(
    task_id: str,
    req: TaskOutcomeRequest,
    db: Session,
) -> tuple:
    """查找任务及其关联 Agent。"""
    task = db.query(Task).filter(
        Task.task_id == task_id
    ).first()
    if task is None:
        raise HTTPException(404, f"任务 {task_id} 不存在")

    agent_id = req.agent_id or task.assignee
    if not agent_id:
        raise HTTPException(
            400,
            "无法确定关联 Agent：请求中未提供 agent_id，任务也未分配 assignee",
        )

    return task, agent_id


# ──────────────────────────────────────────────
# Webhook 端点
# ──────────────────────────────────────────────

@router.post("/{task_id}/complete")
def task_complete_webhook(
    task_id: str,
    req: TaskOutcomeRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """
    标记任务完成，自动更新 Q-Table (reward=+1)。

    1. 更新任务状态为 completed
    2. 调用 Q-Learning 更新奖励值
    3. 返回更新后的统计
    """
    task, agent_id = _lookup_task_and_agent(task_id, req, db)

    # 更新任务状态
    task_svc = TaskService(db)
    task_svc.update_task_status(task_id, "completed")

    # 更新 Q-Table
    q_service = QLearningService(db)
    q_result = q_service.update_q_table(
        task_id=task_id,
        agent_id=agent_id,
        outcome="success",
        task_info={
            "type": task.type or "general",
            "priority": task.priority or "medium",
            "tags": task.tags or [],
        },
    )

    # 触发自动化规则引擎 — task_completed
    try:
        from services.automation_engine import on_task_completed
        on_task_completed(task)
    except Exception:
        pass  # 规则引擎异常不影响主流程

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "outcome": "success",
        "reward": q_result["reward"],
        "new_q": q_result["new_q"],
        "agent_stats": q_result["agent_stats"],
    }


@router.post("/{task_id}/fail")
def task_fail_webhook(
    task_id: str,
    req: TaskOutcomeRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """
    标记任务失败，自动更新 Q-Table (reward=-1)。
    """
    task, agent_id = _lookup_task_and_agent(task_id, req, db)

    # 更新任务状态
    task_svc = TaskService(db)
    task_svc.update_task_status(task_id, "failed")

    # 更新 Q-Table
    q_service = QLearningService(db)
    q_result = q_service.update_q_table(
        task_id=task_id,
        agent_id=agent_id,
        outcome="fail",
        task_info={
            "type": task.type or "general",
            "priority": task.priority or "medium",
            "tags": task.tags or [],
        },
    )

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "outcome": "fail",
        "reward": q_result["reward"],
        "new_q": q_result["new_q"],
        "agent_stats": q_result["agent_stats"],
    }


@router.post("/{task_id}/timeout")
def task_timeout_webhook(
    task_id: str,
    req: TaskOutcomeRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """
    标记任务超时，自动更新 Q-Table (reward=-0.5)。
    """
    task, agent_id = _lookup_task_and_agent(task_id, req, db)

    # 更新任务状态
    task_svc = TaskService(db)
    task_svc.update_task_status(task_id, "timeout")

    # 更新 Q-Table
    q_service = QLearningService(db)
    q_result = q_service.update_q_table(
        task_id=task_id,
        agent_id=agent_id,
        outcome="timeout",
        task_info={
            "type": task.type or "general",
            "priority": task.priority or "medium",
            "tags": task.tags or [],
        },
    )

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "outcome": "timeout",
        "reward": q_result["reward"],
        "new_q": q_result["new_q"],
        "agent_stats": q_result["agent_stats"],
    }
