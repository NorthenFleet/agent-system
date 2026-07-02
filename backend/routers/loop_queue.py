"""
Loop 开发队列 API

端点:
  GET  /api/loop/queue              → 读取 dev-loop/queue.json
  POST /api/loop/queue              → 状态转换（校验 + 更新 + 记录 history）
  GET  /api/loop/tasks              → 读取 dev-loop/tasks/*.json
  POST /api/loop/tasks              → 创建新子任务（task-002-5）
  PUT  /api/loop/tasks/{id}/status  → 推进任务状态（task-002-5）
  GET  /api/loop/sprint             → 返回 sprint 摘要信息

@author 拉斐尔 (🟥 后端开发)
@created 2026-06-24
"""

import json
import os
import time
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["loop-queue"])

# ---------- 路径常量 ----------
DEV_LOOP_DIR = os.path.expanduser("~/.openclaw/workspace/agents/ninja-turtles/dev-loop")
QUEUE_FILE = os.path.join(DEV_LOOP_DIR, "queue.json")
TASKS_DIR = os.path.join(DEV_LOOP_DIR, "tasks")

# ---------- 状态转换规则 ----------
TRANSITIONS = {
    "pending": ["assigned"],
    "assigned": ["in_progress", "pending"],
    "in_progress": ["review", "assigned"],
    "review": ["testing", "in_progress"],
    "testing": ["done", "review"],
    "done": ["archived"],
    "archived": [],
}

# ---------- 辅助 ----------

def _read_queue() -> dict:
    if not os.path.exists(QUEUE_FILE):
        raise HTTPException(status_code=404, detail="queue.json 不存在")
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_queue(data: dict) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _append_history(queue_data: dict, task_id: str, from_status: Optional[str], to_status: str, by: str = "api") -> None:
    history = queue_data.setdefault("workflow_history", [])
    record = {
        "task_id": task_id,
        "from": from_status,
        "to": to_status,
        "by": by,
        "at": datetime.now().isoformat(),
    }
    history.append(record)
    # 保持最近 200 条
    queue_data["workflow_history"] = history[-200:]


def _validate_transition(from_status: str, to_status: str) -> bool:
    allowed = TRANSITIONS.get(from_status, [])
    return to_status in allowed


# ---------- 请求模型 ----------

class StatusTransitionRequest(BaseModel):
    task_id: str
    to_status: str
    by: str = "api"


class CreateSubtaskRequest(BaseModel):
    """在指定主任务下创建子任务"""
    parent_task_id: str
    title: str
    type: str = "backend"  # backend/frontend/fullstack
    priority: str = "medium"  # low/medium/high
    assignee: str = ""


class AdvanceTaskStatusRequest(BaseModel):
    """推进指定任务（主任务或子任务）到下一个状态"""
    to_status: str
    by: str = "api"


class AssignTaskRequest(BaseModel):
    """分配任务人员"""
    assignee: str
    by: str = "api"


# ---------- API ----------

@router.get("/api/loop/queue")
def get_loop_queue():
    """读取 dev-loop/queue.json"""
    return _read_queue()


@router.post("/api/loop/queue")
def update_loop_queue(req: StatusTransitionRequest):
    """
    状态转换：
    1. 读取 queue.json
    2. 找到 task_id 对应的任务（含子任务）
    3. 校验 from → to 是否允许
    4. 更新 task status
    5. 追加 workflow_history
    6. 写回 queue.json
    7. 返回成功响应
    """
    queue = _read_queue()

    # 查找任务（主任务或子任务）
    target_task = None
    parent_task = None

    for task in queue.get("tasks", []):
        if task.get("id") == req.task_id:
            target_task = task
            break
        for sub in task.get("subtasks", []):
            if sub.get("id") == req.task_id:
                target_task = sub
                parent_task = task
                break
        if target_task:
            break

    if not target_task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {req.task_id}")

    from_status = target_task.get("status", "pending")

    if not _validate_transition(from_status, req.to_status):
        raise HTTPException(
            status_code=400,
            detail=f"不允许从 '{from_status}' 转换到 '{req.to_status}'"
        )

    target_task["status"] = req.to_status
    target_task["updated"] = datetime.now().strftime("%Y-%m-%d")

    _append_history(queue, req.task_id, from_status, req.to_status, req.by)
    _write_queue(queue)

    # WebSocket 推送队列变更
    try:
        from websocket_manager import manager as ws_manager
        import asyncio
        asyncio.create_task(ws_manager.push_queue_update(queue))
    except Exception:
        pass

    return {
        "success": True,
        "task_id": req.task_id,
        "from": from_status,
        "to": req.to_status,
        "message": f"状态已从 '{from_status}' 变更为 '{req.to_status}'"
    }


@router.get("/api/loop/tasks")
def get_loop_tasks():
    """读取 dev-loop/tasks/*.json"""
    if not os.path.isdir(TASKS_DIR):
        return {"tasks": []}

    tasks = []
    for filename in sorted(os.listdir(TASKS_DIR)):
        if filename.endswith(".json"):
            filepath = os.path.join(TASKS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    tasks.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                tasks.append({"file": filename, "error": "读取失败"})

    return {"tasks": tasks, "total": len(tasks)}


# ---------- 创建子任务 ----------

@router.post("/api/loop/tasks")
def create_loop_task(req: CreateSubtaskRequest):
    """在指定主任务下创建子任务（task-002-5）"""
    queue = _read_queue()

    parent = None
    for task in queue.get("tasks", []):
        if task.get("id") == req.parent_task_id:
            parent = task
            break

    if not parent:
        raise HTTPException(status_code=404, detail=f"主任务不存在: {req.parent_task_id}")

    subtasks = parent.get("subtasks", [])
    existing_ids = {s["id"] for s in subtasks}

    # 生成子任务 id
    idx = 1
    while True:
        new_id = f"{req.parent_task_id}-{idx}"
        if new_id not in existing_ids:
            break
        idx += 1

    subtask = {
        "id": new_id,
        "title": req.title,
        "type": req.type,
        "assignee": req.assignee,
        "status": "pending",
        "priority": req.priority,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "updated": datetime.now().strftime("%Y-%m-%d"),
    }

    subtasks.append(subtask)
    parent["subtasks"] = subtasks
    parent["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_queue(queue)

    # WebSocket 推送
    try:
        from websocket_manager import manager as ws_manager
        import asyncio
        asyncio.create_task(ws_manager.push_queue_update(queue))
    except Exception:
        pass

    return {
        "success": True,
        "task": subtask,
        "message": f"子任务已创建：{req.title}"
    }


# ---------- 推进任务状态 ----------

@router.put("/api/loop/tasks/{task_id}/status")
def advance_task_status(task_id: str, req: AdvanceTaskStatusRequest):
    """推进指定任务的状态（主任务或子任务均可）（task-002-5）"""
    queue = _read_queue()

    target_task = None
    parent_task = None

    for task in queue.get("tasks", []):
        if task.get("id") == task_id:
            target_task = task
            break
        for sub in task.get("subtasks", []):
            if sub.get("id") == task_id:
                target_task = sub
                parent_task = task
                break
        if target_task:
            break

    if not target_task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    from_status = target_task.get("status", "pending")

    if not _validate_transition(from_status, req.to_status):
        raise HTTPException(
            status_code=400,
            detail=f"不允许从 '{from_status}' 转换到 '{req.to_status}'"
        )

    target_task["status"] = req.to_status
    target_task["updated"] = datetime.now().strftime("%Y-%m-%d")

    _append_history(queue, task_id, from_status, req.to_status, req.by)
    _write_queue(queue)

    # WebSocket 推送
    try:
        from websocket_manager import manager as ws_manager
        import asyncio
        asyncio.create_task(ws_manager.push_queue_update(queue))
    except Exception:
        pass

    return {
        "success": True,
        "task_id": task_id,
        "from": from_status,
        "to": req.to_status,
        "message": f"状态已从 '{from_status}' 变更为 '{req.to_status}'"
    }


@router.get("/api/loop/sprint")
def get_sprint_info():
    """返回 sprint 摘要信息"""
    queue = _read_queue()
    tasks = queue.get("tasks", [])

    # 统计子任务状态
    status_counts: dict[str, int] = {}
    for task in tasks:
        for sub in task.get("subtasks", []):
            s = sub.get("status", "pending")
            status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "sprint": queue.get("sprint"),
        "status": queue.get("status"),
        "loop_mode": queue.get("loop_mode"),
        "total_tasks": len(tasks),
        "total_subtasks": sum(len(t.get("subtasks", [])) for t in tasks),
        "subtask_status_counts": status_counts,
        "coordinator": queue.get("meta", {}).get("coordinator"),
    }
