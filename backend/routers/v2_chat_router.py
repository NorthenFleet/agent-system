from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class ChatAttachment(BaseModel):
    id: Optional[str] = None
    name: str
    type: str = "application/octet-stream"
    size: int = 0
    data_url: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str
    attachments: List[ChatAttachment] = Field(default_factory=list)


router = APIRouter(prefix="/api/v2/chat", tags=["v2-chat"])


@router.post("/{agent_id}/send")
async def v2_send_message(agent_id: str, request: ChatMessageRequest):
    from agent_messenger import agent_messenger
    try:
        attachments = [
            attachment.model_dump() if hasattr(attachment, "model_dump") else attachment.dict()
            for attachment in request.attachments
        ]
        return await agent_messenger.send_to_agent(
            agent_id,
            request.message,
            attachments,
        )
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
