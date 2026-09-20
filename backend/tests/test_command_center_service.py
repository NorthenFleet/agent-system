import asyncio
import json
import sqlite3

import pytest

import services.openclaw_cli as openclaw_cli_module
import services.command_center_worker as command_worker_module
from services.agent_capability_registry import agent_capability_registry
from services.command_center_service import (
    CommandCenterError,
    CommandCenterService,
    InvalidMissionTransition,
)
from services.command_center_worker import (
    CommandCenterWorker,
    normalize_memory_candidates,
    normalize_plan,
)
from services.openclaw_task_executor import ExecutionResult, _agent_visible_output
from services.plan_quality_service import PlanQualityService
from services.work_run_service import WorkRunService


def _sample_plan():
    return {
        "summary": "两步协作计划",
        "rationale": "先分析后复核",
        "risk_level": "low",
        "steps": [
            {
                "order_index": 1,
                "title": "执行",
                "description": "完成目标",
                "task_type": "coordination",
                "agent_id": "optimus",
                "depends_on": [],
            },
            {
                "order_index": 2,
                "title": "复核",
                "description": "检查结果",
                "task_type": "review",
                "agent_id": "shockwave",
                "depends_on": [1],
            },
        ],
    }


def test_mission_run_backfill_links_legacy_events(tmp_path):
    db_path = str(tmp_path / "mission-run-backfill.db")
    service = CommandCenterService(db_path)
    mission = service.create_mission(
        objective="迁移旧任务运行记录",
        requested_by="admin",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE mission_events SET mission_run_id=NULL, correlation_id=NULL, run_sequence=0"
        )
        conn.execute("DELETE FROM mission_runs WHERE mission_id=?", (mission["id"],))

    restarted = CommandCenterService(db_path)
    ledger = restarted.get_mission_run_ledger(mission["id"])

    assert ledger["run"]["id"].startswith("mrun-")
    assert ledger["events"]
    assert all(
        event["mission_run_id"] == ledger["run"]["id"]
        for event in ledger["events"]
    )
    assert [event["run_sequence"] for event in ledger["events"]] == list(
        range(1, len(ledger["events"]) + 1)
    )


def _test_projects():
    return [
        {
            "id": "project-software",
            "name": "OpenClaw 团队信息看板",
            "project_type": "software",
            "status": "active",
            "product_bindings": [{"product_id": "openclaw-3021"}],
        },
        {
            "id": "project-document",
            "name": "博士论文",
            "project_type": "document",
            "status": "active",
        },
    ]


def _routed_service(tmp_path, name="command-center.db"):
    return CommandCenterService(
        str(tmp_path / name),
        project_provider=_test_projects,
    )


def _bind_external(
    service: CommandCenterService,
    external_user_id: str,
    *,
    internal_user_id: str = "1",
):
    service.upsert_external_user_binding(
        channel="feishu",
        external_user_id=external_user_id,
        internal_user_id=internal_user_id,
        profile_user_id=internal_user_id,
    )


def test_enqueue_step_notification_uses_conversation_metadata_column(tmp_path):
    service = _routed_service(tmp_path, "step-notification.db")
    _bind_external(service, "ou_step_notify")
    inbound = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_step_notify",
        user_external_id="ou_step_notify",
        content="创建一个需要独立审校的任务",
        external_message_id="om_step_notify",
        metadata={
            "target": "oc_step_notify",
            "intent_type": "software_project",
            "intent_confidence": 0.99,
            "execution_requested": True,
            "project_id": "project-software",
        },
    )
    mission = inbound["mission"]

    service.enqueue_step_notification(
        step={"id": "step-notify", "agent_id": "optimus", "title": "独立审校"},
        mission=mission,
        result={"success": True, "output": "审校完成"},
    )

    with service.connect() as conn:
        queued = conn.execute(
            """
            SELECT account_id, target, status, message_text
            FROM notification_outbox
            WHERE mission_id=? AND idempotency_key LIKE 'step-done:%'
            """,
            (mission["id"],),
        ).fetchone()
    assert queued is not None
    assert queued["account_id"] == "optimus"
    assert queued["target"] == "oc_step_notify"
    assert queued["status"] == "pending"
    assert "独立审校" in queued["message_text"]


def test_mission_is_idempotent_approval_gated_and_dependency_aware(tmp_path):
    service = _routed_service(tmp_path)
    _bind_external(service, "ou_user")
    first = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="开发一个新的异步任务功能",
        external_message_id="om_1",
        metadata={
            "target": "oc_chat",
            "intent_type": "software_project",
            "intent_confidence": 0.96,
            "intent_reason": "明确要求开发异步任务功能",
            "execution_requested": True,
            "project_id": "project-software",
        },
    )
    duplicate = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="开发一个新的异步任务功能",
        external_message_id="om_1",
        metadata={
            "target": "oc_chat",
            "intent_type": "software_project",
            "intent_confidence": 0.96,
            "intent_reason": "明确要求开发异步任务功能",
            "execution_requested": True,
            "project_id": "project-software",
        },
    )

    assert first["action"] == "mission_created"
    assert duplicate["action"] == "duplicate"
    mission_id = first["mission"]["id"]
    assert first["mission"]["status"] == "received"
    assert first["mission"]["mission_type"] == "software"
    assert service.summary()["outbox_pending"] == 1

    planning = service.claim_planning_mission("test-worker")
    assert planning["id"] == mission_id
    proposed = service.save_plan(mission_id, _sample_plan())
    assert proposed["status"] == "awaiting_approval"
    assert [step["status"] for step in proposed["steps"]] == ["draft", "draft"]

    approved = service.approve(mission_id, decided_by="admin")
    assert approved["status"] == "dispatching"
    assert approved["approval_status"] == "approved"

    service.activate_approved_missions()
    first_steps = service.claim_ready_steps("runner", limit=3)
    assert [step["title"] for step in first_steps] == ["执行"]
    service.complete_step(
        first_steps[0]["id"],
        result={"success": True, "output": "done"},
        success=True,
        actor="optimus",
        lease_token=first_steps[0]["lease_token"],
    )
    second_steps = service.claim_ready_steps("runner", limit=3)
    assert [step["title"] for step in second_steps] == ["复核"]
    service.complete_step(
        second_steps[0]["id"],
        result={"success": True, "output": "verified"},
        success=True,
        actor="shockwave",
        lease_token=second_steps[0]["lease_token"],
    )

    evaluating = service.claim_evaluation_mission("runner")
    assert evaluating["status"] == "evaluating"
    completed = service.complete_mission(
        mission_id,
        summary="验收通过",
        success=True,
    )
    assert completed["status"] == "completed"
    assert len(completed["events"]) >= 8


def test_preplanned_mission_reserves_planning_and_saves_supplied_plan(tmp_path):
    service = CommandCenterService(str(tmp_path / "preplanned.db"))
    reserved = service.create_mission(
        objective="课程批次预编排",
        requested_by="admin",
        project_id="project-course",
        reserve_planning=True,
        planning_owner="course-panel",
    )

    assert reserved["status"] == "planning"
    assert reserved["lease_owner"] == "course-panel"
    assert service.claim_planning_mission("background-planner") is None

    service.cancel(reserved["id"], actor="admin", comment="结束预留测试")
    planned = service.create_preplanned_mission(
        objective="执行课程第一轮",
        requested_by="admin",
        project_id="project-course",
        plan=_sample_plan(),
    )

    assert planned["status"] == "awaiting_approval"
    assert planned["plan_version"] == 1
    assert [step["status"] for step in planned["steps"]] == ["draft", "draft"]
    assert [step["agent_id"] for step in planned["steps"]] == [
        "optimus",
        "shockwave",
    ]
    assert planned["plan"]["plan_quality"]["status"] in {"pass", "warning"}
    assert planned["plan"]["raw_plan"]["steps"][0]["acceptance_criteria"]
    assert planned["plan"]["raw_plan"]["steps"][0]["evidence_required"]
    assert planned["steps"][0]["required_tools"]
    assert planned["steps"][0]["tool_requirements"]
    assert planned["steps"][0]["deliverables"]


def test_completed_mission_can_be_reopened_into_new_auditable_plan_version(tmp_path):
    db_path = str(tmp_path / "recovery-plan.db")
    service = CommandCenterService(db_path)
    mission = service.create_mission(objective="验证恢复计划", requested_by="admin")
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _sample_plan())
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    while True:
        steps = service.claim_ready_steps("runner", limit=1)
        if not steps:
            break
        step = steps[0]
        service.complete_step(
            step["id"],
            result={"success": True, "output": "done"},
            success=True,
            actor=step["agent_id"],
            lease_token=step["lease_token"],
        )
    assert service.claim_evaluation_mission("evaluator") is not None
    assert service.complete_mission(
        mission["id"], summary="首轮完成", success=True
    )["status"] == "completed"

    reopened = service.reopen_for_recovery(
        mission["id"],
        actor="admin",
        reason="发现历史计划存在假完成，保留证据并重新规划",
    )
    recovered = service.save_plan(
        mission["id"],
        {
            "summary": "恢复计划",
            "risk_level": "medium",
            "steps": [
                {
                    "order_index": 1,
                    "title": "从有效交付点恢复",
                    "description": "复用旧版交付物",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "depends_on": [],
                }
            ],
        },
    )

    assert reopened["status"] == "waiting_feedback"
    assert reopened["completed_at"] is None
    assert recovered["plan_version"] == 2
    assert recovered["status"] == "awaiting_approval"
    with service.connect() as conn:
        versions = conn.execute(
            "SELECT plan_version, COUNT(*) AS count FROM mission_steps "
            "WHERE mission_id=? GROUP BY plan_version ORDER BY plan_version",
            (mission["id"],),
        ).fetchall()
    assert [(row["plan_version"], row["count"]) for row in versions] == [(1, 2), (2, 1)]
    assert any(
        event["event_type"] == "mission_reopened_for_recovery"
        for event in recovered["events"]
    )


def test_ready_step_claim_ignores_stale_plan_versions(tmp_path):
    service = CommandCenterService(str(tmp_path / "current-plan-claim.db"))
    mission = service.create_mission(objective="验证只领取当前计划", requested_by="admin")
    service.claim_planning_mission("planner")
    service.save_plan(
        mission["id"],
        {
            "summary": "旧计划",
            "risk_level": "low",
            "steps": [
                {
                    "order_index": 1,
                    "title": "旧版步骤",
                    "description": "用于制造旧版本残留",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "depends_on": [],
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    old_step = service.claim_ready_steps("runner-v1", limit=1)[0]
    service.complete_step(
        old_step["id"],
        result={"success": True, "output": "done"},
        success=True,
        actor="optimus",
        lease_token=old_step["lease_token"],
    )
    service.claim_evaluation_mission("evaluator")
    service.complete_mission(mission["id"], summary="首轮完成", success=True)

    service.reopen_for_recovery(mission["id"], actor="admin", reason="创建第二版计划")
    service.save_plan(
        mission["id"],
        {
            "summary": "当前计划",
            "risk_level": "low",
            "steps": [
                {
                    "order_index": 1,
                    "title": "当前版本步骤",
                    "description": "必须被领取",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "depends_on": [],
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    with service.connect(immediate=True) as conn:
        conn.execute(
            "UPDATE mission_steps SET status='ready', order_index=0 WHERE id=?",
            (old_step["id"],),
        )

    claimed = service.claim_ready_steps("runner-v2", limit=1)

    assert len(claimed) == 1
    assert claimed[0]["plan_version"] == 2
    assert claimed[0]["title"] == "当前版本步骤"

def test_plan_quality_blocks_unknown_agent_before_approval(tmp_path):
    service = CommandCenterService(str(tmp_path / "plan-quality.db"))
    mission = service.create_mission(
        objective="执行一个安全计划",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    bad_plan = _sample_plan()
    bad_plan["steps"][0]["agent_id"] = "unknown-agent"

    with pytest.raises(CommandCenterError, match="计划质量检查未通过"):
        service.save_plan(mission["id"], bad_plan)

    latest = service.get_mission(mission["id"])
    assert latest["status"] == "planning"
    assert latest["plan"] is None


def test_plan_quality_service_enriches_plan_v2_fields():
    enriched = PlanQualityService().enrich_plan(_sample_plan())

    assert enriched["schema_version"] == "2.0"
    assert enriched["plan_quality"]["checked_rules"]
    assert enriched["plan_quality"]["tool_summary"]["total"] >= 1
    assert enriched["capability_registry"]["version"] == "p1-local"
    for step in enriched["steps"]:
        assert step["required_tools"]
        assert step["tool_requirements"]
        assert step["deliverables"]
        assert step["acceptance_criteria"]
        assert step["evidence_required"]


def test_capability_registry_catalog_exposes_agents_and_tools():
    catalog = agent_capability_registry.catalog()

    assert any(agent["id"] == "optimus" for agent in catalog["agents"])
    assert any(tool["id"] == "codex" for tool in catalog["tools"])
    assert catalog["task_agent_defaults"]["backend"] == "raphael"
    assert catalog["task_type_defaults"]["frontend"]["required_tools"] == ["codex", "build_runner"]


def test_plan_quality_blocks_unregistered_required_tool(tmp_path):
    service = CommandCenterService(str(tmp_path / "plan-tool-quality.db"))
    mission = service.create_mission(
        objective="开发 API",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    bad_plan = _sample_plan()
    bad_plan["steps"][0]["required_tools"] = ["unknown_tool"]

    with pytest.raises(CommandCenterError, match="未注册工具"):
        service.save_plan(mission["id"], bad_plan)


def test_ready_step_and_completion_include_execution_quality(tmp_path):
    service = CommandCenterService(str(tmp_path / "execution-quality.db"))
    mission = service.create_mission(
        objective="开发 API",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _sample_plan())
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()

    step = service.claim_ready_steps("runner", limit=1)[0]
    assert step["required_tools"]
    assert step["evidence_required"]
    assert step["tool_requirements"]

    completed = service.complete_step(
        step["id"],
        result={"success": True, "output": "任务输出：完成目标；风险说明：无；证据：context_pack"},
        success=True,
        actor=step["agent_id"],
        lease_token=step["lease_token"],
    )

    assert completed["result"]["execution_quality"]["status"] in {"pass", "warning"}
    assert completed["result"]["execution_quality"]["checked_rules"]
    assert completed["required_tools"]


def test_rejection_and_feedback_resume_without_creating_another_mission(tmp_path):
    service = CommandCenterService(str(tmp_path / "feedback.db"))
    mission = service.create_mission(
        objective="整理一份研究报告",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _sample_plan())
    rejected = service.reject(
        mission["id"],
        decided_by="admin",
        comment="增加引用核查",
    )
    assert rejected["status"] == "planning"
    assert len(service.list_missions()) == 1
    service.mark_planning_failed(mission["id"], "需要目标范围", actor="planner")
    resumed = service.add_feedback(
        mission["id"],
        actor="admin",
        content="范围限定为最近三年",
    )
    assert resumed["status"] == "planning"
    assert len(service.list_missions()) == 1


def test_external_mission_decisions_are_limited_to_requester(tmp_path):
    service = _routed_service(tmp_path, "external-owner.db")
    _bind_external(service, "ou_owner")
    _bind_external(service, "ou_other", internal_user_id="2")
    created = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_shared",
        user_external_id="ou_owner",
        content="执行协作任务",
        external_message_id="om_owner",
        metadata={
            "intent_type": "software_project",
            "intent_confidence": 0.91,
            "execution_requested": True,
            "project_id": "project-software",
        },
    )
    service.claim_planning_mission("planner")
    service.save_plan(created["mission"]["id"], _sample_plan())

    with pytest.raises(CommandCenterError):
        service.process_inbound(
            channel="feishu",
            external_conversation_id="oc_shared",
            user_external_id="ou_other",
            content=f"批准 {created['mission']['id']}",
            external_message_id="om_other",
        )


def test_external_missions_reject_missing_or_unmapped_identity(tmp_path):
    service = CommandCenterService(str(tmp_path / "external-unmapped.db"))
    with pytest.raises(CommandCenterError, match="verified non-empty sender"):
        service.process_inbound(
            channel="feishu",
            external_conversation_id="oc_shared",
            user_external_id="",
            content="匿名任务",
        )
    with pytest.raises(CommandCenterError, match="not mapped"):
        service.process_inbound(
            channel="feishu",
            external_conversation_id="oc_shared",
            user_external_id="ou_unmapped",
            content="未绑定任务",
        )


def test_cancellation_closes_pending_approval_and_summary(tmp_path):
    service = CommandCenterService(str(tmp_path / "cancel.db"))
    mission = service.create_mission(
        objective="取消前等待审批",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _sample_plan())
    assert service.summary()["pending_approvals"] == 1

    cancelled = service.cancel(
        mission["id"],
        actor="admin",
        comment="需求撤回",
    )

    assert cancelled["status"] == "cancelled"
    assert cancelled["approval_status"] == "cancelled"
    assert cancelled["approval"]["decision"] == "cancelled"
    assert service.summary()["pending_approvals"] == 0


def test_schema_bootstrap_repairs_legacy_cancelled_approval(tmp_path):
    db_path = str(tmp_path / "legacy-cancel.db")
    service = CommandCenterService(db_path)
    mission = service.create_mission(
        objective="历史取消任务",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _sample_plan())
    with service.connect() as conn:
        conn.execute(
            "UPDATE orchestration_missions SET status='cancelled' WHERE id=?",
            (mission["id"],),
        )

    restarted = CommandCenterService(db_path)
    repaired = restarted.get_mission(mission["id"])

    assert repaired["approval_status"] == "cancelled"
    assert repaired["approval"]["decision"] == "cancelled"
    assert restarted.summary()["pending_approvals"] == 0


def test_outbox_records_delivery_and_reply_mapping(tmp_path):
    service = _routed_service(tmp_path, "outbox.db")
    _bind_external(service, "ou_user")
    created = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="为 OpenClaw 3021 开发市场分析模块",
        external_message_id="om_in",
        metadata={
            "target": "oc_chat",
            "intent_type": "software_project",
            "intent_confidence": 0.92,
            "execution_requested": True,
            "project_id": "project-software",
        },
    )
    item = service.claim_outbox("sender")[0]
    delivered = service.record_delivery(
        item["id"],
        success=True,
        response='{"message_id":"om_out"}',
        external_message_id="om_out",
    )
    assert delivered["status"] == "sent"

    feedback = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="补充欧洲市场",
        external_message_id="om_feedback",
        reply_to_external_message_id="om_out",
        metadata={"target": "oc_chat"},
    )
    assert feedback["action"] == "feedback"
    assert feedback["mission"]["id"] == created["mission"]["id"]


def test_general_discussion_is_persisted_without_creating_mission(tmp_path):
    service = _routed_service(tmp_path, "discussion.db")
    _bind_external(service, "ou_user")

    routed = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="分析一下3021是否需要重构，并给出方案",
        external_message_id="om_discussion",
        metadata={
            "target": "oc_chat",
            "intent_type": "software_project",
            "intent_confidence": 0.93,
            "intent_reason": "与软件有关，但用户只要求分析方案",
            "execution_requested": False,
        },
    )

    assert routed["action"] == "discussion"
    assert routed["mission"] is None
    assert service.list_missions() == []
    assert service.summary()["discussion_count"] == 1

    recorded = service.record_conversation_response(
        routed["message"]["id"],
        content="已完成分析，当前先不启动项目任务。",
    )
    assert recorded["action"] == "recorded"
    messages = service.list_routed_messages(owner_user_id="1")
    assert messages[0]["routing_status"] == "answered"
    assert messages[0]["response"]["content"].startswith("已完成分析")


def test_project_execution_requires_unique_existing_project(tmp_path):
    service = _routed_service(tmp_path, "project-gate.db")
    _bind_external(service, "ou_user")

    unclear = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="开始开发这个功能",
        external_message_id="om_unclear",
        metadata={
            "intent_type": "software_project",
            "intent_confidence": 0.91,
            "execution_requested": True,
        },
    )
    assert unclear["action"] == "clarification"
    assert unclear["mission"] is None
    assert unclear["project_candidates"][0]["id"] == "project-software"
    assert service.summary()["clarification_pending"] == 1

    created = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="归入 OpenClaw 团队信息看板并执行",
        external_message_id="om_project_selected",
        metadata={
            "intent_type": "software_project",
            "intent_confidence": 0.97,
            "execution_requested": True,
            "project_id": "project-software",
        },
    )
    assert created["action"] == "mission_created"
    assert created["mission"]["project_id"] == "project-software"
    assert created["mission"]["mission_type"] == "software"
    assert service.summary()["clarification_pending"] == 0


def test_document_execution_creates_only_document_mission(tmp_path):
    service = _routed_service(tmp_path, "document-route.db")
    _bind_external(service, "ou_user")

    created = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="撰写博士论文第二章并交付",
        external_message_id="om_document",
        metadata={
            "intent_type": "document_project",
            "intent_confidence": 0.98,
            "intent_reason": "主要交付物为论文章节",
            "execution_requested": True,
            "project_id": "project-document",
        },
    )

    assert created["action"] == "mission_created"
    assert created["mission"]["mission_type"] == "document"
    assert created["mission"]["project_id"] == "project-document"


def test_low_confidence_or_untyped_execution_fails_closed(tmp_path):
    service = _routed_service(tmp_path, "fail-closed.db")
    _bind_external(service, "ou_user")

    routed = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="做一下这个",
        external_message_id="om_ambiguous",
        metadata={
            "intent_type": "clarification_required",
            "intent_confidence": 0.42,
            "intent_reason": "缺少交付物和项目信息",
            "execution_requested": True,
        },
    )

    assert routed["action"] == "clarification"
    assert routed["mission"] is None
    assert "一般讨论" in routed["clarification_question"]


def test_stale_step_and_persisted_mission_recover_after_restart(tmp_path):
    db_path = str(tmp_path / "recovery.db")
    service = CommandCenterService(db_path)
    mission = service.create_mission(
        objective="验证重启恢复",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _sample_plan())
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    claimed = service.claim_ready_steps("old-worker", limit=1)
    assert claimed[0]["status"] == "running"

    with service.connect() as conn:
        conn.execute(
            "UPDATE mission_steps SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (claimed[0]["id"],),
        )

    restarted = CommandCenterService(db_path)
    assert restarted.get_mission(mission["id"])["status"] == "running"
    assert restarted.requeue_stale_steps() == 1
    recovered = restarted.claim_ready_steps("new-worker", limit=1)
    assert recovered[0]["id"] == claimed[0]["id"]
    with pytest.raises(InvalidMissionTransition):
        restarted.attach_work_run(
            claimed[0]["id"],
            "stale-old-run",
            lease_token=claimed[0]["lease_token"],
        )
    restarted.attach_work_run(
        recovered[0]["id"],
        "current-run",
        lease_token=recovered[0]["lease_token"],
    )
    restarted.renew_step_lease(
        recovered[0]["id"],
        lease_token=recovered[0]["lease_token"],
        lease_seconds=120,
    )
    with pytest.raises(InvalidMissionTransition):
        restarted.complete_step(
            claimed[0]["id"],
            result={"success": True},
            success=True,
            actor="old-worker",
            lease_token=claimed[0]["lease_token"],
        )
    restarted.complete_step(
        recovered[0]["id"],
        result={"success": True},
        success=True,
        actor="new-worker",
        lease_token=recovered[0]["lease_token"],
    )


def test_inflight_recovery_reuses_work_run_and_delivers_once(tmp_path):
    db_path = str(tmp_path / "inflight-idempotency.db")
    service = CommandCenterService(db_path, project_provider=_test_projects)
    work_runs = WorkRunService(db_path)
    _bind_external(service, "reliability-drill")
    mission = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_reliability_drill",
        user_external_id="reliability-drill",
        content="验证在途任务故障恢复与幂等续跑",
        external_message_id="om_inflight_recovery",
        metadata={
            "target": "oc_reliability_drill",
            "intent_type": "software_project",
            "intent_confidence": 0.99,
            "intent_reason": "明确的任务可靠性演练",
            "execution_requested": True,
            "project_id": "project-software",
        },
    )["mission"]
    service.claim_planning_mission("planner")
    service.save_plan(
        mission["id"],
        {
            "summary": "单步骤故障恢复演练",
            "rationale": "验证租约接管、执行幂等和单次交付",
            "risk_level": "low",
            "steps": [
                {
                    "order_index": 1,
                    "title": "写入受控演练回执",
                    "description": "使用固定幂等键生成一次受控回执",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "depends_on": [],
                    "side_effect": True,
                    "resources": ["drill://inflight-receipt"],
                    "idempotency_key": f"inflight:{mission['id']}:step-1",
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="reliability-drill")
    service.activate_approved_missions()
    first_claim = service.claim_ready_steps("worker-a", limit=1)[0]
    idempotency_key = first_claim["idempotency_key"]
    mission_run_id = service.get_mission_run_ledger(mission["id"])["run"]["id"]
    first_run = work_runs.claim(
        dispatch_id=first_claim["id"],
        agent_id="worker-a",
        executor="controlled-drill",
        mission_id=mission["id"],
        mission_run_id=mission_run_id,
        idempotency_key=idempotency_key,
        lease_seconds=60,
    )
    work_runs.transition(first_run["id"], "running", actor="worker-a", lease_seconds=60)
    service.attach_work_run(
        first_claim["id"],
        first_run["id"],
        lease_token=first_claim["lease_token"],
    )

    # Fault injection: worker-a disappeared after applying its effect and both
    # durable leases subsequently expired.
    with service.connect(immediate=True) as conn:
        conn.execute(
            "UPDATE mission_steps SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (first_claim["id"],),
        )
        conn.execute(
            "UPDATE work_runs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (first_run["id"],),
        )

    restarted = CommandCenterService(db_path)
    resumed_runs = WorkRunService(db_path)
    assert restarted.requeue_stale_steps() == 1
    second_claim = restarted.claim_ready_steps("worker-b", limit=1)[0]
    second_run = resumed_runs.claim(
        dispatch_id=second_claim["id"],
        agent_id="worker-b",
        executor="controlled-drill",
        mission_id=mission["id"],
        mission_run_id=mission_run_id,
        idempotency_key=idempotency_key,
        lease_seconds=60,
    )
    assert second_run["id"] == first_run["id"]
    assert second_run["attempt"] == 1

    with pytest.raises(InvalidMissionTransition):
        restarted.complete_step(
            first_claim["id"],
            result={"summary": "stale completion"},
            success=True,
            actor="worker-a",
            lease_token=first_claim["lease_token"],
        )

    restarted.attach_work_run(
        second_claim["id"],
        second_run["id"],
        lease_token=second_claim["lease_token"],
    )
    result = {
        "summary": "恢复后复用首次副作用回执并完成",
        "artifacts": [
            {
                "artifact_type": "receipt",
                "title": "幂等执行回执",
                "uri": "drill://inflight-receipt/once",
                "content_hash": "a" * 64,
            }
        ],
        "evidence": [
            {
                "evidence_type": "test_output",
                "source_ref": "drill://inflight-receipt/once",
                "summary": "适配器第二次调用返回首次回执，apply_count=1",
            }
        ],
        "side_effects": [
            {
                "effect_key": "controlled-receipt",
                "resource": "drill://inflight-receipt",
                "action": "write-once",
                "status": "applied",
                "idempotency_key": idempotency_key,
                "receipt_ref": "drill://inflight-receipt/once",
                "evidence_refs": ["drill://inflight-receipt/once"],
            }
        ],
    }
    completed_step = restarted.complete_step(
        second_claim["id"],
        result=result,
        success=True,
        actor="worker-b",
        lease_token=second_claim["lease_token"],
    )
    assert completed_step["status"] == "completed"
    resumed_runs.transition(
        second_run["id"],
        "review",
        actor="worker-b",
        result_summary=result["summary"],
        execution_result=result,
    )
    resumed_runs.transition(
        second_run["id"],
        "completed",
        actor="worker-b",
        result_summary=result["summary"],
        execution_result=result,
    )
    assert restarted.claim_evaluation_mission("evaluator") is not None
    first_completion = restarted.complete_mission(
        mission["id"], summary="故障恢复演练通过", success=True, actor="evaluator"
    )
    replayed_completion = restarted.complete_mission(
        mission["id"], summary="重复完成命令", success=True, actor="evaluator-replay"
    )
    assert first_completion["status"] == "completed"
    assert replayed_completion["updated_at"] == first_completion["updated_at"]

    with restarted.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM work_runs WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM work_run_events WHERE run_id=? AND event_type='lease_reclaimed'",
            (first_run["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='step_requeued'",
            (mission["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='step_completed'",
            (mission["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='mission_completed'",
            (mission["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM notification_outbox WHERE mission_id=? AND idempotency_key LIKE 'result:%'",
            (mission["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM mission_artifacts WHERE mission_id=?",
            (mission["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM mission_evidence WHERE mission_id=?",
            (mission["id"],),
        ).fetchone()["count"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM mission_effects WHERE mission_id=?",
            (mission["id"],),
        ).fetchone()["count"] == 1


def test_context_packs_bind_to_plan_versions_and_steps(tmp_path):
    service = CommandCenterService(str(tmp_path / "context-binding.db"))
    mission = service.create_mission(
        objective="开发带背景检索的审批功能",
        requested_by="admin",
        profile_user_id="1",
    )
    planning_pack = {
        "id": "context-planning-1",
        "version": 1,
        "status": "ready",
        "query": mission["objective"],
        "summary": "profile 1 条；knowledge 1 条",
        "items": [
            {
                "item_type": "profile",
                "source_ref": "profile:1",
                "title": "孙总档案",
            },
            {
                "item_type": "knowledge",
                "source_ref": "knowledge:architecture",
                "title": "系统架构",
            },
        ],
        "citations": [
            {"rank": 1, "source_ref": "profile:1", "title": "孙总档案"},
            {
                "rank": 2,
                "source_ref": "knowledge:architecture",
                "title": "系统架构",
            },
        ],
        "retrieval_health": {"profile": {"status": "ready"}},
    }
    planning_binding = service.bind_context_pack(
        mission["id"],
        plan_version=1,
        purpose="planning",
        agent_id="optimus",
        pack=planning_pack,
    )
    assert planning_binding["context_pack_id"] == "context-planning-1"
    assert planning_binding["source_types"] == ["knowledge", "profile"]

    service.claim_planning_mission("planner")
    planned = service.save_plan(mission["id"], _sample_plan())
    assert planned["planning_context"]["context_pack_id"] == "context-planning-1"
    assert planned["planning_context"]["citation_count"] == 2

    step = planned["steps"][0]
    step_binding = service.bind_context_pack(
        mission["id"],
        plan_version=1,
        step_id=step["id"],
        purpose="execution",
        agent_id=step["agent_id"],
        pack={**planning_pack, "id": "context-step-1", "agent_id": step["agent_id"]},
    )
    refreshed = service.get_mission(mission["id"])
    assert step_binding["context_pack_id"] == "context-step-1"
    assert refreshed["steps"][0]["context_binding"]["purpose"] == "execution"
    assert service.summary()["context_ready"] == 2


class FakeExecutor:
    def __init__(self):
        self.calls = []

    async def execute(self, command, command_args=None, timeout_seconds=300):
        self.calls.append((command, command_args, timeout_seconds))
        message = (command_args or {}).get("message", "")
        if '"memory_candidates"' in message:
            return ExecutionResult(
                success=True,
                output=json.dumps(
                    {
                        "summary": "目标已完成，证据完整。",
                        "verdict": "passed",
                        "memory_candidates": [
                            {
                                "target_scope": "profile",
                                "memory_type": "decision",
                                "memory_key": "decision.approval_gate",
                                "title": "审批门禁",
                                "content": "所有计划必须批准后执行。",
                                "importance": "critical",
                                "confidence": 0.95,
                                "evidence_refs": ["[C1]"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            )
        if "JSON schema" in message:
            return ExecutionResult(
                success=True,
                output=json.dumps(_sample_plan(), ensure_ascii=False),
            )
        return ExecutionResult(success=True, output="步骤完成并通过测试。")


class FakeContextService:
    def __init__(self):
        self.calls = []
        self.packs = {}
        self.effect_calls = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        pack_id = f"context-fake-{len(self.calls)}"
        pack = {
            "id": pack_id,
            "version": 1,
            "status": "ready",
            "query": kwargs["query"],
            "summary": "profile 1 条；project 1 条；knowledge 1 条；agent_memory 1 条",
            "retrieval_health": {
                "profile": {"status": "ready"},
                "knowledge": {"status": "ready"},
                "agent_memory": {"status": "ready"},
            },
            "items": [
                {
                    "id": f"{pack_id}-item-1",
                    "item_type": "profile",
                    "source_ref": "profile:1",
                    "title": "孙总工作档案",
                    "content": "计划必须先批准再执行。",
                    "rank_index": 1,
                },
                {
                    "id": f"{pack_id}-item-2",
                    "item_type": "knowledge",
                    "source_ref": "knowledge:architecture",
                    "title": "系统架构",
                    "content": "统一数据库是状态事实源。",
                    "rank_index": 2,
                },
            ],
            "citations": [
                {"rank": 1, "source_ref": "profile:1", "title": "孙总工作档案"},
                {
                    "rank": 2,
                    "source_ref": "knowledge:architecture",
                    "title": "系统架构",
                },
            ],
        }
        self.packs[pack_id] = pack
        return pack

    def get_pack(self, pack_id):
        return self.packs.get(pack_id)

    def render_prompt_context(self, pack, max_chars=12000):
        return (
            f"上下文快照：{pack['id']} V{pack['version']}\n"
            "[C1] 孙总工作档案\n计划必须先批准再执行。\n"
            "[C2] 系统架构\n统一数据库是状态事实源。"
        )[:max_chars]

    def record_memory_effect(self, **kwargs):
        self.effect_calls.append(kwargs)
        return {"id": f"effect-fake-{len(self.effect_calls)}", **kwargs}

class FakeMemoryService:
    def __init__(self):
        self.calls = []

    def enqueue_candidate_job(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "memory-job-fake-1",
            "mission_id": kwargs["mission_id"],
            "status": "pending",
        }

    def process_candidate_job(self, job_id, *, owner):
        kwargs = self.calls[-1]
        return {
            "job": {
                "id": job_id,
                "mission_id": kwargs["mission_id"],
                "status": "completed",
            },
            "candidates": [
                {
                    "id": "memory-candidate-fake-1",
                    "status": "pending_review",
                    "mission_id": kwargs["mission_id"],
                    **kwargs["candidates"][0],
                }
            ],
        }

    def process_pending_jobs(self, *, owner, limit):
        return []


class FakeSender:
    async def send(self, item):
        return {
            "success": True,
            "response": '{"message_id":"sent"}',
            "error": "",
            "external_message_id": f"sent-{item['id']}",
        }


class FailingEvaluationExecutor:
    async def execute(self, command, command_args=None, timeout_seconds=300):
        return ExecutionResult(
            success=False,
            error="evaluation model unavailable",
        )


def test_evaluation_failure_does_not_report_mission_completed(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "evaluation-failure.db")
        service = CommandCenterService(db_path)
        mission = service.create_mission(
            objective="验证评估失败状态",
            requested_by="admin",
            profile_user_id="1",
        )
        service.claim_planning_mission("planner")
        service.save_plan(mission["id"], _sample_plan())
        service.approve(mission["id"], decided_by="admin")
        service.activate_approved_missions()
        first = service.claim_ready_steps("runner", limit=1)[0]
        service.complete_step(
            first["id"],
            result={"success": True},
            success=True,
            actor="optimus",
            lease_token=first["lease_token"],
        )
        second = service.claim_ready_steps("runner", limit=1)[0]
        service.complete_step(
            second["id"],
            result={"success": True},
            success=True,
            actor="shockwave",
            lease_token=second["lease_token"],
        )
        worker = CommandCenterWorker(
            service=service,
            executor=FailingEvaluationExecutor(),
            work_runs=WorkRunService(db_path),
            sender=FakeSender(),
        )

        await worker._evaluate_one()

        blocked = service.get_mission(mission["id"])
        assert blocked["status"] == "waiting_feedback"
        assert blocked["completed_at"] is None
        assert any(
            event["event_type"] == "evaluation_failed"
            for event in blocked["events"]
        )

    asyncio.run(scenario())


def test_worker_discards_plan_when_mission_is_cancelled_during_planning(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "cancel-during-planning.db")
        service = CommandCenterService(db_path)
        mission = service.create_mission(
            objective="验证规划期间取消",
            requested_by="admin",
            profile_user_id="1",
        )

        class CancellingExecutor:
            async def execute(self, command, command_args=None, timeout_seconds=300):
                service.cancel(
                    mission["id"],
                    actor="admin",
                    comment="用户在规划完成前取消",
                )
                return ExecutionResult(
                    success=True,
                    output=json.dumps(_sample_plan(), ensure_ascii=False),
                )

        worker = CommandCenterWorker(
            service=service,
            executor=CancellingExecutor(),
            work_runs=WorkRunService(db_path),
            sender=FakeSender(),
            context_service=FakeContextService(),
        )

        await worker._plan_one()

        cancelled = service.get_mission(mission["id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["plan"] is None
        assert not any(
            event["event_type"] == "plan_generated"
            for event in cancelled["events"]
        )

    asyncio.run(scenario())


def test_worker_completes_approved_mission_with_work_runs(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "worker.db")
        service = CommandCenterService(db_path)
        executor = FakeExecutor()
        context_service = FakeContextService()
        memory_service = FakeMemoryService()
        worker = CommandCenterWorker(
            service=service,
            executor=executor,
            work_runs=WorkRunService(db_path),
            sender=FakeSender(),
            context_service=context_service,
            memory_service=memory_service,
        )
        mission = service.create_mission(
            objective="开发异步审批功能",
            requested_by="admin",
            profile_user_id="1",
        )
        await worker._plan_one()
        planned = service.get_mission(mission["id"])
        assert planned["status"] == "awaiting_approval"
        assert planned["planning_context"]["status"] == "ready"
        assert planned["planning_context"]["context_pack_id"] == "context-fake-1"
        assert "<BACKGROUND_CONTEXT>" in executor.calls[0][1]["message"]
        assert "[C1]" in executor.calls[0][1]["message"]
        service.approve(mission["id"], decided_by="admin")
        service.activate_approved_missions()

        while True:
            steps = service.claim_ready_steps("test-runner", limit=3)
            if not steps:
                break
            await asyncio.gather(*(worker._execute_step(step) for step in steps))
        await worker._evaluate_one()
        completed = service.get_mission(mission["id"])
        assert completed["status"] == "completed"
        assert all(step["work_run_id"] for step in completed["steps"])
        assert all(step["context_binding"]["status"] == "ready" for step in completed["steps"])
        assert all(step["result"]["context"]["context_pack_id"] for step in completed["steps"])
        assert len(context_service.calls) == 3
        assert len(memory_service.calls) == 1
        assert memory_service.calls[0]["user_id"] == "1"
        assert memory_service.calls[0]["candidates"][0]["target_scope"] == "profile"
        assert any(
            event["event_type"] == "memory_candidates_proposed"
            for event in completed["events"]
        )
        assert context_service.calls[0]["purpose"] == "planning"
        assert {
            call["agent_id"] for call in context_service.calls[1:]
        } == {"optimus", "shockwave"}
        assert len(context_service.effect_calls) == 8
        assert [call["event_type"] for call in context_service.effect_calls].count("used") == 4
        assert [call["event_type"] for call in context_service.effect_calls].count("task_outcome") == 4
        assert all(call["user_id"] == "1" for call in context_service.effect_calls)
        assert {
            call["outcome"]
            for call in context_service.effect_calls
            if call["event_type"] == "task_outcome"
        } == {"success"}
        assert WorkRunService(db_path).summary()["counts"]["completed"] == 2
        ledger = service.get_mission_run_ledger(mission["id"])
        mission_run = ledger["run"]
        assert mission_run["status"] == "completed"
        assert mission_run["outcome"] == "completed"
        assert mission_run["id"].startswith("mrun-")
        assert len(ledger["step_runs"]) == 2
        assert {
            row["mission_run_id"] for row in ledger["step_runs"]
        } == {mission_run["id"]}
        assert {
            row["correlation_id"] for row in ledger["step_runs"]
        } == {mission_run["correlation_id"]}
        assert [event["run_sequence"] for event in ledger["events"]] == list(
            range(1, len(ledger["events"]) + 1)
        )

    asyncio.run(scenario())


def test_worker_course_step_stops_at_review_and_updates_bound_point(
    tmp_path,
    monkeypatch,
):
    class FakePointManager:
        def __init__(self):
            self.transitions = []

        def transition_point(
            self,
            point_id,
            action,
            agent_id="",
            reason="",
            completion_evidence="",
            result_summary="",
        ):
            self.transitions.append(
                {
                    "point_id": point_id,
                    "action": action,
                    "agent_id": agent_id,
                    "reason": reason,
                    "completion_evidence": completion_evidence,
                    "result_summary": result_summary,
                }
            )
            return {"point": {"id": point_id, "status": action}}

    async def scenario():
        db_path = str(tmp_path / "course-worker.db")
        service = CommandCenterService(db_path)
        point_manager = FakePointManager()
        monkeypatch.setattr(command_worker_module, "project_manager", point_manager)
        executor = FakeExecutor()
        worker = CommandCenterWorker(
            service=service,
            executor=executor,
            work_runs=WorkRunService(db_path),
            sender=FakeSender(),
            context_service=FakeContextService(),
        )
        mission = service.create_preplanned_mission(
            objective="执行课程基线要点",
            requested_by="admin",
            project_id="proj-course",
            context={"course_execution": True},
            plan={
                "summary": "课程基线",
                "steps": [
                    {
                        "order_index": 1,
                        "title": "统一20学时课程口径",
                        "description": "完成课程基线",
                        "task_type": "writing",
                        "agent_id": "ultra-magnus",
                        "depends_on": [],
                        "input": {
                            "task_id": "task-baseline",
                            "development_point_id": "point-baseline",
                            "course_iteration": 1,
                        },
                    }
                ],
            },
            auto_approve=True,
        )
        service.activate_approved_missions()
        step = service.claim_ready_steps("course-runner", limit=1)[0]

        await worker._execute_step(step)

        completed_step = service.get_mission(mission["id"])["steps"][0]
        run = WorkRunService(db_path).get(completed_step["work_run_id"])
        assert run["status"] == "review"
        assert run["task_id"] == "task-baseline"
        assert run["development_point_id"] == "point-baseline"
        assert [row["action"] for row in point_manager.transitions] == [
            "claim",
            "submit_review",
        ]
        assert "步骤输入" in executor.calls[-1][1]["message"]
        assert "point-baseline" in executor.calls[-1][1]["message"]

    asyncio.run(scenario())


def test_plan_normalization_rejects_unknown_agents_and_forward_dependencies():
    plan = normalize_plan(
        {
            "steps": [
                {
                    "title": "后端",
                    "task_type": "backend",
                    "agent_id": "unknown",
                    "depends_on": [2, 99],
                }
            ]
        },
        "开发 API",
    )
    assert plan["steps"][0]["agent_id"] == "raphael"
    assert plan["steps"][0]["depends_on"] == []

    filtered = normalize_plan(
        {
            "steps": [
                {"title": "实现", "agent_id": "raphael", "depends_on": []},
                {
                    "title": "孙总人工审批",
                    "agent_id": "optimus",
                    "task_type": "coordination",
                    "depends_on": [1],
                },
            ]
        },
        "开发 API",
    )
    assert [step["title"] for step in filtered["steps"]] == ["实现"]


def test_plan_normalization_preserves_plan_v2_fields():
    plan = normalize_plan(
        {
            "schema_version": "2.0",
            "summary": "开发任务",
            "steps": [
                {
                    "title": "实现接口",
                    "task_type": "backend",
                    "agent_id": "raphael",
                    "depends_on": [],
                    "required_tools": ["codex", "test_runner"],
                    "deliverables": ["接口实现", "测试结果"],
                    "acceptance_criteria": ["接口返回正确"],
                    "evidence_required": ["test_output"],
                    "risk_level": "high",
                    "rollback_plan": "验证失败则停止合并",
                }
            ],
        },
        "开发 API",
    )
    step = plan["steps"][0]
    assert plan["schema_version"] == "2.0"
    assert step["required_tools"] == ["codex", "test_runner"]
    assert step["deliverables"] == ["接口实现", "测试结果"]
    assert step["acceptance_criteria"] == ["接口返回正确"]
    assert step["evidence_required"] == ["test_output"]
    assert step["risk_level"] == "high"
    assert step["rollback_plan"] == "验证失败则停止合并"


def test_planning_prompt_requests_plan_v2_quality_fields():
    prompt = CommandCenterWorker._planning_prompt(
        {"id": "mission-test", "objective": "开发 API", "events": []},
        "[C1] 背景",
    )
    assert "schema_version" in prompt
    assert "required_tools" in prompt
    assert "deliverables" in prompt
    assert "acceptance_criteria" in prompt
    assert "evidence_required" in prompt
    assert "rollback_plan" in prompt


def test_step_prompt_includes_execution_contract():
    prompt = CommandCenterWorker._step_prompt(
        {
            "id": "mission-test",
            "objective": "开发 API",
            "steps": [],
        },
        {
            "id": "step-test",
            "title": "实现接口",
            "description": "完成 API",
            "input": {},
            "required_tools": ["codex", "test_runner"],
            "deliverables": ["API 实现"],
            "acceptance_criteria": ["测试通过"],
            "evidence_required": ["test_output"],
            "rollback_plan": "验证失败则停止合并",
        },
        "[C1] 背景",
    )

    assert "<EXECUTION_CONTRACT>" in prompt
    assert "codex" in prompt
    assert "test_output" in prompt
    assert "工具使用" in prompt
    assert "不得指向目录" in prompt
    assert "测试结果必须写入独立报告文件" in prompt
    assert "artifact_type=build_artifact" in prompt
    assert "不得再返回 dist/ 目录" in prompt


def test_execution_context_uses_bounded_default_memory_budget(monkeypatch):
    worker = object.__new__(CommandCenterWorker)
    captured = {}

    async def fake_ensure_context_pack(mission, **kwargs):
        captured.update(kwargs)
        return None, ""

    worker._ensure_context_pack = fake_ensure_context_pack
    monkeypatch.delenv("COMMAND_CENTER_EXECUTION_CONTEXT_LIMIT", raising=False)
    monkeypatch.delenv("COMMAND_CENTER_EXECUTION_CONTEXT_MAX_CHARS", raising=False)

    asyncio.run(
        worker._execution_context(
            {"id": "mission-test", "objective": "verify", "plan_version": 3},
            {
                "id": "step-test",
                "title": "build",
                "description": "run checks",
                "task_type": "testing",
                "agent_id": "michelangelo",
            },
        )
    )

    assert captured["limit"] == 8
    assert captured["max_chars"] == 4000


def test_step_prompt_prioritizes_dependency_handoffs_over_large_old_results():
    copy_uri = "/tmp/one-sim-website-copy.md"
    mission = {
        "id": "mission-handoff",
        "objective": "构建 One-Sim 网站",
        "steps": [
            {
                "id": "step-1",
                "order_index": 1,
                "title": "事实盘点",
                "agent_id": "ironhide",
                "status": "completed",
                "dependencies": [],
                "result": {"summary": "x" * 20000, "outcome": "succeeded"},
            },
            {
                "id": "step-3",
                "order_index": 3,
                "title": "技术方案",
                "agent_id": "leonardo",
                "status": "completed",
                "dependencies": ["step-1"],
                "result": {"summary": "技术方案已完成", "outcome": "succeeded"},
            },
            {
                "id": "step-4",
                "order_index": 4,
                "title": "内容撰写",
                "agent_id": "ironhide",
                "status": "completed",
                "dependencies": ["step-1", "step-3"],
                "result": {
                    "summary": "One-Sim 网站文案已完成",
                    "outcome": "succeeded",
                    "artifacts": [
                        {
                            "artifact_key": "copy",
                            "artifact_type": "content_docs",
                            "title": "One-Sim 网站文案",
                            "uri": copy_uri,
                            "content_hash": "a" * 64,
                        }
                    ],
                },
            },
        ],
    }
    step = {
        "id": "step-5",
        "title": "前端实现",
        "description": "使用步骤 4 文案",
        "input": {},
        "dependencies": ["step-3", "step-4"],
    }

    prompt = CommandCenterWorker._step_prompt(mission, step)

    assert "direct_dependencies_then_transitive_ancestors" in prompt
    assert copy_uri in prompt
    assert "One-Sim 网站文案已完成" in prompt
    assert "x" * 2000 not in prompt
    assert '"outcome":"succeeded|blocked|failed|needs_input"' in prompt


class BlockedEvaluationExecutor:
    async def execute(self, command, command_args=None, timeout_seconds=300):
        return ExecutionResult(
            success=True,
            output=json.dumps(
                {
                    "verdict": "blocked",
                    "summary": "交付物不完整，等待修复",
                    "blockers": ["前端交付物缺失"],
                    "memory_candidates": [],
                },
                ensure_ascii=False,
            ),
        )


def test_blocked_evaluation_cannot_complete_mission(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "blocked-evaluation.db")
        service = CommandCenterService(db_path)
        mission = service.create_mission(objective="验证最终阻塞", requested_by="admin")
        service.claim_planning_mission("planner")
        service.save_plan(mission["id"], _sample_plan())
        service.approve(mission["id"], decided_by="admin")
        service.activate_approved_missions()
        while True:
            steps = service.claim_ready_steps("runner", limit=1)
            if not steps:
                break
            claimed = steps[0]
            service.complete_step(
                claimed["id"],
                result={"success": True, "output": "done"},
                success=True,
                actor=claimed["agent_id"],
                lease_token=claimed["lease_token"],
            )
        worker = CommandCenterWorker(
            service=service,
            executor=BlockedEvaluationExecutor(),
            work_runs=WorkRunService(db_path),
            sender=FakeSender(),
        )

        await worker._evaluate_one()

        blocked = service.get_mission(mission["id"])
        assert blocked["status"] == "waiting_feedback"
        assert blocked["completed_at"] is None
        assert blocked["last_error"] == "交付物不完整，等待修复"

    asyncio.run(scenario())


def test_memory_candidate_normalization_enforces_scopes_and_evidence():
    mission = {
        "project_id": "project-1",
        "context": {"profile_user_id": "1"},
        "steps": [{"id": "step-1"}],
    }
    candidates = normalize_memory_candidates(
        {
            "memory_candidates": [
                {
                    "target_scope": "profile",
                    "memory_key": "decision.single_entry",
                    "title": "唯一入口",
                    "content": "擎天柱是唯一任务入口。",
                    "importance": "critical",
                    "confidence": 1.4,
                    "agent_id": "unknown",
                    "step_id": "not-a-step",
                    "evidence_refs": ["step-1", "[C1]"],
                },
                {
                    "target_scope": "project",
                    "memory_key": "architecture.database",
                    "content": "统一 SQLite 是事实源。",
                    "agent_id": "optimus",
                    "step_id": "step-1",
                },
                {
                    "target_scope": "unsupported",
                    "memory_key": "bad",
                    "content": "bad",
                },
            ]
        },
        mission,
    )

    assert len(candidates) == 2
    assert candidates[0]["confidence"] == 1.0
    assert candidates[0]["agent_id"] == "optimus"
    assert candidates[0]["step_id"] == ""
    assert candidates[1]["step_id"] == "step-1"


def test_openclaw_json_result_is_reduced_to_visible_agent_text():
    raw = json.dumps(
        {
            "status": "ok",
            "result": {
                "payloads": [{"text": "VISIBLE_RESULT", "mediaUrl": None}],
                "finalAssistantVisibleText": "VISIBLE_RESULT",
            },
        }
    )
    assert _agent_visible_output(raw) == "VISIBLE_RESULT"


def test_openclaw_command_prefers_stable_node_runtime(tmp_path, monkeypatch):
    node = tmp_path / "node"
    script = tmp_path / "openclaw.js"
    path_cli = tmp_path / "openclaw"
    node.write_text("", encoding="utf-8")
    script.write_text("", encoding="utf-8")
    path_cli.write_text("", encoding="utf-8")
    monkeypatch.delenv("OPENCLAW_BIN", raising=False)
    monkeypatch.setattr(openclaw_cli_module, "DEFAULT_NODE", node)
    monkeypatch.setattr(openclaw_cli_module, "DEFAULT_OPENCLAW_SCRIPT", script)
    monkeypatch.setattr(openclaw_cli_module.shutil, "which", lambda _name: str(path_cli))

    command = openclaw_cli_module.openclaw_command("status", "--json")

    assert command == [str(node), str(script), "status", "--json"]


def test_task_workbench_projects_mission_steps_and_agent(tmp_path, monkeypatch):
    service = _routed_service(tmp_path, "workbench.db")
    _bind_external(service, "ou_user")
    synced = []

    def fake_sync(mission):
        synced.append(mission)
        return {"synced": 1, "changed": 1, "deleted": 0, "failed": 0, "total": 1}

    monkeypatch.setattr("services.project_task_sync.sync_command_center_mission_to_v2", fake_sync)
    monkeypatch.setattr(service, "_load_task_ledger", lambda: [{
        "task_id": "ledger-1",
        "title": "生产侧关联任务",
        "source": "command-center",
        "assignee": "raphael",
        "mission_id": synced[-1]["id"] if synced else "",
        "project_id": "project-software",
        "project_name": "OpenClaw 团队信息看板",
        "tags": [],
    }] if synced else [])

    created = service.process_inbound(
        channel="feishu",
        external_conversation_id="oc_chat",
        user_external_id="ou_user",
        content="开发 OpenClaw 统一任务工作台",
        external_message_id="om_workbench",
        metadata={
            "intent_type": "software_project",
            "intent_confidence": 0.97,
            "execution_requested": True,
            "project_id": "project-software",
        },
    )
    mission_id = created["mission"]["id"]
    service.claim_planning_mission("optimus")
    service.save_plan(mission_id, _sample_plan())

    workbench = service.list_task_workbench(agent_id="optimus")

    assert workbench["total"] == 1
    item = workbench["items"][0]
    assert item["mission_id"] == mission_id
    assert item["project_name"] == "OpenClaw 团队信息看板"
    assert item["current_agent_id"] == "optimus"
    assert item["current_agent_name"] == "擎天柱"
    assert item["steps_summary"]["total"] == 2
    assert item["linked_tasks"][0]["source"] == "command-center"


def test_agent_space_enforces_optimus_single_entry(tmp_path, monkeypatch):
    service = _routed_service(tmp_path, "space.db")
    monkeypatch.setattr(service, "_load_task_ledger", lambda: [])
    monkeypatch.setattr(
        "services.command_center_service.unified_data_manager.get_agent_organization_document",
        lambda: {
            "root": {"id": "sun", "name": "孙总", "node_type": "person"},
            "nodes": [
                {
                    "id": "optimus",
                    "parent_id": "executive-office",
                    "node_type": "agent",
                    "agent_id": "optimus",
                    "name": "擎天柱",
                    "title": "总项目管理",
                },
                {
                    "id": "leonardo",
                    "parent_id": "development",
                    "node_type": "agent",
                    "agent_id": "leonardo",
                    "name": "李奥纳多",
                    "title": "架构师",
                },
                {
                    "id": "raphael",
                    "parent_id": "development",
                    "node_type": "agent",
                    "agent_id": "raphael",
                    "name": "拉斐尔",
                    "title": "后端开发",
                },
            ],
            "relations": [],
        },
    )
    mission = service.create_mission(
        objective="实现擎天柱空间视图",
        requested_by="admin",
        project_id="project-software",
        mission_type="software",
    )
    service.claim_planning_mission("optimus")
    service.save_plan(mission["id"], {
        "summary": "擎天柱拆分后交给架构师",
        "rationale": "用户只和擎天柱交互，执行交由内部智能体",
        "risk_level": "low",
        "steps": [
            {
                "order_index": 1,
                "title": "生成开发级拆解",
                "description": "细化空间视图实现范围",
                "task_type": "architecture",
                "agent_id": "leonardo",
                "depends_on": [],
            },
        ],
    })

    space = service.agent_space(mission_id=mission["id"])

    assert space["single_entry"] is True
    assert space["commander"] == "optimus"
    nodes = {node["id"]: node for node in space["nodes"]}
    assert nodes["optimus"]["can_direct_command"] is True
    assert nodes["leonardo"]["can_direct_command"] is False
    assert nodes["raphael"]["can_direct_command"] is False
    assert any(edge["from"] == "optimus" and edge["type"] == "delegates" for edge in space["edges"])
