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
import re

from models.v2_models import get_session, Task, TaskHistory, TaskComment, TaskTemplate
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/tasks", tags=["v2-tasks"])


# ---------- Pydantic Schemas ----------

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


# ---------- Helpers ----------

def _parse_datetime(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _gen_task_id(db) -> str:
    """生成下一个 task_id"""
    latest = db.query(Task.task_id).order_by(Task.task_id.desc()).first()
    if not latest:
        return "task-001"
    match = re.search(r'task-(\d+)', latest[0])
    if not match:
        return "task-001"
    num = int(match.group(1)) + 1
    return f"task-{num:03d}"


def _record_history(db, task_id, field, old_val, new_val, changed_by):
    h = TaskHistory(
        task_id=task_id,
        field=field,
        old_value=str(old_val) if old_val is not None else None,
        new_value=str(new_val) if new_val is not None else None,
        changed_by=changed_by,
    )
    db.add(h)


# ---------- API Endpoints ----------
# ⚠️ 静态路由必须在动态路由之前定义！

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
):
    db = get_session()
    try:
        query = db.query(Task)
        if status:
            query = query.filter(Task.status == status)
        if priority:
            query = query.filter(Task.priority == priority)
        if assignee:
            query = query.filter(Task.assignee == assignee)
        if sprint:
            query = query.filter(Task.sprint == sprint)
        if search:
            query = query.filter(Task.title.contains(search) | Task.description.contains(search))

        total = query.count()
        sort_col = getattr(Task, sort_by, Task.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        tasks = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "tasks": [t.to_dict() for t in tasks],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    finally:
        db.close()


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_task(
    data: TaskCreate,
    user: dict = Depends(require_role("admin", "agent")),
):
    db = get_session()
    try:
        task_id = _gen_task_id(db)
        now = datetime.now(timezone.utc)
        task = Task(
            task_id=task_id,
            title=data.title,
            description=data.description,
            type=data.type,
            priority=data.priority,
            assignee=data.assignee,
            sprint=data.sprint,
            tags=data.tags,
            due_date=_parse_datetime(data.due_date),
            start_date=_parse_datetime(data.start_date) or now,
            parent_task_id=data.parent_task_id,
            created_by=user.get("username"),
        )
        if data.assignee:
            task.status = "assigned"
        db.add(task)
        db.commit()
        return task.to_dict()
    finally:
        db.close()


@router.get("/stats")
def task_stats(user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        all_tasks = db.query(Task).all()
        total = len(all_tasks)
        by_status = {}
        by_priority = {}
        by_assignee = {}
        done_count = 0

        for t in all_tasks:
            by_status[t.status] = by_status.get(t.status, 0) + 1
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            key = t.assignee or "未分配"
            by_assignee[key] = by_assignee.get(key, 0) + 1
            if t.status == "done":
                done_count += 1

        # Sprint progress
        sprints = {}
        for t in all_tasks:
            if t.sprint:
                sk = f"sprint_{t.sprint}"
                if sk not in sprints:
                    sprints[sk] = {"total": 0, "done": 0}
                sprints[sk]["total"] += 1
                if t.status == "done":
                    sprints[sk]["done"] += 1
        for sk in sprints:
            sprints[sk]["rate"] = round(sprints[sk]["done"] / sprints[sk]["total"] * 100, 1) if sprints[sk]["total"] else 0

        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
            "by_assignee": by_assignee,
            "completion_rate": round(done_count / total * 100, 1) if total else 0,
            "sprint_progress": sprints,
        }
    finally:
        db.close()


@router.get("/gantt")
def gantt_data(
    sprint: Optional[int] = Query(None),
    assignee: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        query = db.query(Task).filter(Task.start_date != None)
        if sprint:
            query = query.filter(Task.sprint == sprint)
        if assignee:
            query = query.filter(Task.assignee == assignee)

        tasks = query.order_by(Task.start_date.asc()).all()

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

        # Also include orphan tasks (no parent)
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


# 动态路由必须在静态路由之后定义
@router.get("/{task_id}")
def get_task(task_id: str, user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            raise HTTPException(404, "任务不存在")
        return task.to_dict(include_comments=True, include_history=True)
    finally:
        db.close()


@router.put("/{task_id}")
def update_task(
    task_id: str,
    data: TaskUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            raise HTTPException(404, "任务不存在")

        changed_by = user.get("username")
        fields = data.model_dump(exclude_unset=True)
        for field, value in fields.items():
            old_val = getattr(task, field)
            if old_val != value:
                _record_history(db, task_id, field, old_val, value, changed_by)
                setattr(task, field, value)

        # 自动处理状态变更
        if data.status == "done" and not task.completed_at:
            task.completed_at = datetime.now(timezone.utc)
            task.progress = 100
            _record_history(db, task_id, "progress", task.progress, 100, changed_by)
            _record_history(db, task_id, "completed_at", None, task.completed_at, changed_by)

        task.updated_at = datetime.now(timezone.utc)
        db.commit()

        # TODO: WebSocket 推送
        return task.to_dict()
    finally:
        db.close()


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    user: dict = Depends(require_role("admin")),
):
    db = get_session()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            raise HTTPException(404, "任务不存在")
        db.delete(task)
        db.commit()
        return {"message": "任务已删除", "task_id": task_id}
    finally:
        db.close()


@router.post("/{task_id}/assign")
def assign_task(
    task_id: str,
    data: AssignRequest,
    user: dict = Depends(require_role("admin")),
):
    db = get_session()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            raise HTTPException(404, "任务不存在")

        old_assignee = task.assignee
        old_status = task.status
        task.assignee = data.assignee
        if task.status == "pending":
            task.status = "assigned"

        _record_history(db, task_id, "assignee", old_assignee, data.assignee, user.get("username"))
        if old_status != task.status:
            _record_history(db, task_id, "status", old_status, task.status, user.get("username"))

        db.commit()
        return task.to_dict()
    finally:
        db.close()


@router.post("/{task_id}/comment", status_code=201)
def add_comment(
    task_id: str,
    data: CommentCreate,
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            raise HTTPException(404, "任务不存在")

        comment = TaskComment(
            task_id=task_id,
            user_id=user.get("sub"),
            content=data.content,
        )
        db.add(comment)
        db.commit()
        return comment.to_dict()
    finally:
        db.close()


@router.get("/{task_id}/comments")
def get_comments(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_session()
    try:
        comments = db.query(TaskComment).filter(TaskComment.task_id == task_id).order_by(TaskComment.created_at.asc()).all()
        return {
            "comments": [c.to_dict() for c in comments],
            "total": len(comments),
        }
    finally:
        db.close()
