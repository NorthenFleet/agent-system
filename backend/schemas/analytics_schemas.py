"""
Pydantic 响应模型 — 数据分析模块 (S5 P5)

所有响应 schema 供 analytics_router 和 analytics_service 使用。
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Dict


# ==================== Team Efficiency ====================

class TeamEfficiencyMetrics(BaseModel):
    """团队效率指标"""
    total_tasks: int = Field(..., description="时间范围内任务总数")
    completed_tasks: int = Field(..., description="已完成任务数")
    avg_completion_rate: float = Field(..., description="平均完成率 (0-100)")
    avg_progress: float = Field(..., description="平均进度百分比")
    avg_time_to_complete_hours: Optional[float] = Field(None, description="平均完成耗时（小时）")

    by_status: Dict[str, int] = Field(default_factory=dict, description="按状态统计")
    by_priority: Dict[str, int] = Field(default_factory=dict, description="按优先级统计")
    by_assignee: Dict[str, int] = Field(default_factory=dict, description="按负责人统计")


class TeamEfficiencyResponse(BaseModel):
    """团队效率响应"""
    status: str = "success"
    days: int = 14
    metrics: TeamEfficiencyMetrics


# ==================== Throughput ====================

class ThroughputDataPoint(BaseModel):
    """吞吐量数据点"""
    date: str = Field(..., description="日期 (YYYY-MM-DD)")
    created: int = Field(0, description="创建数量")
    completed: int = Field(0, description="完成数量")
    in_progress: int = Field(0, description="进行中数量")


class ThroughputSummary(BaseModel):
    """吞吐量汇总"""
    total_created: int = Field(..., description="总创建数")
    total_completed: int = Field(..., description="总完成数")
    daily_avg_created: float = Field(..., description="日均创建")
    daily_avg_completed: float = Field(..., description="日均完成")
    trend: str = Field(..., description="趋势: increasing | stable | decreasing")


class ThroughputResponse(BaseModel):
    """吞吐量响应"""
    status: str = "success"
    days: int = 14
    summary: ThroughputSummary
    data_points: List[ThroughputDataPoint] = Field(default_factory=list)


# ==================== Agent Productivity ====================

class AgentProductivityItem(BaseModel):
    """单个 Agent 产出指标"""
    agent_name: str = Field(..., description="Agent 名称")
    team: Optional[str] = Field(None, description="所属团队")
    total_tasks: int = Field(0, description="总任务数")
    completed_tasks: int = Field(0, description="完成任务数")
    completion_rate: float = Field(0, description="完成率 (0-100)")
    avg_progress: float = Field(0, description="平均进度")
    last_heartbeat: Optional[str] = Field(None, description="最近心跳时间 ISO")


class AgentProductivitySummary(BaseModel):
    """产出率汇总"""
    total_agents: int = Field(..., description="活跃 Agent 总数")
    avg_completion_rate: float = Field(..., description="平均完成率")
    avg_tasks_per_agent: float = Field(..., description="人均任务数")
    top_performer: Optional[str] = Field(None, description="表现最佳 Agent")


class AgentProductivityResponse(BaseModel):
    """Agent 产出率响应"""
    status: str = "success"
    days: int = 14
    summary: AgentProductivitySummary
    agents: List[AgentProductivityItem] = Field(default_factory=list)


# ==================== Sprint Burndown ====================

class BurndownPoint(BaseModel):
    """燃尽图数据点"""
    day_index: int = Field(..., description="Sprint 第几天 (0-indexed)")
    date: str = Field(..., description="日期 (YYYY-MM-DD)")
    remaining_tasks: int = Field(..., description="剩余任务数")
    completed_tasks: int = Field(..., description="已完成任务数")
    ideal_remaining: Optional[float] = Field(None, description="理想剩余")


class SprintBurndownSummary(BaseModel):
    """燃尽汇总"""
    sprint_name: str = Field(..., description="Sprint 名称")
    sprint_status: str = Field(..., description="Sprint 状态")
    total_tasks: int = Field(..., description="总任务数")
    completed_tasks: int = Field(..., description="已完成任务数")
    remaining_tasks: int = Field(..., description="剩余任务数")
    completion_pct: float = Field(..., description="完成百分比")
    velocity: Optional[float] = Field(None, description="每日完成速度")
    days_elapsed: int = Field(0, description="已过天数")
    days_total: int = Field(0, description="总天数")


class SprintBurndownResponse(BaseModel):
    """Sprint 燃尽响应"""
    status: str = "success"
    data: List[SprintBurndownSummary] = Field(default_factory=list)


# ==================== Task Trend ====================

class TaskTrendPoint(BaseModel):
    """任务趋势数据点"""
    period: str = Field(..., description="时间段 (YYYY-MM-DD 或 YYYY-WW)")
    total: int = Field(0, description="总任务数")
    created: int = Field(0, description="新增任务")
    completed: int = Field(0, description="完成任务")
    avg_progress: float = Field(0, description="平均进度")


class TaskTrendSummary(BaseModel):
    """趋势汇总"""
    total_tasks: int = Field(..., description="总任务数")
    completion_trend: str = Field(..., description="完成趋势: increasing | stable | decreasing")
    peak_period: Optional[str] = Field(None, description="高峰期")
    period_count: int = Field(..., description="时间段数")


class TaskTrendResponse(BaseModel):
    """任务趋势响应"""
    status: str = "success"
    days: int = 14
    summary: TaskTrendSummary
    data_points: List[TaskTrendPoint] = Field(default_factory=list)
