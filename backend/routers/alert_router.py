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

from models.v2_models import get_session, AlertRule, AlertEvent
from routers.auth_router import get_current_user

router = APIRouter(prefix="/api/v2/alerts", tags=["v2-alerts"])


class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    rule_type: str  # offline | cpu_high | memory_high | custom
    condition_field: str
    condition_op: str  # gt, lt, gte, lte, eq
    threshold: float
    severity: str = "warning"  # info | warning | critical
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
def create_alert_rule(data: AlertRuleCreate, user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        rule = AlertRule(
            name=data.name,
            description=data.description,
            rule_type=data.rule_type,
            condition_field=data.condition_field,
            condition_op=data.condition_op,
            threshold=data.threshold,
            severity=data.severity,
            enabled=data.enabled,
            created_by=user.get("username"),
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return {"success": True, "rule_id": rule.id, "rule": rule.to_dict()}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/rules")
def list_alert_rules(user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        rules = db.query(AlertRule).order_by(AlertRule.created_at.desc()).all()
        return {"rules": [r.to_dict() for r in rules], "total": len(rules)}
    finally:
        db.close()


@router.put("/rules/{rule_id}")
def update_alert_rule(rule_id: int, data: AlertRuleUpdate, user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="告警规则不存在")

        update_data = data.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(rule, k, v)

        db.commit()
        db.refresh(rule)
        return {"success": True, "rule": rule.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/rules/{rule_id}")
def delete_alert_rule(rule_id: int, user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="告警规则不存在")
        db.delete(rule)
        db.commit()
        return {"success": True, "message": "告警规则已删除"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/events")
def list_alert_events(
    user: dict = Depends(get_current_user),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    db = get_session()
    try:
        q = db.query(AlertEvent).order_by(AlertEvent.created_at.desc())
        if severity:
            q = q.filter(AlertEvent.severity == severity)
        if acknowledged is not None:
            q = q.filter(AlertEvent.acknowledged == acknowledged)
        events = q.limit(limit).all()
        return {"events": [e.to_dict() for e in events], "total": len(events)}
    finally:
        db.close()


@router.post("/events/{event_id}/ack")
def ack_alert_event(event_id: int, user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        event = db.query(AlertEvent).filter(AlertEvent.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="告警事件不存在")
        event.acknowledged = True
        event.acknowledged_by = user.get("username")
        event.acknowledged_at = datetime.now(timezone.utc)
        db.commit()
        return {"success": True, "message": "告警已确认"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/stats")
def alert_stats(user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        total = db.query(AlertEvent).count()
        active = db.query(AlertEvent).filter(AlertEvent.acknowledged == False).count()
        critical = db.query(AlertEvent).filter(
            AlertEvent.severity == "critical",
            AlertEvent.acknowledged == False,
        ).count()
        return {
            "total": total,
            "active": active,
            "critical": critical,
            "acknowledged": total - active,
        }
    finally:
        db.close()
