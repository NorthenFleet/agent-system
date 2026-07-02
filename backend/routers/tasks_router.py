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
from sqlalchemy.orm import Session

from models.v2_models import get_session, Task, TaskHistory, User
from services.task_service import TaskService
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/tasks", tags=["v2-tasks"])


# ---------- Request Models ----------

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


# ---------- Service Factory ----------

def get_task_service(db: Session = Depends(get_session)) -> TaskService:
    """依赖注入：获取 TaskService 实例"""
    return TaskService(db)


# ---------- Helpers ----------

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _can_edit_task(user: dict, task: Task) -> bool:
    """admin 或任务负责人可编辑"""
    return user.get("role") == "admin" or user.get("username") == task.assignee


def _record_history(db: Session, task_id: str, field: str, old_val, new_val, changed_by: str):
    """记录变更历史"""
    h = TaskHistory(
        task_id=task_id,
        field=field,
        old_value=str(old_val) if old_val is not None else None,
        new_value=str(new_val) if new_val is not None else None,
        changed_by=changed_by,
    )
    db.add(h)


# ---------- Endpoints ----------
# ⚠️ 静态路由（/stats, /gantt）必须在动态路由（/{task_id}）之前定义！

@router.get("/stats")
def get_task_stats(
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service),
):
    """任务统计（按状态/优先级/负责人汇总）"""
    return svc.get_stats()


@router.get("/gantt")
def get_gantt_data(
    sprint: Optional[int] = Query(None),
    assignee: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """甘特图数据（仅含 start_date 的任务）"""
    try:
        q = db.query(Task).filter(Task.start_date != None)
        if sprint:
            q = q.filter(Task.sprint == sprint)
        if assignee:
            q = q.filter(Task.assignee == assignee)

        tasks = q.order_by(Task.start_date.asc()).all()

        # Group by parent
        result = []
        parents = [t for t in tasks if not t.parent_task_id]
        children = [t for t in tasks if t.parent_task_id]

        for p in parents:
            item = {
                "task_id": p.task_id,
                "title": p.title,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "due_date": p.due_date.isoformat() if p.due_date else None,
                "progress": p.progress,
                "assignee": p.assignee,
                "status": p.status,
                "subtasks": [],
            }
            for c in children:
                if c.parent_task_id == p.task_id:
                    item["subtasks"].append({
                        "task_id": c.task_id,
                        "title": c.title,
                        "assignee": c.assignee,
                        "status": c.status,
                        "start_date": c.start_date.isoformat() if c.start_date else None,
                        "due_date": c.due_date.isoformat() if c.due_date else None,
                    })
            result.append(item)

        # Orphan tasks
        parent_ids = {p.task_id for p in parents}
        for t in tasks:
            if t.parent_task_id and t.parent_task_id not in parent_ids:
                result.append({
                    "task_id": t.task_id,
                    "title": t.title,
                    "start_date": t.start_date.isoformat() if t.start_date else None,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "progress": t.progress,
                    "assignee": t.assignee,
                    "status": t.status,
                    "subtasks": [],
                })

        return {"tasks": result}
    finally:
        db.close()


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
    svc: TaskService = Depends(get_task_service),
):
    """任务列表（支持筛选 + 分页）"""
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
    svc: TaskService = Depends(get_task_service),
):
    """任务详情"""
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict(include_comments=True, include_history=True)


@router.post("")
@router.post("/")
def create_task(
    req: TaskCreateRequest,
    user: dict = Depends(require_role("admin", "agent")),
    svc: TaskService = Depends(get_task_service),
):
    """创建任务（admin / agent）"""
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
    svc: TaskService = Depends(get_task_service),
    db: Session = Depends(get_session),
):
    """更新任务（负责人 / admin）"""
    try:
        task = svc.get_by_task_id(task_id)
        if not task:
            raise HTTPException(404, "任务不存在")
        if not _can_edit_task(user, task):
            raise HTTPException(403, "仅负责人或管理员可修改此任务")

        changed_by = user.get("username")
        fields = req.model_dump(exclude_unset=True)
        for field, value in fields.items():
            old_val = getattr(task, field)
            if old_val != value:
                _record_history(db, task_id, field, old_val, value, changed_by)
                setattr(task, field, value)

        # 自动处理状态变更
        if req.status == "done" and not task.completed_at:
            task.completed_at = datetime.now(timezone.utc)
            task.progress = 100
            _record_history(db, task_id, "progress", task.progress, 100, changed_by)
            _record_history(db, task_id, "completed_at", None, task.completed_at, changed_by)

        if req.progress is not None:
            if req.progress < 0 or req.progress > 100:
                raise HTTPException(400, "progress 必须在 0-100 之间")

        task.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)

        svc._cache_invalidate("by_id", task_id)
        svc._cache_invalidate("stats")

        return {"success": True, "task": task.to_dict()}
    finally:
        db.close()


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    _user: dict = Depends(require_role("admin")),
    svc: TaskService = Depends(get_task_service),
):
    """删除任务（仅 admin）"""
    task = svc.get_by_task_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    svc.delete(task.id)
    return {"success": True, "message": f"任务 {task_id} 已删除"}


@router.get("/{task_id}/comments")
def get_comments(
    task_id: str,
    _user: dict = Depends(get_current_user),
    svc: TaskService = Depends(get_task_service),
):
    """获取任务评论列表"""
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
    svc: TaskService = Depends(get_task_service),
    db: Session = Depends(get_session),
):
    """添加任务评论"""
    try:
        task = svc.get_by_task_id(task_id)
        if not task:
            raise HTTPException(404, "任务不存在")
        if not req.content.strip():
            raise HTTPException(400, "评论内容不能为空")

        db_user = db.query(User).filter(User.username == user["username"]).first()

        comment = svc.add_comment(
            task_id=task_id,
            user_id=db_user.id if db_user else None,
            content=req.content.strip(),
        )
        return {"success": True, "comment": comment.to_dict()}
    finally:
        db.close()


@router.post("/{task_id}/assign")
def assign_task(
    task_id: str,
    req: AssignRequest,
    _user: dict = Depends(require_role("admin")),
    svc: TaskService = Depends(get_task_service),
    db: Session = Depends(get_session),
):
    """分配任务给指定负责人"""
    try:
        task = svc.get_by_task_id(task_id)
        if not task:
            raise HTTPException(404, "任务不存在")

        old_assignee = task.assignee
        old_status = task.status
        task.assignee = req.assignee
        if task.status == "pending":
            task.status = "assigned"

        if old_assignee != req.assignee:
            _record_history(db, task_id, "assignee", old_assignee, req.assignee, _user.get("username"))
        if old_status != task.status:
            _record_history(db, task_id, "status", old_status, task.status, _user.get("username"))

        db.commit()
        db.refresh(task)

        svc._cache_invalidate("by_id", task_id)
        svc._cache_invalidate("stats")

        return {"success": True, "task": task.to_dict()}
    finally:
        db.close()
