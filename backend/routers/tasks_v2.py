"""
V2 任务管理 API 路由

提供完整的任务管理功能，包括创建、查询、更新、删除、分配、评论等操作。
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models.v2_models import get_session, Task
from services.task_service import TaskService
from routers.auth_router import get_current_user, require_role

router = APIRouter(
    prefix="/api/v2/tasks",
    tags=["v2-tasks"],
    responses={
        401: {"description": "未登录或 Token 无效"},
        403: {"description": "权限不足"},
        404: {"description": "资源不存在"},
    },
)


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
    """创建任务请求模型"""
    title: str = Field(..., description="任务标题")
    description: str = Field("", description="任务描述")
    type: str = Field("general", description="任务类型")
    priority: str = Field("medium", description="优先级")
    assignee: Optional[str] = Field(None, description="负责人")
    sprint: Optional[int] = Field(None, description="Sprint 编号")
    tags: List[str] = Field([], description="标签列表")
    due_date: Optional[str] = Field(None, description="截止日期")
    start_date: Optional[str] = Field(None, description="开始日期")
    parent_task_id: Optional[str] = Field(None, description="父任务 ID")


class TaskUpdate(BaseModel):
    """更新任务请求模型"""
    title: Optional[str] = Field(None, description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    status: Optional[str] = Field(None, description="任务状态")
    priority: Optional[str] = Field(None, description="优先级")
    assignee: Optional[str] = Field(None, description="负责人")
    progress: Optional[int] = Field(None, description="进度 (0-100)")
    sprint: Optional[int] = Field(None, description="Sprint 编号")
    due_date: Optional[str] = Field(None, description="截止日期")
    start_date: Optional[str] = Field(None, description="开始日期")
    tags: Optional[List[str]] = Field(None, description="标签列表")


class AssignRequest(BaseModel):
    """任务分配请求模型"""
    assignee: str = Field(..., description="被分配人")
    comment: Optional[str] = Field(None, description="分配备注")


class CommentCreate(BaseModel):
    """评论创建请求模型"""
    content: str = Field(..., min_length=1, max_length=5000, description="评论内容")


@router.get("", summary="任务列表", description="获取任务列表，支持筛选、分页、排序")
@router.get("/", summary="任务列表")
def list_tasks(
    status: Optional[str] = Query(None, description="按状态筛选"),
    priority: Optional[str] = Query(None, description="按优先级筛选"),
    assignee: Optional[str] = Query(None, description="按负责人筛选"),
    sprint: Optional[int] = Query(None, description="按 Sprint 筛选"),
    source: Optional[str] = Query(None, description="按来源筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    return service.search_tasks(
        status=status,
        priority=priority,
        assignee=assignee,
        sprint=sprint,
        source=source,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("", status_code=201, summary="创建任务", description="创建新任务（需 admin 或 agent 角色）")
@router.post("/", status_code=201, summary="创建任务")
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


@router.get("/stats", summary="任务统计", description="获取任务统计数据")
def task_stats(
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    return service.get_full_stats()


@router.get("/gantt", summary="甘特图数据", description="获取甘特图数据")
def gantt_data(
    sprint: Optional[int] = Query(None, description="按 Sprint 筛选"),
    assignee: Optional[str] = Query(None, description="按负责人筛选"),
    user: dict = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
):
    return service.get_gantt_data(sprint=sprint, assignee=assignee)


@router.get("/{task_id}", summary="任务详情", description="获取任务详情")
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


@router.put("/{task_id}", summary="更新任务", description="更新任务信息")
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


@router.delete("/{task_id}", summary="删除任务", description="删除任务（需 admin 角色）")
def delete_task(
    task_id: str,
    user: dict = Depends(require_role("admin")),
    service: TaskService = Depends(get_task_service),
):
    success = service.delete_task_by_task_id(task_id)
    if not success:
        raise HTTPException(404, "任务不存在")
    return {"message": "任务已删除", "task_id": task_id}


@router.post("/{task_id}/assign", summary="分配任务", description="分配任务给指定负责人（需 admin 角色）")
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


@router.post("/{task_id}/comment", status_code=201, summary="添加评论", description="为任务添加评论")
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


@router.get("/{task_id}/comments", summary="任务评论", description="获取任务的评论列表")
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