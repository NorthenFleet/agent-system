from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.work_run_service import (
    WorkRunError,
    WorkRunIdempotencyConflict,
    WorkRunService,
)


def _claim(
    service: WorkRunService,
    *,
    key: str = "cluster:node-1:service-status:v1",
    actor: str = "cluster-worker-a",
    dispatch_id: str = "cluster-operation-1",
    executor: str = "cluster-remote",
    request_binding: dict | None = None,
    input_context: dict | None = None,
):
    return service.claim_at_most_once(
        dispatch_id=dispatch_id,
        idempotency_key=key,
        request_binding=request_binding
        or {
            "node_id": "node-1",
            "operation": "service_status",
            "arguments": {"service": "agent-system"},
            "catalog_version": "cluster-operations.v1",
        },
        agent_id=actor,
        executor=executor,
        input_context=input_context,
        lease_seconds=60,
    )


def test_concurrent_claim_creates_exactly_one_run(tmp_path):
    db_path = str(tmp_path / "concurrent.db")
    service = WorkRunService(db_path)
    callers = 32
    barrier = threading.Barrier(callers)

    def attempt(actor: str):
        barrier.wait(timeout=20)
        return _claim(service, actor=actor)

    with ThreadPoolExecutor(max_workers=callers) as pool:
        results = list(pool.map(attempt, (f"worker-{index}" for index in range(callers))))

    assert sum(created for _run, created in results) == 1
    assert len({run["id"] for run, _created in results}) == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_runs").fetchone()[0] == 1
        assert conn.execute("SELECT MAX(attempt) FROM work_runs").fetchone()[0] == 1


def test_normal_claim_cannot_reclaim_active_at_most_once_key(tmp_path):
    db_path = str(tmp_path / "active-reserved.db")
    service = WorkRunService(db_path)
    run, created = _claim(service, key="reserved-active")
    assert created is True

    with pytest.raises(WorkRunIdempotencyConflict, match="reserved"):
        service.claim(
            dispatch_id="cluster-operation-1",
            idempotency_key="reserved-active",
            agent_id="ordinary-worker",
            executor="cluster-remote",
        )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_runs").fetchone()[0] == 1
        stored = conn.execute(
            "SELECT id, attempt, lease_owner FROM work_runs"
        ).fetchone()
    assert stored == (run["id"], 1, run["lease_owner"])


def test_normal_claim_cannot_retry_terminal_at_most_once_key(tmp_path):
    db_path = str(tmp_path / "terminal-reserved.db")
    service = WorkRunService(db_path)
    run, created = _claim(service, key="reserved-terminal")
    assert created is True
    service.transition(run["id"], "failed", actor="cluster-worker-a")

    with pytest.raises(WorkRunIdempotencyConflict, match="reserved"):
        service.claim(
            dispatch_id="cluster-operation-1",
            idempotency_key="reserved-terminal",
            agent_id="ordinary-worker",
            executor="cluster-remote",
        )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_runs").fetchone()[0] == 1
        assert conn.execute("SELECT MAX(attempt) FROM work_runs").fetchone()[0] == 1


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled", "completed"])
def test_terminal_replay_returns_original_run_without_retry(tmp_path, terminal_status):
    service = WorkRunService(str(tmp_path / f"{terminal_status}.db"))
    run, created = _claim(service, key=f"terminal:{terminal_status}")
    assert created is True
    if terminal_status == "completed":
        service.transition(run["id"], "running", actor="cluster-worker-a")
        service.transition(run["id"], "review", actor="cluster-worker-a")
    terminal = service.transition(run["id"], terminal_status, actor="cluster-worker-a")

    replay, replay_created = _claim(
        service,
        key=f"terminal:{terminal_status}",
        actor="cluster-worker-b",
        request_binding={
            "catalog_version": "cluster-operations.v1",
            "arguments": {"service": "agent-system"},
            "operation": "service_status",
            "node_id": "node-1",
        },
    )

    assert replay_created is False
    assert replay["id"] == terminal["id"]
    assert replay["attempt"] == 1
    assert replay["status"] == terminal_status


def test_expired_active_replay_does_not_reclaim_lease(tmp_path):
    db_path = str(tmp_path / "expired.db")
    service = WorkRunService(db_path)
    run, _created = _claim(service, key="expired-key", actor="worker-a")
    expired_at = "2000-01-01T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE work_runs SET lease_expires_at=? WHERE id=?",
            (expired_at, run["id"]),
        )
        conn.commit()

    replay, created = _claim(service, key="expired-key", actor="worker-b")

    assert created is False
    assert replay["id"] == run["id"]
    assert replay["lease_owner"] == "worker-a"
    assert replay["lease_expires_at"] == expired_at
    assert not any(event["event_type"] == "lease_reclaimed" for event in replay["events"])


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"dispatch_id": "different-dispatch"}, "dispatch_id"),
        ({"executor": "different-executor"}, "executor"),
        (
            {
                "request_binding": {
                    "node_id": "node-2",
                    "operation": "service_status",
                    "arguments": {"service": "agent-system"},
                    "catalog_version": "cluster-operations.v1",
                }
            },
            "request binding",
        ),
    ],
)
def test_replay_with_changed_invariants_is_rejected(tmp_path, overrides, match):
    service = WorkRunService(str(tmp_path / "changed.db"))
    _claim(service, key="fixed-key")

    with pytest.raises(WorkRunIdempotencyConflict, match=match):
        _claim(service, key="fixed-key", **overrides)


def test_legacy_key_without_binding_marker_is_rejected(tmp_path):
    service = WorkRunService(str(tmp_path / "legacy.db"))
    service.claim(
        dispatch_id="legacy-dispatch",
        idempotency_key="legacy-key",
        agent_id="legacy-worker",
        executor="legacy-executor",
    )

    with pytest.raises(WorkRunIdempotencyConflict, match="binding marker"):
        service.claim_at_most_once(
            dispatch_id="legacy-dispatch",
            idempotency_key="legacy-key",
            request_binding={"operation": "status"},
            agent_id="legacy-worker",
            executor="legacy-executor",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"key": ""},
        {"actor": ""},
        {"dispatch_id": ""},
        {"executor": ""},
        {"request_binding": {"value": float("nan")}},
        {"request_binding": {"value": object()}},
        {"input_context": {"_at_most_once": {"binding_sha256": "spoofed"}}},
    ],
)
def test_invalid_claim_contract_is_rejected(tmp_path, kwargs):
    service = WorkRunService(str(tmp_path / "invalid.db"))
    with pytest.raises(WorkRunError):
        _claim(service, **kwargs)


def test_normal_claim_keeps_existing_retry_semantics(tmp_path):
    service = WorkRunService(str(tmp_path / "normal-retry.db"))
    first = service.claim(
        dispatch_id="normal",
        idempotency_key="normal-key",
        agent_id="worker-a",
        executor="normal-executor",
    )
    service.transition(first["id"], "failed", actor="worker-a")

    retry = service.claim(
        dispatch_id="normal",
        idempotency_key="normal-key",
        agent_id="worker-a",
        executor="normal-executor",
    )

    assert retry["id"] != first["id"]
    assert retry["attempt"] == 2
