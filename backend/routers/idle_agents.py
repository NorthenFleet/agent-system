from fastapi import APIRouter, HTTPException
from idle_agent_manager import idle_agent_manager

router = APIRouter(prefix="/api", tags=["idle_agents"])


@router.get("/idle-agents")
def get_idle_agents():
    return {"idle_agents": idle_agent_manager.get_idle_agents() if hasattr(idle_agent_manager, 'get_idle_agents') else []}


@router.post("/idle-agents/{agent_id}/assign")
def assign_idle_agent(agent_id: str, task_data: dict = None):
    result = idle_agent_manager.assign_agent(agent_id, task_data) if hasattr(idle_agent_manager, 'assign_agent') else {"success": True, "agent_id": agent_id}
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
