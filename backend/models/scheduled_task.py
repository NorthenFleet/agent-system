"""
定时任务数据模型
Dev Spec: DEV-SCHEDULED-TASKS v1.0
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class TaskStatus(str, Enum):
    active = "active"
    paused = "paused"
    disabled = "disabled"


class TaskRunStatus(str, Enum):
    success = "success"
    failed = "failed"
    timeout = "timeout"
    skipped = "skipped"
    running = "running"


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class TriggerType(str, Enum):
    scheduled = "scheduled"
    manual = "manual"
    retry = "retry"


class ScheduledTask(BaseModel):
    """定时任务完整定义"""
    id: str
    name: str
    description: Optional[str] = ""
    owner: str
    owner_emoji: str = ""
    cron_expression: str = ""
    schedule_display: str = ""
    time_slot: str = "全天 24 小时"
    command: str = ""
    command_args: Optional[dict] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.paused
    priority: Priority = Priority.medium
    max_retries: int = 3
    retry_interval_seconds: int = 60
    timeout_seconds: int = 300
    last_run: Optional[datetime] = None
    last_run_status: Optional[TaskRunStatus] = None
    last_run_duration_ms: Optional[int] = None
    next_run: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: str = ""

    model_config = {"use_enum_values": True}

    def to_dict(self) -> dict:
        """转换为 JSON 可序列化字典"""
        return self.model_dump()

    @property
    def success_rate_display(self) -> float:
        """计算成功率"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return round(self.success_count / total * 100, 1)


class TaskExecutionLog(BaseModel):
    """单次执行记录"""
    id: str
    task_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    status: TaskRunStatus
    output: Optional[str] = ""
    error: Optional[str] = ""
    retry_of: Optional[str] = None
    trigger_type: TriggerType = TriggerType.scheduled

    model_config = {"use_enum_values": True}

    def to_dict(self) -> dict:
        return self.model_dump()


class TaskStats(BaseModel):
    """聚合统计"""
    total_tasks: int = 0
    active_tasks: int = 0
    paused_tasks: int = 0
    disabled_tasks: int = 0
    total_executions_today: int = 0
    success_rate_overall: float = 0.0
    next_five_runs: list = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()


# ── Request/Response Models ──

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    name: str = Field(..., min_length=1, max_length=200, description="任务名称，不可为空")
    description: Optional[str] = ""
    owner: str = Field(..., min_length=1, max_length=64, description="任务负责人")
    owner_emoji: str = ""
    cron_expression: str = Field(..., min_length=5, description="Cron 表达式")
    schedule_display: Optional[str] = None  # 如果不提供，根据 cron 自动生成
    time_slot: str = "全天 24 小时"
    command: str = Field(..., min_length=1, description="执行的命令")
    command_args: Optional[dict] = None
    priority: Priority = Priority.medium
    max_retries: int = Field(default=3, ge=0, le=10, description="最大重试次数 0-10")
    retry_interval_seconds: int = Field(default=60, ge=1, le=3600, description="重试间隔 1-3600s")
    timeout_seconds: int = Field(default=300, ge=1, le=86400, description="超时时间 1-86400s")
    created_by: str = ""

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("任务名称不能为空或纯空白")
        return v.strip()


class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    owner: Optional[str] = Field(default=None, min_length=1, max_length=64)
    owner_emoji: Optional[str] = None
    cron_expression: Optional[str] = None
    schedule_display: Optional[str] = None
    time_slot: Optional[str] = None
    command: Optional[str] = None
    command_args: Optional[dict] = None
    priority: Optional[Priority] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    retry_interval_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)


class CronParseRequest(BaseModel):
    """Cron 解析请求"""
    cron_expression: str


class CronParseResponse(BaseModel):
    """Cron 解析响应"""
    display: str = ""
    next_runs: list[str] = Field(default_factory=list)
