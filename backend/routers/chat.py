from fastapi import APIRouter
from chat_manager import chat_manager

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/{agent_id}")
def send_to_agent(agent_id: str, message: dict):
    text = message.get("message", "")
    result = chat_manager.send_to_agent(agent_id, text)
    return result


@router.get("/chat/{agent_id}/conversations")
def get_conversations(agent_id: str):
    conversations = chat_manager.get_conversations(agent_id)
    return {"conversations": conversations}


@router.get("/chat/agents")
def get_chat_agents():
    from data_manager import data_manager
    agents = data_manager.get_agents()
    return {"agents": [{"id": a["id"], "name": a["name"]} for a in agents]}
