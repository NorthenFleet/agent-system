"""
Repository 层 — 数据访问层

BaseRepository 提供通用 CRUD；各具体 Repository 继承并扩展。

@task VB-007
@author 🟥 拉斐尔
"""
from repositories.base import BaseRepository
from repositories.task_repository import TaskRepository
from repositories.user_repository import UserRepository
from repositories.agent_repository import AgentRepository
from repositories.device_repository import DeviceRepository
from repositories.product_repository import ProductRepository
from repositories.product_dependency_repository import ProductDependencyRepository
from repositories.sprint_repository import SprintRepository
from repositories.activity_log_repository import ActivityLogRepository
from repositories.agent_session_repository import AgentSessionRepository
from repositories.alert_rule_repository import AlertRuleRepository
from repositories.alert_event_repository import AlertEventRepository
from repositories.agent_heartbeat_repository import AgentHeartbeatRepository
from repositories.agent_status_history_repository import AgentStatusHistoryRepository
from repositories.task_comment_repository import TaskCommentRepository
from repositories.task_history_repository import TaskHistoryRepository
from repositories.task_template_repository import TaskTemplateRepository

__all__ = [
    "BaseRepository",
    "TaskRepository",
    "UserRepository",
    "AgentRepository",
    "DeviceRepository",
    "ProductRepository",
    "ProductDependencyRepository",
    "SprintRepository",
    "ActivityLogRepository",
    "AgentSessionRepository",
    "AlertRuleRepository",
    "AlertEventRepository",
    "AgentHeartbeatRepository",
    "AgentStatusHistoryRepository",
    "TaskCommentRepository",
    "TaskHistoryRepository",
    "TaskTemplateRepository",
]
