"""
Task Repository — 任务表数据访问
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, desc, asc
import re

from repositories.base import BaseRepository
from models.v2_models import Task


class TaskRepository(BaseRepository[Task]):
    def __init__(self):
        super().__init__(Task)

    def get_by_task_id(self, db: Session, task_id: str) -> Optional[Task]:
        """根据 task_id 获取"""
        return db.query(Task).filter(Task.task_id == task_id).first()

    def get_by_assignee(self, db: Session, assignee: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某人的任务"""
        return db.query(Task).filter(Task.assignee == assignee).offset(skip).limit(limit).all()

    def get_by_status(self, db: Session, status: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某状态的任务"""
        return db.query(Task).filter(Task.status == status).offset(skip).limit(limit).all()

    def get_by_sprint(self, db: Session, sprint: int, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某 Sprint 的任务"""
        return db.query(Task).filter(Task.sprint == sprint).offset(skip).limit(limit).all()

    def get_by_priority(self, db: Session, priority: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取某优先级的任务"""
        return db.query(Task).filter(Task.priority == priority).offset(skip).limit(limit).all()

    def get_by_parent(self, db: Session, parent_task_id: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取子任务"""
        return db.query(Task).filter(Task.parent_task_id == parent_task_id).offset(skip).limit(limit).all()

    def get_stats(self, db: Session) -> Dict[str, Any]:
        """获取任务统计"""
        result = db.query(Task.status, sql_func.count(Task.id)).group_by(Task.status).all()
        total = db.query(sql_func.count(Task.id)).scalar()
        return {
            "total": total or 0,
            "by_status": {status: count for status, count in result},
        }

    def get_overdue(self, db: Session, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取逾期任务"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return (
            db.query(Task)
            .filter(Task.due_date < now, Task.status.notin_(["completed", "cancelled"]))
            .order_by(Task.due_date.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def search_tasks(
        self,
        db: Session,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        sprint: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """分页搜索任务"""
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
            "tasks": tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    def get_full_stats(self, db: Session) -> Dict[str, Any]:
        """获取完整任务统计"""
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

    def get_gantt_data(self, db: Session, sprint: Optional[int] = None, assignee: Optional[str] = None) -> List[Task]:
        """获取甘特图数据"""
        query = db.query(Task).filter(Task.start_date != None)
        if sprint:
            query = query.filter(Task.sprint == sprint)
        if assignee:
            query = query.filter(Task.assignee == assignee)
        return query.order_by(Task.start_date.asc()).all()

    def generate_task_id(self, db: Session) -> str:
        """生成下一个 task_id"""
        latest = db.query(Task.task_id).order_by(Task.task_id.desc()).first()
        if not latest:
            return "task-001"
        match = re.search(r'task-(\d+)', latest[0])
        if not match:
            return "task-001"
        num = int(match.group(1)) + 1
        return f"task-{num:03d}"

    def delete_by_task_id(self, db: Session, task_id: str) -> bool:
        """根据 task_id 删除任务"""
        task = self.get_by_task_id(db, task_id)
        if not task:
            return False
        db.delete(task)
        db.flush()
        return True

    def update_by_task_id(self, db: Session, task_id: str, update_data: Dict[str, Any]) -> Optional[Task]:
        """根据 task_id 更新任务"""
        task = self.get_by_task_id(db, task_id)
        if not task:
            return None
        for key, value in update_data.items():
            if hasattr(task, key):
                setattr(task, key, value)
        db.flush()
        return task
