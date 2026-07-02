"""
V2 数据库模型 — SQLite (替代 PostgreSQL)
所有表结构与 Dev Spec 一致，仅替换方言
"""
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey,
    CheckConstraint, Index, JSON, UniqueConstraint, create_engine
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.sql import func
import json
import os

Base = declarative_base()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "dashboard_v2.db")


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(128), nullable=False)
    role = Column(String(20), nullable=False, default='viewer')  # admin | viewer | agent
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)

    comments = relationship('TaskComment', back_populates='user')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'role': self.role,
            'email': self.email,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
        }


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, default='')
    type = Column(String(32), default='general')
    status = Column(String(32), nullable=False, default='pending', index=True)
    priority = Column(String(20), default='medium', index=True)
    assignee = Column(String(64), nullable=True, index=True)
    progress = Column(Integer, nullable=False, default=0)
    source = Column(String(20), default='manual')
    sprint = Column(Integer, nullable=True, index=True)
    dev_spec = Column(String(500), nullable=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    start_date = Column(DateTime, nullable=True)
    tags = Column(JSON, default=list)
    parent_task_id = Column(String(64), nullable=True, index=True)

    history = relationship('TaskHistory', back_populates='task', cascade='all, delete-orphan',
                           order_by='TaskHistory.changed_at.desc()')
    comments = relationship('TaskComment', back_populates='task', cascade='all, delete-orphan',
                            order_by='TaskComment.created_at.asc()')

    __table_args__ = (
        CheckConstraint('progress >= 0 AND progress <= 100', name='chk_progress'),
    )

    def to_dict(self, include_comments=False, include_history=False):
        data = {
            'id': self.id,
            'task_id': self.task_id,
            'title': self.title,
            'description': self.description,
            'type': self.type,
            'status': self.status,
            'priority': self.priority,
            'assignee': self.assignee,
            'progress': self.progress,
            'source': self.source,
            'sprint': self.sprint,
            'dev_spec': self.dev_spec,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'tags': self.tags or [],
            'parent_task_id': self.parent_task_id,
            'comment_count': len(self.comments) if self.comments else 0,
        }
        if include_comments:
            data['comments'] = [c.to_dict() for c in self.comments]
        if include_history:
            data['history'] = [h.to_dict() for h in self.history]
        return data


class TaskHistory(Base):
    __tablename__ = 'task_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey('tasks.task_id', ondelete='CASCADE'), nullable=False, index=True)
    field = Column(String(64), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_by = Column(String(64), nullable=True)
    changed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    task = relationship('Task', back_populates='history')

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'field': self.field,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'changed_by': self.changed_by,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
        }


class TaskComment(Base):
    __tablename__ = 'task_comments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey('tasks.task_id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    agent_id = Column(String(64), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    task = relationship('Task', back_populates='comments')
    user = relationship('User', back_populates='comments')

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'user': {
                'id': self.user.id if self.user else None,
                'username': self.user.username if self.user else None,
                'display_name': self.user.display_name if self.user else None,
            } if self.user else None,
            'agent_id': self.agent_id,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AgentHeartbeat(Base):
    __tablename__ = 'agent_heartbeats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    agent_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)
    current_task = Column(String(500), nullable=True)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    task_queue_len = Column(Integer, default=0)
    extra_data = Column('metadata', JSON, default=dict)
    heartbeat_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'agent_name': self.agent_name,
            'status': self.status,
            'current_task': self.current_task,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'task_queue_len': self.task_queue_len,
            'metadata': self.extra_data or {},
            'heartbeat_at': self.heartbeat_at.isoformat() if self.heartbeat_at else None,
        }


class AgentStatusHistory(Base):
    __tablename__ = 'agent_status_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    current_task = Column(String(500), nullable=True)
    triggered_by = Column(String(64), nullable=True)
    changed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'from_status': self.from_status,
            'to_status': self.to_status,
            'current_task': self.current_task,
            'triggered_by': self.triggered_by,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
        }


class TaskTemplate(Base):
    __tablename__ = 'task_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    template_data = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'template_data': self.template_data or {},
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Agent(Base):
    """智能体模型"""
    __tablename__ = 'agents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    team = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default='offline', index=True)
    role = Column(String(64), nullable=True)
    description = Column(Text, default='')
    avatar_url = Column(String(500), nullable=True)
    current_task = Column(String(500), nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'name': self.name,
            'team': self.team,
            'status': self.status,
            'role': self.role,
            'description': self.description,
            'avatar_url': self.avatar_url,
            'current_task': self.current_task,
            'last_heartbeat_at': self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Device(Base):
    """设备模型"""
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, index=True)
    device_type = Column(String(64), nullable=False, default='server')
    hostname = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    status = Column(String(32), nullable=False, default='offline', index=True)
    os_info = Column(String(255), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    memory_gb = Column(Float, nullable=True)
    disk_gb = Column(Float, nullable=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'device_type': self.device_type,
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'status': self.status,
            'os_info': self.os_info,
            'cpu_cores': self.cpu_cores,
            'memory_gb': self.memory_gb,
            'disk_gb': self.disk_gb,
            'tags': self.tags or [],
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Product(Base):
    """产品/服务模型"""
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    status = Column(String(32), nullable=False, default='planning', index=True)
    owner = Column(String(64), nullable=True)
    start_date = Column(DateTime, nullable=True)
    target_date = Column(DateTime, nullable=True)
    progress = Column(Integer, nullable=False, default=0)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint('progress >= 0 AND progress <= 100', name='chk_product_progress'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'owner': self.owner,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'target_date': self.target_date.isoformat() if self.target_date else None,
            'progress': self.progress,
            'tags': self.tags or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ProductDependency(Base):
    """产品依赖关系"""
    __tablename__ = 'product_dependencies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    to_product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    dependency_type = Column(String(32), nullable=False, default='blocks')
    description = Column(Text, default='')
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'from_product_id': self.from_product_id,
            'to_product_id': self.to_product_id,
            'dependency_type': self.dependency_type,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Sprint(Base):
    """Sprint 模型"""
    __tablename__ = 'sprints'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, default='')
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False, default='planning', index=True)
    goal = Column(Text, default='')
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'status': self.status,
            'goal': self.goal,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ActivityLog(Base):
    """活动日志"""
    __tablename__ = 'activity_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    action = Column(String(128), nullable=False)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    detail = Column(JSON, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'detail': self.detail or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AgentSession(Base):
    """Agent 会话记录"""
    __tablename__ = 'agent_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(128), unique=True, nullable=False)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    task_id = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default='active')
    summary = Column(Text, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'session_id': self.session_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'task_id': self.task_id,
            'status': self.status,
            'summary': self.summary,
        }


class AlertRule(Base):
    """告警规则"""
    __tablename__ = 'alert_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    agent_id = Column(String(64), nullable=True, index=True)
    condition = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default='warning')
    enabled = Column(Boolean, nullable=False, default=True)
    notification_channels = Column(JSON, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'agent_id': self.agent_id,
            'condition': self.condition,
            'severity': self.severity,
            'enabled': self.enabled,
            'notification_channels': self.notification_channels or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AlertEvent(Base):
    """告警事件"""
    __tablename__ = 'alert_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey('alert_rules.id', ondelete='SET NULL'), nullable=True, index=True)
    agent_id = Column(String(64), nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'agent_id': self.agent_id,
            'severity': self.severity,
            'message': self.message,
            'acknowledged': self.acknowledged,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ---------- Database helpers ----------

def get_engine():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return create_engine(f'sqlite:///{DB_PATH}', pool_pre_ping=True)


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
