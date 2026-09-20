#!/usr/bin/env python3
"""Run an isolated PostgreSQL in-flight recovery and idempotency drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.command_center_service import (  # noqa: E402
    CommandCenterService,
    InvalidMissionTransition,
)
from services.work_run_service import WorkRunService  # noqa: E402
from services.workflow_runtime import PostgresLangGraphWorkflowRuntime  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def controlled_apply(ledger_path: Path, key: str) -> tuple[dict[str, Any], bool]:
    receipt = {
        "idempotency_key": key,
        "receipt_ref": f"drill://controlled-adapter/{hashlib.sha256(key.encode()).hexdigest()[:20]}",
        "applied_at": now_iso(),
        "apply_count": 1,
    }
    try:
        descriptor = os.open(ledger_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return json.loads(ledger_path.read_text(encoding="utf-8")), False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
    return receipt, True


def result_for(step: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    evidence_types = list(step.get("evidence_required") or []) or ["test_output"]
    contract = step.get("output_contract") or {}
    artifact_types = list(contract.get("artifact_types") or []) or ["receipt"]
    evidence = [
        {
            "evidence_type": evidence_type,
            "source_ref": receipt["receipt_ref"],
            "summary": "恢复执行命中首次回执，受控适配器 apply_count=1",
        }
        for evidence_type in evidence_types
    ]
    artifacts = [
        {
            "artifact_type": artifact_type,
            "title": "在途任务幂等恢复回执",
            "uri": receipt["receipt_ref"],
            "content_hash": hashlib.sha256(
                json.dumps(receipt, sort_keys=True).encode()
            ).hexdigest(),
        }
        for artifact_type in artifact_types
    ]
    acceptance_results = [
        {
            "criterion": criterion,
            "passed": True,
            "evidence_refs": [receipt["receipt_ref"]],
        }
        for criterion in (step.get("acceptance_criteria") or [])
    ]
    return {
        "summary": "worker-b 从持久化状态续跑，复用首次副作用回执并完成",
        "artifacts": artifacts,
        "evidence": evidence,
        "acceptance_results": acceptance_results,
        "tools_used": list(step.get("required_tools") or []) or ["controlled-drill-adapter"],
        "risk_notes": "隔离演练库；无真实外部写入",
        "side_effects": [
            {
                "effect_key": "controlled-write-once",
                "resource": "drill://controlled-adapter",
                "action": "write-once",
                "status": "applied",
                "idempotency_key": step["idempotency_key"],
                "receipt_ref": receipt["receipt_ref"],
                "evidence_refs": [receipt["receipt_ref"]],
            }
        ],
    }


def count(conn: Any, sql: str, params: tuple[Any, ...]) -> int:
    return int(conn.execute(sql, params).fetchone()["count"])


def run(database_url: str) -> dict[str, Any]:
    started = time.monotonic()
    drill_id = uuid.uuid4().hex[:12]
    os.environ["COMMAND_CENTER_DATABASE_URL"] = database_url
    os.environ["WORK_RUN_DATABASE_URL"] = database_url
    service = CommandCenterService(project_provider=lambda: [])
    work_runs = WorkRunService(database_url=database_url)

    mission = service.create_mission(
        objective=f"[可靠性演练 {drill_id}] 在途任务故障恢复与幂等续跑",
        requested_by="reliability-drill",
    )
    service.claim_planning_mission("drill-planner")
    service.save_plan(
        mission["id"],
        {
            "summary": "隔离 PostgreSQL 单步骤恢复演练",
            "rationale": "验证 lease fencing、WorkRun 复用、副作用幂等和终态幂等",
            "risk_level": "low",
            "steps": [
                {
                    "order_index": 1,
                    "title": "执行受控幂等写入",
                    "description": "生成固定回执；故障接管后只允许复用，不得重复应用",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "executor": "controlled-drill",
                    "depends_on": [],
                    "side_effect": True,
                    "resources": ["drill://controlled-adapter"],
                    "idempotency_key": f"inflight:{drill_id}:step-1",
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="reliability-drill")
    service.activate_approved_missions()
    first_step = service.claim_ready_steps("worker-a", limit=1, lease_seconds=60)[0]
    mission_run_id = service.get_mission_run_ledger(mission["id"])["run"]["id"]
    first_run = work_runs.claim(
        dispatch_id=first_step["id"],
        agent_id="worker-a",
        executor="controlled-drill",
        mission_id=mission["id"],
        mission_run_id=mission_run_id,
        idempotency_key=first_step["idempotency_key"],
        lease_seconds=60,
    )
    work_runs.transition(first_run["id"], "running", actor="worker-a", lease_seconds=60)
    service.attach_work_run(
        first_step["id"], first_run["id"], lease_token=first_step["lease_token"]
    )

    with tempfile.TemporaryDirectory(prefix="inflight-drill-") as temp_dir:
        ledger_path = Path(temp_dir) / "adapter-ledger.json"
        first_receipt, first_applied = controlled_apply(
            ledger_path, first_step["idempotency_key"]
        )

        fault_injected_at = now_iso()
        with service.connect(immediate=True) as conn:
            conn.execute(
                "UPDATE mission_steps SET lease_expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", first_step["id"]),
            )
            conn.execute(
                "UPDATE work_runs SET lease_expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", first_run["id"]),
            )

        # Reconstruct both services to model a new process after worker-a died.
        recovered_service = CommandCenterService(project_provider=lambda: [])
        recovered_runs = WorkRunService(database_url=database_url)
        requeued = recovered_service.requeue_stale_steps()
        second_step = recovered_service.claim_ready_steps(
            "worker-b", limit=1, lease_seconds=60
        )[0]
        second_run = recovered_runs.claim(
            dispatch_id=second_step["id"],
            agent_id="worker-b",
            executor="controlled-drill",
            mission_id=mission["id"],
            mission_run_id=mission_run_id,
            idempotency_key=second_step["idempotency_key"],
            lease_seconds=60,
        )
        replay_receipt, replay_applied = controlled_apply(
            ledger_path, second_step["idempotency_key"]
        )

        old_token_fenced = False
        try:
            recovered_service.complete_step(
                first_step["id"],
                result={"summary": "stale worker completion"},
                success=True,
                actor="worker-a",
                lease_token=first_step["lease_token"],
            )
        except InvalidMissionTransition:
            old_token_fenced = True

        recovered_service.attach_work_run(
            second_step["id"],
            second_run["id"],
            lease_token=second_step["lease_token"],
        )
        execution_result = result_for(second_step, replay_receipt)
        completed_step = recovered_service.complete_step(
            second_step["id"],
            result=execution_result,
            success=True,
            actor="worker-b",
            lease_token=second_step["lease_token"],
        )
        recovered_runs.transition(
            second_run["id"],
            "review",
            actor="worker-b",
            result_summary=execution_result["summary"],
            execution_result=execution_result,
        )
        recovered_runs.transition(
            second_run["id"],
            "completed",
            actor="worker-b",
            result_summary=execution_result["summary"],
            execution_result=execution_result,
        )
        recovered_service.claim_evaluation_mission("drill-evaluator")
        completed_mission = recovered_service.complete_mission(
            mission["id"],
            summary="在途任务恢复演练通过",
            success=True,
            actor="drill-evaluator",
        )
        replayed_completion = recovered_service.complete_mission(
            mission["id"],
            summary="replayed acknowledgement",
            success=True,
            actor="drill-evaluator-replay",
        )

        checkpoint_thread = f"inflight-checkpoint-{drill_id}"
        workflow_input = {
            "id": checkpoint_thread,
            "thread_id": checkpoint_thread,
            "checkpoint_namespace": "inflight-drill",
            "mission_id": mission["id"],
            "plan_version": 1,
            "input": {
                "flow_key": "document",
                "highest_risk": "L0",
                "context_pack_id": f"context-{drill_id}",
            },
        }
        checkpoint_start = PostgresLangGraphWorkflowRuntime(database_url).start(
            workflow_input
        )
        restarted_runtime = PostgresLangGraphWorkflowRuntime(database_url)
        checkpoint_resume = restarted_runtime.resume(
            workflow_input,
            {"decision": "approved", "decided_by": "worker-b"},
        )
        checkpoint_replay = restarted_runtime.resume(
            workflow_input,
            {"decision": "approved", "decided_by": "worker-b"},
        )

        with recovered_service.connect() as conn:
            counts = {
                "work_runs": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM work_runs WHERE idempotency_key=?",
                    (second_step["idempotency_key"],),
                ),
                "lease_reclaims": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM work_run_events WHERE run_id=? AND event_type='lease_reclaimed'",
                    (first_run["id"],),
                ),
                "step_requeued": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='step_requeued'",
                    (mission["id"],),
                ),
                "step_completed": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='step_completed'",
                    (mission["id"],),
                ),
                "mission_completed": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='mission_completed'",
                    (mission["id"],),
                ),
                "artifacts": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM mission_artifacts WHERE mission_id=?",
                    (mission["id"],),
                ),
                "artifact_fingerprints": count(
                    conn,
                    "SELECT COUNT(DISTINCT fingerprint) AS count FROM mission_artifacts WHERE mission_id=?",
                    (mission["id"],),
                ),
                "evidence": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM mission_evidence WHERE mission_id=?",
                    (mission["id"],),
                ),
                "evidence_fingerprints": count(
                    conn,
                    "SELECT COUNT(DISTINCT fingerprint) AS count FROM mission_evidence WHERE mission_id=?",
                    (mission["id"],),
                ),
                "effects": count(
                    conn,
                    "SELECT COUNT(*) AS count FROM mission_effects WHERE mission_id=?",
                    (mission["id"],),
                ),
                "effect_fingerprints": count(
                    conn,
                    "SELECT COUNT(DISTINCT fingerprint) AS count FROM mission_effects WHERE mission_id=?",
                    (mission["id"],),
                ),
            }

    checks = {
        "stale_step_requeued_once": requeued == 1 and counts["step_requeued"] == 1,
        "same_work_run_reclaimed": second_run["id"] == first_run["id"]
        and counts["work_runs"] == 1
        and counts["lease_reclaims"] == 1,
        "old_lease_token_fenced": old_token_fenced,
        "side_effect_applied_once": first_applied
        and not replay_applied
        and first_receipt == replay_receipt
        and replay_receipt["apply_count"] == 1,
        "step_completed_once": completed_step["status"] == "completed"
        and counts["step_completed"] == 1,
        "records_persisted_once": counts["artifacts"] >= 1
        and counts["artifacts"] == counts["artifact_fingerprints"]
        and counts["evidence"] >= 1
        and counts["evidence"] == counts["evidence_fingerprints"]
        and counts["effects"] == 1
        and counts["effects"] == counts["effect_fingerprints"],
        "mission_delivered_once": completed_mission["status"] == "completed"
        and replayed_completion["updated_at"] == completed_mission["updated_at"]
        and counts["mission_completed"] == 1,
        "checkpoint_resumed_idempotently": checkpoint_start.status == "awaiting_approval"
        and checkpoint_resume.status == "ready"
        and checkpoint_replay.status == "ready"
        and checkpoint_resume.state == checkpoint_replay.state,
    }
    return {
        "schema_version": "1.0",
        "drill": "command_center_inflight_recovery",
        "drill_id": drill_id,
        "started_at": fault_injected_at,
        "finished_at": now_iso(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "database": "isolated_postgresql",
        "mission_id": mission["id"],
        "mission_run_id": mission_run_id,
        "step_id": second_step["id"],
        "work_run_id": second_run["id"],
        "idempotency_key": second_step["idempotency_key"],
        "fault": {
            "type": "worker_heartbeat_loss_after_side_effect",
            "injected_at": fault_injected_at,
            "old_owner": "worker-a",
            "recovery_owner": "worker-b",
        },
        "counts": counts,
        "checkpoint": {
            "thread_id": checkpoint_thread,
            "initial_status": checkpoint_start.status,
            "resumed_status": checkpoint_resume.status,
            "replayed_status": checkpoint_replay.status,
        },
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = run(args.database_url)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
