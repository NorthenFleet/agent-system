"""
V2 Agent 实时监控 API 路由 (Service 层重构版)

所有端点通过 Service 调用，路由层仅负责请求解析和响应构造。
API 路径和请求/响应格式保持不变（前端兼容）。
集成 Redis 缓存（Sprint 5 P4）。

POST /api/v2/agents/{id}/heartbeat   — Agent 心跳上报
POST /api/v2/agents/{id}/dispatch    — Agent 任务派发（需 Admin）
GET  /api/v2/agents/live             — 所有 Agent 最新状态
GET  /api/v2/agents/{id}/history     — Agent 状态变更历史
GET  /api/v2/agents/{id}/tasks       — Agent 关联任务列表

@author 🟥 拉斐尔 (后端开发)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from database import get_db
from services.agent_service import AgentService
from services.task_service import TaskService
from services.cache_service import cache_service
from routers.auth_router import get_current_user, require_role
from websocket_manager import manager as ws_manager

router = APIRouter(prefix="/api/v2/agents", tags=["v2-agents"])

HEARTBEAT_TIMEOUT = 60
HEARTBEAT_OFFLINE = 300


class HeartbeatRequest(BaseModel):
    agent_id: str
    agent_name: str
    status: str
    team: Optional[str] = None
    current_task: Optional[str] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    task_queue_len: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


def get_agent_service(db: Session = Depends(get_db)) -> AgentService:
    return AgentService(db)


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)


@router.post("/{agent_id}/heartbeat")
async def submit_heartbeat(
    agent_id: str,
    req: HeartbeatRequest,
    _user: dict = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
):
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

    # 心跳上报成功后，WS 推送心跳变更给所有连接的客户端
    pushed = await ws_manager.push_heartbeat_change({
        "agent_id": req.agent_id,
        "agent_name": req.agent_name,
        "status": req.status,
        "current_task": req.current_task,
        "cpu_usage": req.cpu_usage,
        "memory_usage": req.memory_usage,
        "task_queue_len": req.task_queue_len or 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 心跳更新后失效 agent 缓存
    cache_service.invalidate_pattern("v2:agents:*")

    return {
        "success": True,
        "message": f"Agent {agent_id} 心跳已记录",
        "ws_pushed": pushed > 0,
        "ws_clients_notified": pushed,
    }


@router.get("/live")
def get_live_agents(
    _user: dict = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
):
    cache_key = "v2:agents:live"
    cached = cache_service.get(cache_key)
    if cached is not None:
        return cached

    recent_hbs = svc.get_recent_heartbeats(minutes=HEARTBEAT_OFFLINE // 60 + 10)

    latest_map: Dict[str, Any] = {}
    for hb in recent_hbs:
        if hb["agent_id"] not in latest_map:
            latest_map[hb["agent_id"]] = hb

    now = datetime.now(timezone.utc)
    agents = []
    for aid, hb in latest_map.items():
        hb_time = datetime.fromisoformat(hb["heartbeat_at"])
        if hb_time.tzinfo is None:
            hb_time = hb_time.replace(tzinfo=timezone.utc)
        seconds_ago = (now - hb_time).total_seconds()

        display_status = hb["status"]
        if seconds_ago > HEARTBEAT_OFFLINE:
            display_status = "offline"
        elif seconds_ago > HEARTBEAT_TIMEOUT:
            display_status = "timeout"

        agents.append({
            "agent_id": hb["agent_id"],
            "agent_name": hb["agent_name"],
            "status": display_status,
            "raw_status": hb["status"],
            "current_task": hb["current_task"],
            "cpu_usage": hb["cpu_usage"],
            "memory_usage": hb["memory_usage"],
            "task_queue_len": hb["task_queue_len"],
            "last_heartbeat": hb["heartbeat_at"],
            "seconds_ago": round(seconds_ago, 1),
            "metadata": hb.get("metadata") or {},
        })

    result = {"agents": agents, "total": len(agents)}
    cache_service.set(cache_key, result, ttl=30)
    return result


@router.get("/{agent_id}/history")
def get_agent_history(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    _user: dict = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
):
    status_history = svc.get_status_history(agent_id, limit=limit)

    recent_hbs = svc.get_recent_heartbeats(minutes=60, limit=limit)
    heartbeats_list = [hb for hb in recent_hbs if hb["agent_id"] == agent_id]

    return {
        "agent_id": agent_id,
        "status_history": status_history,
        "heartbeats": heartbeats_list,
        "total_history": len(status_history),
        "total_heartbeats": len(heartbeats_list),
    }


@router.get("/{agent_id}/tasks")
def get_agent_tasks(
    agent_id: str,
    status: Optional[str] = Query(None, description="按状态筛选"),
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service),
):
    tasks = svc.get_by_assignee(agent_id)
    if status:
        tasks = [t for t in tasks if t.status == status]

    return {
        "agent_id": agent_id,
        "tasks": [t.to_dict() for t in tasks],
        "total": len(tasks),
    }


class DispatchRequest(BaseModel):
    task_id: str = Field(..., min_length=1, description="要派发的任务 ID")
    notes: Optional[str] = Field(None, description="派发备注")


@router.post("/{agent_id}/dispatch")
def dispatch_task(
    agent_id: str,
    req: DispatchRequest,
    _user: dict = Depends(require_role("admin")),
    svc: AgentService = Depends(get_agent_service),
):
    """派发任务到指定 Agent（仅 Admin 可操作）"""
    dispatcher_id = _user.get("username") or _user.get("user_id")
    return svc.dispatch_task(
        agent_id=agent_id,
        task_id=req.task_id,
        dispatcher_id=dispatcher_id,
        notes=req.notes,
    )
