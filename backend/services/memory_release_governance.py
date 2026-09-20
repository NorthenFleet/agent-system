"""Auditable release candidates and policy gates for the memory platform."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.memory_system_health_status import (
    read_memory_system_health,
    read_memory_system_matrix,
)
from services.memory_system_slo import calculate_memory_slo, read_memory_system_drill


BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
DEFAULT_POLICY_PATH = BACKEND_ROOT / "config" / "memory_release_policy.json"
DEFAULT_CANDIDATE_PATH = BACKEND_ROOT / "data" / "memory-release-candidate.json"
DEFAULT_DECISION_PATH = BACKEND_ROOT / "data" / "memory-release-decision.json"
DEFAULT_EXECUTION_PATH = BACKEND_ROOT / "data" / "memory-release-execution.json"
DEFAULT_AUDIT_PATH = BACKEND_ROOT / "data" / "memory-release-audit.jsonl"
MAX_ARTIFACT_BYTES = 10_000_000
ALLOWED_CHANGE_TYPES = {"memory-platform", "graph-bridge", "memory-skill", "evaluation-contract", "configuration"}
SUCCESSFUL_EXECUTION_STATUSES = {"promoted", "verified_noop", "completed_noop"}
FAILED_EXECUTION_STATUSES = {
    "rolled_back",
    "rollback_failed",
    "verification_failed_no_change",
    "failed_before_backup",
}


class MemoryReleaseGovernanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoryReleaseGovernanceError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise MemoryReleaseGovernanceError(f"{label} must contain an object")
    return value


def load_release_policy(path: str | Path | None = None) -> dict[str, Any]:
    selected = Path(path or DEFAULT_POLICY_PATH).expanduser()
    policy = _read_object(selected, "memory release policy")
    if policy.get("schema_version") != "memory-release-policy.v1":
        raise MemoryReleaseGovernanceError("unsupported memory release policy schema")
    artifacts = policy.get("managed_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise MemoryReleaseGovernanceError("memory release policy has no managed artifacts")
    return policy


def _release_risk(policy: dict[str, Any], change_type: str) -> dict[str, Any]:
    configured = policy.get("risk_policy") if isinstance(policy.get("risk_policy"), dict) else {}
    selected = configured.get(change_type) if isinstance(configured.get(change_type), dict) else {}
    level = str(selected.get("level") or "medium").strip().lower()
    if level not in {"low", "medium", "high", "critical"}:
        raise MemoryReleaseGovernanceError(f"unsupported release risk level: {level}")
    validations = selected.get("required_validations")
    if not isinstance(validations, list):
        validations = []
    return {
        "level": level,
        "label": str(selected.get("label") or {"low": "低风险", "medium": "中风险", "high": "高风险", "critical": "极高风险"}[level])[:32],
        "approval_mode": str(selected.get("approval_mode") or "human-admin-separated")[:80],
        "requires_creator_separation": selected.get("requires_creator_separation") is not False,
        "required_validations": [str(name).strip()[:160] for name in validations if str(name).strip()],
    }


def _missing_risk_validations(candidate: dict[str, Any]) -> list[str]:
    risk = candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {}
    required = risk.get("required_validations") if isinstance(risk.get("required_validations"), list) else []
    validation = candidate.get("validation") if isinstance(candidate.get("validation"), dict) else {}
    checks = validation.get("checks") if isinstance(validation.get("checks"), list) else []
    passed = {
        str(item.get("name") or "")
        for item in checks
        if isinstance(item, dict) and item.get("passed") is True
    }
    return [str(name) for name in required if str(name) not in passed]


def _resolve_artifact(workspace_root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise MemoryReleaseGovernanceError(f"artifact path must be workspace-relative: {relative}")
    root = workspace_root.resolve()
    selected = (root / relative).resolve()
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise MemoryReleaseGovernanceError(f"artifact escapes workspace: {relative}") from exc
    if not selected.is_file():
        raise MemoryReleaseGovernanceError(f"managed artifact is missing: {relative}")
    size = selected.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise MemoryReleaseGovernanceError(f"managed artifact exceeds size limit: {relative}")
    return selected


def candidate_digest(candidate: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in candidate.items()
        if key not in {"approval", "validation", "candidate_digest"}
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def prepare_release_candidate(
    *,
    version: str,
    created_by: str,
    change_type: str = "memory-platform",
    policy_path: str | Path | None = None,
    workspace_root: str | Path = WORKSPACE_ROOT,
    release_id: str = "",
) -> dict[str, Any]:
    clean_type = str(change_type).strip().lower()
    if clean_type not in ALLOWED_CHANGE_TYPES:
        raise MemoryReleaseGovernanceError(f"unsupported memory change type: {clean_type}")
    clean_version = str(version).strip()[:120]
    clean_actor = str(created_by).strip()[:160]
    if not clean_version or not clean_actor:
        raise MemoryReleaseGovernanceError("version and created_by are required")
    policy = load_release_policy(policy_path)
    root = Path(workspace_root).expanduser().resolve()
    artifacts = []
    for relative in policy["managed_artifacts"]:
        clean_relative = str(relative).strip()
        selected = _resolve_artifact(root, clean_relative)
        artifacts.append(
            {"path": clean_relative, "sha256": _sha256(selected), "size_bytes": selected.stat().st_size}
        )
    candidate = {
        "schema_version": "memory-release-candidate.v1",
        "release_id": str(release_id).strip()[:160] or f"memory-release-{uuid.uuid4().hex[:12]}",
        "version": clean_version,
        "change_type": clean_type,
        "created_at": _now(),
        "created_by": clean_actor,
        "policy_schema": policy["schema_version"],
        "requirements": policy.get("requirements") or {},
        "risk": _release_risk(policy, clean_type),
        "artifacts": artifacts,
        "approval": {"status": "pending", "approved_by": "", "approved_at": None},
        "validation": {"status": "pending", "validated_at": None, "candidate_digest": "", "checks": []},
    }
    candidate["candidate_digest"] = candidate_digest(candidate)
    return candidate


def write_release_candidate(
    candidate: dict[str, Any],
    path: str | Path | None = None,
) -> Path:
    selected = Path(path or DEFAULT_CANDIDATE_PATH).expanduser()
    _atomic_json(selected, candidate)
    return selected


def read_release_candidate(path: str | Path | None = None) -> dict[str, Any] | None:
    selected = Path(path or DEFAULT_CANDIDATE_PATH).expanduser()
    if not selected.is_file():
        return None
    return _read_object(selected, "memory release candidate")


def approve_release_candidate(
    candidate: dict[str, Any],
    *,
    approved_by: str,
    expected_digest: str,
) -> dict[str, Any]:
    actor = str(approved_by).strip()[:160]
    digest = candidate_digest(candidate)
    if not actor:
        raise MemoryReleaseGovernanceError("approved_by is required")
    risk = candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {}
    if risk.get("requires_creator_separation") is not False and actor == str(candidate.get("created_by") or "").strip():
        raise MemoryReleaseGovernanceError("candidate creator cannot approve the same release")
    if str(expected_digest).strip().lower() != digest:
        raise MemoryReleaseGovernanceError("candidate digest changed before approval")
    validation = candidate.get("validation") if isinstance(candidate.get("validation"), dict) else {}
    if validation.get("status") != "passed" or validation.get("candidate_digest") != digest:
        raise MemoryReleaseGovernanceError("candidate validation has not passed for this digest")
    missing_validations = _missing_risk_validations(candidate)
    if missing_validations:
        raise MemoryReleaseGovernanceError(
            "candidate is missing risk-required validations: " + ", ".join(missing_validations)
        )
    result = json.loads(json.dumps(candidate))
    result["candidate_digest"] = digest
    result["approval"] = {"status": "approved", "approved_by": actor, "approved_at": _now()}
    return result


def revoke_release_candidate(
    candidate: dict[str, Any],
    *,
    revoked_by: str,
    expected_digest: str,
) -> dict[str, Any]:
    actor = str(revoked_by).strip()[:160]
    digest = candidate_digest(candidate)
    if not actor:
        raise MemoryReleaseGovernanceError("revoked_by is required")
    if str(expected_digest).strip().lower() != digest:
        raise MemoryReleaseGovernanceError("candidate digest changed before revocation")
    result = json.loads(json.dumps(candidate))
    result["candidate_digest"] = digest
    result["approval"] = {
        "status": "pending",
        "approved_by": "",
        "approved_at": None,
        "revoked_by": actor,
        "revoked_at": _now(),
    }
    return result


def update_release_candidate_approval(
    *,
    actor: str,
    expected_digest: str,
    approve: bool,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Update approval under a sidecar lock so digest checking and persistence are atomic."""
    selected = Path(path or DEFAULT_CANDIDATE_PATH).expanduser()
    selected.parent.mkdir(parents=True, exist_ok=True)
    lock_path = selected.with_name(f".{selected.name}.lock")
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        candidate = read_release_candidate(selected)
        if not candidate:
            raise MemoryReleaseGovernanceError("release candidate is missing")
        if approve:
            updated = approve_release_candidate(
                candidate,
                approved_by=actor,
                expected_digest=expected_digest,
            )
        else:
            updated = revoke_release_candidate(
                candidate,
                revoked_by=actor,
                expected_digest=expected_digest,
            )
        write_release_candidate(updated, selected)
        return updated
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)


def attest_candidate_validation(
    candidate: dict[str, Any],
    *,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    if not checks:
        raise MemoryReleaseGovernanceError("at least one validation check is required")
    normalized = []
    for item in checks:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise MemoryReleaseGovernanceError("validation checks require a name")
        normalized.append(
            {
                "name": str(item["name"])[:160],
                "passed": item.get("passed") is True,
                "return_code": int(item.get("return_code") or 0),
                "detail": str(item.get("detail") or "")[:1000],
            }
        )
    result = json.loads(json.dumps(candidate))
    digest = candidate_digest(result)
    passed = all(item["passed"] for item in normalized)
    result["candidate_digest"] = digest
    result["validation"] = {
        "status": "passed" if passed else "failed",
        "validated_at": _now(),
        "candidate_digest": digest,
        "checks": normalized,
    }
    if not passed:
        result["approval"] = {"status": "pending", "approved_by": "", "approved_at": None}
    return result


def verify_candidate_artifacts(
    candidate: dict[str, Any],
    *,
    workspace_root: str | Path = WORKSPACE_ROOT,
) -> list[dict[str, Any]]:
    root = Path(workspace_root).expanduser().resolve()
    artifacts = candidate.get("artifacts") if isinstance(candidate.get("artifacts"), list) else []
    failures: list[dict[str, Any]] = []
    if not artifacts:
        return [{"check": "candidate.artifacts", "expected": "non-empty", "actual": 0}]
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            failures.append({"check": "candidate.artifact", "expected": "object", "actual": type(artifact).__name__})
            continue
        relative = str(artifact.get("path") or "")
        try:
            selected = _resolve_artifact(root, relative)
            actual = _sha256(selected)
        except MemoryReleaseGovernanceError as exc:
            failures.append({"check": f"artifact.{relative or 'unknown'}", "expected": artifact.get("sha256"), "actual": str(exc)})
            continue
        if actual != artifact.get("sha256"):
            failures.append({"check": f"artifact.{relative}", "expected": artifact.get("sha256"), "actual": actual})
    return failures


def evaluate_release_gate(
    candidate: dict[str, Any] | None,
    *,
    health: dict[str, Any],
    matrix: dict[str, Any],
    slo: dict[str, Any],
    drill: dict[str, Any],
    workspace_root: str | Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, expected: Any, actual: Any, *, blocking: bool = True) -> None:
        checks.append({"name": name, "passed": bool(passed), "blocking": blocking, "expected": expected, "actual": actual})

    if not candidate:
        add("candidate.present", False, "prepared release candidate", "missing")
        requirements: dict[str, Any] = {}
    else:
        add("candidate.schema", candidate.get("schema_version") == "memory-release-candidate.v1", "memory-release-candidate.v1", candidate.get("schema_version"))
        expected_digest = candidate_digest(candidate)
        add("candidate.digest", candidate.get("candidate_digest") == expected_digest, expected_digest, candidate.get("candidate_digest"))
        artifact_failures = verify_candidate_artifacts(candidate, workspace_root=workspace_root)
        add("candidate.artifacts", not artifact_failures, "all hashes match", artifact_failures)
        validation = candidate.get("validation") if isinstance(candidate.get("validation"), dict) else {}
        validation_ready = (
            validation.get("status") == "passed"
            and validation.get("candidate_digest") == expected_digest
            and bool(validation.get("checks"))
            and not _missing_risk_validations(candidate)
        )
        add(
            "candidate.validation",
            validation_ready,
            "tests and build passed for candidate digest",
            {
                "status": validation.get("status") or "missing",
                "candidate_digest": validation.get("candidate_digest") or "",
                "checks": validation.get("checks") or [],
                "missing_risk_validations": _missing_risk_validations(candidate),
            },
        )
        requirements = candidate.get("requirements") if isinstance(candidate.get("requirements"), dict) else {}

    add("primary.current_health", health.get("healthy") is True, True, health.get("status"))
    matrix_summary = matrix.get("summary") if isinstance(matrix.get("summary"), dict) else {}
    matrix_min = max(1, int(requirements.get("matrix_cases") or 5))
    matrix_passed = int(matrix_summary.get("passed_cases") or 0)
    matrix_total = int(matrix_summary.get("total_cases") or 0)
    add("matrix.current_health", matrix.get("healthy") is True, True, matrix.get("status"))
    add("matrix.coverage", matrix_total >= matrix_min and matrix_passed == matrix_total, {"minimum_cases": matrix_min, "all_passed": True}, {"passed": matrix_passed, "total": matrix_total})

    monitors = slo.get("monitors") if isinstance(slo.get("monitors"), dict) else {}
    primary_slo = monitors.get("primary") if isinstance(monitors.get("primary"), dict) else {}
    matrix_slo = monitors.get("matrix") if isinstance(monitors.get("matrix"), dict) else {}
    primary_min = max(1, int(requirements.get("primary_slo_min_samples") or 20))
    matrix_slo_min = max(1, int(requirements.get("matrix_slo_min_samples") or 1))
    add("slo.data_quality", (slo.get("data_quality") or {}).get("valid") is True, True, slo.get("data_quality"))
    add("slo.primary", primary_slo.get("status") == "healthy" and int(primary_slo.get("sample_count") or 0) >= primary_min, {"status": "healthy", "minimum_samples": primary_min}, {"status": primary_slo.get("status"), "samples": primary_slo.get("sample_count")})
    add("slo.matrix", matrix_slo.get("status") == "healthy" and int(matrix_slo.get("sample_count") or 0) >= matrix_slo_min, {"status": "healthy", "minimum_samples": matrix_slo_min}, {"status": matrix_slo.get("status"), "samples": matrix_slo.get("sample_count")})

    drill_summary = drill.get("summary") if isinstance(drill.get("summary"), dict) else {}
    drill_min = max(1, int(requirements.get("drill_scenarios") or 4))
    drill_passed = int(drill_summary.get("passed_scenarios") or 0)
    drill_total = int(drill_summary.get("total_scenarios") or 0)
    add("drill.current", drill.get("healthy") is True, True, drill.get("status"))
    add("drill.coverage", drill_total >= drill_min and drill_passed == drill_total, {"minimum_scenarios": drill_min, "all_passed": True}, {"passed": drill_passed, "total": drill_total})

    approval = candidate.get("approval") if candidate and isinstance(candidate.get("approval"), dict) else {}
    approval_ready = approval.get("status") == "approved" and bool(str(approval.get("approved_by") or "").strip())
    add("approval", approval_ready, "explicit human approval", approval.get("status") or "pending", blocking=False)
    blocking_failures = [item for item in checks if item["blocking"] and not item["passed"]]
    technical_ready = not blocking_failures
    promotion_ready = technical_ready and approval_ready
    status = "ready" if promotion_ready else "awaiting_approval" if technical_ready else "blocked"
    release_id = str((candidate or {}).get("release_id") or "")
    approval_summary = {
        "status": str(approval.get("status") or "pending"),
        "approved_by": str(approval.get("approved_by") or ""),
        "approved_at": approval.get("approved_at"),
        "revoked_by": str(approval.get("revoked_by") or ""),
        "revoked_at": approval.get("revoked_at"),
    }
    decision_material = {
        "release_id": release_id,
        "status": status,
        "checks": checks,
        "approval": approval_summary,
    }
    decision_id = hashlib.sha256(json.dumps(decision_material, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return {
        "schema_version": "memory-release-decision.v1",
        "decision_id": decision_id,
        "calculated_at": _now(),
        "release_id": release_id,
        "candidate_digest": str((candidate or {}).get("candidate_digest") or ""),
        "version": str((candidate or {}).get("version") or ""),
        "change_type": str((candidate or {}).get("change_type") or ""),
        "risk": (candidate or {}).get("risk") if isinstance((candidate or {}).get("risk"), dict) else {},
        "status": status,
        "technical_ready": technical_ready,
        "promotion_ready": promotion_ready,
        "approval": approval_summary,
        "blocking_failures": [item["name"] for item in blocking_failures],
        "checks": checks,
        "rollout_plan": {
            "strategy": "optimus-canary-then-matrix",
            "steps": ["preflight_gate", "recoverable_backup", "deploy", "restart_gateway", "optimus_canary", "multi_agent_matrix", "promote"],
            "automatic_rollback_on": ["deploy_failure", "optimus_canary_failure", "multi_agent_matrix_failure"],
        },
    }


def attach_release_execution(
    decision: dict[str, Any],
    execution: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach terminal execution state only when it belongs to this exact release."""
    result = json.loads(json.dumps(decision))
    release_id = str(result.get("release_id") or "")
    matches = bool(
        release_id
        and execution
        and str(execution.get("release_id") or "") == release_id
    )
    execution_status = str((execution or {}).get("status") or "") if matches else ""
    completed = execution_status in SUCCESSFUL_EXECUTION_STATUSES
    result["release_completed"] = completed
    result["execution_required"] = result.get("promotion_ready") is True and not completed
    result["execution_status"] = execution_status or None
    result["completed_at"] = (execution or {}).get("completed_at") if matches else None
    if completed and result.get("promotion_ready") is True:
        result["status"] = "completed"
    elif matches and execution_status in FAILED_EXECUTION_STATUSES and result.get("technical_ready") is True:
        result["status"] = "execution_failed"
    return result


def current_release_gate(
    *,
    candidate_path: str | Path | None = None,
    workspace_root: str | Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    candidate = read_release_candidate(candidate_path)
    decision = evaluate_release_gate(
        candidate,
        health=read_memory_system_health(),
        matrix=read_memory_system_matrix(),
        slo=calculate_memory_slo(days=7),
        drill=read_memory_system_drill(),
        workspace_root=workspace_root,
    )
    return attach_release_execution(decision, read_latest_release_execution())


def record_release_decision(
    decision: dict[str, Any],
    *,
    latest_path: str | Path | None = None,
    audit_path: str | Path | None = None,
) -> None:
    default_latest = (
        DEFAULT_EXECUTION_PATH
        if decision.get("schema_version") == "memory-release-execution.v1"
        else DEFAULT_DECISION_PATH
    )
    latest = Path(latest_path or default_latest).expanduser()
    audit = Path(audit_path or DEFAULT_AUDIT_PATH).expanduser()
    _atomic_json(latest, decision)
    audit.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(audit, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        encoded = (json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)


def read_latest_release_execution(
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    selected = Path(path or DEFAULT_EXECUTION_PATH).expanduser()
    if not selected.is_file():
        return None
    return _read_object(selected, "memory release execution")


def read_release_audit(
    path: str | Path | None = None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    selected = Path(path or DEFAULT_AUDIT_PATH).expanduser()
    if not selected.is_file():
        return []
    try:
        lines = selected.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MemoryReleaseGovernanceError(f"cannot read memory release audit: {exc}") from exc
    result: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
        if len(result) >= max(1, min(int(limit), 1000)):
            break
    return result


def summarize_release_history(
    rows: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Collapse append-only audit rows into one operational timeline item per release."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        release_id = str(row.get("release_id") or "").strip()
        if release_id:
            grouped.setdefault(release_id, []).append(row)

    history: list[dict[str, Any]] = []
    for release_id, events in grouped.items():
        decision = next(
            (row for row in events if row.get("schema_version") == "memory-release-decision.v1"),
            {},
        )
        executions = [
            row for row in events if row.get("schema_version") == "memory-release-execution.v1"
        ]
        execution = next(
            (row for row in executions if row.get("status") != "blocked"),
            executions[0] if executions else {},
        )
        execution_status = str(execution.get("status") or "")
        if execution_status in SUCCESSFUL_EXECUTION_STATUSES:
            status = "completed"
        elif execution_status == "rolled_back":
            status = "rolled_back"
        elif execution_status == "rollback_failed":
            status = "rollback_failed"
        elif execution_status in FAILED_EXECUTION_STATUSES:
            status = "failed"
        else:
            status = str(decision.get("status") or execution_status or "unknown")
        timestamps = [
            str(row.get("completed_at") or row.get("calculated_at") or row.get("started_at") or "")
            for row in events
        ]
        timestamps = [value for value in timestamps if value]
        approval = decision.get("approval") if isinstance(decision.get("approval"), dict) else {}
        risk = decision.get("risk") if isinstance(decision.get("risk"), dict) else {}
        if not risk and isinstance(execution.get("risk"), dict):
            risk = execution["risk"]
        history.append(
            {
                "release_id": release_id,
                "version": str(decision.get("version") or execution.get("version") or ""),
                "change_type": str(decision.get("change_type") or execution.get("change_type") or ""),
                "candidate_digest": str(decision.get("candidate_digest") or execution.get("candidate_digest") or ""),
                "status": status,
                "execution_status": execution_status or None,
                "risk": risk,
                "approved_by": str(approval.get("approved_by") or ""),
                "started_at": min(timestamps) if timestamps else None,
                "updated_at": max(timestamps) if timestamps else None,
                "completed_at": execution.get("completed_at"),
                "event_count": len(events),
                "events": execution.get("events") if isinstance(execution.get("events"), list) else [],
            }
        )
    history.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return history[: max(1, min(int(limit), 50))]
