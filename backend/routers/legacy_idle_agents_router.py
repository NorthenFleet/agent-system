"""
Legacy Idle Agent routes extracted from main.py
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/idle-agents", tags=["legacy-idle-agents"])

_data_manager = None
_task_manager = None
_idle_agent_manager = None


def set_managers(dm, tm, iam):
    global _data_manager, _task_manager, _idle_agent_manager
    _data_manager = dm
    _task_manager = tm
    _idle_agent_manager = iam


@router.get("")
def get_idle_agents():
    agents = _data_manager.get_agents()
    idle = _idle_agent_manager.scan_idle_agents(agents)
    return {"idle_agents": idle, "total": len(idle)}


@router.get("/stats")
def get_idle_agents_stats():
    agents = _data_manager.get_agents()
    return _idle_agent_manager.get_idle_stats(agents)


@router.get("/assignment-history")
def get_assignment_history(limit: int = 20):
    history = _idle_agent_manager.get_assignment_history(limit)
    return {"history": history, "total": len(history)}


@router.get("/development-plans")
def get_development_plans():
    agents = _data_manager.get_agents()
    tasks = _task_manager.get_all_tasks()
    plans = []
    for agent in agents:
        status = agent.get("status", "")
        current_task = agent.get("current_task", "")
        is_idle = (status == "idle") or (current_task == "待分配") or (current_task == "")
        if is_idle:
            recommended = _idle_agent_manager.match_task_to_agent(agent, tasks)
            if recommended:
                plan = _idle_agent_manager.generate_development_plan(agent, recommended)
                plans.append(plan)
    return {"plans": plans, "total": len(plans)}


@router.get("/development-plans/agent/{agent_id}")
def get_agent_development_plan(agent_id: str):
    agents = _data_manager.get_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tasks = _task_manager.get_all_tasks()
    recommended = _idle_agent_manager.match_task_to_agent(agent, tasks)
    if not recommended:
        return {"agent_id": agent_id, "plan": None, "message": "暂无推荐任务"}
    plan = _idle_agent_manager.generate_development_plan(agent, recommended)
    return {"agent_id": agent_id, "plan": plan}


@router.post("/development-plans/assign")
def assign_development_plan(agent_id: str, task_id: str):
    agents = _data_manager.get_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tasks = _task_manager.get_all_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    recommended = {"task_id": task["id"], "task_title": task["title"], "task_type": task.get("type", "general"), "match_score": 100, "match_reason": "手动分配"}
    plan = _idle_agent_manager.generate_development_plan(agent, recommended)
    assignment = _idle_agent_manager.assign_task_to_agent(agent_id, task_id, plan)
    _data_manager.update_agent(agent_id, {"status": "busy", "current_task": task["title"]})
    return {"success": True, "assignment": assignment, "message": f"任务已分配给 {agent['name']}"}
