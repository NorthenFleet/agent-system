"""
V2 任务管理 API 路由
GET    /api/v2/tasks
POST   /api/v2/tasks
GET    /api/v2/tasks/{task_id}
PUT    /api/v2/tasks/{task_id}
DELETE /api/v2/tasks/{task_id}
POST   /api/v2/tasks/{task_id}/assign
POST   /api/v2/tasks/{task_id}/comment
GET    /api/v2/tasks/{task_id}/comments
GET    /api/v2/tasks/stats
GET    /api/v2/tasks/gantt
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models.v2_models import get_session, Task
from services.task_service import TaskService
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/tasks", tags=["v2-tasks"])


def _parse_datetime(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def get_task_service(db: Session = Depends(get_session)) -> TaskService:
    return TaskService(db)


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    type: str = "general"
    priority: str = "medium"
    assignee: Optional[str] = None
    sprint: Optional[int] = None
    tags: List[str] = []
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    parent_task_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    progress: Optional[int] = None
    sprint: Optional[int] = None
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    tags: Optional[List[str]] = None


class AssignRequest(BaseModel):
    assignee: str
    comment: Optional[str] = None


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


@router.get("")
@router.get("/")
def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    sprint: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    return service.search_tasks(
        status=status,
        priority=priority,
        assignee=assignee,
        sprint=sprint,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_task(
    data: TaskCreate,
    user: dict = Depends(require_role("admin", "agent")),
    service: TaskService = Depends(get_task_service),
):
    task_data = {
        "title": data.title,
        "description": data.description,
        "type": data.type,
        "priority": data.priority,
        "assignee": data.assignee,
        "sprint": data.sprint,
        "tags": data.tags,
        "due_date": _parse_datetime(data.due_date),
        "start_date": _parse_datetime(data.start_date),
        "parent_task_id": data.parent_task_id,
    }
    task = service.create_task(task_data, created_by=user.get("username"))
    return task.to_dict()


@router.get("/stats")
def task_stats(
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    return service.get_full_stats()


@router.get("/gantt")
def gantt_data(
    sprint: Optional[int] = Query(None),
    assignee: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    return service.get_gantt_data(sprint=sprint, assignee=assignee)


@router.get("/{task_id}")
def get_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    task = service.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {
        **task.to_dict(),
        "comments": service.get_comments(task_id),
        "history": service.get_history(task_id),
    }


@router.put("/{task_id}")
def update_task(
    task_id: str,
    data: TaskUpdate,
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    update_data = {}
    if data.title is not None:
        update_data["title"] = data.title
    if data.description is not None:
        update_data["description"] = data.description
    if data.status is not None:
        update_data["status"] = data.status
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.assignee is not None:
        update_data["assignee"] = data.assignee
    if data.progress is not None:
        update_data["progress"] = data.progress
    if data.sprint is not None:
        update_data["sprint"] = data.sprint
    if data.due_date is not None:
        update_data["due_date"] = _parse_datetime(data.due_date)
    if data.start_date is not None:
        update_data["start_date"] = _parse_datetime(data.start_date)
    if data.tags is not None:
        update_data["tags"] = data.tags

    task = service.update_task_by_task_id(task_id, update_data, changed_by=user.get("username"))
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict()


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    user: dict = Depends(require_role("admin")),
    service: TaskService = Depends(get_task_service),
):
    success = service.delete_task_by_task_id(task_id)
    if not success:
        raise HTTPException(404, "任务不存在")
    return {"message": "任务已删除", "task_id": task_id}


@router.post("/{task_id}/assign")
def assign_task(
    task_id: str,
    data: AssignRequest,
    user: dict = Depends(require_role("admin")),
    service: TaskService = Depends(get_task_service),
):
    task = service.assign_task(task_id, data.assignee, changed_by=user.get("username"))
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict()


@router.post("/{task_id}/comment", status_code=201)
def add_comment(
    task_id: str,
    data: CommentCreate,
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    comment = service.add_comment(task_id, user_id=user.get("sub"), content=data.content)
    if not comment:
        raise HTTPException(404, "任务不存在")
    return comment.to_dict()


@router.get("/{task_id}/comments")
def get_comments(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    comments = service.get_comments(task_id)
    return {
        "comments": comments,
        "total": len(comments),
    }