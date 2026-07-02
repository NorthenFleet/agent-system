"""
Task-Plan 数据模型定义

描述任务 (Task) 与开发计划 (Development Plan) 的从属关系
一对多关系：一个任务可以关联多个开发计划（方案迭代）

@author 拉斐尔 (🐢 后端开发)
@created 2026-04-16
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey,
    CheckConstraint, Numeric, Boolean, Index, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


def portable_enum(enum_class):
    return SAEnum(enum_class, native_enum=False, validate_strings=True)

# ============================================================================
# 枚举类型定义
# ============================================================================


class TaskStatusEnum(str, Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    TESTING = 'testing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    BLOCKED = 'blocked'


class TaskPriorityEnum(str, Enum):
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    CRITICAL = 'critical'


class PlanStatusEnum(str, Enum):
    DRAFT = 'draft'
    PENDING_REVIEW = 'pending_review'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    ARCHIVED = 'archived'


class PlanStepStatusEnum(str, Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    SKIPPED = 'skipped'
    BLOCKED = 'blocked'


class PlanTypeEnum(str, Enum):
    FRONTEND = 'frontend'
    BACKEND = 'backend'
    TESTING = 'testing'
    DESIGN = 'design'
    RESEARCH = 'research'
    GENERAL = 'general'


# ============================================================================
# 核心数据模型
# ============================================================================


class Task(Base):
    """
    任务模型 (Task Model)
    
    表示一个完整的工作任务，可关联多个开发计划
    """
    __tablename__ = 'tasks'

    # 基础信息
    id = Column(String(32), primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    priority = Column(portable_enum(TaskPriorityEnum), nullable=False, default=TaskPriorityEnum.NORMAL)

    # 状态信息
    status = Column(portable_enum(TaskStatusEnum), nullable=False, default=TaskStatusEnum.PENDING)
    progress = Column(Integer, nullable=False, default=0)

    # 人员信息
    assignee = Column(String(100), nullable=False)
    creator = Column(String(100), nullable=False)

    # 时间信息
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    deadline = Column(DateTime(timezone=True))

    # 从属关系
    active_plan_id = Column(String(64), ForeignKey('plans.id', ondelete='SET NULL'))

    # 扩展字段
    context = Column(JSON, default=dict)
    subtasks = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    extra_metadata = Column('metadata', JSON, default=dict)

    # 关系
    plans = relationship(
        'DevelopmentPlan',
        back_populates='task',
        cascade='all, delete-orphan',
        foreign_keys='DevelopmentPlan.task_id',
    )
    active_plan = relationship('DevelopmentPlan', foreign_keys=[active_plan_id], post_update=True)

    # 约束
    __table_args__ = (
        CheckConstraint('progress >= 0 AND progress <= 100', name='tasks_progress_check'),
        CheckConstraint('deadline IS NULL OR deadline > created_at', name='tasks_deadline_check'),
        Index('idx_tasks_status', 'status'),
        Index('idx_tasks_priority', 'priority'),
        Index('idx_tasks_assignee', 'assignee'),
        Index('idx_tasks_creator', 'creator'),
        Index('idx_tasks_deadline', 'deadline'),
        Index('idx_tasks_created_at', 'created_at'),
        Index('idx_tasks_updated_at', 'updated_at'),
        Index('idx_tasks_active_plan', 'active_plan_id'),
    )

    @validates('progress')
    def validate_progress(self, key, value):
        if value < 0 or value > 100:
            raise ValueError('Progress must be between 0 and 100')
        return value

    def to_dict(self, include_plans: bool = False, include_active_plan: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'priority': self.priority.value if self.priority else None,
            'status': self.status.value if self.status else None,
            'progress': self.progress,
            'assignee': self.assignee,
            'creator': self.creator,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'active_plan_id': self.active_plan_id,
            'context': self.context or {},
            'subtasks': self.subtasks or [],
            'tags': self.tags or [],
            'metadata': self.extra_metadata or {},
        }

        if include_active_plan and self.active_plan:
            data['activePlan'] = self.active_plan.to_dict()

        if include_plans:
            data['plans'] = [plan.to_dict() for plan in self.plans]

        return data


class DevelopmentPlan(Base):
    """
    开发计划模型 (Development Plan Model)
    
    任务的从属对象，描述如何完成任务的详细方案
    一个任务可以有多个计划（方案迭代），但同一时间只有一个激活计划
    """
    __tablename__ = 'plans'

    # 基础信息
    id = Column(String(64), primary_key=True)
    task_id = Column(String(32), ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(500), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    type = Column(portable_enum(PlanTypeEnum), nullable=False, default=PlanTypeEnum.GENERAL)

    # 状态信息
    status = Column(portable_enum(PlanStatusEnum), nullable=False, default=PlanStatusEnum.DRAFT)

    # 人员信息
    creator = Column(String(100), nullable=False)
    reviewer = Column(String(100))
    executors = Column(JSON, default=list)

    # 时间信息
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 计划内容
    steps = Column(JSON, nullable=False, default=list)
    estimated_total_hours = Column(Numeric(10, 2), default=0)
    actual_total_hours = Column(Numeric(10, 2))

    # 审核信息
    review_comment = Column(Text)
    rejection_reason = Column(Text)

    # 从属关系元数据
    is_based_on = Column(String(64), ForeignKey('plans.id', ondelete='SET NULL'))
    superseded_by = Column(String(64), ForeignKey('plans.id', ondelete='SET NULL'))

    # 扩展字段
    extra_metadata = Column('metadata', JSON, default=dict)

    # 关系
    task = relationship('Task', back_populates='plans', foreign_keys=[task_id])
    plan_steps = relationship('PlanStep', back_populates='plan', cascade='all, delete-orphan', order_by='PlanStep.step_index')

    # 约束
    __table_args__ = (
        CheckConstraint('version > 0', name='plans_version_check'),
        CheckConstraint('estimated_total_hours >= 0', name='plans_hours_check'),
        Index('idx_plans_task_id', 'task_id'),
        Index('idx_plans_status', 'status'),
        Index('idx_plans_type', 'type'),
        Index('idx_plans_creator', 'creator'),
        Index('idx_plans_reviewer', 'reviewer'),
        Index('idx_plans_created_at', 'created_at'),
        Index('idx_plans_reviewed_at', 'reviewed_at'),
        Index('idx_plans_version', 'task_id', 'version'),
    )

    def to_dict(self, include_task: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            'id': self.id,
            'task_id': self.task_id,
            'title': self.title,
            'version': self.version,
            'status': self.status.value if self.status else None,
            'type': self.type.value if self.type else None,
            'creator': self.creator,
            'reviewer': self.reviewer,
            'executors': self.executors or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'steps': self.steps or [],
            'estimated_total_hours': float(self.estimated_total_hours) if self.estimated_total_hours else 0,
            'actual_total_hours': float(self.actual_total_hours) if self.actual_total_hours else None,
            'review_comment': self.review_comment,
            'rejection_reason': self.rejection_reason,
            'is_based_on': self.is_based_on,
            'superseded_by': self.superseded_by,
            'metadata': self.extra_metadata or {},
        }

        if include_task and self.task:
            data['task'] = self.task.to_dict()

        return data


class PlanStep(Base):
    """
    计划步骤 (Plan Step)
    
    开发计划中的具体执行步骤
    """
    __tablename__ = 'plan_steps'

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(String(64), ForeignKey('plans.id', ondelete='CASCADE'), nullable=False)
    step_index = Column(Integer, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    estimated_hours = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(portable_enum(PlanStepStatusEnum), nullable=False, default=PlanStepStatusEnum.PENDING)
    executor = Column(String(100))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    output = Column(Text)
    dependencies = Column(JSON, default=list)

    # 关系
    plan = relationship('DevelopmentPlan', back_populates='plan_steps')

    # 约束
    __table_args__ = (
        CheckConstraint('estimated_hours >= 0', name='plan_steps_hours_check'),
        Index('idx_plan_steps_plan_id', 'plan_id'),
        Index('idx_plan_steps_status', 'status'),
        Index('idx_plan_steps_executor', 'executor'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'step_index': self.step_index,
            'name': self.name,
            'description': self.description,
            'estimated_hours': float(self.estimated_hours) if self.estimated_hours else 0,
            'status': self.status.value if self.status else None,
            'executor': self.executor,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'output': self.output,
            'dependencies': self.dependencies or [],
        }


class TaskPlanRelation(Base):
    """
    任务 - 计划关联表
    
    记录任务与所有计划的历史关联关系，支持审计和版本追溯
    """
    __tablename__ = 'task_plans'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    plan_id = Column(String(64), ForeignKey('plans.id', ondelete='CASCADE'), nullable=False)
    relation_type = Column(String(32), nullable=False, default='owns')
    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(DateTime(timezone=True))
    deactivated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # 约束
    __table_args__ = (
        Index('idx_task_plans_task_id', 'task_id'),
        Index('idx_task_plans_plan_id', 'plan_id'),
        Index('idx_task_plans_active', 'task_id', 'is_active'),
        Index('idx_task_plans_relation_type', 'relation_type'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'plan_id': self.plan_id,
            'relation_type': self.relation_type,
            'is_active': self.is_active,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'deactivated_at': self.deactivated_at.isoformat() if self.deactivated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
