import asyncio
import json
from datetime import datetime, timedelta, timezone

from services.command_center_service import CommandCenterService
from services.command_center_worker import CommandCenterWorker
from services.compensation_service import CompensationService
from services.openclaw_task_executor import ExecutionResult
from services.work_run_service import WorkRunService


def _side_effect_plan():
    return {
        "summary": "高风险变更",
        "steps": [
            {
                "title": "生产配置变更",
                "description": "更新生产配置",
                "task_type": "operations",
                "agent_id": "optimus",
                "risk_class": "L3",
                "approval_required": True,
                "side_effect": True,
                "resources": ["production-config"],
                "rollback_plan": "恢复上一份已验证配置",
                "compensation": {
                    "type": "restore_configuration",
                    "instructions": "恢复上一份已验证配置并检查服务健康状态",
                },
                "depends_on": [],
            }
        ],
    }


def _running_step(service: CommandCenterService):
    mission = service.create_mission(
        objective="执行生产配置变更",
        requested_by="admin",
        context={"business_flow_key": "operations"},
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _side_effect_plan())
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    assert service.claim_ready_steps("runner", limit=1) == []
    blocked = service.get_mission(mission["id"])
    step = blocked["steps"][0]
    approval = step["step_approval"]
    service.decide_step_approval(
        mission["id"],
        step["id"],
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="admin",
    )
    return service.get_mission(mission["id"]), service.claim_ready_steps("runner", limit=1)[0]


def _applied_effect(step):
    return {
        "effect_key": "production-config-update",
        "resource": "production-config",
        "action": "更新生产配置",
        "status": "applied",
        "idempotency_key": step["idempotency_key"],
        "receipt_ref": "ops-log:change-1",
        "evidence_refs": ["healthcheck:before-failure"],
    }


def test_failed_side_effect_creates_approved_compensation_flow(tmp_path):
    service = CommandCenterService(str(tmp_path / "compensation.db"))
    mission, step = _running_step(service)

    failed = service.complete_step(
        step["id"],
        result={
            "success": False,
            "error": "健康检查失败",
            "side_effects": [_applied_effect(step)],
        },
        success=False,
        actor="optimus",
        lease_token=step["lease_token"],
    )
    recovery = service.list_compensations(mission["id"])

    assert failed["status"] == "failed"
    assert recovery["effects"][0]["status"] == "applied"
    compensation = recovery["compensations"][0]
    assert compensation["status"] == "pending_approval"
    assert compensation["idempotency_key"].startswith("compensate:")
    assert service.summary()["pending_compensations"] == 1

    approved = service.decide_compensation(
        compensation["id"],
        expected_mission_id=mission["id"],
        contract_hash=compensation["contract_hash"],
        decision="approved",
        decided_by="admin",
        comment="批准恢复上一配置",
    )
    assert approved["compensation"]["status"] == "ready"

    claimed = service.claim_ready_compensation("recovery-worker")
    assert claimed["id"] == compensation["id"]
    assert claimed["effect"]["status"] == "applied"
    assert claimed["lease_token"]
    completed = service.complete_compensation(
        claimed["id"],
        lease_token=claimed["lease_token"],
        result={
            "status": "reverted",
            "summary": "已恢复上一份配置并通过健康检查",
            "receipt_ref": "ops-log:rollback-1",
            "evidence_refs": ["healthcheck:rollback-pass"],
            "risk_notes": "无",
        },
        actor="optimus",
    )
    refreshed = service.list_compensations(mission["id"])

    assert completed["status"] == "completed"
    assert refreshed["effects"][0]["status"] == "reverted"
    assert service.summary()["pending_compensations"] == 0


def test_missing_effect_journal_is_hard_blocked_and_requires_review(tmp_path):
    service = CommandCenterService(str(tmp_path / "unknown-effect.db"))
    mission, step = _running_step(service)

    result = service.complete_step(
        step["id"],
        result={"success": True, "output": "配置已更新"},
        success=True,
        actor="optimus",
        lease_token=step["lease_token"],
    )

    assert result["status"] == "failed"
    assert result["result"]["effect_quality"]["accepted"] is False
    assert result["effects"][0]["status"] == "unknown"
    assert result["compensations"][0]["status"] == "pending_approval"

    service.claim_evaluation_mission("evaluator")
    feedback = service.add_feedback(
        mission["id"],
        actor="admin",
        content="请重新执行",
    )
    assert feedback["status"] == "waiting_feedback"
    assert feedback["steps"][0]["status"] == "failed"


def test_cli_start_failure_is_known_not_applied_and_needs_no_compensation(tmp_path):
    service = CommandCenterService(str(tmp_path / "cli-start-failure.db"))
    mission, step = _running_step(service)

    result = service.complete_step(
        step["id"],
        result={
            "success": False,
            "error": "Could not start the CLI: all models rate limited",
            "output": json.dumps(
                {
                    "ok": False,
                    "origin": "gateway",
                    "error": {"type": "cli_error", "message": "all models failed"},
                }
            ),
        },
        success=False,
        actor="optimus",
        lease_token=step["lease_token"],
    )

    assert result["status"] == "failed"
    assert result["result"]["outcome"] == "failed"
    assert result["effects"][0]["status"] == "not_applied"
    assert result["result"]["effect_quality"]["accepted"] is True
    assert result["compensations"] == []


def test_interrupted_compensation_requires_fresh_approval(tmp_path):
    service = CommandCenterService(str(tmp_path / "compensation-recovery.db"))
    mission, step = _running_step(service)
    service.complete_step(
        step["id"],
        result={"error": "failed", "side_effects": [_applied_effect(step)]},
        success=False,
        actor="optimus",
        lease_token=step["lease_token"],
    )
    compensation = service.list_compensations(mission["id"])["compensations"][0]
    service.decide_compensation(
        compensation["id"],
        contract_hash=compensation["contract_hash"],
        decision="approved",
        decided_by="admin",
    )
    claimed = service.claim_ready_compensation("worker")
    with service.connect(immediate=True) as conn:
        conn.execute(
            "UPDATE mission_compensations SET lease_expires_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                compensation["id"],
            ),
        )

    assert service.requeue_stale_compensations() == 1
    current = service.list_compensations(mission["id"])["compensations"][0]
    assert current["status"] == "pending_approval"
    assert current["approved_by"] is None
    assert service.claim_ready_compensation("worker-2") is None


def test_expired_compensation_approval_requires_fresh_approval(tmp_path):
    service = CommandCenterService(str(tmp_path / "compensation-approval-expiry.db"))
    mission, step = _running_step(service)
    service.complete_step(
        step["id"],
        result={"error": "failed", "side_effects": [_applied_effect(step)]},
        success=False,
        actor="optimus",
        lease_token=step["lease_token"],
    )
    compensation = service.list_compensations(mission["id"])["compensations"][0]
    approved = service.decide_compensation(
        compensation["id"],
        contract_hash=compensation["contract_hash"],
        decision="approved",
        decided_by="admin",
    )
    assert approved["compensation"]["authorization_expires_at"]

    with service.connect(immediate=True) as conn:
        conn.execute(
            "UPDATE mission_compensations SET authorization_expires_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                compensation["id"],
            ),
        )

    assert service.expire_compensation_approvals() == 1
    current = service.list_compensations(mission["id"])["compensations"][0]
    assert current["status"] == "pending_approval"
    assert current["approved_by"] is None
    assert current["authorization_expires_at"] is None
    assert service.claim_ready_compensation("worker") is None


def test_compensation_result_requires_receipt_and_evidence():
    result = CompensationService.normalize_compensation_result(
        {"status": "reverted", "summary": "done"}
    )
    assert result["accepted"] is False


def test_worker_executes_only_approved_compensation_contract(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "compensation-worker.db")
        service = CommandCenterService(db_path)
        mission, step = _running_step(service)
        service.complete_step(
            step["id"],
            result={"error": "failed", "side_effects": [_applied_effect(step)]},
            success=False,
            actor="optimus",
            lease_token=step["lease_token"],
        )
        compensation = service.list_compensations(mission["id"])["compensations"][0]

        class Executor:
            def __init__(self):
                self.messages = []

            async def execute(self, command, command_args=None, timeout_seconds=300):
                self.messages.append((command_args or {})["message"])
                return ExecutionResult(
                    success=True,
                    output=json.dumps(
                        {
                            "status": "reverted",
                            "summary": "配置已恢复",
                            "receipt_ref": "ops:rollback-worker",
                            "evidence_refs": ["health:pass"],
                            "risk_notes": "无",
                        },
                        ensure_ascii=False,
                    ),
                )

        executor = Executor()
        worker = CommandCenterWorker(
            service=service,
            executor=executor,
            work_runs=WorkRunService(db_path),
        )
        await worker._drain_compensation()
        assert executor.messages == []

        service.decide_compensation(
            compensation["id"],
            contract_hash=compensation["contract_hash"],
            decision="approved",
            decided_by="admin",
        )
        await worker._drain_compensation()

        current = service.list_compensations(mission["id"])["compensations"][0]
        assert current["status"] == "completed"
        assert compensation["idempotency_key"] in executor.messages[0]
        assert compensation["contract_hash"] in executor.messages[0]

    asyncio.run(scenario())
