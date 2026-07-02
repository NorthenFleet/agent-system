"""
告警规则评估器
在心跳记录后触发，检查所有启用的告警规则，生成告警事件并返回。
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from models.v2_models import get_session, AlertRule, AlertEvent


def evaluate_rules_for_heartbeat(
    agent_id: str,
    status: str,
    cpu_usage: Optional[float],
    memory_usage: Optional[float],
    seconds_ago: float,
) -> List[AlertEvent]:
    """评估所有启用的告警规则，返回新生成的告警事件列表。"""
    db = get_session()
    try:
        rules = db.query(AlertRule).filter(AlertRule.enabled == True).all()
        new_events: List[AlertEvent] = []

        for rule in rules:
            if rule.agent_id and rule.agent_id != agent_id:
                continue

            triggered = _check_rule(rule, status, cpu_usage, memory_usage, seconds_ago)
            if triggered:
                ev = _create_event(rule, agent_id, status, cpu_usage, memory_usage, seconds_ago)
                db.add(ev)
                new_events.append(ev)

        if new_events:
            db.commit()
            for ev in new_events:
                db.refresh(ev)
        return new_events
    except Exception:
        db.rollback()
        return []
    finally:
        db.close()


def _check_rule(
    rule: AlertRule,
    status: str,
    cpu_usage: Optional[float],
    memory_usage: Optional[float],
    seconds_ago: float,
) -> bool:
    field = rule.condition_field
    op = rule.condition_op
    value = rule.condition_value
    if not field or not op or not value:
        return False

    actual_val = _get_field_value(field, status, cpu_usage, memory_usage, seconds_ago)
    if actual_val is None:
        return False

    try:
        threshold = float(value)
    except (ValueError, TypeError):
        threshold = value  # string comparison

    return _compare(actual_val, op, threshold)


def _get_field_value(
    field: str,
    status: str,
    cpu_usage: Optional[float],
    memory_usage: Optional[float],
    seconds_ago: float,
):
    mapping = {
        "status": status,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "seconds_ago": seconds_ago,
    }
    return mapping.get(field)


def _compare(actual, op: str, threshold):
    if isinstance(actual, str):
        if op == "eq":
            return actual == str(threshold)
        return False
    try:
        actual = float(actual)
        threshold = float(threshold)
    except (ValueError, TypeError):
        return False

    ops = {
        "eq": lambda a, b: a == b,
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
    }
    fn = ops.get(op)
    return fn(actual, threshold) if fn else False


def _create_event(
    rule: AlertRule,
    agent_id: str,
    status: str,
    cpu_usage: Optional[float],
    memory_usage: Optional[float],
    seconds_ago: float,
) -> AlertEvent:
    msg = f"Agent {agent_id} 触发告警: {rule.name}"
    details = {
        "rule_type": rule.rule_type,
        "condition_field": rule.condition_field,
        "condition_op": rule.condition_op,
        "condition_value": rule.condition_value,
        "current_status": status,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "seconds_ago": round(seconds_ago, 1),
    }
    return AlertEvent(
        rule_id=rule.id,
        agent_id=agent_id,
        severity=rule.severity,
        message=msg,
        details=details,
    )
