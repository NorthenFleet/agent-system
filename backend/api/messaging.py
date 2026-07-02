"""
智能体聊天 API - agent_messenger
"""
from fastapi import APIRouter, HTTPException, WebSocket, Query
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["agent-chat"])


class ChatMessageRequest(BaseModel):
    message: str


# ==================== 聊天路由 ====================

@router.post("/api/v2/chat/{agent_id}/send")
async def chat_send_message(agent_id: str, request: ChatMessageRequest):
    """发送消息到智能体"""
    from agent_messenger import agent_messenger
    result = await agent_messenger.send_to_agent(agent_id, request.message)
    return result


@router.get("/api/v2/chat/{agent_id}/messages")
def chat_get_messages(agent_id: str, limit: int = 50):
    """获取与智能体的对话记录"""
    from agent_messenger import agent_messenger
    messages = agent_messenger.load_conversation(agent_id)
    return {"agent_id": agent_id, "messages": messages[-limit:]}


@router.get("/api/v2/chat/{agent_id}/clear")
def chat_clear_messages(agent_id: str):
    """清空与智能体的对话"""
    from agent_messenger import agent_messenger
    success = agent_messenger.clear_conversation(agent_id)
    return {"agent_id": agent_id, "cleared": success}


@router.get("/api/v2/chat/conversations")
def chat_get_conversations():
    """获取所有对话列表"""
    from agent_messenger import agent_messenger
    conversations = agent_messenger.get_conversations_list()
    return {"conversations": conversations}


# ==================== 酒吧（实时消息广播）路由 ====================

@router.get("/api/bar/messages")
def bar_get_messages(limit: int = 50):
    """获取酒吧最近消息"""
    from agent_messenger import agent_messenger
    messages = agent_messenger.load_bar_messages()
    return {"messages": messages[-limit:], "total": len(messages)}


@router.post("/api/bar/message")
def bar_send_message(
    agent_id: str,
    agent_name: str,
    message: str,
    emoji: Optional[str] = "🤖",
    is_system: bool = False
):
    """向酒吧发送消息"""
    from agent_messenger import agent_messenger
    success = agent_messenger.send_to_bar(agent_id, message, agent_name, emoji)
    if success:
        return {"success": True}
    return {"success": False, "error": "发送失败"}


@router.get("/api/bar/notifications")
def bar_get_notifications():
    """获取酒吧通知"""
    from agent_messenger import agent_messenger
    messages = agent_messenger.load_bar_messages()
    notifications = [
        {
            "message": msg["message"][:100],
            "timestamp": msg["timestamp"],
            "agent_id": msg["agent_id"],
            "agent_name": msg["agent_name"]
        }
        for msg in messages[-10:]
    ]
    return {"notifications": notifications}


# ==================== 酒吧 WebSocket ====================

@router.websocket("/api/bar/websocket")
async def bar_websocket(websocket: WebSocket):
    """酒吧 WebSocket 连接"""
    from agent_messenger import agent_messenger
    await agent_messenger.add_websocket(websocket)
    try:
        while True:
            await websocket.receive_text()
            # 持续保持连接
    except Exception:
        await agent_messenger.remove_websocket(websocket)


# ==================== Agent 聊天 WebSocket ====================

@router.websocket("/api/v2/chat/{agent_id}/websocket")
async def chat_agent_websocket(websocket: WebSocket, agent_id: str):
    """智能体聊天 WebSocket"""
    from agent_messenger import agent_messenger
    await agent_messenger.add_chat_websocket(agent_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        await agent_messenger.remove_chat_websocket(agent_id, websocket)
