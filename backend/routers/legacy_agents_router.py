"""
Legacy Agent & Device routes extracted from main.py

These endpoints use the old JSON-file data source.
They remain functional for backward compatibility.
"""
import os
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from typing import Optional

router = APIRouter(tags=["legacy-agents-devices"])

# Injected at runtime
_data_manager = None
_task_manager = None
_device_manager = None
_openclaw_integration = None


def set_managers(dm, tm, dvm, oi):
    global _data_manager, _task_manager, _device_manager, _openclaw_integration
    _data_manager = dm
    _task_manager = tm
    _device_manager = dvm
    _openclaw_integration = oi


def get_agent_emoji(agent_id: str) -> str:
    emoji_map = {
        "optimus": "🤖", "bumblebee": "🐝",
        "leonardo": "🟦", "raphael": "🟥", "donatello": "🟪", "michelangelo": "🟧",
        "ironhide": "🛡️", "perceptor": "🔬", "wheeljack": "🔧", "shockwave": "🟣",
    }
    return emoji_map.get(agent_id, "👤")


def _load_memory_map() -> dict:
    """Load memory data from agents.json file."""
    import json
    agents_file = os.path.join(os.path.dirname(__file__), "..", "data", "agents.json")
    if not os.path.exists(agents_file):
        return {}
    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        agents = data if isinstance(data, list) else data.get("agents", [])
        return {a.get("id", a.get("agent_id")): a.get("memory", []) for a in agents if a.get("id") or a.get("agent_id")}
    except Exception:
        return {}


AGENT_CHINESE_NAMES = {
    "optimus": "擎天柱",
    "bumblebee": "大黄蜂",
    "donatello": "多纳泰罗",
    "inspector": "巡检员",
    "ironhide": "铁皮",
    "jazz": "爵士",
    "leonardo": "李奥纳多",
    "michelangelo": "米开朗基罗",
    "perceptor": "感知器",
    "raphael": "拉斐尔",
    "ratchet": "救护车",
    "shockwave": "震荡波",
    "soundwave": "声波",
    "ultra-magnus": "通天晓",
    "wheeljack": "千斤顶",
    "wheeljack-donatello": "千斤顶-多纳泰罗",
    "wheeljack-leonardo": "千斤顶-李奥纳多",
    "wheeljack-michelangelo": "千斤顶-米开朗基罗",
    "wheeljack-raphael": "千斤顶-拉斐尔",
    "main": "小梦",
}


def localize_agent_names(agents):
    localized = []
    for agent in agents:
        item = agent.copy()
        agent_id = item.get("id") or item.get("agent_id")
        chinese_name = AGENT_CHINESE_NAMES.get(agent_id)
        if chinese_name:
            item["name"] = chinese_name
            item["agent_name"] = chinese_name
        localized.append(item)
    return localized


@router.get("/api/agents")
def get_agents():
    try:
        agents = localize_agent_names(_openclaw_integration.sync_agents())
        if agents:
            # Enrich with memory data from agents.json
            memory_map = _load_memory_map()
            for agent in agents:
                agent_id = agent.get("id") or agent.get("agent_id", "")
                if agent_id and agent_id not in memory_map:
                    # Try with Chinese name mapping reversed
                    for orig_id, loc_name in AGENT_CHINESE_NAMES.items():
                        if agent.get("name") == loc_name:
                            agent_id = orig_id
                            break
                if agent_id and agent_id in memory_map:
                    agent["memory"] = memory_map[agent_id]
            return {"agents": agents, "total": len(agents), "source": "openclaw"}
    except Exception:
        pass
    agents = localize_agent_names(_data_manager.get_agents())
    # Enrich with memory data
    memory_map = _load_memory_map()
    for agent in agents:
        agent_id = agent.get("id") or agent.get("agent_id", "")
        if agent_id and agent_id not in memory_map:
            for orig_id, loc_name in AGENT_CHINESE_NAMES.items():
                if agent.get("name") == loc_name:
                    agent_id = orig_id
                    break
        if agent_id and agent_id in memory_map and "memory" not in agent:
            agent["memory"] = memory_map[agent_id]
    return {"agents": agents, "total": len(agents), "source": "local"}


@router.get("/api/team/status")
def get_team_status():
    agents = _data_manager.get_agents()
    return {
        "total_agents": len(agents),
        "online": sum(1 for a in agents if a["status"] == "online"),
        "busy": sum(1 for a in agents if a["status"] == "busy"),
        "idle": sum(1 for a in agents if a["status"] == "idle"),
        "pending": sum(1 for a in agents if a["status"] == "pending"),
        "autobots_count": sum(1 for a in agents if a["team"] == "autobots"),
        "ninja_turtles_count": sum(1 for a in agents if a["team"] == "ninja_turtles"),
        "task_stats": _task_manager.get_stats(),
    }


@router.get("/api/tasks/stats")
def get_task_stats():
    return _task_manager.get_stats()


# ─── Devices ───

@router.get("/api/devices")
def list_devices():
    devices = _device_manager.get_devices()
    devices_with_agents = []
    for device in devices:
        device_dict = device.copy()
        device_dict["assigned_agents_details"] = [
            {"id": a["id"], "name": a["name"], "role": a["role"], "status": a["status"], "emoji": get_agent_emoji(a["id"])}
            for a in _data_manager.get_agents() if a["id"] in device.get("assigned_agents", [])
        ]
        devices_with_agents.append(device_dict)
    return {"devices": devices_with_agents, "total": len(devices_with_agents)}


@router.get("/api/devices/stats")
def get_device_stats():
    return _device_manager.get_device_stats()


@router.get("/api/devices/alerts")
def get_device_alerts(status: str = "active"):
    alerts = _device_manager.get_alerts(status)
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/api/devices/alerts/{alert_id}/acknowledge")
def acknowledge_alert(request: Request, alert_id: str):
    success = _device_manager.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert acknowledged", "alert_id": alert_id}


@router.get("/api/devices/{device_id}")
def get_device(device_id: str):
    device = _device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device_dict = device.copy()
    device_dict["assigned_agents_details"] = [
        {"id": a["id"], "name": a["name"], "role": a["role"], "status": a["status"], "emoji": get_agent_emoji(a["id"])}
        for a in _data_manager.get_agents() if a["id"] in device.get("assigned_agents", [])
    ]
    return device_dict


@router.post("/api/devices")
def create_device(request: Request, device: dict):
    new_device = _device_manager.add_device(device)
    return {"message": "Device created", "device": new_device}


@router.put("/api/devices/{device_id}")
def update_device(request: Request, device_id: str, updates: dict):
    success = _device_manager.update_device(device_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device updated", "device_id": device_id}


@router.delete("/api/devices/{device_id}")
def delete_device(request: Request, device_id: str):
    success = _device_manager.delete_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device deleted", "device_id": device_id}


@router.get("/api/devices/{device_id}/health")
async def check_device_health(device_id: str):
    device = _device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    health = await _device_manager.check_device_health(device_id)
    return health


@router.get("/api/devices/{device_id}/health/history")
def get_device_health_history(device_id: str, limit: int = 10):
    device = _device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    history = _device_manager.get_health_history(device_id, limit)
    return {"device_id": device_id, "history": history, "total": len(history)}


# ─── OpenClaw ───

@router.get("/api/openclaw/stats")
def get_openclaw_stats():
    return _openclaw_integration.sync_data()


@router.get("/api/email/stats")
def get_email_stats():
    return _openclaw_integration.get_email_stats()


@router.get("/api/codex/tasks")
def get_codex_tasks():
    tasks = _openclaw_integration.get_codex_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/api/heartbeat/state")
def get_heartbeat_state():
    return _openclaw_integration.get_heartbeat_state()
