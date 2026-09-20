from datetime import datetime, timedelta, timezone

import pytest

from services.command_center_service import (
    CommandCenterService,
    InvalidMissionTransition,
)


def _high_risk_plan():
    return {
        "summary": "生产发布计划",
        "risk_level": "high",
        "steps": [
            {
                "order_index": 1,
                "title": "执行生产发布",
                "description": "将已验证版本发布到生产环境",
                "objective": "生产发布",
                "task_type": "operations",
                "agent_id": "optimus",
                "depends_on": [],
                "risk_class": "L3",
                "approval_required": True,
                "side_effect": True,
                "resources": ["production"],
                "rollback_plan": "恢复上一稳定版本",
            }
        ],
    }


def _awaiting_step_approval(service: CommandCenterService):
    mission = service.create_mission(
        objective="发布已经验收的版本",
        requested_by="admin",
        context={"business_flow_key": "operations"},
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _high_risk_plan())
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    assert service.claim_ready_steps("runner", limit=1) == []
    current = service.get_mission(mission["id"])
    return current, current["steps"][0], current["step_approvals"][0]


def test_high_risk_step_requires_contract_bound_single_use_approval(tmp_path):
    service = CommandCenterService(str(tmp_path / "step-approval.db"))
    mission, step, approval = _awaiting_step_approval(service)

    assert mission["status"] == "running"
    assert step["status"] == "awaiting_approval"
    assert approval["status"] == "pending"
    assert len(approval["contract_hash"]) == 64
    assert service.summary()["pending_step_approvals"] == 1

    approved = service.decide_step_approval(
        mission["id"],
        step["id"],
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="admin",
        comment="批准本次生产发布",
    )
    assert approved["approval"]["status"] == "approved"
    assert service.summary()["pending_step_approvals"] == 0

    claimed = service.claim_ready_steps("runner", limit=1)
    assert len(claimed) == 1
    assert claimed[0]["step_approval"]["status"] == "consumed"
    assert claimed[0]["step_approval"]["consumed"] is True
    assert claimed[0]["idempotency_key"]


def test_stale_or_consumed_approval_cannot_authorize_retry(tmp_path):
    service = CommandCenterService(str(tmp_path / "step-approval-retry.db"))
    mission, step, approval = _awaiting_step_approval(service)
    service.decide_step_approval(
        mission["id"],
        step["id"],
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="admin",
    )
    claimed = service.claim_ready_steps("runner", limit=1)[0]
    with service.connect(immediate=True) as conn:
        conn.execute(
            "UPDATE mission_steps SET lease_expires_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                claimed["id"],
            ),
        )

    assert service.requeue_stale_steps() == 1
    assert service.claim_ready_steps("runner-2", limit=1) == []
    refreshed = service.get_mission(mission["id"])
    latest = refreshed["steps"][0]["step_approval"]
    assert refreshed["steps"][0]["status"] == "awaiting_approval"
    assert latest["status"] == "pending"
    assert latest["request_version"] == 2

    with pytest.raises(InvalidMissionTransition, match="stale"):
        service.decide_step_approval(
            mission["id"],
            step["id"],
            approval_id=approval["id"],
            contract_hash=approval["contract_hash"],
            decision="approved",
            decided_by="admin",
        )


def test_rejecting_high_risk_step_blocks_mission(tmp_path):
    service = CommandCenterService(str(tmp_path / "step-approval-reject.db"))
    mission, step, approval = _awaiting_step_approval(service)

    result = service.decide_step_approval(
        mission["id"],
        step["id"],
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="rejected",
        decided_by="admin",
        comment="发布窗口已关闭",
    )

    assert result["approval"]["status"] == "rejected"
    assert result["mission"]["status"] == "waiting_feedback"
    assert result["mission"]["steps"][0]["status"] == "failed"
    assert "发布窗口已关闭" in result["mission"]["last_error"]


def test_expired_step_approval_is_rotated_without_execution(tmp_path):
    service = CommandCenterService(str(tmp_path / "step-approval-expiry.db"))
    mission, step, approval = _awaiting_step_approval(service)
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with service.connect(immediate=True) as conn:
        conn.execute(
            "UPDATE mission_step_approvals SET expires_at=? WHERE id=?",
            (expired_at, approval["id"]),
        )

    assert service.expire_step_approvals() == 1
    refreshed = service.get_mission(mission["id"])
    replacement = refreshed["steps"][0]["step_approval"]
    assert replacement["request_version"] == 2
    assert replacement["status"] == "pending"
    assert refreshed["steps"][0]["status"] == "awaiting_approval"
    assert service.claim_ready_steps("runner", limit=1) == []
