"""
Legacy 任务路由 — main.py 中未迁移的 /api/tasks、/api/team 端点
"""
from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter(prefix="/api/tasks", tags=["legacy-tasks"])

# 需要在运行时注入
_data_manager = None
_task_manager = None


def set_managers(dm, tm):
    global _data_manager, _task_manager
    _data_manager = dm
    _task_manager = tm


@router.get("")
def get_tasks():
    merged = _data_manager.get_merged_tasks()
    return {"tasks": merged, "total": len(merged)}


@router.get("/merged")
def get_tasks_merged():
    merged = _data_manager.get_merged_tasks()
    return {"tasks": merged, "total": len(merged), "source": "merged"}


@router.post("")
def create_task(task_data: dict):
    title = task_data.get("title", "")
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")
    task_id = _task_manager.create_task(
        title=title,
        assignee=task_data.get("assignee", ""),
        priority=task_data.get("priority", "normal"),
        description=task_data.get("description", ""),
        context=task_data.get("context"),
    )
    return {"success": True, "task_id": task_id, "title": title}


@router.get("/{task_id}/context")
def get_task_context(task_id: str):
    task = _task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "context": task.get("context", {})}


@router.put("/{task_id}/context")
def update_task_context(task_id: str, context_updates: dict):
    success = _task_manager.update_task_context(task_id, context_updates)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Context updated", "task_id": task_id}


@router.get("/{task_id}/subtasks")
def get_task_subtasks(task_id: str):
    task = _task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "subtasks": task.get("subtasks", [])}


@router.post("/{task_id}/subtasks")
def add_task_subtask(task_id: str, subtask: dict):
    success = _task_manager.add_subtask(task_id, subtask.get("title", ""), subtask.get("assignee", ""), subtask.get("completed", False))
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Subtask added", "task_id": task_id}


@router.put("/{task_id}/subtasks/{subtask_id}")
def update_subtask_status(task_id: str, subtask_id: str, completed: bool):
    success = _task_manager.update_subtask(task_id, subtask_id, completed)
    if not success:
        raise HTTPException(status_code=404, detail="Subtask not found")
    return {"message": "Subtask updated", "task_id": task_id, "subtask_id": subtask_id}


@router.get("/{task_id}/logs")
def get_task_logs(task_id: str, limit: int = 50):
    logs = _task_manager.get_task_logs(task_id, limit)
    return {"task_id": task_id, "logs": logs, "total": len(logs)}


@router.post("/{task_id}/logs")
def add_task_log(task_id: str, log_entry: dict):
    success = _task_manager.add_task_log(task_id, log_entry.get("content", ""), log_entry.get("action", "note"))
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Log added", "task_id": task_id}


@router.get("/{task_id}/details")
def get_task_full_details(task_id: str):
    task = _task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logs = _task_manager.get_task_logs(task_id, 50)
    return {
        "task": task,
        "logs": logs,
        "subtasks_count": len(task.get("subtasks", [])),
        "completed_subtasks": sum(1 for s in task.get("subtasks", []) if s.get("completed")),
    }


@router.get("/assignee/{assignee}")
def get_tasks_by_assignee(assignee: str):
    tasks = _task_manager.get_tasks_by_assignee(assignee)
    return {"assignee": assignee, "tasks": tasks, "total": len(tasks)}
