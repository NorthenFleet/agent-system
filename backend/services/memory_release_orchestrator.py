"""Canary-first promotion with automatic rollback for memory platform releases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


Deploy = Callable[[], dict[str, Any]]
Restart = Callable[[], None]
Verify = Callable[[], dict[str, Any]]
Rollback = Callable[[str], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def orchestrate_memory_release(
    decision: dict[str, Any],
    *,
    deploy: Deploy,
    restart: Restart,
    verify_canary: Verify,
    verify_matrix: Verify,
    rollback: Rollback,
) -> dict[str, Any]:
    """Execute a promoted release; every post-change failure attempts rollback."""
    events: list[dict[str, Any]] = []

    def event(stage: str, status: str, detail: Any = None) -> None:
        row = {"stage": stage, "status": status, "at": _now()}
        if detail is not None:
            row["detail"] = detail
        events.append(row)

    result: dict[str, Any] = {
        "schema_version": "memory-release-execution.v1",
        "release_id": str(decision.get("release_id") or ""),
        "decision_id": str(decision.get("decision_id") or ""),
        "candidate_digest": str(decision.get("candidate_digest") or ""),
        "version": str(decision.get("version") or ""),
        "change_type": str(decision.get("change_type") or ""),
        "risk": decision.get("risk") if isinstance(decision.get("risk"), dict) else {},
        "started_at": _now(),
        "status": "blocked",
        "events": events,
    }
    if decision.get("promotion_ready") is not True:
        event("preflight_gate", "blocked", decision.get("blocking_failures") or ["approval"])
        result["completed_at"] = _now()
        return result

    event("preflight_gate", "passed")
    backup = ""
    changed = False
    deployment_completed = False
    try:
        deployed = deploy()
        deployment_completed = True
        backup = str(deployed.get("backup") or "")
        changed = deployed.get("changed") is True
        event("deploy", "changed" if changed else "noop", {"backup_created": bool(backup)})
        if changed:
            if not backup:
                raise RuntimeError("deployment changed files without a recoverable backup")
            restart()
            event("restart_gateway", "passed")
        else:
            event("restart_gateway", "skipped", {"reason": "artifact_unchanged"})
        canary = verify_canary()
        event("optimus_canary", "passed" if canary.get("healthy") is True else "failed", {"healthy": canary.get("healthy") is True, "failures": canary.get("failures") or []})
        if canary.get("healthy") is not True:
            raise RuntimeError("Optimus canary failed")
        matrix = verify_matrix()
        event("multi_agent_matrix", "passed" if matrix.get("healthy") is True else "failed", {"healthy": matrix.get("healthy") is True, "failures": matrix.get("failures") or []})
        if matrix.get("healthy") is not True:
            raise RuntimeError("multi-agent matrix failed")
        result["status"] = "promoted" if changed else "verified_noop"
    except Exception as exc:
        event("release", "failed", str(exc)[:500])
        if backup:
            try:
                rollback_result = rollback(backup)
                event("automatic_rollback", "passed", {"restored": rollback_result.get("restored") is True})
                restart()
                event("rollback_restart_gateway", "passed")
                result["status"] = "rolled_back"
            except Exception as rollback_exc:
                event("automatic_rollback", "failed", str(rollback_exc)[:500])
                result["status"] = "rollback_failed"
        elif deployment_completed and not changed:
            result["status"] = "verification_failed_no_change"
        else:
            result["status"] = "failed_before_backup"
    result["completed_at"] = _now()
    return result
