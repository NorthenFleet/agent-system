"""
监控数据聚合 API

聚合 agent_heartbeats 表和 tasks 表，提供实时状态与统计数据。
所有端点受 JWT 认证保护。

GET  /api/v2/monitoring/agents  — 所有 Agent 实时状态（从心跳表聚合）
GET  /api/v2/monitoring/stats   — 任务统计 + 系统指标

@author 🟥 拉斐尔 (后端开发)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from models.v2_models import AgentHeartbeat, Agent, Task, AgentDispatch, get_session
from routers.auth_router import get_current_user

router = APIRouter(prefix="/api/v2/monitoring", tags=["v2-monitoring"])

# Agent 在线判定阈值（秒）
HEARTBEAT_TIMEOUT = 60       # 超过 60s 标记为 timeout
HEARTBEAT_OFFLINE = 300      # 超过 300s 标记为 offline


def _compute_display_status(heartbeat_at: str) -> str:
    """根据心跳时间计算展示状态"""
    now = datetime.now(timezone.utc)
    hb_time = datetime.fromisoformat(heartbeat_at)
    if hb_time.tzinfo is None:
        hb_time = hb_time.replace(tzinfo=timezone.utc)
    seconds_ago = (now - hb_time).total_seconds()
    if seconds_ago > HEARTBEAT_OFFLINE:
        return "offline"
    elif seconds_ago > HEARTBEAT_TIMEOUT:
        return "timeout"
    return "online"


def _get_service(db: Session) -> Session:
    return db


# ============================================================
# GET /api/v2/monitoring/agents — Agent 实时状态
# ============================================================

@router.get("/agents")
def get_monitoring_agents(
    status_filter: Optional[str] = Query(None, description="状态筛选: online|timeout|offline|busy"),
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    基于 agent_heartbeats 表聚合，返回所有 Agent 最新心跳状态。
    对每个 agent_id 取最近一次心跳，计算在线/超时/离线状态。
    """
    # 子查询：每个 agent_id 的最近心跳时间
    latest_subq = (
        db.query(
            AgentHeartbeat.agent_id,
            sql_func.max(AgentHeartbeat.heartbeat_at).label("max_hb")
        )
        .group_by(AgentHeartbeat.agent_id)
        .subquery()
    )

    # 关联取完整心跳记录
    rows = (
        db.query(AgentHeartbeat)
        .join(
            latest_subq,
            (AgentHeartbeat.agent_id == latest_subq.c.agent_id) &
            (AgentHeartbeat.heartbeat_at == latest_subq.c.max_hb)
        )
        .order_by(AgentHeartbeat.agent_id)
        .all()
    )

    # 合并 Agent 表信息
    agents_map: Dict[str, Dict[str, Any]] = {}
    agent_rows = db.query(Agent).all()
    for a in agent_rows:
        agents_map[a.agent_id] = {
            "name": a.name,
            "team": a.team,
            "role": a.role,
            "avatar_url": a.avatar_url,
            "registered": True,
        }

    now = datetime.now(timezone.utc)
    agents: List[Dict[str, Any]] = []

    for hb in rows:
        display_status = _compute_display_status(hb.heartbeat_at.isoformat())
        if hb.status == "busy":
            display_status = "busy"

        seconds_ago = 0.0
        hb_time = hb.heartbeat_at
        if isinstance(hb_time, str):
            hb_time = datetime.fromisoformat(hb_time)
        if hb_time.tzinfo is None:
            hb_time = hb_time.replace(tzinfo=timezone.utc)
        seconds_ago = round((now - hb_time).total_seconds(), 1)

        agent_info = agents_map.get(hb.agent_id, {})

        agents.append({
            "agent_id": hb.agent_id,
            "agent_name": hb.agent_name,
            "status": display_status,
            "raw_status": hb.status,
            "current_task": hb.current_task,
            "cpu_usage": hb.cpu_usage,
            "memory_usage": hb.memory_usage,
            "task_queue_len": hb.task_queue_len or 0,
            "last_heartbeat": hb.heartbeat_at.isoformat() if hb.heartbeat_at else None,
            "seconds_ago": seconds_ago,
            "team": agent_info.get("team"),
            "role": agent_info.get("role"),
            "avatar_url": agent_info.get("avatar_url"),
            "metadata": hb.extra_data or {},
        })

    # 包含没有心跳但已注册的 Agent
    registered_ids = {a["agent_id"] for a in agents}
    for aid, info in agents_map.items():
        if aid not in registered_ids:
            agents.append({
                "agent_id": aid,
                "agent_name": info.get("name", aid),
                "status": "offline",
                "raw_status": "offline",
                "current_task": None,
                "cpu_usage": None,
                "memory_usage": None,
                "task_queue_len": 0,
                "last_heartbeat": None,
                "seconds_ago": None,
                "team": info.get("team"),
                "role": info.get("role"),
                "avatar_url": info.get("avatar_url"),
                "metadata": {},
            })

    # 状态筛选
    if status_filter:
        agents = [a for a in agents if a["status"] == status_filter]

    # 汇总
    status_counts: Dict[str, int] = {}
    for a in agents:
        s = a["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "agents": agents,
        "total": len(agents),
        "status_counts": status_counts,
        "timestamp": now.isoformat(),
    }


# ============================================================
# GET /api/v2/monitoring/stats — 任务统计 + 系统指标
# ============================================================

@router.get("/stats")
def get_monitoring_stats(
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    聚合任务统计、Agent 活跃度、系统健康指标。
    数据源: tasks, agent_heartbeats, agent_dispatches 表。
    """
    now = datetime.now(timezone.utc)
    window_5m = now - timedelta(minutes=5)
    window_1h = now - timedelta(hours=1)
    window_24h = now - timedelta(hours=24)

    # ── 任务统计 ──
    total_tasks = db.query(sql_func.count(Task.id)).scalar() or 0

    status_rows = (
        db.query(Task.status, sql_func.count(Task.id))
        .group_by(Task.status).all()
    )
    tasks_by_status = {s: c for s, c in status_rows}

    priority_rows = (
        db.query(Task.priority, sql_func.count(Task.id))
        .group_by(Task.priority).all()
    )
    tasks_by_priority = {p: c for p, c in priority_rows}

    # 按负责人统计
    assignee_rows = (
        db.query(Task.assignee, sql_func.count(Task.id))
        .filter(Task.assignee != None)
        .group_by(Task.assignee).all()
    )
    tasks_by_assignee = {a: c for a, c in assignee_rows}

    done_count = tasks_by_status.get("done", 0) + tasks_by_status.get("completed", 0)
    completion_rate = round(done_count / total_tasks * 100, 1) if total_tasks else 0

    # ── Agent 活跃度 ──
    total_agents = db.query(sql_func.count(Agent.id)).scalar() or 0

    hb_5m = (
        db.query(sql_func.count(sql_func.distinct(AgentHeartbeat.agent_id)))
        .filter(AgentHeartbeat.heartbeat_at >= window_5m)
        .scalar() or 0
    )
    hb_1h = (
        db.query(sql_func.count(sql_func.distinct(AgentHeartbeat.agent_id)))
        .filter(AgentHeartbeat.heartbeat_at >= window_1h)
        .scalar() or 0
    )
    hb_24h = (
        db.query(sql_func.count(sql_func.distinct(AgentHeartbeat.agent_id)))
        .filter(AgentHeartbeat.heartbeat_at >= window_24h)
        .scalar() or 0
    )
    total_heartbeats = (
        db.query(sql_func.count(AgentHeartbeat.id)).scalar() or 0
    )

    # 各状态 Agent 数量（从 Agent 表）
    agent_status_rows = (
        db.query(Agent.status, sql_func.count(Agent.id))
        .group_by(Agent.status).all()
    )
    agents_by_status = {s: c for s, c in agent_status_rows}

    # ── 派发统计 ──
    total_dispatches = (
        db.query(sql_func.count(AgentDispatch.id)).scalar() or 0
    )
    dispatch_status_rows = (
        db.query(AgentDispatch.status, sql_func.count(AgentDispatch.id))
        .group_by(AgentDispatch.status).all()
    )
    dispatches_by_status = {s: c for s, c in dispatch_status_rows}

    # ── 系统健康 ──
    # 最近心跳的平均 CPU / 内存 (最近 100 条)
    recent_hbs = (
        db.query(AgentHeartbeat.cpu_usage, AgentHeartbeat.memory_usage)
        .filter(AgentHeartbeat.cpu_usage != None)
        .order_by(AgentHeartbeat.heartbeat_at.desc())
        .limit(100)
        .all()
    )

    avg_cpu = None
    avg_memory = None
    if recent_hbs:
        cpus = [h[0] for h in recent_hbs if h[0] is not None]
        mems = [h[1] for h in recent_hbs if h[1] is not None]
        avg_cpu = round(sum(cpus) / len(cpus), 1) if cpus else None
        avg_memory = round(sum(mems) / len(mems), 1) if mems else None

    # Agent 负载分布: 当前有 current_task 的 Agent 数量
    busy_agents = (
        db.query(sql_func.count(Agent.id))
        .filter(Agent.current_task != None, Agent.current_task != "")
        .scalar() or 0
    )

    return {
        "tasks": {
            "total": total_tasks,
            "by_status": tasks_by_status,
            "by_priority": tasks_by_priority,
            "by_assignee": tasks_by_assignee,
            "completion_rate": completion_rate,
        },
        "agents": {
            "total_registered": total_agents,
            "active_5m": hb_5m,
            "active_1h": hb_1h,
            "active_24h": hb_24h,
            "total_heartbeats": total_heartbeats,
            "by_status": agents_by_status,
            "busy_count": busy_agents,
        },
        "dispatches": {
            "total": total_dispatches,
            "by_status": dispatches_by_status,
        },
        "system": {
            "avg_cpu_usage": avg_cpu,
            "avg_memory_usage": avg_memory,
            "timestamp": now.isoformat(),
        },
    }
