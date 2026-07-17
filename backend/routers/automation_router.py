"""
自动化规则引擎 API 路由

提供 6 个端点：
  - GET  /api/v2/automation/rules          — 规则列表
  - POST /api/v2/automation/rules          — 创建规则
  - GET  /api/v2/automation/rules/{id}     — 规则详情
  - PUT  /api/v2/automation/rules/{id}     — 更新规则
  - DELETE /api/v2/automation/rules/{id}   — 删除规则
  - PUT  /api/v2/automation/rules/{id}/toggle — 启用/禁用规则
  - GET  /api/v2/automation/rules/{id}/history — 执行历史

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-09 (Sprint 5 P6)
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.automation_models import AutomationRule, AutomationRuleExecution
from services.automation_engine import VALID_TRIGGER_TYPES, VALID_ACTION_TYPES
from routers.auth_router import get_current_user

router = APIRouter(
    prefix="/api/v2/automation",
    tags=["v2-automation"],
    responses={
        401: {"description": "未登录或 Token 无效"},
        403: {"description": "权限不足"},
        404: {"description": "资源不存在"},
    },
)


# ─── Pydantic Models ────────────────────────────────────────────────────
class TriggerSchema(BaseModel):
    type: str = Field(..., description="触发类型")
    conditions: Dict[str, Any] = Field({}, description="触发条件")


class ActionItem(BaseModel):
    type: str = Field(..., description="动作类型")
    params: Dict[str, Any] = Field({}, description="动作参数")


class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="规则名称")
    description: str = Field("", max_length=2000, description="规则描述")
    trigger: TriggerSchema = Field(..., description="触发器")
    actions: List[ActionItem] = Field(..., min_items=1, description="动作列表")
    priority: int = Field(10, ge=1, le=100, description="优先级 (1-100, 越小越先执行)")


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="规则名称")
    description: Optional[str] = Field(None, max_length=2000, description="规则描述")
    trigger: Optional[TriggerSchema] = Field(None, description="触发器")
    actions: Optional[List[ActionItem]] = Field(None, description="动作列表")
    priority: Optional[int] = Field(None, ge=1, le=100, description="优先级")


# ─── 端点 ───────────────────────────────────────────────────────────────
@router.get("/rules", summary="规则列表", description="获取所有自动化规则")
def list_rules(
    is_active: Optional[bool] = Query(None, description="按启用状态筛选"),
    trigger_type: Optional[str] = Query(None, description="按触发类型筛选"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AutomationRule)
    if is_active is not None:
        query = query.filter(AutomationRule.is_active == is_active)
    if trigger_type is not None:
        # 使用 JSON 字段过滤
        rules = [r for r in query.order_by(AutomationRule.priority.asc()).all()
                 if (r.trigger or {}).get("type") == trigger_type]
    else:
        rules = query.order_by(AutomationRule.priority.asc()).all()
    return {
        "rules": [r.to_dict() for r in rules],
        "total": len(rules),
    }


@router.post("/rules", status_code=201, summary="创建规则", description="创建新的自动化规则")
def create_rule(
    data: RuleCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 校验 trigger type
    if data.trigger.type not in VALID_TRIGGER_TYPES:
        raise HTTPException(400, f"无效的触发类型: {data.trigger.type}，支持: {sorted(VALID_TRIGGER_TYPES)}")
    # 校验 action types
    for act in data.actions:
        if act.type not in VALID_ACTION_TYPES:
            raise HTTPException(400, f"无效的动作类型: {act.type}，支持: {sorted(VALID_ACTION_TYPES)}")

    rule = AutomationRule(
        name=data.name,
        description=data.description,
        trigger={"type": data.trigger.type, "conditions": data.trigger.conditions},
        actions=[{"type": a.type, "params": a.params} for a in data.actions],
        priority=data.priority,
        created_by=user.get("username"),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.get("/rules/{rule_id}", summary="规则详情", description="获取单条规则详情")
def get_rule(
    rule_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")
    return rule.to_dict(include_executions=True)


@router.put("/rules/{rule_id}", summary="更新规则", description="更新规则定义")
def update_rule(
    rule_id: int,
    data: RuleUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")

    if data.name is not None:
        rule.name = data.name
    if data.description is not None:
        rule.description = data.description
    if data.trigger is not None:
        if data.trigger.type not in VALID_TRIGGER_TYPES:
            raise HTTPException(400, f"无效的触发类型: {data.trigger.type}")
        rule.trigger = {"type": data.trigger.type, "conditions": data.trigger.conditions}
    if data.actions is not None:
        for act in data.actions:
            if act.type not in VALID_ACTION_TYPES:
                raise HTTPException(400, f"无效的动作类型: {act.type}")
        rule.actions = [{"type": a.type, "params": a.params} for a in data.actions]
    if data.priority is not None:
        rule.priority = data.priority

    from datetime import datetime, timezone
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/rules/{rule_id}", summary="删除规则", description="删除规则及其执行历史")
def delete_rule(
    rule_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")
    db.delete(rule)
    db.commit()
    return {"message": "规则已删除", "rule_id": rule_id}


@router.put("/rules/{rule_id}/toggle", summary="切换规则状态", description="启用或禁用规则")
def toggle_rule(
    rule_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")
    rule.is_active = not rule.is_active
    from datetime import datetime, timezone
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return {
        "rule_id": rule.id,
        "is_active": rule.is_active,
        "message": f"规则已{'启用' if rule.is_active else '禁用'}",
    }


@router.get("/rules/{rule_id}/history", summary="规则执行历史", description="获取规则的执行记录")
def get_rule_history(
    rule_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="按状态筛选: success | failed"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 验证规则存在
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")

    query = db.query(AutomationRuleExecution).filter(
        AutomationRuleExecution.rule_id == rule_id
    )
    if status is not None:
        query = query.filter(AutomationRuleExecution.status == status)

    total = query.count()
    executions = (
        query.order_by(AutomationRuleExecution.executed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "rule_id": rule_id,
        "executions": [e.to_dict() for e in executions],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
