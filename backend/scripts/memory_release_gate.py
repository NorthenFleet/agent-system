#!/usr/bin/env python3
"""Prepare, approve, check, or promote a governed memory-platform release."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.memory_release_governance import (
    DEFAULT_CANDIDATE_PATH,
    MemoryReleaseGovernanceError,
    attest_candidate_validation,
    current_release_gate,
    prepare_release_candidate,
    read_release_candidate,
    read_latest_release_execution,
    record_release_decision,
    update_release_candidate_approval,
    write_release_candidate,
)
from services.memory_release_orchestrator import orchestrate_memory_release
from services.memory_release_notifications import publish_memory_release_notification
from services.memory_system_health_status import read_memory_system_health, read_memory_system_matrix


DEPLOYER_PATH = WORKSPACE_ROOT / "integrations" / "openclaw" / "graph-memory" / "deploy.py"
GATE_SCRIPT = BACKEND_ROOT / "scripts" / "memory_system_gate.py"
MATRIX_SCRIPT = BACKEND_ROOT / "scripts" / "memory_system_matrix.py"


def _deployer():
    spec = importlib.util.spec_from_file_location("governed_graph_memory_deployer", DEPLOYER_PATH)
    if not spec or not spec.loader:
        raise MemoryReleaseGovernanceError("cannot load graph-memory deployer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_verifier(script: Path, reader) -> dict[str, Any]:
    completed = subprocess.run(
        [str(BACKEND_ROOT / "venv" / "bin" / "python"), str(script)],
        cwd=BACKEND_ROOT,
        check=False,
    )
    result = reader()
    if completed.returncode != 0 and result.get("healthy") is True:
        result = {**result, "healthy": False, "failures": [{"check": "verifier_exit_code", "expected": 0, "actual": completed.returncode}]}
    return result


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _notify_execution(execution: dict[str, Any]) -> dict[str, Any]:
    """Notification delivery is observable but cannot rewrite the release outcome."""
    from database import SessionLocal, ensure_db_initialized

    db = None
    try:
        ensure_db_initialized()
        db = SessionLocal()
        return publish_memory_release_notification(db, execution)
    except Exception as exc:
        if db is not None:
            db.rollback()
        return {"status": "failed", "notifications_created": 0, "error": str(exc)[:300]}
    finally:
        if db is not None:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--created-by", required=True)
    prepare.add_argument("--change-type", default="memory-platform")
    commands.add_parser("check")
    commands.add_parser("validate")
    approve = commands.add_parser("approve")
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--expected-digest", required=True)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--revoked-by", required=True)
    revoke.add_argument("--expected-digest", required=True)
    promote = commands.add_parser("promote-graph-bridge")
    promote.add_argument("--target", type=Path)
    promote.add_argument("--backup-root", type=Path)
    promote.add_argument(
        "--force-reverify",
        action="store_true",
        help="rerun canary and matrix even when this release already completed successfully",
    )
    args = parser.parse_args()

    try:
        if args.command == "prepare":
            candidate = prepare_release_candidate(
                version=args.version,
                created_by=args.created_by,
                change_type=args.change_type,
            )
            write_release_candidate(candidate, args.candidate)
            decision = current_release_gate(candidate_path=args.candidate)
            record_release_decision(decision)
            _print({"candidate": candidate, "decision": decision})
            return 0 if decision["technical_ready"] else 2
        if args.command in {"approve", "revoke"}:
            if args.command == "revoke" and current_release_gate(
                candidate_path=args.candidate
            ).get("release_completed") is True:
                raise MemoryReleaseGovernanceError("completed release approval is immutable")
            actor = args.approved_by if args.command == "approve" else args.revoked_by
            updated = update_release_candidate_approval(
                actor=actor,
                expected_digest=args.expected_digest,
                approve=args.command == "approve",
                path=args.candidate,
            )
            decision = current_release_gate(candidate_path=args.candidate)
            record_release_decision(decision)
            _print({"candidate": updated, "decision": decision})
            expected_ready = args.command == "approve"
            return 0 if decision["promotion_ready"] is expected_ready else 2

        if args.command == "validate":
            candidate = read_release_candidate(args.candidate)
            if not candidate:
                raise MemoryReleaseGovernanceError("release candidate is missing")
            validations = [
                (
                    "backend_memory_release_regression",
                    [
                        str(BACKEND_ROOT / "venv" / "bin" / "python"),
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_memory_release_governance.py",
                        "tests/test_memory_release_notifications.py",
                        "tests/test_memory_release_orchestrator.py",
                        "tests/test_memory_system_health_status.py",
                        "tests/test_memory_system_gate.py",
                        "tests/test_memory_system_matrix.py",
                        "tests/test_memory_system_slo.py",
                        "tests/test_memory_system_drill.py",
                        "tests/test_graph_memory_bridge_deploy.py",
                    ],
                    BACKEND_ROOT,
                ),
                ("frontend_production_build", ["npm", "run", "build"], WORKSPACE_ROOT / "frontend-v2"),
            ]
            checks = []
            for name, command, cwd in validations:
                completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
                detail = (completed.stdout + "\n" + completed.stderr).strip()[-1000:]
                checks.append(
                    {
                        "name": name,
                        "passed": completed.returncode == 0,
                        "return_code": completed.returncode,
                        "detail": detail,
                    }
                )
            validated = attest_candidate_validation(candidate, checks=checks)
            write_release_candidate(validated, args.candidate)
            decision = current_release_gate(candidate_path=args.candidate)
            record_release_decision(decision)
            _print({"candidate": validated, "decision": decision})
            return 0 if decision["technical_ready"] else 2

        decision = current_release_gate(candidate_path=args.candidate)
        record_release_decision(decision)
        if args.command == "check":
            _print(decision)
            return 0 if decision["technical_ready"] else 2

        if decision.get("change_type") not in {"graph-bridge", "memory-platform"}:
            raise MemoryReleaseGovernanceError(
                "promote-graph-bridge requires a graph-bridge or memory-platform candidate"
            )
        previous_execution = read_latest_release_execution()
        if (
            not args.force_reverify
            and decision.get("status") == "completed"
            and previous_execution
            and previous_execution.get("release_id") == decision.get("release_id")
        ):
            _print(
                {
                    "decision": decision,
                    "execution": previous_execution,
                    "replay_prevented": True,
                }
            )
            return 0
        deployer = _deployer()
        target = args.target or deployer.DEFAULT_TARGET
        backup_root = args.backup_root or deployer.DEFAULT_BACKUP_ROOT
        execution = orchestrate_memory_release(
            decision,
            deploy=lambda: deployer.deploy(target, backup_root=backup_root),
            restart=deployer.restart_gateway,
            verify_canary=lambda: _run_verifier(GATE_SCRIPT, read_memory_system_health),
            verify_matrix=lambda: _run_verifier(MATRIX_SCRIPT, read_memory_system_matrix),
            rollback=lambda backup: deployer.restore_backup(target, Path(backup)),
        )
        execution["notification_delivery"] = _notify_execution(execution)
        record_release_decision(execution)
        _print({"decision": decision, "execution": execution})
        return 0 if execution["status"] in {"promoted", "verified_noop"} else 2
    except (MemoryReleaseGovernanceError, OSError, ValueError) as exc:
        _print({"success": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
