"""
Legacy Bar (酒吧) routes extracted from main.py
"""
import os
import time
import json
from fastapi import APIRouter

router = APIRouter(prefix="/api/bar", tags=["legacy-bar"])

DATA_DIR = os.path.expanduser("~/WorkSpace/team-dashboard/data")
BAR_DATA_FILE = os.path.join(DATA_DIR, "bar.json")


def load_bar_data():
    if os.path.exists(BAR_DATA_FILE):
        with open(BAR_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"messages": [], "agent_stats": {}}


def save_bar_data(data):
    with open(BAR_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def can_agent_talk(agent_id: str):
    data = load_bar_data()
    now = time.time()
    hour_ago = now - 3600
    if agent_id not in data["agent_stats"]:
        data["agent_stats"][agent_id] = {"talks": [], "last_drink": None}
        save_bar_data(data)
        return True, "可以发言"
    recent = [t for t in data["agent_stats"][agent_id]["talks"] if t > hour_ago]
    data["agent_stats"][agent_id]["talks"] = recent
    save_bar_data(data)
    if len(recent) >= 3:
        return False, "每小时最多发言 3 次，请稍后再来"
    return True, "可以发言"


def can_agent_drink(agent_id: str):
    data = load_bar_data()
    today = time.strftime("%Y-%m-%d")
    if agent_id not in data["agent_stats"]:
        data["agent_stats"][agent_id] = {"talks": [], "last_drink": None}
        save_bar_data(data)
        return True, "可以喝酒"
    return data["agent_stats"][agent_id].get("last_drink") != today, "每天只能喝一次酒，明天再来吧" if data["agent_stats"][agent_id].get("last_drink") == today else "可以喝酒"


@router.get("/messages")
def get_bar_messages(limit: int = 50):
    data = load_bar_data()
    messages = data["messages"][-limit:]
    return {"messages": messages, "total": len(messages)}


@router.get("/stats")
def get_bar_stats():
    return {"agent_stats": load_bar_data()["agent_stats"]}


@router.post("/talk")
def post_bar_talk(agent_id: str, agent_name: str, message: str):
    can, reason = can_agent_talk(agent_id)
    if not can:
        return {"success": False, "message": reason}
    data = load_bar_data()
    now = time.time()
    data["messages"].append({
        "agent_id": agent_id, "agent_name": agent_name, "message": message,
        "timestamp": now, "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
    })
    if agent_id not in data["agent_stats"]:
        data["agent_stats"][agent_id] = {"talks": [], "last_drink": None}
    data["agent_stats"][agent_id]["talks"].append(now)
    data["messages"] = data["messages"][-100:]
    save_bar_data(data)
    remaining = 3 - len(data["agent_stats"][agent_id]["talks"])
    return {"success": True, "message": "发言成功", "remaining": remaining}


@router.post("/drink")
def post_bar_drink(agent_id: str, agent_name: str, drink: str = "啤酒"):
    can, reason = can_agent_drink(agent_id)
    if not can:
        return {"success": False, "message": reason}
    data = load_bar_data()
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    data["messages"].append({
        "agent_id": agent_id, "agent_name": agent_name, "action": "drink",
        "drink": drink, "timestamp": now, "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
    })
    if agent_id not in data["agent_stats"]:
        data["agent_stats"][agent_id] = {"talks": [], "last_drink": None}
    data["agent_stats"][agent_id]["last_drink"] = today
    data["messages"] = data["messages"][-100:]
    save_bar_data(data)
    return {"success": True, "message": f"{agent_name} 喝了一杯{drink} 🍺"}


@router.get("/agent/{agent_id}/status")
def get_agent_bar_status(agent_id: str):
    data = load_bar_data()
    now = time.time()
    hour_ago = now - 3600
    today = time.strftime("%Y-%m-%d")
    if agent_id not in data["agent_stats"]:
        return {"agent_id": agent_id, "talks_remaining": 3, "can_drink": True, "last_drink": None}
    recent = [t for t in data["agent_stats"][agent_id]["talks"] if t > hour_ago]
    last_drink = data["agent_stats"][agent_id].get("last_drink")
    return {
        "agent_id": agent_id,
        "talks_remaining": 3 - len(recent),
        "can_drink": last_drink != today,
        "last_drink": last_drink,
    }
