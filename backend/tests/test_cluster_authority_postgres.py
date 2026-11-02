"""Isolated PostgreSQL gates for canonical cluster approval and step fences."""

from __future__ import annotations

import importlib.util
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from repositories.command_center_repository import (
    PostgresCommandCenterRepository,
    _postgres_dsn,
)
from services.cluster_execution import OperationRequest
from services.cluster_step_authority import ClusterStepAuthority
from services.command_center_service import (
    CommandCenterService,
    InvalidMissionTransition,
)
from services.work_run_service import WorkRunService
from tests.test_cluster_work_run_postgres import (
    POSTGRES_URL,
    SCHEMA_ISOLATION_CONFIRMED,
    _is_explicit_test_database,
    _url_for_schema,
    psycopg2,
    sql,
)


pytestmark = pytest.mark.skipif(
    not POSTGRES_URL
    or not SCHEMA_ISOLATION_CONFIRMED
    or not _is_explicit_test_database(POSTGRES_URL)
    or psycopg2 is None,
    reason=(
        "requires an explicitly confirmed isolated PostgreSQL test database and "
        "WORK_RUN_POSTGRES_TEST_ISOLATED_SCHEMA=true"
    ),
)


MIGRATIONS = (
    "20260918_command_center_postgres.py",
    "20260919_work_run_postgres.py",
    "20260920_langgraph_checkpoint_postgres.py",
    "20260921_command_center_worker_registry.py",
    "20260922_agent_team_foundation.py",
    "20260923_agent_team_contract_hardening.py",
)


def _load_migration(filename: str):
    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    )
    spec = importlib.util.spec_from_file_location(
        f"cluster_authority_{migration_path.stem}",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.fixture(scope="module")
def postgres_cluster_services():
    schema_name = f"cluster_authority_{uuid.uuid4().hex}"
    admin_connection = psycopg2.connect(_postgres_dsn(POSTGRES_URL))
    admin_connection.autocommit = True
    repository = None
    try:
        with admin_connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))

        scoped_url = _url_for_schema(POSTGRES_URL, schema_name)
        engine = create_engine(scoped_url)
        try:
            with engine.begin() as connection:
                assert (
                    connection.exec_driver_sql("SELECT current_schema()").scalar_one()
                    == schema_name
                )
                with Operations.context(MigrationContext.configure(connection)):
                    for filename in MIGRATIONS:
                        _load_migration(filename).upgrade()
        finally:
            engine.dispose()

        repository = PostgresCommandCenterRepository(
            scoped_url,
            pool_min_size=1,
            pool_max_size=32,
            pool_acquire_timeout_seconds=20,
        )
        command_center = CommandCenterService(
            repository=repository,
            project_provider=lambda: [],
        )
        work_runs = WorkRunService(repository=repository)
        yield command_center, work_runs
    finally:
        if repository is not None:
            repository.close()
        with admin_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema_name)
                )
            )
        admin_connection.close()


def _request(suffix: str) -> OperationRequest:
    return OperationRequest(
        request_id=f"postgres-{suffix}",
        node_id="compute-05",
        tailscale_id="nCompute05",
        operation="host.info",
        timeout_seconds=10,
    )


def _pending_cluster_step(command_center: CommandCenterService, suffix: str):
    request = _request(suffix)
    mission = command_center.create_mission(
        objective="读取已登记节点的系统版本",
        requested_by="42",
    )
    command_center.claim_planning_mission(f"planner-{suffix}")
    command_center.save_plan(
        mission["id"],
        {
            "summary": "读取系统版本",
            "steps": [
                {
                    "title": "读取系统版本",
                    "objective": "读取系统版本",
                    "order_index": 1,
                    "task_type": "cluster_operation",
                    "executor": "cluster-readonly-v1",
                    "agent_id": "optimus",
                    "depends_on": [],
                    "approval_required": True,
                    "risk_class": "L2",
                    "side_effect": False,
                    "max_attempts": 1,
                    "input": {"cluster_operation": request.model_dump()},
                    "evidence_required": ["cluster_receipt"],
                    "idempotency_key": f"cluster-step:{suffix}:{uuid.uuid4().hex}",
                }
            ],
        },
    )
    command_center.approve(mission["id"], decided_by="42")
    assert command_center.activate_approved_missions() == 1
    step_id = command_center.get_mission(mission["id"])["steps"][0]["id"]
    assert command_center.claim_ready_steps(
        f"approval-probe-{suffix}",
        cluster_step_id=step_id,
    ) == []
    snapshot = command_center.get_mission(mission["id"])
    approval = snapshot["step_approvals"][-1]
    return mission["id"], step_id, approval, request


def _approve_and_claim(command_center: CommandCenterService, suffix: str):
    mission_id, step_id, approval, request = _pending_cluster_step(
        command_center,
        suffix,
    )
    command_center.decide_step_approval(
        mission_id,
        step_id,
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="42",
    )
    assert command_center.claim_ready_steps(f"generic-{suffix}") == []
    claimed = command_center.claim_ready_steps(
        f"cluster-{suffix}",
        cluster_step_id=step_id,
    )
    assert len(claimed) == 1
    return mission_id, claimed[0], request


def _expire_and_reapprove(
    command_center: CommandCenterService,
    mission_id: str,
    step: dict,
):
    with command_center.connect(immediate=True) as connection:
        connection.execute(
            "UPDATE mission_steps SET lease_expires_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                step["id"],
            ),
        )
    assert command_center.requeue_stale_steps() == 1
    assert command_center.claim_ready_steps(
        "replacement",
        cluster_step_id=step["id"],
    ) == []
    pending = command_center.get_mission(mission_id)["steps"][0]["step_approval"]
    assert pending["status"] == "pending"
    command_center.decide_step_approval(
        mission_id,
        step["id"],
        approval_id=pending["id"],
        contract_hash=pending["contract_hash"],
        decision="approved",
        decided_by="42",
    )
    replacement = command_center.claim_ready_steps(
        "replacement",
        cluster_step_id=step["id"],
    )
    assert len(replacement) == 1
    return replacement[0]


def test_postgres_approval_decision_is_single_and_consistent(
    postgres_cluster_services,
):
    command_center, _work_runs = postgres_cluster_services
    mission_id, step_id, approval, _request_model = _pending_cluster_step(
        command_center,
        "approval-race",
    )
    callers = 32
    barrier = threading.Barrier(callers)

    def decide(index: int):
        decision = "approved" if index % 2 == 0 else "rejected"
        barrier.wait(timeout=20)
        try:
            result = command_center.decide_step_approval(
                mission_id,
                step_id,
                approval_id=approval["id"],
                contract_hash=approval["contract_hash"],
                decision=decision,
                decided_by=f"approver-{index}",
                comment="concurrent rejection" if decision == "rejected" else "",
            )
            return decision, result
        except InvalidMissionTransition:
            return decision, None

    with ThreadPoolExecutor(max_workers=callers) as pool:
        outcomes = list(pool.map(decide, range(callers)))

    winners = [(decision, result) for decision, result in outcomes if result]
    assert len(winners) == 1
    winning_decision, result = winners[0]
    assert result["approval"]["status"] == winning_decision
    snapshot = command_center.get_mission(mission_id)
    stored_approval = snapshot["step_approvals"][-1]
    assert stored_approval["status"] == winning_decision
    if winning_decision == "approved":
        assert snapshot["status"] == "running"
        assert snapshot["steps"][0]["status"] == "ready"
    else:
        assert snapshot["status"] == "waiting_feedback"
        assert snapshot["steps"][0]["status"] == "failed"


def test_postgres_cluster_step_claim_consumes_approval_once(
    postgres_cluster_services,
):
    command_center, _work_runs = postgres_cluster_services
    mission_id, step_id, approval, _request_model = _pending_cluster_step(
        command_center,
        "step-claim-race",
    )
    command_center.decide_step_approval(
        mission_id,
        step_id,
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="42",
    )
    assert command_center.claim_ready_steps("generic-worker") == []
    callers = 32
    barrier = threading.Barrier(callers)

    def claim(index: int):
        barrier.wait(timeout=20)
        return command_center.claim_ready_steps(
            f"cluster-worker-{index}",
            cluster_step_id=step_id,
        )

    with ThreadPoolExecutor(max_workers=callers) as pool:
        batches = list(pool.map(claim, range(callers)))

    claimed = [step for batch in batches for step in batch]
    assert len(claimed) == 1
    assert claimed[0]["attempt_count"] == 1
    snapshot = command_center.get_mission(mission_id)
    assert snapshot["steps"][0]["status"] == "running"
    assert snapshot["step_approvals"][-1]["status"] == "consumed"
    assert snapshot["step_approvals"][-1]["consumed_at"]


def test_postgres_expiry_and_claim_rotate_one_approval_without_consumption(
    postgres_cluster_services,
):
    command_center, _work_runs = postgres_cluster_services
    mission_id, step_id, approval, _request_model = _pending_cluster_step(
        command_center,
        "expiry-claim-race",
    )
    command_center.decide_step_approval(
        mission_id,
        step_id,
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="42",
    )
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with command_center.connect(immediate=True) as connection:
        connection.execute(
            "UPDATE mission_step_approvals SET expires_at=? WHERE id=?",
            (expired_at, approval["id"]),
        )

    barrier = threading.Barrier(2)

    def expire():
        barrier.wait(timeout=20)
        return command_center.expire_step_approvals()

    def claim():
        barrier.wait(timeout=20)
        return command_center.claim_ready_steps(
            "expired-approval-worker",
            cluster_step_id=step_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        expire_future = pool.submit(expire)
        claim_future = pool.submit(claim)
        rotated = expire_future.result()
        claimed = claim_future.result()

    assert rotated in {0, 1}
    assert claimed == []
    with command_center.connect() as connection:
        approvals = connection.execute(
            "SELECT request_version, status, consumed_at "
            "FROM mission_step_approvals WHERE step_id=? ORDER BY request_version",
            (step_id,),
        ).fetchall()
        work_run_count = connection.execute(
            "SELECT COUNT(*) AS count FROM work_runs WHERE mission_id=?",
            (mission_id,),
        ).fetchone()["count"]
    assert [row["request_version"] for row in approvals] == [1, 2]
    assert approvals[0]["status"] == "expired"
    assert approvals[0]["consumed_at"] is None
    assert approvals[1]["status"] == "pending"
    assert approvals[1]["consumed_at"] is None
    assert work_run_count == 0
    snapshot = command_center.get_mission(mission_id)
    assert snapshot["steps"][0]["status"] == "awaiting_approval"
    assert snapshot["steps"][0]["attempt_count"] == 0


def test_postgres_pending_approval_and_expiry_race_rejects_stale_decision(
    postgres_cluster_services,
):
    command_center, _work_runs = postgres_cluster_services
    mission_id, step_id, approval, _request_model = _pending_cluster_step(
        command_center,
        "pending-expiry-race",
    )
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with command_center.connect(immediate=True) as connection:
        connection.execute(
            "UPDATE mission_step_approvals SET expires_at=? WHERE id=?",
            (expired_at, approval["id"]),
        )
    barrier = threading.Barrier(2)

    def expire():
        barrier.wait(timeout=20)
        return command_center.expire_step_approvals()

    def decide():
        barrier.wait(timeout=20)
        try:
            command_center.decide_step_approval(
                mission_id,
                step_id,
                approval_id=approval["id"],
                contract_hash=approval["contract_hash"],
                decision="approved",
                decided_by="late-approver",
            )
        except InvalidMissionTransition:
            return "rejected"
        return "accepted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        expire_future = pool.submit(expire)
        decide_future = pool.submit(decide)
        rotated = expire_future.result()
        decision = decide_future.result()

    assert rotated in {0, 1}
    assert decision == "rejected"
    with command_center.connect() as connection:
        approvals = connection.execute(
            "SELECT request_version, status, consumed_at "
            "FROM mission_step_approvals WHERE step_id=? ORDER BY request_version",
            (step_id,),
        ).fetchall()
    assert [row["request_version"] for row in approvals] == [1, 2]
    assert approvals[0]["status"] == "expired"
    assert approvals[0]["consumed_at"] is None
    assert approvals[1]["status"] == "pending"
    snapshot = command_center.get_mission(mission_id)
    assert snapshot["status"] == "running"
    assert snapshot["steps"][0]["status"] == "awaiting_approval"


@pytest.mark.parametrize("replacement", ["renewed_expiry", "replacement_token"])
def test_postgres_stale_requeue_cas_preserves_current_lease(
    postgres_cluster_services,
    monkeypatch,
    replacement,
):
    command_center, _work_runs = postgres_cluster_services
    mission_id, step, _request_model = _approve_and_claim(
        command_center,
        f"requeue-{replacement}",
    )
    original_transaction = command_center.repository.transaction
    stale_read_complete = threading.Event()
    allow_stale_cas = threading.Event()

    class ControlledConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement, parameters=()):
            if (
                "SELECT * FROM mission_steps" in statement
                and "lease_expires_at <=" in statement
            ):
                cursor = self.connection.execute(
                    statement.rstrip() + " AND id=?",
                    ("2100-01-01T00:00:00+00:00", step["id"]),
                )
                stale_read_complete.set()
                assert allow_stale_cas.wait(timeout=20)
                return cursor
            return self.connection.execute(statement, parameters)

    @contextmanager
    def controlled_transaction(*, immediate=False):
        with original_transaction(immediate=immediate) as connection:
            if threading.current_thread().name.startswith("stale-requeue"):
                yield ControlledConnection(connection)
            else:
                yield connection

    monkeypatch.setattr(
        command_center.repository,
        "transaction",
        controlled_transaction,
    )
    with command_center.connect() as connection:
        events_before = connection.execute(
            "SELECT COUNT(*) AS count FROM mission_events "
            "WHERE mission_id=? AND event_type='step_requeued'",
            (mission_id,),
        ).fetchone()["count"]

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="stale-requeue",
    ) as pool:
        future = pool.submit(command_center.requeue_stale_steps)
        assert stale_read_complete.wait(timeout=20)
        if replacement == "renewed_expiry":
            expected_token = step["lease_token"]
            expected_expiry = command_center.renew_step_lease(
                step["id"],
                lease_token=step["lease_token"],
                lease_seconds=1200,
            )
        else:
            expected_token = f"replacement-{uuid.uuid4().hex}"
            expected_expiry = (
                datetime.now(timezone.utc) + timedelta(minutes=20)
            ).isoformat()
            with command_center.connect(immediate=True) as connection:
                changed = connection.execute(
                    "UPDATE mission_steps SET lease_token=?, lease_expires_at=? "
                    "WHERE id=? AND status='running' AND lease_token=?",
                    (
                        expected_token,
                        expected_expiry,
                        step["id"],
                        step["lease_token"],
                    ),
                )
                assert changed.rowcount == 1
        allow_stale_cas.set()
        assert future.result() == 0

    with command_center.connect() as connection:
        current = connection.execute(
            "SELECT status, lease_token, lease_expires_at FROM mission_steps WHERE id=?",
            (step["id"],),
        ).fetchone()
        events_after = connection.execute(
            "SELECT COUNT(*) AS count FROM mission_events "
            "WHERE mission_id=? AND event_type='step_requeued'",
            (mission_id,),
        ).fetchone()["count"]
    assert current["status"] == "running"
    assert current["lease_token"] == expected_token
    assert current["lease_expires_at"] == expected_expiry
    assert events_after == events_before


def test_postgres_cluster_authority_claims_one_work_run(
    postgres_cluster_services,
):
    command_center, work_runs = postgres_cluster_services
    mission_id, step, request = _approve_and_claim(
        command_center,
        "authority-race",
    )
    authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=step["lease_token"],
        worker_id=step["lease_owner"],
    )
    callers = 32
    barrier = threading.Barrier(callers)

    def claim(_index: int):
        barrier.wait(timeout=20)
        return authority.claim(
            request,
            {"sub": "42", "role": "admin"},
            "clusterprobe",
        )

    with ThreadPoolExecutor(max_workers=callers) as pool:
        results = list(pool.map(claim, range(callers)))

    canonical_run = command_center.get_mission(mission_id)["mission_run"]
    assert sum(created for _run, created in results) == 1
    assert len({run["id"] for run, _created in results}) == 1
    assert {run["mission_id"] for run, _created in results} == {mission_id}
    assert {run["mission_run_id"] for run, _created in results} == {
        canonical_run["id"]
    }
    assert {run["correlation_id"] for run, _created in results} == {
        canonical_run["correlation_id"]
    }
    run_id = results[0][0]["id"]
    with command_center.connect() as connection:
        ledger = connection.execute(
            "SELECT COUNT(*) AS count, MAX(attempt) AS max_attempt "
            "FROM work_runs WHERE mission_id=?",
            (mission_id,),
        ).fetchone()
    assert ledger["count"] == 1
    assert ledger["max_attempt"] == 1
    assert work_runs.get(run_id)["status"] == "running"


def test_postgres_fresh_approval_closes_unknown_old_run_without_redispatch(
    postgres_cluster_services,
):
    command_center, work_runs = postgres_cluster_services
    mission_id, step, request = _approve_and_claim(
        command_center,
        "unknown-run-recovery",
    )
    original_authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=step["lease_token"],
        worker_id=step["lease_owner"],
    )
    original, created = original_authority.claim(
        request,
        {"sub": "42", "role": "admin"},
        "clusterprobe",
    )
    assert created is True
    replacement = _expire_and_reapprove(command_center, mission_id, step)
    fresh_authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=replacement["lease_token"],
        worker_id=replacement["lease_owner"],
    )

    replay, replay_created = fresh_authority.claim(
        request,
        {"sub": "42", "role": "admin"},
        "clusterprobe",
    )

    assert replay_created is False
    assert replay["id"] == original["id"]
    assert replay["execution_result"]["remote_outcome"] == "unknown"
    assert replay["execution_result"]["status"] == "reconciliation_required"
    assert replay["execution_result"]["previous_approval_id"] == step["step_approval"]["id"]
    stored = work_runs.get(original["id"])
    assert stored["status"] == "blocked"
    assert stored["failure_code"] == "remote_outcome_unknown"
    with command_center.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM work_runs WHERE mission_id=?",
            (mission_id,),
        ).fetchone()["count"]
    assert count == 1
    current = command_center.get_mission(mission_id)["steps"][0]
    assert current["status"] == "failed"
    assert current["work_run_id"] == original["id"]
    assert current["result"]["cluster_receipt"]["remote_outcome"] == "unknown"


def test_postgres_unknown_recovery_rolls_back_after_step_completion(
    postgres_cluster_services,
    monkeypatch,
):
    command_center, work_runs = postgres_cluster_services
    mission_id, step, request = _approve_and_claim(
        command_center,
        "unknown-run-rollback",
    )
    original_authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=step["lease_token"],
        worker_id=step["lease_owner"],
    )
    original, created = original_authority.claim(
        request,
        {"sub": "42", "role": "admin"},
        "clusterprobe",
    )
    assert created is True
    replacement = _expire_and_reapprove(command_center, mission_id, step)
    fresh_authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=replacement["lease_token"],
        worker_id=replacement["lease_owner"],
    )
    original_complete = command_center.complete_step

    def fail_after_complete(*args, **kwargs):
        original_complete(*args, **kwargs)
        raise RuntimeError("injected PostgreSQL recovery rollback")

    monkeypatch.setattr(command_center, "complete_step", fail_after_complete)
    with pytest.raises(RuntimeError, match="recovery rollback"):
        fresh_authority.claim(
            request,
            {"sub": "42", "role": "admin"},
            "clusterprobe",
        )

    stored = work_runs.get(original["id"])
    assert stored["status"] == "running"
    assert stored["execution_result"] == {}
    with command_center.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM work_runs WHERE mission_id=?",
            (mission_id,),
        ).fetchone()["count"]
    assert count == 1
    current = command_center.get_mission(mission_id)["steps"][0]
    assert current["status"] == "running"
    assert current["lease_token"] == replacement["lease_token"]
    assert current["work_run_id"] == original["id"]


def test_postgres_cluster_completion_commits_atomically(
    postgres_cluster_services,
):
    command_center, work_runs = postgres_cluster_services
    mission_id, step, request = _approve_and_claim(
        command_center,
        "completion-commit",
    )
    authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=step["lease_token"],
        worker_id=step["lease_owner"],
    )
    run, created = authority.claim(
        request,
        {"sub": "42", "role": "admin"},
        "clusterprobe",
    )
    assert created is True
    canonical_run = command_center.get_mission(mission_id)["mission_run"]
    assert run["mission_id"] == mission_id
    assert run["mission_run_id"] == canonical_run["id"]
    assert run["correlation_id"] == canonical_run["correlation_id"]
    receipt = authority.finish(
        run["id"],
        {
            "schema_version": "cluster-execution-receipt.v1",
            "status": "succeeded",
            "remote_outcome": "confirmed",
            "exit_code": 0,
            "log": "Linux 6.8 x86_64",
            "replayed": False,
        },
    )
    assert receipt["status"] == "succeeded"
    stored = work_runs.get(run["id"])
    assert stored["status"] == "completed"
    assert stored["mission_id"] == mission_id
    assert stored["mission_run_id"] == canonical_run["id"]
    assert stored["correlation_id"] == canonical_run["correlation_id"]
    snapshot = command_center.get_mission(mission_id)
    assert snapshot["mission_run"]["id"] == stored["mission_run_id"]
    assert snapshot["mission_run"]["correlation_id"] == stored["correlation_id"]
    assert snapshot["steps"][0]["status"] == "completed"
    assert snapshot["steps"][0]["work_run_id"] == run["id"]


def test_postgres_cluster_completion_rolls_back_atomically(
    postgres_cluster_services,
    monkeypatch,
):
    command_center, work_runs = postgres_cluster_services
    mission_id, step, request = _approve_and_claim(
        command_center,
        "completion-rollback",
    )
    authority = ClusterStepAuthority(
        command_center=command_center,
        work_runs=work_runs,
        step_id=step["id"],
        lease_token=step["lease_token"],
        worker_id=step["lease_owner"],
    )
    run, created = authority.claim(
        request,
        {"sub": "42", "role": "admin"},
        "clusterprobe",
    )
    assert created is True
    original_complete = command_center.complete_step

    def fail_after_step(*args, **kwargs):
        original_complete(*args, **kwargs)
        raise RuntimeError("injected PostgreSQL transaction failure")

    monkeypatch.setattr(command_center, "complete_step", fail_after_step)
    with pytest.raises(RuntimeError, match="injected PostgreSQL"):
        authority.finish(
            run["id"],
            {
                "schema_version": "cluster-execution-receipt.v1",
                "status": "succeeded",
                "remote_outcome": "confirmed",
                "exit_code": 0,
                "log": "Linux 6.8 x86_64",
                "replayed": False,
            },
        )

    assert work_runs.get(run["id"])["status"] == "running"
    snapshot = command_center.get_mission(mission_id)
    assert snapshot["steps"][0]["status"] == "running"
    assert snapshot["steps"][0]["work_run_id"] == run["id"]
