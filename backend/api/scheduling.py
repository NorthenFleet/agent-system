"""
智能体调度 API - 空闲智能体分配
"""
from fastapi import APIRouter, HTTPException
from typing import Dict

router = APIRouter(prefix="/api/agents/schedule", tags=["scheduling"])


@router.get("/available")
def get_available_agents():
    """获取空闲智能体列表"""
    from idle_agent_manager import idle_agent_manager
    agents = idle_agent_manager.get_available_agents()
    return {"agents": agents, "total": len(agents)}


@router.get("/busy")
def get_busy_agents():
    """获取忙碌智能体列表"""
    from idle_agent_manager import idle_agent_manager
    agents = idle_agent_manager.get_busy_agents()
    return {"agents": agents, "total": len(agents)}


@router.get("/history")
def get_assignment_history(limit: int = 20):
    """获取任务分配历史"""
    from idle_agent_manager import idle_agent_manager
    history = idle_agent_manager.get_assignment_history(limit)
    return {"history": history, "total": len(history)}


@router.get("/stats")
def get_schedule_stats():
    """获取调度统计"""
    from idle_agent_manager import idle_agent_manager
    stats = idle_agent_manager.get_schedule_stats()
    return stats


@router.post("/assign/{agent_id}/{task_id}")
def assign_task(agent_id: str, task_id: str):
    """为空闲智能体分配任务"""
    from idle_agent_manager import idle_agent_manager
    from data_manager import data_manager
    from task_queue import task_queue

    agents = data_manager.get_agents()
    agent = None
    for a in agents:
        if a["id"] == agent_id:
            agent = a
            break

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    tasks = task_queue.get_all_tasks()
    task = None
    for t in tasks:
        if t["id"] == task_id:
            task = t
            break

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    recommended_task = {
        "task_id": task["id"],
        "task_title": task["title"],
        "task_type": task.get("type", "general"),
        "match_score": 100,
        "match_reason": "手动分配"
    }

    plan = idle_agent_manager.generate_development_plan(agent, recommended_task)
    assignment = idle_agent_manager.assign_task_to_agent(agent_id, task_id, plan)

    data_manager.update_agent(agent_id, {
        "status": "busy",
        "current_task": task["title"]
    })

    return {
        "success": True,
        "assignment": assignment,
        "message": f"任务已分配给 {agent['name']}"
    }


@router.get("/available/full")
def get_available_agent_profiles():
    """获取空闲智能体完整档案"""
    from idle_agent_manager import idle_agent_manager
    agents = idle_agent_manager.get_available_agents()
    profiles = []
    for a in agents:
        profiles.append({
            "id": a["id"],
            "name": a["name"],
            "emoji": a.get("emoji", "🤖"),
            "role": a.get("role", ""),
            "skill_tags": a.get("skill_tags", [])
        })
    return {"agents": profiles, "total": len(profiles)}
