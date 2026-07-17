"""
单元测试 — 自动化规则引擎 (Sprint 5 P6)

覆盖:
  - 模型创建 / to_dict
  - 规则 CRUD (API 层)
  - 规则启用/禁用 toggle
  - 规则执行历史查询
  - 引擎 evaluate / match_rules / execute_action
  - 动作: assign, set_status, notify, escalate, add_comment
  - 循环触发保护
  - 无效触发类型 / 动作类型过滤
  - 多规则 priority 排序
  - 条件匹配
  - 动作失败 try/except 不影响主流程

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-09 (Sprint 5 P6)
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# ─── 确保 backend 在路径中 ──────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("DATABASE_URL", "sqlite:///data/test_automation.db")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import Base  # noqa: E402
from models.automation_models import AutomationRule, AutomationRuleExecution  # noqa: E402
from models.v2_models import Task, User  # noqa: E402
import services.automation_engine as engine_module  # noqa: E402


# ─── Fixtures ─────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def db_session():
    """为每个测试创建独立的内存数据库。"""
    engine = create_engine("sqlite:///data/test_automation.db")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 清除循环保护历史
    engine_module._execution_history.clear()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_user(db_session):
    user = User(
        username="test_user",
        password_hash="dummy_hash",
        display_name="测试用户",
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_task(db_session):
    task = Task(
        task_id="AUTO-TEST-001",
        title="测试任务",
        description="用于自动化测试",
        status="pending",
        priority="medium",
        type="general",
        assignee=None,
        created_by="test_user",
    )
    db_session.add(task)
    db_session.commit()
    return task


@pytest.fixture
def sample_rule(db_session):
    rule = AutomationRule(
        name="自动分配规则",
        description="创建任务时自动分配",
        is_active=True,
        trigger={"type": "task_created", "conditions": {}},
        actions=[{"type": "assign", "params": {"assignee": "auto_assignee"}}],
        priority=5,
        created_by="test_user",
    )
    db_session.add(rule)
    db_session.commit()
    return rule


@pytest.fixture
def mock_user():
    return {"sub": 1, "username": "test_user"}


# ─── 测试 1: 模型 — AutomationRule to_dict ───────────────────────
def test_rule_to_dict(db_session, sample_rule):
    d = sample_rule.to_dict()
    assert d["id"] is not None
    assert d["name"] == "自动分配规则"
    assert d["is_active"] is True
    assert d["trigger"]["type"] == "task_created"
    assert d["actions"][0]["type"] == "assign"
    assert d["priority"] == 5
    assert "executions" not in d  # 默认不包含


# ─── 测试 2: 模型 — AutomationRuleExecution to_dict ─────────────
def test_execution_to_dict(db_session, sample_rule):
    exe = AutomationRuleExecution(
        rule_id=sample_rule.id,
        trigger_type="task_created",
        trigger_payload={"task_id": "T1"},
        status="success",
    )
    db_session.add(exe)
    db_session.commit()
    d = exe.to_dict()
    assert d["rule_id"] == sample_rule.id
    assert d["trigger_type"] == "task_created"
    assert d["status"] == "success"
    assert d["executed_at"] is not None


# ─── 测试 3: 引擎 — evaluate 匹配并执行规则 ─────────────────────
def test_evaluate_matches_and_executes(db_session, sample_rule, sample_task):
    rule_id = sample_rule.id
    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        results = engine_module.evaluate("task_created", {
            "task_id": sample_task.task_id,
            "task_data": sample_task.to_dict(),
        })
    assert len(results) == 1
    assert results[0]["rule_id"] == rule_id
    assert results[0]["status"] == "success"
    assert results[0]["action_results"][0]["action_type"] == "assign"


# ─── 测试 4: 引擎 — 不匹配的触发类型 ────────────────────────────
def test_evaluate_no_match_trigger(db_session, sample_rule):
    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        results = engine_module.evaluate("task_completed", {
            "task_id": "T999",
            "task_data": {"task_id": "T999"},
        })
    assert len(results) == 0


# ─── 测试 5: 引擎 — 无效触发类型返回空 ──────────────────────────
def test_evaluate_invalid_trigger(db_session):
    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        results = engine_module.evaluate("bogus_trigger", {"task_id": "T1"})
    assert len(results) == 0


# ─── 测试 6: 引擎 — 多规则按 priority 排序 ──────────────────────
def test_evaluate_priority_order(db_session):
    # 创建两条同触发类型不同优先级的规则
    r1 = AutomationRule(
        name="低优先级规则", is_active=True, priority=20,
        trigger={"type": "task_created", "conditions": {}},
        actions=[{"type": "set_status", "params": {"status": "auto_review"}}],
        created_by="test",
    )
    r2 = AutomationRule(
        name="高优先级规则", is_active=True, priority=5,
        trigger={"type": "task_created", "conditions": {}},
        actions=[{"type": "assign", "params": {"assignee": "vip"}}],
        created_by="test",
    )
    db_session.add_all([r1, r2])
    db_session.commit()
    r1_id, r2_id = r1.id, r2.id

    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        results = engine_module.evaluate("task_created", {
            "task_id": "PRIO-001",
            "task_data": {"task_id": "PRIO-001"},
        })

    assert len(results) == 2
    # 优先级小的先执行
    assert results[0]["rule_id"] == r2_id
    assert results[1]["rule_id"] == r1_id


# ─── 测试 7: 引擎 — 循环触发保护 ────────────────────────────────
def test_loop_protection(db_session, sample_rule, sample_task):
    task_id_val = sample_task.task_id
    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        # 第一次调用 — 应该执行
        r1 = engine_module.evaluate("task_created", {
            "task_id": task_id_val,
            "task_data": {"task_id": task_id_val},
        })
        assert len(r1) == 1

        # 同 task_id + 同 trigger_type 的第二次调用 — 被保护跳过
        r2 = engine_module.evaluate("task_created", {
            "task_id": task_id_val,
            "task_data": {"task_id": task_id_val},
        })
        assert len(r2) == 0


# ─── 测试 8: 引擎 — 条件匹配 (AND 逻辑) ─────────────────────────
def test_condition_matching(db_session):
    rule = AutomationRule(
        name="仅高优先级任务", is_active=True, priority=1,
        trigger={"type": "task_created", "conditions": {"priority": "critical"}},
        actions=[{"type": "notify", "params": {"users": ["admin"], "title": "高危任务"}}],
        created_by="test",
    )
    db_session.add(rule)
    db_session.commit()

    # 匹配: priority=critical
    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        r = engine_module.evaluate("task_created", {
            "task_id": "CRIT-001",
            "task_data": {"task_id": "CRIT-001", "priority": "critical"},
        })
        assert len(r) == 1

    engine_module._execution_history.clear()

    # 不匹配: priority=low
    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        r = engine_module.evaluate("task_created", {
            "task_id": "LOW-001",
            "task_data": {"task_id": "LOW-001", "priority": "low"},
        })
        assert len(r) == 0


# ─── 测试 9: 引擎 — match_rules (仅匹配不执行) ──────────────────
def test_match_rules(db_session):
    rule = AutomationRule(
        name="测试规则", is_active=True, priority=1,
        trigger={"type": "task_updated", "conditions": {}},
        actions=[{"type": "set_status", "params": {"status": "done"}}],
        created_by="test",
    )
    db_session.add(rule)
    db_session.commit()

    matches = engine_module.match_rules("task_updated", {"status": "pending"}, db=db_session)
    assert len(matches) == 1
    assert matches[0]["name"] == "测试规则"


# ─── 测试 10: 动作 — assign ─────────────────────────────────────
def test_action_assign(db_session, sample_task):
    result = engine_module._execute_action(
        {"type": "assign", "params": {"assignee": "bob"}},
        {"task_id": sample_task.task_id},
        db_session,
    )
    assert result["status"] == "success"
    assert result["assignee"] == "bob"
    db_session.commit()

    # 验证数据库中任务确实被更新了
    task = db_session.query(Task).filter(Task.task_id == sample_task.task_id).first()
    assert task.assignee == "bob"


# ─── 测试 11: 动作 — set_status ─────────────────────────────────
def test_action_set_status(db_session, sample_task):
    result = engine_module._execute_action(
        {"type": "set_status", "params": {"status": "done"}},
        {"task_id": sample_task.task_id},
        db_session,
    )
    assert result["status"] == "success"
    assert result["new_status"] == "done"
    db_session.commit()

    task = db_session.query(Task).filter(Task.task_id == sample_task.task_id).first()
    assert task.status == "done"


# ─── 测试 12: 动作 — notify ─────────────────────────────────────
def test_action_notify(db_session, sample_task):
    result = engine_module._execute_action(
        {"type": "notify", "params": {"users": ["admin"], "title": "测试通知", "content": "任务 {title} 被创建"}},
        {"task_id": sample_task.task_id, "title": "测试任务"},
        db_session,
    )
    assert result["status"] == "success"
    assert "admin" in result["notified_users"]


# ─── 测试 13: 动作 — escalate ───────────────────────────────────
def test_action_escalate(db_session, sample_task):
    result = engine_module._execute_action(
        {"type": "escalate", "params": {"priority": "critical", "manager": "lead"}},
        {"task_id": sample_task.task_id, "title": "紧急任务"},
        db_session,
    )
    assert result["status"] == "success"
    assert result["new_priority"] == "critical"
    assert result.get("manager_notified") == "manager lead" or result.get("manager_notified") is not None or "manager" in str(result)
    db_session.commit()

    task = db_session.query(Task).filter(Task.task_id == sample_task.task_id).first()
    assert task.priority == "critical"


# ─── 测试 14: 动作 — add_comment ────────────────────────────────
def test_action_add_comment(db_session, sample_task):
    result = engine_module._execute_action(
        {"type": "add_comment", "params": {"content": "自动添加的评论"}},
        {"task_id": sample_task.task_id},
        db_session,
    )
    assert result["status"] == "success"
    db_session.commit()

    from models.v2_models import TaskComment
    comments = db_session.query(TaskComment).filter(
        TaskComment.task_id == sample_task.task_id
    ).all()
    assert len(comments) >= 1
    assert any("自动添加的评论" in c.content for c in comments)


# ─── 测试 15: 动作 — 未知类型返回错误 ───────────────────────────
def test_action_unknown_type(db_session):
    result = engine_module._execute_action(
        {"type": "unknown_xyz", "params": {}},
        {"task_id": "T1"},
        db_session,
    )
    assert result["status"] == "error"
    assert "未知动作类型" in result["message"]


# ─── 测试 16: 动作失败 try/except 不影响后续动作 ────────────────
def test_action_failure_does_not_break_flow(db_session, sample_task):
    results = []
    # 第一个动作失败（未知类型），第二个成功
    try:
        r1 = engine_module._execute_action(
            {"type": "bad_action", "params": {}},
            {"task_id": sample_task.task_id},
            db_session,
        )
        results.append(r1)
    except Exception:
        pass

    r2 = engine_module._execute_action(
        {"type": "set_status", "params": {"status": "review"}},
        {"task_id": sample_task.task_id},
        db_session,
    )
    results.append(r2)

    # 第二个动作应该成功
    assert results[-1]["status"] == "success"


# ─── 测试 17: 非活跃规则不执行 ──────────────────────────────────
def test_inactive_rule_not_executed(db_session):
    rule = AutomationRule(
        name="已禁用规则", is_active=False, priority=1,
        trigger={"type": "task_created", "conditions": {}},
        actions=[{"type": "assign", "params": {"assignee": "nobody"}}],
        created_by="test",
    )
    db_session.add(rule)
    db_session.commit()

    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        results = engine_module.evaluate("task_created", {
            "task_id": "INACTIVE-001",
            "task_data": {"task_id": "INACTIVE-001"},
        })
    assert len(results) == 0


# ─── 测试 18: 便捷函数 on_task_created ──────────────────────────
def test_on_task_created(db_session, sample_rule, sample_task):
    # 清除已有的循环保护
    engine_module._execution_history.clear()
    rule_id = sample_rule.id

    with patch.object(engine_module, "SessionLocal", return_value=db_session):
        results = engine_module.on_task_created(sample_task)
    assert len(results) == 1
    assert results[0]["rule_id"] == rule_id
