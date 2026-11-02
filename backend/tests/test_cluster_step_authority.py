"""Canonical approval/lease integration; only local test subprocesses execute."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from services.cluster_execution import ExecutionBlocked
from services.cluster_step_authority import ClusterStepAuthority
from services.command_center_service import CommandCenterService
from services.work_run_service import WorkRunService, WorkRunLeaseConflict
from tests.test_cluster_execution import harness, request, PRINCIPAL  # noqa: F401


@pytest.fixture()
def approved(harness):
    make, ledger, calls, processes, observed, credential = harness
    service = CommandCenterService(repository=ledger.repository, project_provider=lambda: [])
    mission = service.create_mission(objective="读取已登记节点的系统版本", requested_by="42")
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], {"summary": "读取系统版本", "steps": [{
        "title": "读取系统版本", "objective": "读取系统版本", "order_index": 1,
        "task_type": "cluster_operation", "executor": "cluster-readonly-v1",
        "agent_id": "optimus", "depends_on": [], "approval_required": True,
        "risk_class": "L2", "side_effect": False, "max_attempts": 1,
        "input": {"cluster_operation": request().model_dump()},
        "evidence_required": ["cluster_receipt"],
    }]})
    service.approve(mission["id"], decided_by="42")
    service.activate_approved_missions()
    step_id = service.get_mission(mission["id"])["steps"][0]["id"]
    assert service.claim_ready_steps("ordinary-worker") == []
    assert service.claim_ready_steps("cluster-worker", cluster_step_id=step_id) == []
    pending = service.get_mission(mission["id"])["step_approvals"][-1]
    service.decide_step_approval(mission["id"], step_id, approval_id=pending["id"],
        contract_hash=pending["contract_hash"], decision="approved", decided_by="42")
    step = service.claim_ready_steps("cluster-worker", cluster_step_id=step_id)[0]
    authority = ClusterStepAuthority(command_center=service, work_runs=ledger,
        step_id=step_id, lease_token=step["lease_token"], worker_id="cluster-worker")
    return make, ledger, calls, service, mission["id"], step, authority


def test_consumed_approval_and_step_key_are_durable(approved):
    make, ledger, calls, service, mission_id, step, authority = approved
    result = asyncio.run(make(authorize=None, step_authority=authority).execute(request(), PRINCIPAL))
    stored = ledger.get(result["run_id"])
    current = service.get_mission(mission_id)["steps"][0]
    assert current["status"] == stored["status"] == "completed"
    assert current["work_run_id"] == stored["id"]
    assert stored["idempotency_key"] == step["idempotency_key"]
    assert result["approval_id"] == step["step_approval"]["id"]
    assert result["contract_hash"] == step["step_approval"]["contract_hash"]
    assert result["mission_id"] == mission_id and result["step_id"] == step["id"]
    assert "lease_token" not in json.dumps(result)
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", ["expired", "token", "owner", "approval", "input", "plan", "cancel"])
def test_stale_or_changed_authority_never_dispatches(approved, mutation):
    make, ledger, calls, service, mission_id, step, authority = approved
    with service.connect(immediate=True) as conn:
        if mutation == "expired":
            conn.execute("UPDATE mission_steps SET lease_expires_at=? WHERE id=?",
                ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), step["id"]))
        elif mutation in {"token", "owner"}:
            field = "lease_token" if mutation == "token" else "lease_owner"
            conn.execute(f"UPDATE mission_steps SET {field}=? WHERE id=?", ("different", step["id"]))
        elif mutation == "approval":
            conn.execute("UPDATE mission_step_approvals SET status='cancelled' WHERE step_id=?", (step["id"],))
        elif mutation == "input":
            conn.execute("UPDATE mission_steps SET input_json='{}' WHERE id=?", (step["id"],))
        elif mutation == "plan":
            conn.execute("UPDATE orchestration_missions SET plan_version=plan_version+1 WHERE id=?", (mission_id,))
        else:
            conn.execute("UPDATE orchestration_missions SET status='cancelled' WHERE id=?", (mission_id,))
    with pytest.raises(ExecutionBlocked):
        asyncio.run(make(authorize=None, step_authority=authority).execute(request(), PRINCIPAL))
    assert calls == [] and ledger.list() == []


@pytest.mark.parametrize("principal,payload", [
    ({**PRINCIPAL, "sub": "43"}, request()),
    (PRINCIPAL, request(request_id="another-request")),
    (PRINCIPAL, request(timeout_seconds=2)),
])
def test_request_and_owner_are_bound(approved, principal, payload):
    make, ledger, calls, _, _, _, authority = approved
    with pytest.raises(ExecutionBlocked):
        asyncio.run(make(authorize=None, step_authority=authority).execute(payload, principal))
    assert calls == [] and ledger.list() == []


def test_same_repository_required(approved, tmp_path):
    _, _, _, service, _, step, _ = approved
    with pytest.raises(ExecutionBlocked, match="shared_repository"):
        ClusterStepAuthority(command_center=service, work_runs=WorkRunService(str(tmp_path/"other.db")),
            step_id=step["id"], lease_token=step["lease_token"], worker_id="cluster-worker")


def test_concurrent_delivery_is_one_dispatch(approved):
    make, ledger, calls, _, _, _, authority = approved
    async def run():
        executor = make("import time; time.sleep(.05); print('Linux 6.8 x86_64')",
                        authorize=None, step_authority=authority)
        return await asyncio.gather(*(executor.execute(request(), PRINCIPAL) for _ in range(8)))
    results = asyncio.run(run())
    assert len(calls) == 1 and len(ledger.list()) == 1
    assert sum(not r["replayed"] for r in results) == 1


def test_late_completion_is_rejected_and_reconciled_unknown(approved):
    make, ledger, calls, service, mission_id, step, authority = approved
    async def factory(*argv, **kwargs):
        with service.connect(immediate=True) as conn:
            conn.execute("UPDATE mission_steps SET lease_token='replacement' WHERE id=?", (step["id"],))
        calls.append(argv)
        import sys
        return await asyncio.create_subprocess_exec(sys.executable, "-c", "print('Linux 6.8 x86_64')", **kwargs)
    with pytest.raises(ExecutionBlocked):
        asyncio.run(make(authorize=None, step_authority=authority, process_factory=factory).execute(request(), PRINCIPAL))
    run = ledger.list()[0]
    assert run["status"] == "running" and not run["execution_result"]
    reconciled = authority.reconcile(run["id"])
    assert reconciled["status"] == "blocked"
    assert reconciled["execution_result"]["remote_outcome"] == "unknown"
    assert service.get_mission(mission_id)["steps"][0]["lease_token"] == "replacement"


def test_completion_is_atomic_with_work_run(approved, monkeypatch):
    make, ledger, _, service, mission_id, _, authority = approved
    original = service.complete_step
    def fail_after_step(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected transaction failure")
    monkeypatch.setattr(service, "complete_step", fail_after_step)
    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(make(authorize=None, step_authority=authority).execute(request(), PRINCIPAL))
    assert ledger.list()[0]["status"] == "running"
    assert service.get_mission(mission_id)["steps"][0]["status"] == "running"


def test_generic_transition_cannot_bypass_step_fence(approved):
    _, ledger, _, _, _, _, authority = approved
    run, created = authority.claim(request(), PRINCIPAL, "clusterprobe")
    assert created
    with pytest.raises(WorkRunLeaseConflict):
        ledger.transition(run["id"], "review", actor="intruder")
    with pytest.raises(WorkRunLeaseConflict):
        ledger.heartbeat(run["id"], actor=run["lease_owner"])
    with pytest.raises(WorkRunLeaseConflict):
        ledger.add_artifact(run["id"], artifact_type="forged", title="Unfenced artifact")


def _expire_and_reapprove(service, mission_id, step):
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_steps SET lease_expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), step["id"]))
    assert service.requeue_stale_steps() == 1
    assert service.claim_ready_steps("replacement", cluster_step_id=step["id"]) == []
    pending = service.get_mission(mission_id)["steps"][0]["step_approval"]
    assert pending["status"] == "pending"
    service.decide_step_approval(mission_id, step["id"], approval_id=pending["id"],
        contract_hash=pending["contract_hash"], decision="approved", decided_by="42")
    return service.claim_ready_steps("replacement", cluster_step_id=step["id"])[0]


def test_crash_before_work_run_requires_new_approval(approved):
    _, ledger, calls, service, mission_id, step, _ = approved
    assert ledger.list() == [] and calls == []
    replacement = _expire_and_reapprove(service, mission_id, step)
    assert replacement["step_approval"]["id"] != step["step_approval"]["id"]
    assert replacement["lease_token"] != step["lease_token"]
    assert ledger.list() == [] and calls == []


def test_reapproval_after_dispatch_never_creates_second_run(approved):
    _, ledger, calls, service, mission_id, step, authority = approved
    original, _ = authority.claim(request(), PRINCIPAL, "clusterprobe")
    replacement = _expire_and_reapprove(service, mission_id, step)
    fresh_authority = ClusterStepAuthority(command_center=service, work_runs=ledger,
        step_id=step["id"], lease_token=replacement["lease_token"], worker_id="replacement")
    replay, created = fresh_authority.claim(request(), PRINCIPAL, "clusterprobe")
    assert not created and replay["id"] == original["id"]
    # Recovery is possible with the new authority, without the lost process's token.
    assert fresh_authority.reconcile(original["id"])["status"] == "blocked"
    recovered = service.get_mission(mission_id)["steps"][0]
    assert recovered["status"] == "failed" and recovered["lease_token"] is None
    assert recovered["result"]["cluster_receipt"]["previous_approval_id"] == step["step_approval"]["id"]
    assert len(ledger.list()) == 1 and calls == []


def test_confirmed_receipt_can_resolve_fresh_authorized_step_without_dispatch(approved):
    make, ledger, calls, service, mission_id, step, authority = approved
    original = asyncio.run(make(authorize=None, step_authority=authority).execute(request(), PRINCIPAL))
    # Model an explicit operator recovery request; no public API does this.
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_steps SET status='running', lease_token=?, lease_expires_at=? WHERE id=?",
            (step["lease_token"], datetime.now(timezone.utc).isoformat(), step["id"]))
    replacement = _expire_and_reapprove(service, mission_id, step)
    fresh = ClusterStepAuthority(command_center=service, work_runs=ledger,
        step_id=step["id"], lease_token=replacement["lease_token"], worker_id="replacement")
    replay = asyncio.run(make(authorize=None, step_authority=fresh).execute(request(), PRINCIPAL))
    assert replay["replayed"] and replay["run_id"] == original["run_id"]
    assert len(calls) == 1 and ledger.get(original["run_id"])["execution_result"] == original
    assert service.get_mission(mission_id)["steps"][0]["status"] == "completed"


def test_recovery_rolls_back_both_ledgers_if_step_write_fails(approved, monkeypatch):
    _, ledger, _, service, mission_id, step, authority = approved
    original, _ = authority.claim(request(), PRINCIPAL, "clusterprobe")
    replacement = _expire_and_reapprove(service, mission_id, step)
    fresh = ClusterStepAuthority(command_center=service, work_runs=ledger,
        step_id=step["id"], lease_token=replacement["lease_token"], worker_id="replacement")
    old_complete = service.complete_step
    def fail(*args, **kwargs):
        old_complete(*args, **kwargs)
        raise RuntimeError("recovery rollback")
    monkeypatch.setattr(service, "complete_step", fail)
    with pytest.raises(RuntimeError, match="recovery rollback"):
        fresh.claim(request(), PRINCIPAL, "clusterprobe")
    assert ledger.get(original["id"])["status"] == "running"
    assert service.get_mission(mission_id)["steps"][0]["status"] == "running"


def test_live_lease_cannot_be_reconciled(approved):
    _, _, _, _, _, _, authority = approved
    run, _ = authority.claim(request(), PRINCIPAL, "clusterprobe")
    with pytest.raises(ExecutionBlocked, match="live_lease"):
        authority.reconcile(run["id"])


def test_unknown_transport_result_is_blocked_without_retry(approved):
    make, ledger, calls, service, mission_id, _, authority = approved
    result = asyncio.run(make("print('unexpected output')", authorize=None,
                             step_authority=authority).execute(request(), PRINCIPAL))
    assert result["remote_outcome"] == "unknown"
    assert ledger.get(result["run_id"])["status"] == "blocked"
    current = service.get_mission(mission_id)["steps"][0]
    assert current["status"] == "failed" and current["result"]["completion_decision"]["retry_scheduled"] is False
    assert service.claim_ready_steps("generic") == [] and len(calls) == 1


@pytest.mark.parametrize("principal", [dict(PRINCIPAL, role="member"), dict(PRINCIPAL, auth_mode="development")])
def test_authority_claim_rejects_development_and_nonadmin(approved, principal):
    _, ledger, _, _, _, _, authority = approved
    with pytest.raises(ExecutionBlocked, match="formal_administrator"):
        authority.claim(request(), principal, "clusterprobe")
    assert ledger.list() == []


def test_executor_is_part_of_cluster_approval_contract(approved):
    _, _, _, service, _, step, _ = approved
    assert service._step_contract_hash(step) != service._step_contract_hash({**step, "executor": "openclaw"})


@pytest.mark.parametrize("action", ["attach", "renew", "complete"])
@pytest.mark.parametrize("invalid", ["expired", "old_plan"])
def test_canonical_step_mutations_reject_expired_or_old_plan(approved, action, invalid):
    _, _, _, service, mission_id, step, _ = approved
    with service.connect(immediate=True) as conn:
        # Exercise the common SQL fence, not just the dedicated cluster entry gate.
        if action == "complete":
            conn.execute("UPDATE mission_steps SET task_type='coordination' WHERE id=?", (step["id"],))
        if invalid == "expired":
            conn.execute("UPDATE mission_steps SET lease_expires_at=? WHERE id=?",
                ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), step["id"]))
        else:
            conn.execute("UPDATE orchestration_missions SET plan_version=plan_version+1 WHERE id=?", (mission_id,))
    from services.command_center_service import InvalidMissionTransition
    with pytest.raises(InvalidMissionTransition):
        if action == "attach":
            service.attach_work_run(step["id"], "nonexistent", lease_token=step["lease_token"])
        elif action == "renew":
            service.renew_step_lease(step["id"], lease_token=step["lease_token"])
        else:
            service.complete_step(step["id"], result={}, success=False, actor="test", lease_token=step["lease_token"])
