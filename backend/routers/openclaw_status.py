"""
OpenClaw 智能体状态 API

端点:
  GET  /api/agents/openclaw   → OpenClaw 实时状态（CLI 输出解析，降级到 agents.json）
  GET  /api/agents/{id}/tasks → 智能体当前任务

@author 拉斐尔 (🟥 后端开发)
@created 2026-06-24
"""

import json
import os
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["openclaw-agents"])

# ---------- 路径常量 ----------
AGENTS_JSON = os.path.expanduser("~/.openclaw/workspace/team-dashboard/backend/data/agents.json")

# ---------- 辅助 ----------

AGENT_EMOJI = {
    "optimus": "🤖",
    "bumblebee": "🐝",
    "leonardo": "🟦",
    "raphael": "🟥",
    "donatello": "🟪",
    "michelangelo": "🟧",
    "ironhide": "🛡️",
    "perceptor": "🔬",
    "wheeljack": "🔧",
    "shockwave": "🟣",
}


def _run_openclaw_status() -> Optional[list]:
    """尝试通过 CLI 获取 OpenClaw 实时状态"""
    try:
        result = subprocess.run(
            ["openclaw", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        pass
    return None


def _read_agents_json() -> list:
    """降级：从 agents.json 读取"""
    if not os.path.exists(AGENTS_JSON):
        return []
    with open(AGENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    agents = data.get("agents", data) if isinstance(data, dict) else data
    return agents


# ---------- API ----------

@router.get("/api/agents/openclaw")
def get_openclaw_agents():
    """
    OpenClaw 实时状态。
    优先通过 CLI 获取，失败时降级到 agents.json。
    """
    cli_data = _run_openclaw_status()

    if cli_data:
        return {
            "source": "cli",
            "agents": cli_data,
            "total": len(cli_data) if isinstance(cli_data, list) else 0,
        }

    # 降级
    agents = _read_agents_json()
    for a in agents:
        if "emoji" not in a:
            a["emoji"] = AGENT_EMOJI.get(a.get("id", ""), "👤")

    return {
        "source": "agents.json (fallback)",
        "agents": agents,
        "total": len(agents),
    }


@router.get("/api/agents/{agent_id}/tasks")
def get_agent_tasks(agent_id: str):
    """智能体当前任务"""
    agents = _read_agents_json()
    for agent in agents:
        if agent.get("id") == agent_id:
            return {
                "agent_id": agent_id,
                "name": agent.get("name", agent_id),
                "emoji": agent.get("emoji", AGENT_EMOJI.get(agent_id, "👤")),
                "role": agent.get("role", ""),
                "status": agent.get("status", "unknown"),
                "current_task": agent.get("current_task"),
            }

    raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
