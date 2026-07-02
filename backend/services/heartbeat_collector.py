"""
Agent 状态采集器

定时从 OpenClaw 获取真实 Agent 状态并写入 agent_heartbeats 表。
支持两种采集方式：
1. OpenClaw sessions_list — 获取活跃会话
2. 直接调用 openclaw CLI

采集间隔：默认 10 秒
离线判定：超过 60s 无心跳 → timeout，超过 5 分钟 → offline
"""
import asyncio
import json
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from models.v2_models import get_session, AgentHeartbeat, AgentStatusHistory

# 采集配置
COLLECT_INTERVAL = 10           # 采集间隔（秒）
HEARTBEAT_TIMEOUT = 60          # 超时阈值
HEARTBEAT_OFFLINE = 300         # 离线阈值


def get_agents_from_sessions_list() -> List[Dict[str, Any]]:
    """
    通过 OpenClaw CLI 获取会话列表，提取 Agent 状态。
    返回: [{agent_id, name, status, current_task, ...}]
    """
    try:
        result = subprocess.run(
            ["openclaw", "sessions", "list", "--json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            sessions = json.loads(result.stdout)
            agents = []
            for s in sessions:
                agent_id = s.get("agentId", s.get("id", ""))
                if not agent_id:
                    continue
                agents.append({
                    "agent_id": agent_id,
                    "agent_name": agent_id,
                    "status": s.get("status", "online"),
                    "current_task": s.get("label", ""),
                    "team": "unknown",
                })
            return agents
    except Exception as e:
        print(f"[HeartbeatCollector] sessions_list 失败: {e}")
    return []


def get_agents_from_status() -> List[Dict[str, Any]]:
    """
    通过 openclaw status 获取状态。
    """
    try:
        result = subprocess.run(
            ["openclaw", "status", "--json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            agents = []
            for agent in data.get("agents", []):
                agents.append({
                    "agent_id": agent.get("id", ""),
                    "agent_name": agent.get("name", agent.get("id", "")),
                    "status": agent.get("status", "online"),
                    "current_task": agent.get("currentTask", ""),
                    "team": agent.get("team", "unknown"),
                })
            return agents
    except Exception as e:
        print(f"[HeartbeatCollector] status 失败: {e}")
    return []


def collect_and_store(agents: List[Dict[str, Any]]):
    """
    将采集到的 Agent 状态写入数据库。
    """
    if not agents:
        return

    db = get_session()
    try:
        for agent in agents:
            agent_id = agent.get("agent_id")
            if not agent_id:
                continue

            # 查最新心跳
            latest = (
                db.query(AgentHeartbeat)
                .filter(AgentHeartbeat.agent_id == agent_id)
                .order_by(AgentHeartbeat.heartbeat_at.desc())
                .first()
            )

            new_status = agent.get("status", "online")

            # 如果状态有变化，记录历史
            if latest and latest.status != new_status:
                history = AgentStatusHistory(
                    agent_id=agent_id,
                    from_status=latest.status,
                    to_status=new_status,
                    current_task=agent.get("current_task"),
                    triggered_by="collector",
                )
                db.add(history)

            heartbeat = AgentHeartbeat(
                agent_id=agent_id,
                agent_name=agent.get("agent_name", agent_id),
                status=new_status,
                current_task=agent.get("current_task"),
                team=agent.get("team"),
                task_queue_len=0,
            )
            db.add(heartbeat)

        db.commit()
        print(f"[HeartbeatCollector] 已采集 {len(agents)} 个 Agent 状态")
    except Exception as e:
        db.rollback()
        print(f"[HeartbeatCollector] 写入失败: {e}")
    finally:
        db.close()


async def run_collector():
    """
    后台持续采集 Agent 状态。
    """
    print("[HeartbeatCollector] 启动状态采集器...")
    while True:
        try:
            # 方式 1: 尝试 openclaw status
            agents = get_agents_from_status()
            if not agents:
                # 方式 2: 尝试 sessions list
                agents = get_agents_from_sessions_list()

            if agents:
                collect_and_store(agents)
            else:
                print("[HeartbeatCollector] 未获取到 Agent 数据")
        except Exception as e:
            print(f"[HeartbeatCollector] 采集异常: {e}")

        await asyncio.sleep(COLLECT_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_collector())
