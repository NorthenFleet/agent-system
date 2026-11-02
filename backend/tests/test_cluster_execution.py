"""Phase 3A contract tests; subprocesses are local test fixtures, never remote SSH."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sys

import pytest
from pydantic import ValidationError

from services.cluster_execution import (
    ClusterExecutionAdapter, ExecutionBlocked, OperationRequest,
    SSHCredential, execution_preparation,
)
from services.work_run_service import WorkRunIdempotencyConflict, WorkRunService


def snapshot():
    stamp = datetime.now(timezone.utc).isoformat()
    return {"generated_at": stamp, "discovery": {"state": "fresh", "observed_at": stamp},
            "nodes": [{"node_id": "compute-05", "tailscale_id": "nCompute05", "managed": True,
                       "identity_status": "confirmed", "maintenance": False, "os": "linux",
                       "addresses": ["100.91.246.95"],
                       "network": {"state": "online", "observed_at": stamp, "expired": False},
                       "telemetry": {"state": "fresh", "observed_at": stamp}}]}


def request(**patch):
    return OperationRequest(**{"request_id": "request-001", "node_id": "compute-05",
                               "tailscale_id": "nCompute05", "operation": "host.info", **patch})


@pytest.mark.parametrize("patch", [
    {"command": "rm -rf /"}, {"host": "8.8.8.8"}, {"parameters": {}},
    {"operation": "shell"}, {"node_id": "a;bad"}, {"timeout_seconds": True},
    {"timeout_seconds": 16}, {"timeout_seconds": 0},
])
def test_closed_request_contract(patch):
    with pytest.raises(ValidationError):
        request(**patch)


def test_readiness_is_read_only_never_authorization():
    observed = snapshot()
    before = deepcopy(observed)
    result = execution_preparation(observed, login_required=False)
    assert result["mode"] == "preparation_only" and result["enabled"] is False
    assert "production_login_required" in result["blockers"]
    assert "approval_adapter_not_connected" in result["blockers"]
    assert result["nodes"][0] == {"node_id": "compute-05", "ready": False, "blockers": []}
    assert observed == before


@pytest.mark.parametrize("field,value,reason", [
    ("identity_status", "unconfirmed", "identity_unconfirmed"),
    ("maintenance", True, "maintenance"), ("os", "windows", "unsupported_os"),
    ("network", {"state": "offline"}, "network_unavailable"),
    ("telemetry", {"state": "error"}, "telemetry_not_fresh"),
])
def test_node_preflight_fail_closed(field, value, reason):
    observed = snapshot()
    observed["nodes"][0][field] = value
    assert reason in execution_preparation(observed, login_required=True)["nodes"][0]["blockers"]


def test_old_future_and_naive_timestamps_are_not_fresh():
    for stamp in ["bad", "2026-01-01T00:00:00", None,
                  (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                  (datetime.now(timezone.utc) - timedelta(seconds=91)).isoformat()]:
        observed = snapshot()
        observed["generated_at"] = stamp
        assert "discovery_not_fresh" in execution_preparation(observed, login_required=True)["nodes"][0]["blockers"]


@pytest.fixture()
def harness(tmp_path):
    root = tmp_path / "dedicated"
    root.mkdir(mode=0o700)
    key, hosts = root / "id_ed25519", root / "known_hosts"
    key.write_text("fixture only, not a private key")
    hosts.write_text("fixture only, no host trust")
    key.chmod(0o600)
    hosts.chmod(0o600)
    credential = SSHCredential("compute-05", "nCompute05", "clusterprobe", root, key, hosts)
    ledger = WorkRunService(str(tmp_path / "ledger.db"))
    calls, processes = [], []
    observed = snapshot()

    def adapter(code="print('Linux 6.8 x86_64')", **overrides):
        async def factory(*argv, **kwargs):
            calls.append((argv, kwargs))
            process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, **kwargs)
            processes.append(process)
            return process
        options = dict(work_runs=ledger, snapshot_provider=lambda: deepcopy(observed),
                       login_required=lambda: True, authorize=lambda *_: True,
                       credentials={"compute-05": credential}, enabled=True, process_factory=factory)
        options.update(overrides)
        return ClusterExecutionAdapter(**options)

    return adapter, ledger, calls, processes, observed, credential


PRINCIPAL = {"sub": "42", "role": "admin"}


@pytest.mark.parametrize("overrides,principal,reason", [
    ({"enabled": False}, PRINCIPAL, "execution_not_activated"),
    ({"login_required": lambda: False}, PRINCIPAL, "production_login_required"),
    ({}, {**PRINCIPAL, "auth_mode": "development"}, "production_login_required"),
    ({}, {"sub": "42", "role": "member"}, "administrator_required"),
    ({"authorize": None}, PRINCIPAL, "approval_required"),
    ({"authorize": lambda *_: False}, PRINCIPAL, "approval_required"),
    ({"credentials": {}}, PRINCIPAL, "dedicated_credentials_not_configured"),
])
def test_denied_requests_create_neither_process_nor_run(harness, overrides, principal, reason):
    make, ledger, calls, *_ = harness
    with pytest.raises(ExecutionBlocked, match=reason):
        asyncio.run(make(**overrides).execute(request(), principal))
    assert calls == [] and ledger.list() == []


def test_default_constructor_is_disabled(harness):
    _, ledger, calls, _, observed, _ = harness
    executor = ClusterExecutionAdapter(work_runs=ledger, snapshot_provider=lambda: observed,
                                      login_required=lambda: True)
    with pytest.raises(ExecutionBlocked, match="execution_not_activated"):
        asyncio.run(executor.execute(request(), PRINCIPAL))
    assert calls == [] and ledger.list() == []


def test_fixed_argv_receipt_and_replay(harness):
    make, ledger, calls, *_ = harness
    executor = make()
    first = asyncio.run(executor.execute(request(), PRINCIPAL))
    second = asyncio.run(executor.execute(request(), PRINCIPAL))
    assert first["status"] == "succeeded" and first["exit_code"] == 0
    assert first["remote_outcome"] == "confirmed" and first["log"] == "Linux 6.8 x86_64"
    assert first["started_at"] and first["ended_at"] and first["node_id"] == "compute-05"
    assert second["replayed"] is True and first["run_id"] == second["run_id"]
    assert len(calls) == 1 and len(ledger.list()) == 1
    argv, kwargs = calls[0]
    assert argv[0] == "/usr/bin/ssh" and argv[-1] == "/usr/bin/uname -srm"
    assert argv[-2] == "clusterprobe@100.91.246.95"
    for flag in ["StrictHostKeyChecking=yes", "IdentitiesOnly=yes", "IdentityAgent=none",
                 "ForwardAgent=no", "PasswordAuthentication=no", "ProxyCommand=none"]:
        assert flag in argv
    assert not kwargs.get("shell")
    assert ledger.get(first["run_id"])["execution_result"]["status"] == "succeeded"


def test_concurrent_duplicates_spawn_once(harness):
    make, _, calls, *_ = harness
    async def run():
        executor = make("import time; time.sleep(.05); print('Linux 6.8 x86_64')")
        return await asyncio.gather(*(executor.execute(request(), PRINCIPAL) for _ in range(5)))
    results = asyncio.run(run())
    assert len(calls) == 1 and sum(not item["replayed"] for item in results) == 1


def test_same_request_cannot_repeat_under_another_administrator(harness):
    make, ledger, calls, *_ = harness
    executor = make()
    asyncio.run(executor.execute(request(), PRINCIPAL))
    with pytest.raises(WorkRunIdempotencyConflict):
        asyncio.run(executor.execute(request(), {"sub": "43", "role": "admin"}))
    assert len(calls) == 1 and len(ledger.list()) == 1


def test_expired_snapshot_and_identity_mismatch_block_before_ssh(harness):
    make, ledger, calls, _, observed, _ = harness
    with pytest.raises(ExecutionBlocked, match="identity_mismatch"):
        asyncio.run(make().execute(request(tailscale_id="nOther"), PRINCIPAL))
    observed["nodes"][0]["network"]["state"] = "offline"
    with pytest.raises(ExecutionBlocked, match="network_unavailable"):
        asyncio.run(make().execute(request(), PRINCIPAL))
    assert calls == [] and ledger.list() == []


def test_credential_permissions_or_binding_cannot_fall_back_to_operator_key(harness):
    make, ledger, calls, _, _, credential = harness
    credential.private_key.chmod(0o644)
    with pytest.raises(ExecutionBlocked, match="unsafe_credential_files"):
        asyncio.run(make().execute(request(), PRINCIPAL))
    assert calls == [] and ledger.list() == []


def test_collector_known_hosts_cannot_be_reused(harness, monkeypatch):
    make, ledger, calls, _, _, credential = harness
    monkeypatch.setenv("CLUSTER_KNOWN_HOSTS", str(credential.known_hosts))
    with pytest.raises(ExecutionBlocked, match="unsafe_credential_files"):
        asyncio.run(make().execute(request(), PRINCIPAL))
    assert calls == [] and ledger.list() == []


@pytest.mark.parametrize("code,status", [
    ("import time; time.sleep(10)", "timed_out"),
    ("print('x' * 20000)", "output_limit"),
    ("import sys; sys.stderr.write('secret-token'); sys.exit(255)", "connection_failed"),
])
def test_unknown_outcomes_are_bounded_persisted_and_not_retried(harness, code, status):
    make, ledger, calls, processes, *_ = harness
    executor = make(code)
    result = asyncio.run(executor.execute(request(timeout_seconds=1), PRINCIPAL))
    assert result["status"] == status and result["remote_outcome"] == "unknown"
    assert ledger.get(result["run_id"])["status"] == "blocked"
    assert "secret-token" not in str(result)
    assert all(process.returncode is not None for process in processes)
    again = asyncio.run(executor.execute(request(timeout_seconds=1), PRINCIPAL))
    assert again["replayed"] and len(calls) == 1


def test_cancel_event_stops_local_transport_without_claiming_remote_stop(harness):
    make, ledger, calls, processes, *_ = harness
    async def run():
        cancel = asyncio.Event()
        task = asyncio.create_task(make("import time; time.sleep(10)").execute(request(), PRINCIPAL, cancel=cancel))
        while not processes:
            await asyncio.sleep(.001)
        cancel.set()
        return await task
    result = asyncio.run(run())
    assert result["status"] == "cancelled" and result["remote_outcome"] == "unknown"
    assert processes[0].returncode is not None and len(calls) == 1
    assert ledger.get(result["run_id"])["status"] == "blocked"


def test_cancelled_coroutine_keeps_uncertain_receipt(harness):
    make, ledger, _, processes, *_ = harness
    async def run():
        task = asyncio.create_task(make("import time; time.sleep(10)").execute(request(), PRINCIPAL))
        while not processes:
            await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    run = ledger.list()[0]
    assert run["status"] == "blocked" and run["execution_result"]["remote_outcome"] == "unknown"
    assert processes[0].returncode is not None
