"""
计划与任务管理 API
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
import re

router = APIRouter(tags=["planning"])

# ==================== Pydantic Models ====================

class PlanCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""
    priority: str = "medium"
    due_date: Optional[str] = None
    
    def validate_priority(self) -> str:
        priority_map = {
            "critical": 1,
            "high": 2, 
            "medium": 3,
            "low": 4
        }
        p = self.priority.lower()
        if p not in priority_map:
            raise ValueError("优先级必须为 critical/high/medium/low 之一")
        return p
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "2024Q1 Sprint",
                "description": "完成核心功能开发",
                "priority": "high",
                "due_date": "2024-12-31"
            }
        }

class TaskCreate(BaseModel):
    plan_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""
    priority: str = "medium"
    status: str = "pending"
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    estimated_hours: Optional[float] = None
    
    def validate_priority(self) -> str:
        valid_priorities = ["critical", "high", "medium", "low"]
        p = self.priority.lower()
        if p not in valid_priorities:
            raise ValueError("优先级必须为 critical/high/medium/low 之一")
        return p

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    completed_hours: Optional[float] = None

class ContextCreate(BaseModel):
    plan_id: str
    title: str
    content: str
    metadata: Optional[dict] = None

class SubtaskCreate(BaseModel):
    parent_task_id: str
    title: str
    description: Optional[str] = None
    order: int = 0

class LogEntry(BaseModel):
    plan_id: str
    entry: str
    metadata: Optional[dict] = None

class TaskCompletion(BaseModel):
    completed_hours: float
    notes: Optional[str] = ""

# ==================== 计划 CRUD ====================

@router.post("/api/v2/plans", status_code=201)
async def create_plan(plan_data: PlanCreate):
    """创建计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    plan = data_manager.create_plan(
        plan_data.title,
        plan_data.description,
        priority=plan_data.priority,
        due_date=plan_data.due_date
    )
    return plan

@router.get("/api/v2/plans")
def list_plans(
    priority: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    """列���计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    result = data_manager.get_plans(priority=priority, status=status_filter, search=search)
    start = (page - 1) * page_size
    end = start + page_size
    plans = result.get("plans", [])
    return {
        "plans": plans[start:end],
        "total": len(plans),
        "page": page,
        "page_size": page_size,
        "total_pages": (len(plans) + page_size - 1) // page_size
    }

@router.get("/api/v2/plans/{plan_id}")
def get_plan(plan_id: str):
    """获取计划详情"""
    try:
        from data_manager import DataManager
        data_manager = DataManager()
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    plan = data_manager.get_plan(plan_id_int)
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    # 加载子数据
    result = dict(plan)
    
    result["tasks"] = data_manager.get_tasks(plan_id_int)
    result["contexts"] = data_manager.get_contexts(plan_id_int)
    result["logs"] = data_manager.get_logs(plan_id_int)
    
    return result

@router.put("/api/v2/plans/{plan_id}")
def update_plan(plan_id: str, update_data: dict):
    """更新计划"""
    try:
        from data_manager import DataManager
        data_manager = DataManager()
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    updated_plan = data_manager.update_plan(plan_id_int, update_data)
    if not updated_plan:
        raise HTTPException(404, "Plan not found")
    return updated_plan

@router.delete("/api/v2/plans/{plan_id}")
def delete_plan(plan_id: str):
    """删除计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_plan(plan_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Plan {plan_id} not found")

# ==================== 计划状态机 ====================

@router.post("/api/v2/plans/{plan_id}/status")
def update_plan_status(plan_id: str, new_status: str):
    """更新计划状态"""
    from data_manager import DataManager
    data_manager = DataManager()
    plan = data_manager.update_plan(plan_id, {"status": new_status})
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan

@router.post("/api/v2/plans/{plan_id}/start")
def start_plan(plan_id: str):
    """启动计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    plan = data_manager.update_plan(plan_id, {"status": "active"})
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan

@router.post("/api/v2/plans/{plan_id}/complete")
def complete_plan(plan_id: str):
    """完成计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    plan = data_manager.update_plan(plan_id, {"status": "completed"})
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan

@router.post("/api/v2/plans/{plan_id}/archive")
def archive_plan(plan_id: str):
    """归档计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    plan = data_manager.update_plan(plan_id, {"status": "archived"})
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan

@router.post("/api/v2/plans/{plan_id}/pause")
def pause_plan(plan_id: str):
    """暂停计划"""
    from data_manager import DataManager
    data_manager = DataManager()
    plan = data_manager.update_plan(plan_id, {"status": "paused"})
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan

# ==================== 任务 CRUD ====================

@router.post("/api/v2/plans/{plan_id}/tasks", status_code=201)
def create_task(plan_id: str, task_data: TaskCreate):
    """创建任务"""
    try:
        from data_manager import DataManager
        data_manager = DataManager()
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    task = data_manager.create_task(
        plan_id_int,
        task_data.title,
        task_data.description,
        priority=task_data.priority,
        status=task_data.status,
        assignee=task_data.assignee,
        due_date=task_data.due_date,
        estimated_hours=task_data.estimated_hours
    )
    return task

@router.get("/api/v2/plans/{plan_id}/tasks")
def list_tasks(
    plan_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None
):
    """列出计划任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    try:
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    tasks = data_manager.get_tasks(plan_id=plan_id_int, status=status, priority=priority)
    
    if assignee:
        tasks = [t for t in tasks if t.get("assignee") == assignee]
    
    return {"tasks": tasks}

@router.get("/api/v2/tasks/{task_id}")
def get_task(task_id: str):
    """获取任务详情"""
    from data_manager import DataManager
    data_manager = DataManager()
    try:
        task_id_int = int(task_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 task_id")
    
    task = data_manager.get_task(task_id_int)
    if not task:
        raise HTTPException(404, "Task not found")
    
    result = dict(task)
    # 加载上下文
    result["contexts"] = data_manager.get_contexts_for_task(task_id_int)
    # 加载子任务
    if "subtasks" in result:
        subtasks = result.pop("subtasks")
        result["subtasks"] = json.loads(subtasks) if isinstance(subtasks, str) else subtasks
    return result

@router.put("/api/v2/tasks/{task_id}")
def update_task(task_id: str, update_data: TaskUpdate):
    """更新任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    filtered_update = update_data.dict(exclude_none=True)
    
    updated_task = data_manager.update_task(task_id, filtered_update)
    if not updated_task:
        raise HTTPException(404, "Task not found")
    
    return {"updated_task": updated_task}

@router.delete("/api/v2/tasks/{task_id}")
def delete_task(task_id: str):
    """删除任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_task(task_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Task {task_id} not found")

# ==================== 任务状态机 ====================

@router.post("/api/v2/tasks/{task_id}/status")
def update_task_status(task_id: str, new_status: str):
    """更新任务状态"""
    from data_manager import DataManager
    data_manager = DataManager()
    updated_task = data_manager.update_task(task_id, {"status": new_status})
    if not updated_task:
        raise HTTPException(404, "Task not found")
    return updated_task

@router.post("/api/v2/tasks/{task_id}/start")
def start_task(task_id: str):
    """开始任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    updated_task = data_manager.update_task(task_id, {"status": "running"})
    if not updated_task:
        raise HTTPException(404, "Task not found")
    return updated_task

@router.post("/api/v2/tasks/{task_id}/pause")
def pause_task(task_id: str):
    """暂停任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    updated_task = data_manager.update_task(task_id, {"status": "paused"})
    if not updated_task:
        raise HTTPException(404, "Task not found")
    return updated_task

@router.post("/api/v2/tasks/{task_id}/complete")
def complete_task(task_id: str, completion_data: TaskCompletion):
    """完成任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    updated_task = data_manager.update_task(
        task_id,
        {"status": "completed", "completed_hours": completion_data.completed_hours}
    )
    if not updated_task:
        raise HTTPException(404, "Task not found")
    return updated_task

# ==================== 上下文 CRUD ====================

@router.post("/api/v2/plans/{plan_id}/contexts", status_code=201)
def create_context(plan_id: str, context_data: ContextCreate):
    """创建上下文"""
    try:
        from data_manager import DataManager
        data_manager = DataManager()
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    context = data_manager.create_context(
        plan_id_int,
        context_data.title,
        context_data.content,
        metadata=context_data.metadata
    )
    return context

@router.get("/api/v2/plans/{plan_id}/contexts")
def list_contexts(plan_id: str):
    """列出上下文"""
    from data_manager import DataManager
    data_manager = DataManager()
    try:
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    contexts = data_manager.get_contexts(plan_id=plan_id_int)
    return {"contexts": contexts}

@router.put("/api/v2/contexts/{context_id}")
def update_context(context_id: str, content: str):
    """更新上下文"""
    from data_manager import DataManager
    data_manager = DataManager()
    updated_context = data_manager.update_context(context_id, content)
    if not updated_context:
        raise HTTPException(404, "Context not found")
    return updated_context

@router.delete("/api/v2/contexts/{context_id}")
def delete_context(context_id: str):
    """删除上下文"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_context(context_id)
    if success:
        return {"success": True}
    raise HTTPException(404, "Context not found")

# ==================== 子任务 ====================

@router.post("/api/v2/tasks/{task_id}/subtasks", status_code=201)
def create_subtask(task_id: str, subtask: SubtaskCreate):
    """创建子任务"""
    from data_manager import DataManager
    from datetime import datetime
    data_manager = DataManager()
    
    new_subtask = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "title": subtask.title,
        "content": subtask.description or "",
        "completed": False,
        "order": subtask.order,
        "created_at": datetime.now().isoformat()
    }
    
    success = data_manager.add_subtask(task_id, new_subtask)
    if not success:
        raise HTTPException(404, "Task not found")
    
    return new_subtask

@router.put("/api/v2/tasks/subtasks/{subtask_id}/toggle")
def toggle_subtask(subtask_id: str):
    """切换子任务状态"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.toggle_subtask(subtask_id)
    if not success:
        raise HTTPException(404, "Subtask not found")
    return {"success": True}

# ==================== 日志 ====================

@router.post("/api/v2/plans/{plan_id}/logs", status_code=201)
def create_log(plan_id: str, log_data: LogEntry):
    """创建日志"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    try:
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    # 检查计划是否存在
    plan = data_manager.get_plan(plan_id_int)
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    log = data_manager.create_log(
        plan_id_int,
        log_data.entry,
        metadata=log_data.metadata
    )
    return log

@router.get("/api/v2/plans/{plan_id}/logs")
def list_logs(plan_id: str, limit: int = 50):
    """列出计划���志"""
    from data_manager import DataManager
    data_manager = DataManager()
    try:
        plan_id_int = int(plan_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "无效的 plan_id")
    
    logs = data_manager.get_logs(plan_id=plan_id_int)
    return {"logs": logs[-limit:]}
