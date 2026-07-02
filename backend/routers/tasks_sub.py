from fastapi import APIRouter, HTTPException
from task_queue import task_manager

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks")
def get_tasks(status: str = None):
    tasks = task_manager.get_all_tasks() if hasattr(task_manager, 'get_all_tasks') else []
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = task_manager.get_task(task_id) if hasattr(task_manager, 'get_task') else None
    if not task:
        return {"error": "task not found"}
    return task


@router.post("/tasks")
def create_task(task_data: dict):
    task = task_manager.create_task(task_data) if hasattr(task_manager, 'create_task') else task_data
    return {"success": True, "task": task}


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    success = task_manager.complete_task(task_id) if hasattr(task_manager, 'complete_task') else True
    if not success:
        return {"error": "task not found"}
    return {"success": True}
