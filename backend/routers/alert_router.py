"""
告警规则 API 路由
POST   /api/v2/alerts/rules              创建告警规则
GET    /api/v2/alerts/rules              获取告警规则列表
PUT    /api/v2/alerts/rules/{rule_id}    更新告警规则
DELETE /api/v2/alerts/rules/{rule_id}    删除告警规则
GET    /api/v2/alerts/events             获取告警事件列表
POST   /api/v2/alerts/events/{event_id}/ack  确认告警
GET    /api/v2/alerts/stats              告警统计
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models.v2_models import get_session
from services.alert_service import AlertService
from routers.auth_router import get_current_user

router = APIRouter(prefix="/api/v2/alerts", tags=["v2-alerts"])


def get_alert_service(db: Session = Depends(get_session)) -> AlertService:
    return AlertService(db)


class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    rule_type: str
    condition_field: str
    condition_op: str
    threshold: float
    severity: str = "warning"
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rule_type: Optional[str] = None
    condition_field: Optional[str] = None
    condition_op: Optional[str] = None
    threshold: Optional[float] = None
    severity: Optional[str] = None
    enabled: Optional[bool] = None


@router.post("/rules")
def create_alert_rule(
    data: AlertRuleCreate,
    user: dict = Depends(get_current_user),
    svc: AlertService = Depends(get_alert_service),
):
    rule = svc.create_rule({
        "name": data.name,
        "description": data.description,
        "rule_type": data.rule_type,
        "condition_field": data.condition_field,
        "condition_op": data.condition_op,
        "threshold": data.threshold,
        "severity": data.severity,
        "enabled": data.enabled,
    })
    return {"success": True, "rule_id": rule.id, "rule": rule.to_dict()}


@router.get("/rules")
def list_alert_rules(
    user: dict = Depends(get_current_user),
    svc: AlertService = Depends(get_alert_service),
):
    rules = svc.list_rules()
    return {"rules": [r.to_dict() for r in rules], "total": len(rules)}


@router.put("/rules/{rule_id}")
def update_alert_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    user: dict = Depends(get_current_user),
    svc: AlertService = Depends(get_alert_service),
):
    rule = svc.get_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")

    update_data = data.model_dump(exclude_unset=True)
    updated_rule = svc.update(rule_id, update_data)
    return {"success": True, "rule": updated_rule.to_dict()}


@router.delete("/rules/{rule_id}")
def delete_alert_rule(
    rule_id: int,
    user: dict = Depends(get_current_user),
    svc: AlertService = Depends(get_alert_service),
):
    rule = svc.get_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")

    svc.delete(rule_id)
    return {"success": True, "message": "告警规则已删除"}


@router.get("/events")
def list_alert_events(
    user: dict = Depends(get_current_user),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    svc: AlertService = Depends(get_alert_service),
):
    events = svc.list_events(limit=limit)
    if severity:
        events = [e for e in events if e.severity == severity]
    if acknowledged is not None:
        events = [e for e in events if e.acknowledged == acknowledged]
    return {"events": [e.to_dict() for e in events], "total": len(events)}


@router.post("/events/{event_id}/ack")
def ack_alert_event(
    event_id: int,
    user: dict = Depends(get_current_user),
    svc: AlertService = Depends(get_alert_service),
):
    event = svc.get_event_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="告警事件不存在")

    svc.acknowledge_event(event_id, acknowledged_by=user.get("username"))
    return {"success": True, "message": "告警已确认"}


@router.get("/stats")
def alert_stats(
    user: dict = Depends(get_current_user),
    svc: AlertService = Depends(get_alert_service),
):
    stats = svc.get_event_stats()
    return {
        "total": stats["total"],
        "active": stats["active"],
        "critical": stats["critical"],
        "acknowledged": stats["total"] - stats["active"],
    }