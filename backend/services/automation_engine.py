"""
自动化规则引擎 — 规则评估、匹配与动作执行

提供 evaluate() 接口，由 router 端点在任务事件发生时调用。
支持多规则按 priority 排序执行，循环触发保护，动作失败不影响主流程。

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-09 (Sprint 5 P6)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.automation_models import AutomationRule, AutomationRuleExecution
from models.v2_models import Task, Notification, User
from database import SessionLocal

logger = logging.getLogger(__name__)

# ─── 常量 ───────────────────────────────────────────────────────────────
VALID_TRIGGER_TYPES: Set[str] = {
    "task_created", "task_updated", "task_completed",
    "task_overdue", "agent_offline", "schedule",
}
VALID_ACTION_TYPES: Set[str] = {
    "assign", "set_status", "notify", "escalate", "add_comment",
}
# 循环触发保护：同一 task_id 在窗口期内最多触发同一规则一次
LOOP_WINDOW_SECONDS: int = 30
MAX_EXECUTIONS_PER_WINDOW: int = 1

# 线程本地跟踪 _execution_history: Set[str] = set() 用于单次 evaluate 调用内防循环
_execution_history: Set[str] = set()


# ─── 辅助函数 ───────────────────────────────────────────────────────────
def _task_matches_conditions(
    task: Optional[Dict[str, Any]],
    conditions: Dict[str, Any],
) -> bool:
    """检查任务字典是否满足规则条件（AND 逻辑）。"""
    if not task or not conditions:
        return True
    for key, expected in conditions.items():
        actual = task.get(key)
        # 支持列表匹配（任一匹配即可）
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _log_execution(db: Session, rule: AutomationRule, trigger_type: str,
                   trigger_payload: Optional[Dict], status: str,
                   action_results: Optional[List] = None,
                   error_message: Optional[str] = None) -> None:
    """记录一次规则执行到 history 表。"""
    try:
        execution = AutomationRuleExecution(
            rule_id=rule.id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            action_results=action_results,
            status=status,
            error_message=error_message,
        )
        db.add(execution)
        db.flush()
    except Exception:
        logger.exception("记录规则执行历史失败 (rule_id=%s)", rule.id)


# ─── 动作执行 ───────────────────────────────────────────────────────────
def _execute_action(action: Dict[str, Any], task: Dict[str, Any],
                    db: Session) -> Dict[str, Any]:
    """执行单条动作。返回结果字典。失败时 try/except 返回 error 状态。"""
    action_type = action.get("type", "")
    params = action.get("params", {})

    if action_type == "assign":
        return _action_assign(task, params, db)
    elif action_type == "set_status":
        return _action_set_status(task, params, db)
    elif action_type == "notify":
        return _action_notify(task, params, db)
    elif action_type == "escalate":
        return _action_escalate(task, params, db)
    elif action_type == "add_comment":
        return _action_add_comment(task, params, db)
    else:
        return {"action_type": action_type, "status": "error",
                "message": f"未知动作类型: {action_type}"}


def _action_assign(task: Dict, params: Dict, db: Session) -> Dict:
    """分配任务给指定负责人。"""
    assignee = params.get("assignee")
    if not assignee:
        return {"action_type": "assign", "status": "error", "message": "缺少 assignee 参数"}
    task_obj = db.query(Task).filter(Task.task_id == task.get("task_id")).first()
    if not task_obj:
        return {"action_type": "assign", "status": "error", "message": "任务不存在"}
    old = task_obj.assignee
    task_obj.assignee = assignee
    if task_obj.status == "pending":
        task_obj.status = "assigned"
    task_obj.updated_at = datetime.now(timezone.utc)
    return {"action_type": "assign", "status": "success",
            "assignee": assignee, "previous_assignee": old}


def _action_set_status(task: Dict, params: Dict, db: Session) -> Dict:
    """设置任务状态。"""
    new_status = params.get("status")
    if not new_status:
        return {"action_type": "set_status", "status": "error", "message": "缺少 status 参数"}
    task_obj = db.query(Task).filter(Task.task_id == task.get("task_id")).first()
    if not task_obj:
        return {"action_type": "set_status", "status": "error", "message": "任务不存在"}
    old_status = task_obj.status
    task_obj.status = new_status
    task_obj.updated_at = datetime.now(timezone.utc)
    return {"action_type": "set_status", "status": "success",
            "new_status": new_status, "old_status": old_status}


def _action_notify(task: Dict, params: Dict, db: Session) -> Dict:
    """向用户发送通知。"""
    users_param = params.get("users")
    if not users_param:
        return {"action_type": "notify", "status": "error", "message": "缺少 users 参数"}
    user_list = users_param if isinstance(users_param, list) else [users_param]
    title = params.get("title", "自动化通知")
    content_template = params.get("content", "规则触发动作: {title}")
    content = content_template.format(title=task.get("title", ""))
    notified: List[str] = []
    for uname in user_list:
        try:
            user_obj = db.query(User).filter(User.username == uname).first()
            user_id = user_obj.id if user_obj else None
            notif = Notification(
                user_id=user_id or 0,
                type="system",
                title=title,
                content=content,
                source_id=task.get("task_id"),
            )
            db.add(notif)
            notified.append(uname)
        except Exception:
            logger.warning("通知用户 %s 失败", uname)
    return {"action_type": "notify", "status": "success", "notified_users": notified}


def _action_escalate(task: Dict, params: Dict, db: Session) -> Dict:
    """升级任务（提高优先级 + 通知）。"""
    new_priority = params.get("priority", "critical")
    manager = params.get("manager")
    task_obj = db.query(Task).filter(Task.task_id == task.get("task_id")).first()
    if not task_obj:
        return {"action_type": "escalate", "status": "error", "message": "任务不存在"}
    old_priority = task_obj.priority
    task_obj.priority = new_priority
    task_obj.updated_at = datetime.now(timezone.utc)
    result: Dict[str, Any] = {
        "action_type": "escalate", "status": "success",
        "new_priority": new_priority, "old_priority": old_priority,
    }
    if manager:
        notif = Notification(
            user_id=0, type="alert",
            title=f"任务升级: {task.get('title', '')}",
            content=f"任务 {task.get('task_id')} 优先级提升至 {new_priority}",
            source_id=task.get("task_id"),
        )
        db.add(notif)
        result["manager_notified"] = manager
    return result


def _action_add_comment(task: Dict, params: Dict, db: Session) -> Dict:
    """向任务添加评论。"""
    from models.v2_models import TaskComment
    content = params.get("content")
    if not content:
        return {"action_type": "add_comment", "status": "error", "message": "缺少 content 参数"}
    task_obj = db.query(Task).filter(Task.task_id == task.get("task_id")).first()
    if not task_obj:
        return {"action_type": "add_comment", "status": "error", "message": "任务不存在"}
    comment = TaskComment(
        task_id=task_obj.task_id,
        content=content,
    )
    db.add(comment)
    return {"action_type": "add_comment", "status": "success"}


# ─── 核心引擎 ───────────────────────────────────────────────────────────
def evaluate(trigger_type: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    评估触发事件并执行匹配规则的动作。

    1. 加载所有活跃规则，筛选 trigger.type 匹配的
    2. 按 priority 升序排序（数字越小越先执行）
    3. 检查循环触发保护
    4. 对每条规则执行所有 actions
    5. 记录执行历史

    Args:
        trigger_type: 触发类型 (task_created / task_updated / ...)
        payload: 事件载荷，至少包含 task_id / task_data

    Returns:
        每条规则的执行结果列表
    """
    if trigger_type not in VALID_TRIGGER_TYPES:
        logger.warning("不支持的触发类型: %s", trigger_type)
        return []

    # 提取 task_id 用于循环检测
    task_id = payload.get("task_id") or payload.get("task_data", {}).get("task_id")
    dedup_key = f"{trigger_type}:{task_id}"
    if dedup_key in _execution_history:
        logger.debug("循环触发保护: 跳过 %s", dedup_key)
        return []
    _execution_history.add(dedup_key)

    db: Session = SessionLocal()
    results: List[Dict[str, Any]] = []

    try:
        # 1. 加载活跃规则并过滤
        rules = (
            db.query(AutomationRule)
            .filter(AutomationRule.is_active)
            .order_by(AutomationRule.priority.asc(), AutomationRule.created_at.asc())
            .all()
        )

        matching_rules = []
        for rule in rules:
            rule_trigger = rule.trigger or {}
            if rule_trigger.get("type") == trigger_type:
                # 检查 conditions
                conditions = rule_trigger.get("conditions", {})
                task_data = payload.get("task_data", {})
                if _task_matches_conditions(task_data, conditions):
                    matching_rules.append(rule)

        logger.info("规则引擎: 触发类型=%s, 匹配规则数=%d", trigger_type, len(matching_rules))

        # 2. 按 priority 依次执行
        for rule in matching_rules:
            rule_result = _execute_rule(rule, trigger_type, payload, task_data, db)
            results.append(rule_result)

        db.commit()

    except Exception:
        logger.exception("规则引擎执行异常")
        db.rollback()
    finally:
        db.close()

    return results


def _execute_rule(
    rule: AutomationRule, trigger_type: str,
    payload: Dict, task_data: Dict, db: Session,
) -> Dict[str, Any]:
    """执行单条规则的所有 actions。"""
    action_results: List[Dict[str, Any]] = []
    has_error = False
    error_msg = None

    for action in (rule.actions or []):
        try:
            result = _execute_action(action, task_data, db)
            action_results.append(result)
            if result.get("status") == "error":
                has_error = True
        except Exception as exc:
            logger.exception("动作执行失败: rule=%s, action=%s", rule.id, action.get("type"))
            action_results.append({
                "action_type": action.get("type"),
                "status": "error",
                "message": str(exc),
            })
            has_error = True
            # 不影响后续动作，继续执行

    status = "failed" if has_error else "success"
    if has_error:
        error_msg = "部分或全部动作执行失败"

    # 记录执行历史
    _log_execution(db, rule, trigger_type, payload, status,
                   action_results=action_results, error_message=error_msg)

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "status": status,
        "action_results": action_results,
        "error_message": error_msg,
    }


def match_rules(
    trigger_type: str,
    task_data: Optional[Dict] = None,
    db: Optional[Session] = None,
) -> List[Dict]:
    """
    仅匹配规则（不执行），返回匹配的规则列表。
    用于预览哪些规则会被触发。
    """
    if trigger_type not in VALID_TRIGGER_TYPES:
        return []

    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        rules = (
            db.query(AutomationRule)
            .filter(AutomationRule.is_active)
            .order_by(AutomationRule.priority.asc())
            .all()
        )
        task_data = task_data or {}
        matching = []
        for rule in rules:
            rule_trigger = rule.trigger or {}
            if rule_trigger.get("type") == trigger_type:
                conditions = rule_trigger.get("conditions", {})
                if _task_matches_conditions(task_data, conditions):
                    matching.append(rule.to_dict())
        return matching
    finally:
        if owns_session:
            db.close()


# ─── 便捷触发接口 ───────────────────────────────────────────────────────
def on_task_created(task: Task) -> List[Dict[str, Any]]:
    """任务创建时触发。"""
    payload = {"task_id": task.task_id, "task_data": task.to_dict()}
    return evaluate("task_created", payload)


def on_task_updated(task: Task, changes: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """任务更新时触发。"""
    task_data = task.to_dict()
    if changes:
        task_data["_changes"] = changes
    payload = {"task_id": task.task_id, "task_data": task_data}
    return evaluate("task_updated", payload)


def on_task_completed(task: Task) -> List[Dict[str, Any]]:
    """任务完成时触发。"""
    payload = {"task_id": task.task_id, "task_data": task.to_dict()}
    return evaluate("task_completed", payload)


def on_task_overdue(task: Task) -> List[Dict[str, Any]]:
    """任务逾期时触发。"""
    payload = {"task_id": task.task_id, "task_data": task.to_dict()}
    return evaluate("task_overdue", payload)
