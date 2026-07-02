from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class MessageRequest(BaseModel):
    message: str

# 导入 messenger（延迟导入避免循环依赖）
def get_messenger():
    from agent_messenger import agent_messenger
    return agent_messenger

@router.post("/api/chat/{agent_id}/send")
async def send_message(agent_id: str, request: MessageRequest):
    """发送消息到智能体"""
    messenger = get_messenger()
    result = await messenger.send_to_agent(agent_id, request.message)
    return result

@router.get("/api/chat/{agent_id}/messages")
def get_messages(agent_id: str, limit: int = 50):
    """获取对话历史"""
    messenger = get_messenger()
    messages = messenger.load_conversation(agent_id)
    return {"agent_id": agent_id, "messages": messages[-limit:]}

@router.get("/api/chat/{agent_id}/clear")
def clear_messages(agent_id: str):
    """清空对话"""
    messenger = get_messenger()
    success = messenger.clear_conversation(agent_id)
    return {"agent_id": agent_id, "cleared": success}

@router.get("/api/chat/conversations")
def get_conversations():
    """获取所有对话列表"""
    messenger = get_messenger()
    conversations = messenger.get_conversations_list()
    return {"conversations": conversations}

