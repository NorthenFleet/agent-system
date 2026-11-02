import asyncio
import hashlib
import json

import pytest

from services import deterministic_executor_service as deterministic
from services.command_center_service import CommandCenterService, CommandCenterError, InvalidMissionTransition
from services.command_center_worker import CommandCenterWorker, normalize_plan
from services.work_run_service import WorkRunService
from tests.test_decision_router_service import start, finish


def step_input():
    return {"operation": "sha256_text", "text": "hello", "expected_sha256": hashlib.sha256(b"hello").hexdigest()}


def step(args=None):
    value = {"id": "s", "attempt_count": 1, "title": "内联检查", "task_type": "general", "agent_id": "optimus", "executor": deterministic.EXECUTOR, "input": args or step_input()}
    deterministic.defaults(value)
    return value


def mission_setup(tmp_path, monkeypatch, args=None):
    monkeypatch.setenv("COMMAND_CENTER_DETERMINISTIC_ENABLED", "true")
    service = CommandCenterService(str(tmp_path / "deterministic.db"))
    mission = service.create_mission(objective="检查内联输入", requested_by="admin", context={"business_flow_key": "general"})
    service.claim_planning_mission("planner")
    plan = normalize_plan({"steps": [step(args)], "risk_level": "low"}, mission["objective"])
    service.save_plan(mission["id"], plan)
    return service, mission


@pytest.mark.parametrize("args", [step_input(), {"operation": "json_required_keys", "text": '{"name":"demo"}', "required_keys": ["name"]}])
def test_worker_runs_without_model_and_persists_verifiable_receipt(tmp_path, monkeypatch, args):
    service, mission = mission_setup(tmp_path, monkeypatch, args)
    assert service.claim_ready_steps("runner") == []
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    claimed = service.claim_ready_steps("runner")[0]
    class NoModel:
        async def execute(self, *args, **kwargs):
            raise AssertionError("deterministic step must not call model")
    class NoContext:
        def __getattr__(self, name):
            raise AssertionError("deterministic step must not retrieve context")
    worker = CommandCenterWorker(service=service, executor=NoModel(), work_runs=WorkRunService(str(tmp_path / "runs.db")), context_service=NoContext())
    asyncio.run(worker._execute_step(claimed))
    completed = service.get_mission(mission["id"])["steps"][0]
    assert completed["status"] == "completed"
    assert completed["result"]["execution_quality"]["enforced"] is True
    artifact = completed["artifacts"][0]
    assert hashlib.sha256(artifact["metadata"]["canonical_content"].encode()).hexdigest() == artifact["content_hash"]
    assert worker.work_runs.get(completed["work_run_id"])["executor"] == deterministic.EXECUTOR
    assert deterministic.execute(step(args)).success
    with pytest.raises(InvalidMissionTransition):
        service.complete_step(claimed["id"], result=deterministic.execute(claimed).to_dict(), success=True, actor="optimus", lease_token=claimed["lease_token"])


@pytest.mark.parametrize("change", [
    {"operation": "shell"}, {"path": "/etc/passwd"}, {"text": "x" * 65537},
    {"expected_sha256": "invalid"}, {"operation": "json_required_keys", "text": '{"a":1,"a":2}', "required_keys": ["a"]},
])
def test_invalid_operation_and_budgets_rejected(monkeypatch, change):
    monkeypatch.setenv("COMMAND_CENTER_DETERMINISTIC_ENABLED", "true")
    args = step_input()
    args.update(change)
    if args["operation"] == "json_required_keys":
        args.pop("expected_sha256")
    assert not deterministic.execute(step(args)).success


@pytest.mark.parametrize("text", ['{"a":NaN}', '[1,2]', '{"other":1}', '{"a":' + '[' * 40 + '0' + ']' * 40 + '}'])
def test_json_validation_rejects_bad_or_out_of_budget_input(monkeypatch, text):
    monkeypatch.setenv("COMMAND_CENTER_DETERMINISTIC_ENABLED", "true")
    assert not deterministic.execute(step({"operation": "json_required_keys", "text": text, "required_keys": ["a"]})).success


def test_disabled_executor_never_falls_back_and_plan_is_rejected(tmp_path, monkeypatch):
    service, mission = mission_setup(tmp_path, monkeypatch)
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    monkeypatch.setenv("COMMAND_CENTER_DETERMINISTIC_ENABLED", "false")
    assert service.claim_ready_steps("runner") == []
    assert not deterministic.execute(step()).success
    other = service.create_mission(objective="another", requested_by="admin")
    service.claim_planning_mission("planner")
    with pytest.raises(CommandCenterError, match="未启用"):
        service.save_plan(other["id"], {"steps": [step()]})


def test_repeated_failure_stops_and_feedback_requires_new_plan(tmp_path, monkeypatch):
    service, mission, _ = start(tmp_path, monkeypatch)
    monkeypatch.setenv("COMMAND_CENTER_RECOVERY_CONTROL_ENABLED", "true")
    first = service.claim_ready_steps("runner")[0]
    assert finish(service, first)["status"] == "ready"
    second = service.claim_ready_steps("runner")[0]
    result = finish(service, second)
    assert result["status"] == "failed"
    assert result["result"]["recovery_control"]["reason_code"] == "repeated_failure"
    service.claim_evaluation_mission("review")
    assert service.get_mission(mission["id"])["status"] == "waiting_feedback"
    revised = service.add_feedback(mission["id"], actor="admin", content="补齐证据", replan=False)
    assert revised["status"] == "planning"
    assert service.claim_ready_steps("runner") == []


def test_approval_hash_binds_operation_and_executor():
    original = step()
    one = CommandCenterService._step_contract_hash(original)
    assert one != CommandCenterService._step_contract_hash({**original, "executor": "openclaw"})
    assert one != CommandCenterService._step_contract_hash({**original, "input": {**step_input(), "text": "changed"}})


def test_attempt_budget_prevents_stale_requeue_execution(tmp_path, monkeypatch):
    service, mission = mission_setup(tmp_path, monkeypatch)
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_steps SET attempt_count=1 WHERE mission_id=?", (mission["id"],))
    assert service.claim_ready_steps("runner") == []
    stored = service.get_mission(mission["id"])["steps"][0]
    assert stored["status"] == "failed"
    assert stored["result"]["recovery_control"]["reason_code"] == "attempt_budget_exhausted"


def test_repair_budget_and_new_plan_approval(tmp_path, monkeypatch):
    from tests.test_execution_evidence_service import _single_step_plan
    service, mission, _ = start(tmp_path, monkeypatch)
    monkeypatch.setenv("COMMAND_CENTER_RECOVERY_CONTROL_ENABLED", "true")
    for version in range(1, 4):
        for _ in range(2):
            finish(service, service.claim_ready_steps("runner")[0])
        service.claim_evaluation_mission("review")
        snapshot = service.get_mission(mission["id"])
        prompt = CommandCenterWorker._planning_prompt(snapshot)
        assert 'repeated_failure' in prompt
        assert '<RECOVERY_CONTEXT>' in prompt
        if version == 3:
            with pytest.raises(CommandCenterError, match="两次重新规划预算"):
                service.add_feedback(mission["id"], actor="admin", content="改正", replan=True)
            assert service.get_mission(mission["id"])["status"] == "waiting_feedback"
        else:
            service.add_feedback(mission["id"], actor="admin", content="改正", replan=False)
            service.claim_planning_mission("planner")
            saved = service.save_plan(mission["id"], _single_step_plan(max_attempts=3))
            assert saved["plan_version"] == version + 1
            assert service.claim_ready_steps("runner") == []
            service.approve(mission["id"], decided_by="admin")
            service.activate_approved_missions()


def test_wrong_acceptance_contract_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_CENTER_DETERMINISTIC_ENABLED", "true")
    candidate = step()
    candidate["acceptance_criteria"] = ["外部部署成功"]
    with pytest.raises(ValueError, match="acceptance_criteria"):
        deterministic.validate(candidate)
