import json
import asyncio
from datetime import datetime
#!/usr/bin/env python3
"""
独立的智能体聊天服务
运行在端口 3021
"""
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent_messenger import agent_messenger
from sse_manager import sse_manager, Events
from task_dispatcher import task_dispatcher
import uvicorn

app = FastAPI(title="Agent Chat Service")

async def broadcast_event(event_name, data):
    """非阻塞广播事件"""
    try:
        await sse_manager.broadcast(event_name, data)
    except Exception as e:
        print(f"[SSE] 广播失败: {e}")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class MessageRequest(BaseModel):
    message: str

@app.get("/health")
def health():
    return {"status": "ok", "service": "chat"}

@app.get("/api/chat/{agent_id}/messages")
def get_messages(agent_id: str, limit: int = 50):
    messages = agent_messenger.load_conversation(agent_id)
    return {"agent_id": agent_id, "messages": messages[-limit:]}

@app.post("/api/chat/{agent_id}/send")
async def send_message(agent_id: str, request: MessageRequest):
    result = await agent_messenger.send_to_agent(agent_id, request.message)
    
    # 非阻塞广播消息事件
    asyncio.create_task(broadcast_event(Events.MESSAGE_RECEIVED, {
        "agent_id": agent_id,
        "message": request.message,
        "response": result.get("agent_response", "")
    }))
    
    return result

@app.get("/api/chat/{agent_id}/clear")
def clear_messages(agent_id: str):
    success = agent_messenger.clear_conversation(agent_id)
    return {"agent_id": agent_id, "cleared": success}

@app.get("/api/chat/conversations")
def get_conversations():
    conversations = agent_messenger.get_conversations_list()
    return {"conversations": conversations}



# ========== 任务派发 API ==========

from pydantic import BaseModel as TaskBaseModel

class TaskDispatchRequest(TaskBaseModel):
    agent_id: str
    task: str
    priority: str = "normal"

class TaskStatusRequest(TaskBaseModel):
    status: str
    result: str = None

@app.post("/api/tasks/dispatch")
async def dispatch_task(request: TaskDispatchRequest):
    """派发任务到智能体"""
    task = task_dispatcher.dispatch_task(
        agent_id=request.agent_id,
        task_desc=request.task,
        priority=request.priority
    )
    
    # 非阻塞广播任务派发事件
    asyncio.create_task(broadcast_event(Events.TASK_DISPATCHED, {
        "task": task,
        "agent_id": request.agent_id
    }))
    
    return {"status": "dispatched", "task": task}

@app.get("/api/tasks/list")
def list_tasks(agent_id: str = None, status: str = None):
    """获取任务列表"""
    tasks = task_dispatcher.get_tasks(agent_id=agent_id, status=status)
    return {"tasks": tasks}

@app.get("/api/tasks/stats")
def task_stats():
    """获取任务统计"""
    stats = task_dispatcher.get_task_stats()
    return stats

@app.post("/api/tasks/{task_id}/status")
async def update_task_status(task_id: str, request: TaskStatusRequest):
    """更新任务状态"""
    task = task_dispatcher.update_task_status(
        task_id=task_id,
        status=request.status,
        result=request.result
    )
    # 广播任务更新事件
    await sse_manager.broadcast(Events.TASK_UPDATED, {
        "task": task
    })
    
    # 非阻塞广播任务更新事件
    asyncio.create_task(broadcast_event(Events.TASK_UPDATED, {
        "task": task
    }))
    
    return {"status": "updated", "task": task}

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """获取单个任务详情"""
    tasks = task_dispatcher.load_tasks()
    for task in tasks:
        if task["task_id"] == task_id:
            return task
    return {"error": "Task not found"}




# ========== 智能体控制 API ==========

class AgentControlRequest(TaskBaseModel):
    action: str  # pause, resume, restart, refresh

@app.post("/api/agents/{agent_id}/control")
async def control_agent(agent_id: str, request: AgentControlRequest):
    """控制智能体（暂停/恢复/重启/刷新）"""
    actions = {
        "pause": "⏸️ 已暂停",
        "resume": "▶️ 已恢复",
        "restart": "🔄 已重启",
        "refresh": "📊 已刷新"
    }
    
    result_msg = actions.get(request.action, f"⚠️ 未知操作：{request.action}")
    
    # 记录控制操作
    return {
        "status": "success",
        "agent_id": agent_id,
        "action": request.action,
        "message": result_msg,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/agents/{agent_id}/status")
def get_agent_status(agent_id: str):
    """获取智能体状态"""
    return {
        "agent_id": agent_id,
        "status": "online",
        "last_seen": datetime.now().isoformat()
    }



# ========== SSE 实时推送 ==========

import uuid

@app.get("/api/sse/stream")
async def sse_stream(request: Request):
    """SSE 事件流"""
    client_id = str(uuid.uuid4())
    queue = sse_manager.add_connection(client_id)
    
    async def event_stream():
        try:
            # 发送连接成功事件
            yield f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n"
            
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {message['event']}\ndata: {json.dumps(message['data'])}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield f"event: heartbeat\ndata: {json.dumps({'ping': True})}\n\n"
        finally:
            sse_manager.remove_connection(client_id)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )

@app.get("/api/sse/clients")
def get_sse_clients():
    """获取 SSE 连接数"""
    return {"connected_clients": sse_manager.get_connected_clients()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3021)
