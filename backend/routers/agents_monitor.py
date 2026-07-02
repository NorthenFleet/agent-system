"""
V2 Agent 监控 API 路由
POST /api/v2/agents/{agent_id}/heartbeat
GET  /api/v2/agents/live
GET  /api/v2/agents/{agent_id}/history
GET  /api/v2/agents/{agent_id}/tasks
"""
from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any, Set
from datetime import datetime, timezone, timedelta
import json
import asyncio
import os
import subprocess

from models.v2_models import get_session, AgentHeartbeat, AgentStatusHistory, Task
from routers.auth_router import get_current_user

router = APIRouter(prefix="/api/v2/agents", tags=["v2-agents"])

# ---------- 内存 WebSocket 管理器 ----------
class WSManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self._heartbeat_last: Dict[str, float] = {}
        self.rate_limit_sec = 30.0

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.connections.discard(ws)

    async def broadcast_ratelimited(self, msg_type: str, data: dict):
        import time
        now = time.time()
        last = self._heartbeat_last.get(msg_type, 0)
        if now - last < self.rate_limit_sec:
            return
        self._heartbeat_last[msg_type] = now
        await self.broadcast({"type": msg_type, **data})

ws_manager = WSManager()

# ---------- Agent emoji 映射 ----------
AGENT_EMOJI = {
    "optimus": "🤖", "bumblebee": "🐝", "leonardo": "🟦", "raphael": "🟥",
    "donatello": "🟪", "michelangelo": "🟧", "ironhide": "🛡️", "perceptor": "🚗",
    "wheeljack": "🔧", "shockwave": "🟣", "ultra-magnus": "🔵", "ratchet": "🚑",
}

AGENT_NAMES = {
    "optimus": "擎天柱", "bumblebee": "大黄蜂", "leonardo": "李奥纳多", "raphael": "拉斐尔",
    "donatello": "多纳泰罗", "michelangelo": "米开朗基罗", "ironhide": "铁皮", "perceptor": "感知器",
    "wheeljack": "千斤顶", "shockwave": "震荡波", "ultra-magnus": "通天晓", "ratchet": "救护车",
}

# ---------- Schemas ----------
class HeartbeatRequest(BaseModel):
    status: str
    current_task: Optional[str] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    task_queue_len: Optional[int] = 0
    metadata: Optional[Dict[str, Any]] = None


@router.post("/{agent_id}/heartbeat")
def heartbeat(
    agent_id: str,
    data: HeartbeatRequest,
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        now = datetime.now(timezone.utc)
        name = AGENT_NAMES.get(agent_id, agent_id)

        # 查上一个状态
        last = db.query(AgentHeartbeat).filter(
            AgentHeartbeat.agent_id == agent_id
        ).order_by(AgentHeartbeat.heartbeat_at.desc()).first()

        prev_status = last.status if last else None

        # 记录心跳
        hb = AgentHeartbeat(
            agent_id=agent_id,
            agent_name=name,
            status=data.status,
            current_task=data.current_task,
            cpu_usage=data.cpu_usage,
            memory_usage=data.memory_usage,
            task_queue_len=data.task_queue_len or 0,
            metadata=data.metadata or {},
            heartbeat_at=now,
        )
        db.add(hb)

        # 如果状态变了，记录状态历史
        if prev_status and prev_status != data.status:
            history = AgentStatusHistory(
                agent_id=agent_id,
                from_status=prev_status,
                to_status=data.status,
                current_task=data.current_task,
                triggered_by=user.get("username"),
                changed_at=now,
            )
            db.add(history)

        db.commit()

        # WebSocket 推送
        asyncio.create_task(ws_manager.broadcast_ratelimited("heartbeat_update", {
            "data": {
                "agent_id": agent_id,
                "agent_name": name,
                "status": data.status,
                "cpu_usage": data.cpu_usage,
                "memory_usage": data.memory_usage,
                "heartbeat_at": now.isoformat(),
            }
        }))

        return {
            "agent_id": agent_id,
            "status": data.status,
            "next_heartbeat_in": 30,
            "message": "心跳已记录",
        }
    finally:
        db.close()


@router.get("/live")
def agents_live(user: dict = Depends(get_current_user)):
    """实时 Agent 状态 — 从 OpenClaw CLI + 心跳数据合并"""
    db = get_session()
    try:
        agents_list = []
        now = datetime.now(timezone.utc)

        # 1. 从 agents.json 读取基本信息
        agents_json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "agents.json")
        base_agents = []
        if os.path.exists(agents_json_path):
            with open(agents_json_path, 'r', encoding='utf-8') as f:
                base_agents = json.load(f)

        for agent in base_agents:
            aid = agent.get("id", "")
            name = agent.get("name", aid)

            # 取最新心跳
            last_hb = db.query(AgentHeartbeat).filter(
                AgentHeartbeat.agent_id == aid
            ).order_by(AgentHeartbeat.heartbeat_at.desc()).first()

            hb_age = None
            health = "offline"
            if last_hb:
                hb_age = (now - last_hb.heartbeat_at).total_seconds()
                if hb_age <= 60:
                    health = "healthy"
                elif hb_age <= 300:
                    health = "warning"
                else:
                    health = "offline"

            agents_list.append({
                "agent_id": aid,
                "agent_name": name,
                "emoji": AGENT_EMOJI.get(aid, "👤"),
                "role": agent.get("role", ""),
                "team": agent.get("team", ""),
                "status": last_hb.status if last_hb else agent.get("status", "idle"),
                "current_task": last_hb.current_task if last_hb else agent.get("current_task", ""),
                "last_heartbeat": last_hb.heartbeat_at.isoformat() if last_hb else None,
                "heartbeat_age_seconds": round(hb_age, 1) if hb_age is not None else None,
                "health": health,
                "cpu_usage": last_hb.cpu_usage if last_hb else None,
                "memory_usage": last_hb.memory_usage if last_hb else None,
            })

        online = sum(1 for a in agents_list if a["health"] in ("healthy", "warning"))
        busy = sum(1 for a in agents_list if a["status"] == "busy")
        idle = sum(1 for a in agents_list if a["status"] == "idle")
        offline_count = sum(1 for a in agents_list if a["health"] == "offline")

        return {
            "agents": agents_list,
            "total": len(agents_list),
            "online": online,
            "busy": busy,
            "idle": idle,
            "offline": offline_count,
        }
    finally:
        db.close()


@router.get("/{agent_id}/history")
def agent_history(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    hours: int = Query(24, ge=1, le=720),
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        records = db.query(AgentStatusHistory).filter(
            AgentStatusHistory.agent_id == agent_id,
            AgentStatusHistory.changed_at >= cutoff,
        ).order_by(AgentStatusHistory.changed_at.desc()).limit(limit).all()

        return {
            "agent_id": agent_id,
            "history": [r.to_dict() for r in records],
            "total": len(records),
        }
    finally:
        db.close()


@router.get("/{agent_id}/tasks")
def agent_tasks(
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        tasks = db.query(Task).filter(Task.assignee == agent_id).order_by(Task.created_at.desc()).all()
        return {
            "agent_id": agent_id,
            "tasks": [t.to_dict() for t in tasks],
            "total": len(tasks),
        }
    finally:
        db.close()


# ---------- WebSocket ----------
@router.websocket("/ws")
async def agents_websocket(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # 保持连接，接收客户端心跳
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
