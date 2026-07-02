"""
V2 任务管理 API 路由 (Service 层重构版)

所有端点通过 TaskService 调用，路由层仅负责请求解析和响应构造。
API 路径和请求/响应格式保持不变（前端兼容）。

GET    /api/v2/tasks                — 任务列表（筛选 + 分页）
GET    /api/v2/tasks/stats          — 任务统计
GET    /api/v2/tasks/gantt          — 甘特图数据
GET    /api/v2/tasks/{id}           — 任务详情
POST   /api/v2/tasks                — 创建任务（admin/agent）
PUT    /api/v2/tasks/{id}           — 更新任务（负责人/admin）
DELETE /api/v2/tasks/{id}           — 删除任务（admin）
POST   /api/v2/tasks/{id}/assign    — 分配任务（admin）
POST   /api/v2/tasks/{id}/comments  — 添加评论
GET    /api/v2/tasks/{id}/comments  — 任务评论列表

@author 🟥 拉斐尔 (后端开发)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid

from services.task_service import TaskService
from services.user_service import UserService
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/tasks", tags=["v2-tasks"])


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    type: str = "general"
    priority: str = "medium"
    assignee: Optional[str] = None
    sprint: Optional[int] = None
    dev_spec: Optional[str] = None
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    tags: List[str] = []
    parent_task_id: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    progress: Optional[int] = None
    sprint: Optional[int] = None
    dev_spec: Optional[str] = None
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    tags: Optional[List[str]] = None
    parent_task_id: Optional[str] = None


class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class AssignRequest(BaseModel):
    assignee: str
    comment: Optional[str] = None


def get_task_service():
    from models.v2_models import get_session
    from sqlalchemy.orm import Session
    def _get(db: Session = Depends(get_session)) -> TaskService:
        return TaskService(db)
    return _get


def get_user_service():
    from models.v2_models import get_session
    from sqlalchemy.orm import Session
    def _get(db: Session = Depends(get_session)) -> UserService:
        return UserService(db)
    return _get


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _can_edit_task(user: dict, task) -> bool:
    return user.get("role") == "admin" or user.get("username") == task.assignee


@router.get("/stats")
def get_task_stats(
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service()),
):
    return svc.get_stats()


@router.get("/gantt")
def get_gantt_data(
    sprint: Optional[int] = Query(None),
    assignee: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service()),
):
    return svc.get_gantt_data(sprint=sprint, assignee=assignee)


@router.get("")
@router.get("/")
def list_tasks(
    status: Optional[str] = Query(None, description="按状态筛选"),
    priority: Optional[str] = Query(None, description="按优先级筛选"),
    assignee: Optional[str] = Query(None, description="按负责人筛选"),
    sprint: Optional[int] = Query(None, description="按 sprint 筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service()),
):
    filters: Dict[str, Any] = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if assignee:
        filters["assignee"] = assignee
    if sprint is not None:
        filters["sprint"] = sprint

    tasks = svc.list(
        skip=(page - 1) * page_size,
        limit=page_size,
        order_by="created_at",
        order_desc=True,
        filters=filters if filters else None,
    )
    total = svc.count(filters=filters if filters else None)

    return {
        "tasks": [t.to_dict() for t in tasks],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{task_id}")
def get_task(
    task_id: str,
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service()),
):
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict(include_comments=True, include_history=True)


@router.post("")
@router.post("/")
def create_task(
    req: TaskCreateRequest,
    user: dict = Depends(require_role("admin", "agent")),
    svc: TaskService = Depends(get_task_service()),
):
    task_data: Dict[str, Any] = {
        "task_id": f"task-{uuid.uuid4().hex[:8]}",
        "title": req.title,
        "description": req.description,
        "type": req.type,
        "priority": req.priority,
        "assignee": req.assignee,
        "sprint": req.sprint,
        "dev_spec": req.dev_spec,
        "created_by": user.get("username"),
        "due_date": _parse_dt(req.due_date),
        "start_date": _parse_dt(req.start_date) or datetime.now(timezone.utc),
        "tags": req.tags or [],
        "parent_task_id": req.parent_task_id,
    }
    if req.assignee:
        task_data["status"] = "assigned"

    task = svc.create_task(task_data)
    return {"success": True, "task": task.to_dict()}


@router.put("/{task_id}")
def update_task(
    task_id: str,
    req: TaskUpdateRequest,
    user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service()),
):
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if not _can_edit_task(user, task):
        raise HTTPException(403, "仅负责人或管理员可修改此任务")

    update_data = req.model_dump(exclude_unset=True)
    if update_data.get("progress") is not None:
        if update_data["progress"] < 0 or update_data["progress"] > 100:
            raise HTTPException(400, "progress 必须在 0-100 之间")

    updated_task = svc.update_task_by_task_id(task_id, update_data, changed_by=user.get("username"))
    return {"success": True, "task": updated_task.to_dict()}


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    _user: dict = Depends(require_role("admin")),
    svc: TaskService = Depends(get_task_service()),
):
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    svc.delete_by_task_id(task_id)
    return {"success": True, "message": f"任务 {task_id} 已删除"}


@router.get("/{task_id}/comments")
def get_comments(
    task_id: str,
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service()),
):
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    comments = svc.get_comments(task_id)
    return {"comments": [c.to_dict() for c in comments], "total": len(comments)}


@router.post("/{task_id}/comments")
def create_comment(
    task_id: str,
    req: CommentCreateRequest,
    user: dict = Depends(get_current_user),
    task_svc: TaskService = Depends(get_task_service()),
    user_svc: UserService = Depends(get_user_service()),
):
    task = task_svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if not req.content.strip():
        raise HTTPException(400, "评论内容不能为空")

    db_user = user_svc.get_by_username(user["username"])

    comment = task_svc.add_comment(
        task_id=task_id,
        user_id=db_user.id if db_user else None,
        content=req.content.strip(),
    )
    return {"success": True, "comment": comment.to_dict()}


@router.post("/{task_id}/assign")
def assign_task(
    task_id: str,
    req: AssignRequest,
    _user: dict = Depends(require_role("admin")),
    svc: TaskService = Depends(get_task_service()),
):
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    updated_task = svc.assign_task(task_id, req.assignee, changed_by=_user.get("username"))
    return {"success": True, "task": updated_task.to_dict()}