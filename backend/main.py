from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
import os

from websocket_manager import manager
from data_manager import data_manager
from task_queue import task_manager, init_sample_tasks
from device_manager import device_manager

app = FastAPI(title="团队状态看板 API")

# 获取前端文件路径
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class Agent(BaseModel):
    id: str
    name: str
    role: str
    status: str
    team: str
    current_task: Optional[str] = None
    capabilities: List[str] = []
    device_id: Optional[str] = None

class DeviceCreate(BaseModel):
    id: str
    name: str
    ip: str
    os: str = "Unknown"
    role: str = "Unknown"
    ports: List[int] = []
    specs: dict = {}
    assigned_agents: List[str] = []
    location: str = ""
    description: str = ""

# 初始化示例任务
init_sample_tasks()

# API 接口
@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index-old.html"))

# 模块化版
@app.get("/modular")
def modular_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "index-old.html"))

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
app.mount("/views", StaticFiles(directory=os.path.join(FRONTEND_DIR, "views")), name="views")

@app.get("/health")
def health_check():
    return {"status": "ok", "port": 3020}

@app.get("/api/agents")
def get_agents():
    return {"agents": data_manager.get_agents(), "total": len(data_manager.get_agents())}

@app.get("/api/tasks")
def get_tasks():
    return {"tasks": task_manager.get_all_tasks(), "total": task_manager.get_stats()["total"]}

@app.get("/api/team/status")
def get_team_status():
    agents = data_manager.get_agents()
    return {
        "total_agents": len(agents),
        "online": sum(1 for a in agents if a["status"] == "online"),
        "busy": sum(1 for a in agents if a["status"] == "busy"),
        "idle": sum(1 for a in agents if a["status"] == "idle"),
        "pending": sum(1 for a in agents if a["status"] == "pending"),
        "autobots_count": sum(1 for a in agents if a["team"] == "autobots"),
        "ninja_turtles_count": sum(1 for a in agents if a["team"] == "ninja_turtles"),
        "task_stats": task_manager.get_stats()
    }

@app.get("/api/tasks/stats")
def get_task_stats():
    return task_manager.get_stats()

# ==================== 设备管理接口 ====================
# 注意：静态路由必须在动态路由之前定义！

@app.get("/api/devices")
def list_devices():
    """获取所有设备信息，包含关联的智能体详情"""
    devices = device_manager.get_devices()
    devices_with_agents = []
    
    for device in devices:
        device_dict = device.copy()
        device_dict["assigned_agents_details"] = [
            {"id": a["id"], "name": a["name"], "role": a["role"], "status": a["status"], "emoji": get_agent_emoji(a["id"])}
            for a in data_manager.get_agents() if a["id"] in device.get("assigned_agents", [])
        ]
        devices_with_agents.append(device_dict)
    
    return {"devices": devices_with_agents, "total": len(devices_with_agents)}

@app.get("/api/devices/stats")
def get_device_stats():
    """获取设备统计信息"""
    return device_manager.get_device_stats()

@app.get("/api/devices/alerts")
def get_device_alerts(status: str = "active"):
    """获取设备告警列表"""
    alerts = device_manager.get_alerts(status)
    return {"alerts": alerts, "total": len(alerts)}

@app.post("/api/devices/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str):
    """确认告警"""
    success = device_manager.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert acknowledged", "alert_id": alert_id}

@app.get("/api/devices/discover")
async def discover_devices(ip_range: str = "192.168.31.0/24"):
    """自动发现网络中的设备"""
    discovered = await device_manager.auto_discover_devices(ip_range)
    return {"discovered": discovered, "total": len(discovered)}

@app.get("/api/devices/{device_id}")
def get_device(device_id: str):
    """获取单个设备详情"""
    device = device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device_dict = device.copy()
    device_dict["assigned_agents_details"] = [
        {"id": a["id"], "name": a["name"], "role": a["role"], "status": a["status"], "emoji": get_agent_emoji(a["id"])}
        for a in data_manager.get_agents() if a["id"] in device.get("assigned_agents", [])
    ]
    
    return device_dict

@app.post("/api/devices")
def create_device(device: DeviceCreate):
    """创建新设备"""
    new_device = device_manager.add_device(device.dict())
    return {"message": "Device created", "device": new_device}

@app.put("/api/devices/{device_id}")
def update_device(device_id: str, updates: dict):
    """更新设备信息"""
    success = device_manager.update_device(device_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device updated", "device_id": device_id}

@app.delete("/api/devices/{device_id}")
def delete_device(device_id: str):
    """删除设备"""
    success = device_manager.delete_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device deleted", "device_id": device_id}

@app.get("/api/devices/{device_id}/health")
async def check_device_health(device_id: str):
    """检查设备健康状态 - 核心接口"""
    device = device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    health = await device_manager.check_device_health(device_id)
    return health

@app.get("/api/devices/{device_id}/health/history")
def get_device_health_history(device_id: str, limit: int = 10):
    """获取设备健康历史"""
    device = device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    history = device_manager.get_health_history(device_id, limit)
    return {"device_id": device_id, "history": history, "total": len(history)}

# ==================== 辅助函数 ====================

def get_agent_emoji(agent_id: str) -> str:
    """根据智能体 ID 返回对应的 emoji"""
    emoji_map = {
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
    return emoji_map.get(agent_id, "👤")

# WebSocket 实时推送
@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[WebSocket] 收到消息：{data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"[WebSocket] 客户端断开连接")


# ==================== OpenClaw 实时数据接口 ====================

from openclaw_integration import openclaw_integration

@app.get("/api/openclaw/stats")
def get_openclaw_stats():
    return openclaw_integration.sync_data()

@app.get("/api/email/stats")
def get_email_stats():
    return openclaw_integration.get_email_stats()

@app.get("/api/codex/tasks")
def get_codex_tasks():
    tasks = openclaw_integration.get_codex_tasks()
    return {"tasks": tasks, "total": len(tasks)}

@app.get("/api/heartbeat/state")
def get_heartbeat_state():
    return openclaw_integration.get_heartbeat_state()


# ==================== 智能体文档管理接口 ====================

from document_manager import doc_manager

@app.get("/api/agents/{agent_id}/memory")
def get_agent_memory(agent_id: str):
    agents = data_manager.get_agents()
    for agent in agents:
        if agent["id"] == agent_id:
            return {"agent_id": agent_id, "memory": agent.get("memory", [])}
    raise HTTPException(status_code=404, detail="Agent not found")

@app.get("/api/agents/{agent_id}/documents")
def get_agent_documents(agent_id: str):
    documents = doc_manager.scan_documents(agent_id)
    return {"agent_id": agent_id, "documents": documents, "total": len(documents)}

@app.get("/api/agents/{agent_id}/details")
def get_agent_full_details(agent_id: str):
    details = doc_manager.get_agent_full_details(agent_id, data_manager)
    if "error" in details:
        raise HTTPException(status_code=404, detail=details["error"])
    return details

@app.get("/api/documents/preview")
def preview_document(filepath: str, max_lines: int = 100):
    content = doc_manager.get_document_content(filepath, max_lines)
    return {"filepath": filepath, "content": content, "lines": max_lines}



# ========== 测试页面路由 ==========
@app.get("/test")
def test_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "min-test.html"))

@app.get("/simple")
def simple_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "simple-index.html"))

@app.get("/step2")
def step2_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "step2.html"))

# 步骤 3 测试页面
@app.get("/step3")
def step3_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "step3.html"))

# 步骤 4 测试页面
@app.get("/step4")
def step4_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "step4.html"))
# ===================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3020)

