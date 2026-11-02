"""Dormant controlled execution kernel, NOT wired to HTTP or a production worker.

Production imports only ``execution_preparation``. Canonical step integration is
in ``cluster_step_authority``; activation and restricted SSH identities are absent.
An at-most-once local dispatch does not imply exactly-once remote execution.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import os
from pathlib import Path
import re
import signal
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from services.cluster_inventory_service import DEFAULT_FRESHNESS_SECONDS


class ExecutionBlocked(ValueError):
    """Sanitized admission failure, before any durable claim or subprocess."""


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["cluster-operation.v1"] = "cluster-operation.v1"
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]+$")
    node_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    tailscale_id: str = Field(min_length=2, max_length=255, pattern=r"^n[A-Za-z0-9]+$")
    operation: Literal["host.info"]
    timeout_seconds: int = Field(default=10, ge=1, le=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _current(value, now: datetime) -> bool:
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return observed.tzinfo is not None and 0 <= (now - observed).total_seconds() <= DEFAULT_FRESHNESS_SECONDS
    except (AttributeError, ValueError, TypeError):
        return False


def _node_blockers(snapshot: dict, node: dict, now: datetime) -> list[str]:
    blockers = []
    if node.get("identity_status") != "confirmed":
        blockers.append("identity_unconfirmed")
    if node.get("maintenance") is not False:
        blockers.append("maintenance")
    discovery, network, telemetry = (snapshot.get("discovery") or {},
                                     node.get("network") or {}, node.get("telemetry") or {})
    if (not _current(snapshot.get("generated_at"), now) or discovery.get("state") != "fresh"
            or not _current(discovery.get("observed_at"), now)):
        blockers.append("discovery_not_fresh")
    if (network.get("state") != "online" or network.get("expired") is not False
            or not _current(network.get("observed_at"), now)):
        blockers.append("network_unavailable")
    if telemetry.get("state") != "fresh" or not _current(telemetry.get("observed_at"), now):
        blockers.append("telemetry_not_fresh")
    if str(node.get("os", "")).lower() not in {"linux", "macos"}:
        blockers.append("unsupported_os")
    return blockers


def execution_preparation(snapshot: dict, *, login_required: bool) -> dict:
    """Read-only capability inventory. Even zero node blockers is NOT a permit."""
    blockers = ["execution_not_activated", "approval_adapter_not_connected",
                "dedicated_credentials_not_configured"]
    if login_required is not True:
        blockers.append("production_login_required")
    now = _now()
    return {"schema_version": "cluster-execution-preparation.v1", "mode": "preparation_only",
            "enabled": False, "ledger": "work_runs", "approval_authority": "command_center",
            "operations": [{"operation": "host.info", "read_only": True,
                            "supported_os": ["linux", "macOS"], "max_timeout_seconds": 15}],
            "blockers": blockers,
            "nodes": [{"node_id": node["node_id"], "ready": False,
                       "blockers": _node_blockers(snapshot, node, now)}
                      for node in snapshot["nodes"] if node.get("managed") is True]}


@dataclass(frozen=True)
class SSHCredential:
    """Operator-supplied dedicated binding; never accepted from an HTTP request.

    Restriction of the remote account/authorized_keys must be independently
    verified before Phase 3B. Files being separate does not prove least privilege.
    """
    node_id: str
    tailscale_id: str
    user: str
    directory: Path
    private_key: Path
    known_hosts: Path

    def validate(self, request: OperationRequest) -> None:
        if self.node_id != request.node_id or self.tailscale_id != request.tailscale_id:
            raise ExecutionBlocked("credential_identity_mismatch")
        if not re.fullmatch(r"[a-z_][a-z0-9_.-]{0,63}", self.user) or self.user in {"root", "administrator"}:
            raise ExecutionBlocked("restricted_account_required")
        try:
            directory = self.directory
            if not directory.is_absolute() or directory.is_symlink():
                raise ValueError()
            if directory.resolve() == (Path.home() / ".ssh").resolve():
                raise ValueError()
            collector_hosts = Path(os.getenv("CLUSTER_KNOWN_HOSTS", str(Path(__file__).resolve().parents[1] / "data/cluster_known_hosts")))
            if self.known_hosts.resolve() == collector_hosts.resolve():
                raise ValueError()
            root_stat = directory.stat()
            if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.getuid() or root_stat.st_mode & 0o077:
                raise ValueError()
            if self.private_key == self.known_hosts:
                raise ValueError()
            for path in (self.private_key, self.known_hosts):
                if not path.is_absolute() or path.is_symlink() or path.parent != directory:
                    raise ValueError()
                info = path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
                    raise ValueError()
        except (OSError, ValueError):
            raise ExecutionBlocked("unsafe_credential_files") from None


def _argv(credential: SSHCredential, address: str) -> list[str]:
    return ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-p", "22",
            "-i", str(credential.private_key),
            "-o", f"UserKnownHostsFile={credential.known_hosts}",
            "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
            "-o", "CertificateFile=none", "-o", "PasswordAuthentication=no",
            "-o", "KbdInteractiveAuthentication=no", "-o", "ForwardAgent=no",
            "-o", "ClearAllForwardings=yes", "-o", "ProxyCommand=none", "-o", "ProxyJump=none",
            "-o", "ConnectTimeout=4", "-o", "ConnectionAttempts=1",
            f"{credential.user}@{address}", "/usr/bin/uname -srm"]


class _OutputLimit(Exception):
    pass


async def _bounded_read(stream, limit=4096) -> bytes:
    output = bytearray()
    while chunk := await stream.read(1024):
        if len(output) + len(chunk) > limit:
            raise _OutputLimit()
        output.extend(chunk)
    return bytes(output)


async def _transport(argv, timeout_seconds, cancel, factory) -> dict:
    process = await factory(*argv, stdin=asyncio.subprocess.DEVNULL,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                            limit=8192, start_new_session=True)
    readers = [asyncio.create_task(_bounded_read(process.stdout)),
               asyncio.create_task(_bounded_read(process.stderr))]
    async def receive():
        stdout, _stderr = await asyncio.gather(*readers)
        return await process.wait(), stdout
    receive_task = asyncio.create_task(receive())
    cancel_task = asyncio.create_task(cancel.wait()) if cancel else None
    tasks = [receive_task, *([cancel_task] if cancel_task else [])]
    try:
        done, _ = await asyncio.wait(tasks, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED)
        if cancel_task in done:
            return {"status": "cancelled", "remote_outcome": "unknown", "exit_code": None, "log": ""}
        if receive_task not in done:
            return {"status": "timed_out", "remote_outcome": "unknown", "exit_code": None, "log": ""}
        try:
            code, output = receive_task.result()
        except _OutputLimit:
            return {"status": "output_limit", "remote_outcome": "unknown", "exit_code": None, "log": ""}
        # The only allowed output is uname's three bounded printable fields.
        line = output.decode("utf-8", errors="replace").strip()
        if code == 0 and re.fullmatch(r"(?:Linux|Darwin) [A-Za-z0-9_.+~:/-]{1,180} [A-Za-z0-9_.-]{1,40}", line):
            return {"status": "succeeded", "remote_outcome": "confirmed", "exit_code": 0, "log": line}
        return {"status": "connection_failed" if code == 255 else "unverified_result",
                "remote_outcome": "unknown", "exit_code": code, "log": ""}
    finally:
        for task in [*tasks, *readers]:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, *readers, return_exceptions=True)
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        # A paused full pipe can keep Process.wait() pending even after exit.
        # Discard buffered bytes without retaining them after stopping readers.
        async def drain(stream):
            while await stream.read(1024):
                pass
        await asyncio.wait_for(asyncio.gather(process.wait(), drain(process.stdout), drain(process.stderr)), timeout=2)


class ClusterExecutionAdapter:
    """Testable service seam, intentionally not instantiated by production.

    ``step_authority`` integrates canonical approval/fencing. The legacy
    ``authorize`` callback is an isolated test seam, not a production grant.
    Neither path is currently instantiated in production. A future authenticated
    caller must pass the real principal; a worker must never fabricate one.
    """
    def __init__(self, *, work_runs, snapshot_provider, login_required,
                 authorize=None, credentials=None, enabled=False,
                 process_factory=asyncio.create_subprocess_exec, step_authority=None):
        self.work_runs = work_runs
        self.snapshot_provider = snapshot_provider
        self.login_required = login_required
        self.authorize = authorize
        self.credentials = credentials or {}
        self.enabled = enabled is True
        self.process_factory = process_factory
        self.step_authority = step_authority
        if step_authority is not None and (authorize is not None or step_authority.work_runs is not work_runs):
            raise ExecutionBlocked("ambiguous_approval_authority")

    async def execute(self, request: OperationRequest, principal: dict, *, cancel=None) -> dict:
        if not self.enabled:
            raise ExecutionBlocked("execution_not_activated")
        if self.login_required() is not True or principal.get("auth_mode") == "development":
            raise ExecutionBlocked("production_login_required")
        if principal.get("role") != "admin" or not re.fullmatch(r"[0-9]{1,20}", str(principal.get("sub", ""))):
            raise ExecutionBlocked("administrator_required")
        # Revalidate even constructed model instances before consulting authority.
        request = OperationRequest.model_validate(request.model_dump())
        snapshot = self.snapshot_provider()
        matches = [node for node in snapshot["nodes"] if node.get("node_id") == request.node_id]
        if len(matches) != 1 or matches[0].get("managed") is not True:
            raise ExecutionBlocked("managed_node_required")
        node = matches[0]
        if node.get("tailscale_id") != request.tailscale_id:
            raise ExecutionBlocked("identity_mismatch")
        blockers = _node_blockers(snapshot, node, _now())
        if blockers:
            raise ExecutionBlocked(",".join(blockers))
        address = None
        for raw in node.get("addresses", []):
            try:
                candidate = ipaddress.ip_address(raw)
                if isinstance(candidate, ipaddress.IPv4Address) and candidate in ipaddress.ip_network("100.64.0.0/10"):
                    address = str(candidate)
                    break
            except ValueError:
                continue
        if address is None:
            raise ExecutionBlocked("tailnet_address_required")
        credential = self.credentials.get(request.node_id)
        if not isinstance(credential, SSHCredential):
            raise ExecutionBlocked("dedicated_credentials_not_configured")
        credential.validate(request)
        if self.step_authority is None and (self.authorize is None or self.authorize(request, principal) is not True):
            raise ExecutionBlocked("approval_required")
        if cancel and cancel.is_set():
            raise ExecutionBlocked("cancelled_before_start")
        actor = f"cluster-user:{principal['sub']}"
        binding = {"request": request.model_dump(), "actor": actor,
                   "credential_user": credential.user}
        # Global request identity; a different principal must conflict, not
        # silently gain another dispatch namespace for the same operation.
        key = f"cluster-operation:{request.request_id}"
        if self.step_authority is not None:
            run, created = self.step_authority.claim(request, principal, credential.user)
        else:
            run, created = self.work_runs.claim_at_most_once(
                dispatch_id=key, idempotency_key=key, request_binding=binding,
                agent_id=actor, executor="cluster-readonly-v1", input_context={"request": request.model_dump()},
                lease_seconds=60,
            )
        if not created:
            return {**(run.get("execution_result") or {"status": run["status"], "remote_outcome": "unknown"}),
                    "run_id": run["id"], "replayed": True}
        started = _now().isoformat()
        if self.step_authority is None:
            self.work_runs.transition(run["id"], "running", actor=actor, detail="Fixed host.info dispatch")
        cancelled = False
        try:
            result = await _transport(_argv(credential, address), request.timeout_seconds, cancel, self.process_factory)
        except asyncio.CancelledError:
            cancelled = True
            result = {"status": "cancelled", "remote_outcome": "unknown", "exit_code": None, "log": ""}
        except Exception:
            # Raw SSH stderr, exception strings, paths and credentials never escape.
            result = {"status": "transport_error", "remote_outcome": "unknown", "exit_code": None, "log": ""}
        receipt = {"schema_version": "cluster-execution-receipt.v1", "run_id": run["id"],
                   "request_id": request.request_id, "node_id": request.node_id,
                   "tailscale_id": request.tailscale_id, "operation": request.operation,
                   "parameters_summary": {}, "started_at": started, "ended_at": _now().isoformat(),
                   "replayed": False, **result}
        if self.step_authority is not None:
            receipt = self.step_authority.finish(run["id"], receipt)
        else:
            self.work_runs.transition(run["id"], "review" if result["status"] == "succeeded" else "blocked",
                                      actor=actor, detail="Controlled probe receipt",
                                      execution_result=receipt, failure_code=None if result["status"] == "succeeded" else "remote_outcome_unknown")
            if result["status"] == "succeeded":
                self.work_runs.transition(run["id"], "completed", actor=actor, detail="Fixed output contract verified")
        if cancelled:
            raise asyncio.CancelledError()
        return receipt
