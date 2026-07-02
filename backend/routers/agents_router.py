"""
V2 Agent 实时监控 API 路由 (Service 层重构版)

所有端点通过 AgentService 调用，路由层仅负责请求解析和响应构造。
API 路径和请求/响应格式保持不变（前端兼容）。

POST /api/v2/agents/{id}/heartbeat   — Agent 心跳上报
GET  /api/v2/agents/live             — 所有 Agent 最新状态
GET  /api/v2/agents/{id}/history     — Agent 状态变更历史
GET  /api/v2/agents/{id}/tasks       — Agent 关联任务列表

@author 🟥 拉斐尔 (后端开发)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from models.v2_models import get_session, AgentHeartbeat, AgentStatusHistory, Task
from services.agent_service import AgentService
from services.task_service import TaskService
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/agents", tags=["v2-agents"])

# 离线判定阈值（秒）
HEARTBEAT_TIMEOUT = 60      # 超过 60s 无心跳 → timeout
HEARTBEAT_OFFLINE = 300     # 超过 5 分钟无心跳 → offline


class HeartbeatRequest(BaseModel):
    agent_id: str
    agent_name: str
    status: str  # online | busy | idle | offline
    team: Optional[str] = None
    current_task: Optional[str] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    task_queue_len: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


def get_agent_service(db: Session = Depends(get_session)) -> AgentService:
    """依赖注入：获取 AgentService 实例"""
    return AgentService(db)


def get_task_service(db: Session = Depends(get_session)) -> TaskService:
    """依赖注入：获取 TaskService 实例"""
    return TaskService(db)


@router.post("/{agent_id}/heartbeat")
def submit_heartbeat(
    agent_id: str,
    req: HeartbeatRequest,
    _user: dict = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
):
    """Agent 心跳上报"""
    if req.agent_id != agent_id:
        raise HTTPException(400, "路径 agent_id 与请求体不一致")

    svc.record_heartbeat({
        "agent_id": req.agent_id,
        "agent_name": req.agent_name,
        "status": req.status,
        "current_task": req.current_task,
        "cpu_usage": req.cpu_usage,
        "memory_usage": req.memory_usage,
        "task_queue_len": req.task_queue_len or 0,
        "metadata": req.metadata or {},
    })
    return {
        "success": True,
        "message": f"Agent {agent_id} 心跳已记录",
    }


@router.get("/live")
def get_live_agents(
    _user: dict = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
    db: Session = Depends(get_session),
):
    """获取所有 Agent 最新状态（含在线状态自动判定）"""
    try:
        heartbeats = db.query(AgentHeartbeat).order_by(
            AgentHeartbeat.heartbeat_at.desc()
        ).all()

        latest_map: Dict[str, AgentHeartbeat] = {}
        for hb in heartbeats:
            if hb.agent_id not in latest_map:
                latest_map[hb.agent_id] = hb

        now = datetime.now(timezone.utc)
        agents = []
        for aid, hb in latest_map.items():
            hb_time = hb.heartbeat_at
            if hb_time.tzinfo is None:
                hb_time = hb_time.replace(tzinfo=timezone.utc)
            seconds_ago = (now - hb_time).total_seconds()

            display_status = hb.status
            if seconds_ago > HEARTBEAT_OFFLINE:
                display_status = "offline"
            elif seconds_ago > HEARTBEAT_TIMEOUT:
                display_status = "timeout"

            agents.append({
                "agent_id": hb.agent_id,
                "agent_name": hb.agent_name,
                "status": display_status,
                "raw_status": hb.status,
                "current_task": hb.current_task,
                "cpu_usage": hb.cpu_usage,
                "memory_usage": hb.memory_usage,
                "task_queue_len": hb.task_queue_len,
                "last_heartbeat": hb.heartbeat_at.isoformat(),
                "seconds_ago": round(seconds_ago, 1),
                "metadata": hb.extra_data or {},
            })

        return {"agents": agents, "total": len(agents)}
    finally:
        db.close()


@router.get("/{agent_id}/history")
def get_agent_history(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    _user: dict = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
    db: Session = Depends(get_session),
):
    """获取 Agent 状态变更历史"""
    try:
        history = svc.get_status_history(agent_id, limit=limit)
        heartbeats = svc.get_latest_heartbeat(agent_id)
        # Also get heartbeat list
        from repositories.agent_heartbeat_repository import AgentHeartbeatRepository
        hb_repo = AgentHeartbeatRepository()
        heartbeats_list = hb_repo.get_latest_by_agent(db, agent_id, limit=limit)

        return {
            "agent_id": agent_id,
            "status_history": [h.to_dict() for h in history],
            "heartbeats": [h.to_dict() for h in heartbeats_list],
            "total_history": len(history),
            "total_heartbeats": len(heartbeats_list),
        }
    finally:
        db.close()


@router.get("/{agent_id}/tasks")
def get_agent_tasks(
    agent_id: str,
    status: Optional[str] = Query(None, description="按状态筛选"),
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service),
    db: Session = Depends(get_session),
):
    """获取 Agent 关联的任务列表（分配给该 Agent 的任务）"""
    try:
        if status:
            tasks = svc.get_by_assignee(agent_id)
            tasks = [t for t in tasks if t.status == status]
        else:
            tasks = svc.get_by_assignee(agent_id)

        return {
            "agent_id": agent_id,
            "tasks": [t.to_dict() for t in tasks],
            "total": len(tasks),
        }
    finally:
        db.close()
