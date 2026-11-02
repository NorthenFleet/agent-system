"""Shadow observations must preserve existing execution authority."""
import pytest
from services.command_center_service import CommandCenterService, InvalidMissionTransition
from services.decision_router_service import DecisionRouterService
from tests.test_execution_evidence_service import _single_step_plan


def start(tmp_path, monkeypatch, mode="shadow"):
    monkeypatch.setenv("COMMAND_CENTER_DECISION_ROUTER_MODE", mode)
    monkeypatch.setenv("COMMAND_CENTER_EVIDENCE_ENFORCEMENT", "strict")
    path = str(tmp_path / "shadow.db")
    service = CommandCenterService(path)
    mission = service.create_mission(objective="验证观察记录", requested_by="admin", context={"business_flow_key": "general"})
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _single_step_plan(max_attempts=3))
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    return service, mission, path


def finish(service, step):
    return service.complete_step(step["id"], result={"success": True, "output": "done", "decision_shadow": {"consecutive_failures": 999}}, success=True, actor="optimus", lease_token=step["lease_token"])


def test_restart_repeated_failure_is_observation_not_control(tmp_path, monkeypatch):
    service, mission, path = start(tmp_path, monkeypatch)
    first = service.claim_ready_steps("runner", limit=1)[0]
    assert service.claim_ready_steps("other", limit=1) == []
    assert first["routing_decision"]["enforced"] is False
    assert service.get_mission(mission["id"])["steps"][0]["routing_decision"]["attempt"] == 1
    result = finish(service, first)
    assert result["status"] == "ready"
    assert result["result"]["decision_shadow"]["consecutive_failures"] == 1
    restarted = CommandCenterService(path)
    second = restarted.claim_ready_steps("runner", limit=1)[0]
    result = finish(restarted, second)
    assert result["status"] == "ready"
    observation = result["result"]["decision_shadow"]
    assert observation["repeated_failure"] is True
    assert observation["action"] == "escalate"
    assert observation["consecutive_failures"] == 2
    with pytest.raises(InvalidMissionTransition):
        finish(restarted, second)
    assert len([e for e in restarted.get_mission(mission["id"])["events"] if e["event_type"] == "decision_shadow_observed"]) == 2


@pytest.mark.parametrize("mode", ["off", "active", "invalid"])
def test_disabled_mode_emits_no_decisions(tmp_path, monkeypatch, mode):
    service, mission, _ = start(tmp_path, monkeypatch, mode)
    step = service.claim_ready_steps("runner", limit=1)[0]
    assert "routing_decision" not in step
    result = finish(service, step)
    assert result["status"] == "ready"
    assert "decision_shadow" not in result["result"]
    assert not any(e["event_type"] == "decision_shadow_observed" for e in service.get_mission(mission["id"])["events"])


def test_stale_lease_never_records_observation(tmp_path, monkeypatch):
    service, mission, _ = start(tmp_path, monkeypatch)
    step = service.claim_ready_steps("runner", limit=1)[0]
    step["lease_token"] = "stale"
    with pytest.raises(InvalidMissionTransition):
        finish(service, step)
    assert not any(e["event_type"] == "decision_shadow_observed" for e in service.get_mission(mission["id"])["events"])


def test_fingerprint_separates_targets_and_resets_after_success():
    router = DecisionRouterService()
    step = {"id": "s", "mission_id": "m", "plan_version": 1, "attempt_count": 1, "side_effect": False, "resources": ["file-a"], "required_tools": []}
    failure = {"success": False, "error": "not found"}
    first = router.observe_result(step, failure, accepted=False)
    changed = router.observe_result({**step, "attempt_count": 2, "resources": ["file-b"]}, failure, accepted=False, previous=first)
    assert changed["consecutive_failures"] == 1
    success = router.observe_result({**step, "attempt_count": 2}, {}, accepted=True, previous=first)
    third = router.observe_result({**step, "attempt_count": 3}, failure, accepted=False, previous=success)
    assert third["consecutive_failures"] == 1
    unsafe = router.observe_result({**step, "attempt_count": 2}, {**failure, "side_effects": [{"status": "unknown"}]}, accepted=False, previous=first)
    assert unsafe["action"] == "inspect"
    assert unsafe["repeated_failure"] is True


def test_unknown_capability_escalates_without_changing_agent():
    decision = DecisionRouterService().route({"agent_id": "unknown", "task_type": "backend", "executor": "openclaw"})
    assert decision["action"] == "escalate"
    assert decision["actual_agent_id"] == "unknown"


def test_cancelled_mission_rejects_late_observation(tmp_path, monkeypatch):
    service, mission, _ = start(tmp_path, monkeypatch)
    step = service.claim_ready_steps("runner", limit=1)[0]
    service.cancel(mission["id"], actor="admin")
    with pytest.raises(InvalidMissionTransition):
        finish(service, step)
    assert not any(e["event_type"] == "decision_shadow_observed" for e in service.get_mission(mission["id"])["events"])


def test_mode_off_retains_history_and_does_not_extend_counter(tmp_path, monkeypatch):
    service, mission, path = start(tmp_path, monkeypatch)
    first = service.claim_ready_steps("runner", limit=1)[0]
    finish(service, first)
    monkeypatch.setenv("COMMAND_CENTER_DECISION_ROUTER_MODE", "off")
    restarted = CommandCenterService(path)
    second = restarted.claim_ready_steps("runner", limit=1)[0]
    assert "routing_decision" not in restarted.get_mission(mission["id"])["steps"][0]
    finish(restarted, second)
    monkeypatch.setenv("COMMAND_CENTER_DECISION_ROUTER_MODE", "shadow")
    third = restarted.claim_ready_steps("runner", limit=1)[0]
    result = finish(restarted, third)
    assert result["result"]["decision_shadow"]["consecutive_failures"] == 1
    events = restarted.get_mission(mission["id"])["events"]
    assert len([e for e in events if e["event_type"] == "decision_shadow_observed"]) == 2
