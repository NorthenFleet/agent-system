from __future__ import annotations
"""
V3 数据库模型 — SQLAlchemy ORM

与 database.py 共享 Base 和 engine。
模型定义：tasks, task_history, task_comments, users, task_templates,
agent_heartbeats, agent_status_history, agent_sessions,
devices, device_health_history,
products, product_dependencies,
alert_rules, alert_events,
sprints, activity_logs.

@author: 拉斐尔 (🐢 后端开发)
@updated: 2026-07-03
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey,
    CheckConstraint, Index, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database import Base, SessionLocal, engine, get_db


def get_engine():
    return engine


def get_session():
    return SessionLocal()


# ==================== 用户与认证 ====================

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


# ==================== 任务管理 ====================

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
            'id': self.id, 'task_id': self.task_id, 'title': self.title,
            'description': self.description, 'type': self.type,
            'status': self.status, 'priority': self.priority,
            'assignee': self.assignee, 'progress': self.progress,
            'source': self.source, 'sprint': self.sprint,
            'dev_spec': self.dev_spec, 'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'tags': self.tags or [], 'parent_task_id': self.parent_task_id,
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
            'id': self.id, 'task_id': self.task_id, 'field': self.field,
            'old_value': self.old_value, 'new_value': self.new_value,
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
            'id': self.id, 'task_id': self.task_id,
            'user': {
                'id': self.user.id if self.user else None,
                'username': self.user.username if self.user else None,
                'display_name': self.user.display_name if self.user else None,
            } if self.user else None,
            'agent_id': self.agent_id, 'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TaskTemplate(Base):
    __tablename__ = 'task_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    template_data = Column(JSON, nullable=False)
    category = Column(String(64), nullable=True, index=True)
    is_system = Column(Boolean, nullable=False, default=False)
    usage_count = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'description': self.description,
            'template_data': self.template_data or {},
            'category': self.category,
            'is_system': self.is_system,
            'usage_count': self.usage_count,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ==================== Agent 监控 ====================

class Agent(Base):
    __tablename__ = 'agents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), unique=True, nullable=True, index=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    role = Column(String(32), nullable=False)
    team = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, index=True)
    current_task = Column(String(500), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    capabilities = Column(JSON, default=list)
    model_name = Column(String(128), nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    heartbeats = None  # agent_id 类型不匹配 (agents.id=Integer, heartbeats.agent_id=VARCHAR)
    # 心跳通过 agent_name 关联，在 Service 层查询

    def to_dict(self):
        return {
            'id': self.id, 'agent_id': self.agent_id or self.name,
            'name': self.name, 'role': self.role,
            'team': self.team, 'status': self.status,
            'current_task': self.current_task,
            'avatar_url': self.avatar_url,
            'capabilities': self.capabilities or [],
            'model_name': self.model_name,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'last_heartbeat_at': self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
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
            'id': self.id, 'agent_id': self.agent_id, 'agent_name': self.agent_name,
            'status': self.status, 'current_task': self.current_task,
            'cpu_usage': self.cpu_usage, 'memory_usage': self.memory_usage,
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
            'id': self.id, 'agent_id': self.agent_id,
            'from_status': self.from_status, 'to_status': self.to_status,
            'current_task': self.current_task, 'triggered_by': self.triggered_by,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
        }


class AgentSession(Base):
    __tablename__ = 'agent_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    session_key = Column(String(128), nullable=False)
    status = Column(String(32), default='active')
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    model = Column(String(128), nullable=True)

    def to_dict(self):
        return {
            'id': self.id, 'agent_id': self.agent_id,
            'session_key': self.session_key, 'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'model': self.model,
        }


# ==================== 设备管理 ====================

class Device(Base):
    __tablename__ = 'devices'

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    ip = Column(String(64), nullable=False)
    os = Column(String(64), default='Unknown')
    role = Column(String(64), default='Unknown')
    ports = Column(JSON, default=list)
    specs = Column(JSON, default=dict)
    assigned_agents = Column(JSON, default=list)
    location = Column(String(255), nullable=True)
    description = Column(Text, default='')
    status = Column(String(32), default='unknown', index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    health_history = relationship('DeviceHealthHistory', back_populates='device', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'ip': self.ip,
            'os': self.os, 'role': self.role,
            'ports': self.ports or [], 'specs': self.specs or {},
            'assigned_agents': self.assigned_agents or [],
            'location': self.location, 'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class DeviceHealthHistory(Base):
    __tablename__ = 'device_health_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(64), ForeignKey('devices.id', ondelete='CASCADE'), nullable=False, index=True)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    disk_usage = Column(Float, nullable=True)
    status = Column(String(32), nullable=False)
    checked_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    device = relationship('Device', back_populates='health_history')

    def to_dict(self):
        return {
            'id': self.id, 'device_id': self.device_id,
            'cpu_usage': self.cpu_usage, 'memory_usage': self.memory_usage,
            'disk_usage': self.disk_usage, 'status': self.status,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None,
        }


# ==================== 产品管理 ====================

class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    category = Column(String(64), nullable=True)
    status = Column(String(32), default='active')
    owner = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    dependencies = relationship('ProductDependency', back_populates='product', cascade='all, delete-orphan')

    def to_dict(self, include_deps=False):
        data = {
            'id': self.id, 'product_id': self.product_id,
            'name': self.name, 'description': self.description,
            'category': self.category, 'status': self.status,
            'owner': self.owner,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_deps:
            data['dependencies'] = [d.to_dict() for d in self.dependencies]
        return data


class ProductDependency(Base):
    __tablename__ = 'product_dependencies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    dependency_name = Column(String(200), nullable=False)
    dependency_type = Column(String(32), nullable=False)
    version = Column(String(64), nullable=True)
    notes = Column(Text, default='')

    product = relationship('Product', back_populates='dependencies')

    def to_dict(self):
        return {
            'id': self.id, 'product_id': self.product_id,
            'dependency_name': self.dependency_name,
            'dependency_type': self.dependency_type,
            'version': self.version, 'notes': self.notes,
        }


# ==================== 告警管理 ====================

class AlertRule(Base):
    __tablename__ = 'alert_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    target_type = Column(String(32), nullable=False)  # agent | device | task
    target_id = Column(String(64), nullable=False)
    condition = Column(JSON, nullable=False)
    threshold = Column(Float, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'target_type': self.target_type, 'target_id': self.target_id,
            'condition': self.condition, 'threshold': self.threshold,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AlertEvent(Base):
    __tablename__ = 'alert_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey('alert_rules.id', ondelete='SET NULL'), nullable=True)
    target_type = Column(String(32), nullable=False)
    target_id = Column(String(64), nullable=False)
    severity = Column(String(20), default='warning')
    message = Column(Text, nullable=False)
    acknowledged = Column(Boolean, nullable=False, default=False)
    triggered_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    acknowledged_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id, 'rule_id': self.rule_id,
            'target_type': self.target_type, 'target_id': self.target_id,
            'severity': self.severity, 'message': self.message,
            'acknowledged': self.acknowledged,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


# ==================== Sprint 管理 ====================

class Sprint(Base):
    __tablename__ = 'sprints'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    status = Column(String(32), nullable=False, default='planning', index=True)  # planning | running | completed | archived
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    goal = Column(Text, default='')
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'goal': self.goal,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ActivityLog(Base):
    __tablename__ = 'activity_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=True)
    target_id = Column(String(64), nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            'id': self.id, 'agent_id': self.agent_id,
            'action': self.action, 'target_type': self.target_type,
            'target_id': self.target_id, 'details': self.details or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==================== 情报资讯 ====================

class IntelligenceCategory(Base):
    __tablename__ = 'intelligence_categories'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, index=True)
    description = Column(String(255), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    articles = relationship('IntelligenceArticle', back_populates='category_rel', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'description': self.description,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class IntelligenceArticle(Base):
    __tablename__ = 'intelligence_articles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    url = Column(String(512), nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    source = Column(String(128), nullable=True)
    category = Column(String(64), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey('intelligence_categories.id', ondelete='SET NULL'), nullable=True, index=True)
    author = Column(String(64), nullable=True)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    is_duplicate = Column(Integer, default=0)
    image_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    category_rel = relationship('IntelligenceCategory', back_populates='articles')

    def to_dict(self, include_content=False):
        d = {
            'id': self.id, 'title': self.title,
            'url': self.url, 'summary': self.summary,
            'source': self.source, 'category': self.category,
            'author': self.author,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'image_url': self.image_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_content:
            d['content'] = self.content
        return d


# ==================== 模块权限 ====================


class FeatureModule(Base):
    __tablename__ = 'feature_modules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_key = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    route_path = Column(String(128), nullable=False)
    description = Column(Text, default='')
    icon = Column(String(64), nullable=True)
    sort_order = Column(Integer, default=0)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id, 'module_key': self.module_key,
            'name': self.name, 'route_path': self.route_path,
            'description': self.description,
            'icon': self.icon, 'sort_order': self.sort_order,
            'is_enabled': self.is_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class UserFeatureModule(Base):
    __tablename__ = 'user_feature_modules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    module_key = Column(String(64), nullable=False, index=True)
    can_view = Column(Boolean, nullable=False, default=True)
    can_manage = Column(Boolean, nullable=False, default=False)
    granted_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', 'module_key', name='uq_user_module'),
    )

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'module_key': self.module_key,
            'can_view': self.can_view, 'can_manage': self.can_manage,
            'granted_by': self.granted_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ==================== Agent 任务派发 ====================


class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    type = Column(String(32), nullable=False, index=True)  # system / task / alert / mention
    title = Column(String(200), nullable=False)
    content = Column(Text, default='')
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    source_id = Column(String(128), nullable=True)  # 关联的任务ID/Agent ID等
    link = Column(String(500), nullable=True)  # 跳转链接
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    read_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'type': self.type, 'title': self.title,
            'content': self.content, 'is_read': self.is_read,
            'source_id': self.source_id, 'link': self.link,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }


class AgentDispatch(Base):
    __tablename__ = 'agent_dispatches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=False, index=True)
    dispatcher_id = Column(String(64), nullable=True)
    dispatched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    status = Column(String(32), nullable=False, default='pending', index=True)  # pending | dispatched | running | completed | failed | cancelled
    notes = Column(Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'task_id': self.task_id,
            'dispatcher_id': self.dispatcher_id,
            'dispatched_at': self.dispatched_at.isoformat() if self.dispatched_at else None,
            'status': self.status,
            'notes': self.notes,
        }
