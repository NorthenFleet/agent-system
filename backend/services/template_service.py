from __future__ import annotations
"""
Task Template Service — 模板业务逻辑层

提供模板 CRUD + 从模板创建任务。
"""
from typing import Optional, Sequence, Tuple, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models.v2_models import TaskTemplate, Task


class TemplateService:
    """任务模板业务逻辑服务"""

    def __init__(self, db: Session):
        self.db = db

    # ── CRUD ──

    def list_templates(
        self,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[Sequence[TaskTemplate], int]:
        """模板列表，支持 category 筛选和分页"""
        skip = (page - 1) * page_size
        query = self.db.query(TaskTemplate)
        if category:
            query = query.filter(TaskTemplate.category == category)
        query = query.order_by(TaskTemplate.created_at.desc())
        total = query.count()
        templates = query.offset(skip).limit(page_size).all()
        return templates, total

    def get_template(self, template_id: int) -> Optional[TaskTemplate]:
        """获取单个模板"""
        return self.db.query(TaskTemplate).filter(
            TaskTemplate.id == template_id
        ).first()

    def create_template(
        self,
        name: str,
        template_data: dict,
        description: str = "",
        category: str = "",
        is_system: bool = False,
        created_by: Optional[int] = None,
    ) -> TaskTemplate:
        """创建模板"""
        template = TaskTemplate(
            name=name,
            description=description,
            template_data=template_data,
            category=category if category else None,
            is_system=is_system,
            usage_count=0,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def update_template(
        self, template_id: int, updates: Dict
    ) -> Optional[TaskTemplate]:
        """更新模板（仅更新提供的字段）"""
        template = self.get_template(template_id)
        if not template:
            return None
        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)
        template.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: int) -> Tuple[bool, str]:
        """删除模板（系统模板不可删）

        Returns (success, message)
        """
        template = self.get_template(template_id)
        if not template:
            return False, "模板不存在"
        if template.is_system:
            return False, "系统模板不可删除"
        self.db.delete(template)
        self.db.commit()
        return True, "模板已删除"

    # ── 从模板创建任务 ──

    def create_task_from_template(
        self,
        template_id: int,
        overrides: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """从模板创建任务

        1. 读取模板的 template_data 作为默认值
        2. 合并请求体中的 overrides 覆盖字段
        3. 生成新的 task_id
        4. 写入 tasks 表
        5. 更新模板 usage_count
        6. 返回创建的任务信息
        """
        template = self.get_template(template_id)
        if not template:
            return None

        # 模板默认值
        task_data = dict(template.template_data or {})
        # 覆盖字段
        if overrides:
            task_data.update(overrides)

        now = datetime.now(timezone.utc)
        task_id = f"tmpl-{template_id}-{int(now.timestamp()*1000000)}"

        task = Task(
            task_id=task_id,
            title=task_data.get("title", template.name),
            description=task_data.get("description", template.description),
            type=task_data.get("type", "general"),
            status=task_data.get("status", "pending"),
            priority=task_data.get("priority", "medium"),
            assignee=task_data.get("assignee"),
            source="template",
            sprint=task_data.get("sprint"),
            created_by=str(template.created_by) if template.created_by else None,
            created_at=now,
            updated_at=now,
            tags=task_data.get("tags", []),
            parent_task_id=task_data.get("parent_task_id"),
            due_date=task_data.get("due_date"),
            start_date=task_data.get("start_date"),
        )
        self.db.add(task)

        # 更新模板使用次数
        template.usage_count = (template.usage_count or 0) + 1
        template.updated_at = now

        self.db.commit()
        self.db.refresh(task)

        return task.to_dict()
