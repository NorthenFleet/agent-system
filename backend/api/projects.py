"""
项目/任务管理 API (项目、任务、状态追踪)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(tags=["projects"])

# ==================== Pydantic Models ====================

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    status: str = "active"  # active / on_hold / completed / archived
    priority: str = "medium"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    team_members: Optional[list] = []
    tags: Optional[str] = None

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    team_members: Optional[list] = None
    tags: Optional[str] = None

class ProjectTaskCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    assignee: Optional[str] = None
    due_date: Optional[str] = None

class ProjectTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None

class TaskDependency(BaseModel):
    task_id: int
    depends_on: int

# ==================== 项目 CRUD ====================

@router.post("/api/v2/projects", status_code=201)
async def create_project(project: ProjectCreate):
    """创建项目"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    team_json = None
    if project.team_members:
        import json
        team_json = json.dumps(project.team_members)
    
    new_project = data_manager.create_project(
        title=project.title,
        description=project.description,
        status=project.status,
        priority=project.priority,
        start_date=project.start_date,
        end_date=project.end_date,
        team_members=team_json,
        tags=project.tags
    )
    return new_project

@router.get("/api/v2/projects")
async def list_projects(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    """列出项目"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    project_list = data_manager.get_projects()
    
    if status:
        project_list = [p for p in project_list if p.get("status") == status]
    if priority:
        project_list = [p for p in project_list if p.get("priority") == priority]
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "total": len(project_list),
        "page": page,
        "page_size": page_size,
        "total_pages": (len(project_list) + page_size - 1) // page_size,
        "projects": project_list[start:end]
    }

@router.get("/api/v2/projects/{project_id}")
async def get_project(project_id: str):
    """获取项目详情"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    project = data_manager.get_project(project_id_int)
    if not project:
        raise HTTPException(404, "project not found")
    
    result = dict(project)
    # 加载团队成员
    if project.get("team_members"):
        import json
        result["team_members_list"] = json.loads(project["team_members"])
    
    # 加载进度
    stats = data_manager.get_project_stats(project_id_int)
    result["progress"] = stats
    
    return result

@router.put("/api/v2/projects/{project_id}")
async def update_project(project_id: str, updates: ProjectUpdate):
    """更新项目信息"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    data = updates.dict(exclude_none=True)
    
    if data.get("team_members"):
        import json
        data["team_members"] = json.dumps(data["team_members"])
    
    updated = data_manager.update_project(project_id_int, data)
    if not updated:
        raise HTTPException(404, "project not found")
    
    return updated

@router.delete("/api/v2/projects/{project_id}")
async def delete_project(project_id: str):
    """删除项目"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.delete_project(project_id)
    if success:
        return {"success": True}
    raise HTTPException(404, "project not found")

# ==================== 项目任务 CRUD ====================

@router.post("/api/v2/projects/{project_id}/tasks", status_code=201)
async def create_project_task(project_id: str, task: ProjectTaskCreate):
    """创建项目任务"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_task = data_manager.create_project_task(
        project_id=project_id_int,
        title=task.title,
        description=task.description or "",
        status=task.status,
        priority=task.priority,
        assignee=task.assignee,
        due_date=task.due_date
    )
    
    if not new_task:
        raise HTTPException(404, "project not found")
    
    return new_task

@router.get("/api/v2/projects/{project_id}/tasks")
async def list_project_tasks(
    project_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None
):
    """列出项目任务"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    tasks = data_manager.get_project_tasks(project_id_int)
    
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if priority:
        tasks = [t for t in tasks if t.get("priority") == priority]
    
    return tasks

@router.get("/api/v2/tasks/{task_id}")
async def get_project_task(task_id: str):
    """获取单个任务详情"""
    try:
        task_id_int = int(task_id)
    except ValueError:
        raise HTTPException(400, "invalid task ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    task = data_manager.get_project_task(task_id_int)
    if not task:
        raise HTTPException(404, "task not found")
    
    return task

@router.put("/api/v2/tasks/{task_id}")
async def update_task(task_id: str, updates: ProjectTaskUpdate):
    """更新任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    data = updates.dict(exclude_none=True)
    
    updated = data_manager.update_project_task(task_id, data)
    if not updated:
        raise HTTPException(404, "task not found")
    
    return updated

@router.delete("/api/v2/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.delete_project_task(task_id)
    if success:
        return {"success": True}
    raise HTTPException(404, "task not found")

# ==================== 项目统计 ====================

@router.get("/api/v2/projects/{project_id}/stats")
async def get_project_stats(project_id: str):
    """获取项目统计"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    stats = data_manager.get_project_stats(project_id_int)
    if not stats:
        raise HTTPException(404, "project not found")
    
    return stats

@router.get("/api/v2/projects/{project_id}/progress")
async def get_project_progress(project_id: str):
    """获取项目进度报告"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    # 获取任务列表
    tasks = data_manager.get_project_tasks(project_id_int)
    total = len(tasks)
    if total == 0:
        return {"total": 0, "completed": 0, "in_progress": 0, "todo": 0, "percentage": 0}
    
    completed = len([t for t in tasks if t.get("status") == "completed"])
    in_progress = len([t for t in tasks if t.get("status") == "in_progress"])
    todo = len([t for t in tasks if t.get("status") == "todo"])
    
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "todo": todo,
        "percentage": round(completed / total * 100, 2)
    }

# ==================== 任务依赖 ====================

@router.post("/api/v2/tasks/{task_id}/dependencies")
async def add_task_dependency(task_id: str, dep: TaskDependency):
    """添加任务依赖"""
    try:
        task_id_int = int(task_id)
    except ValueError:
        raise HTTPException(400, "invalid task ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.add_task_dependency(task_id_int, dep.depends_on)
    if success:
        return {"success": True}
    raise HTTPException(400, "failed to add dependency")

@router.get("/api/v2/tasks/{task_id}/dependencies")
async def get_task_dependencies(task_id: str):
    """获取任务依赖列表"""
    try:
        task_id_int = int(task_id)
    except ValueError:
        raise HTTPException(400, "invalid task ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    deps = data_manager.get_task_dependencies(task_id_int)
    return deps

# ==================== 项目日志 ====================

@router.post("/api/v2/projects/{project_id}/logs")
async def add_project_log(project_id: str, log_data: dict):
    """添加项目日志"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    entry = data_manager.create_project_log(
        project_id_int,
        log_data.get("entry", log_data.get("content", "")),
        log_data.get("author"),
        log_data.get("metadata")
    )
    
    return entry

@router.get("/api/v2/projects/{project_id}/logs")
async def list_project_logs(project_id: str, limit: int = 50):
    """列出项目日志"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    logs = data_manager.get_project_logs(project_id_int)
    return logs[-limit:]

@router.get("/api/v2/projects/{project_id}/activities")
async def list_project_activities(project_id: str, limit: int = 50):
    """列出项目活动"""
    try:
        project_id_int = int(project_id)
    except ValueError:
        raise HTTPException(400, "invalid project ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    activities = data_manager.get_project_activities(project_id_int)
    return activities[-limit:]
