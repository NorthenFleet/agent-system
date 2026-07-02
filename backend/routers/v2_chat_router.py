from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    message: str


router = APIRouter(prefix="/api/v2/chat", tags=["v2-chat"])


@router.post("/{agent_id}/send")
async def v2_send_message(agent_id: str, request: ChatMessageRequest):
    from agent_messenger import agent_messenger
    try:
        return await agent_messenger.send_to_agent(agent_id, request.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenClaw agent 调用失败：{exc}") from exc


@router.get("/{agent_id}/messages")
def v2_get_messages(agent_id: str, limit: int = 50):
    from agent_messenger import agent_messenger
    messages = agent_messenger.load_conversation(agent_id)
    return {"agent_id": agent_id, "messages": messages[-limit:]}


@router.get("/{agent_id}/clear")
def v2_clear_messages(agent_id: str):
    from agent_messenger import agent_messenger
    success = agent_messenger.clear_conversation(agent_id)
    return {"agent_id": agent_id, "cleared": success}


@router.get("/conversations")
def v2_get_conversations():
    from agent_messenger import agent_messenger
    conversations = agent_messenger.get_conversations_list()
    return {"conversations": conversations}
