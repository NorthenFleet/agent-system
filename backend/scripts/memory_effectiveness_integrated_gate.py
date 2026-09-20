#!/usr/bin/env python3
"""Evaluate real-memory recall plus isolated lifecycle/abstention fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.context_retrieval_service import ContextRetrievalService
from services.memory_effectiveness_service import (
    DATASET_VERSION,
    evaluate_effectiveness_dataset,
    load_dataset,
    save_json,
)
from services.memory_feedback_service import MemoryFeedbackService
from services.memory_lifecycle_service import MemoryLifecycleService
from unified_data_manager import UNIFIED_DB_PATH


FIXTURE_USER = "memory-effectiveness-controlled-fixture"
FIXTURE_PROJECT = "memory-effectiveness-controlled-project"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the unified memory-effectiveness gate on a temporary database copy."
        )
    )
    parser.add_argument("--db", default=UNIFIED_DB_PATH)
    parser.add_argument(
        "--base-dataset",
        default=str(BACKEND_ROOT / "evals" / "memory_effectiveness_phase1.json"),
    )
    parser.add_argument("--dataset-output", default="")
    parser.add_argument("--report-output", default="")
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args()


def _clone_sqlite(source: str, destination: str) -> None:
    source_uri = f"file:{Path(source).expanduser().resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=8) as source_conn:
        with sqlite3.connect(destination, timeout=8) as destination_conn:
            source_conn.backup(destination_conn)


def _publish(
    feedback: MemoryFeedbackService,
    *,
    mission_id: str,
    target_scope: str,
    memory_key: str,
    content: str,
    project_id: str = "",
    agent_id: str = "optimus",
) -> dict:
    candidate = feedback.create_candidates(
        user_id=FIXTURE_USER,
        mission_id=mission_id,
        plan_version=1,
        project_id=project_id,
        candidates=[
            {
                "target_scope": target_scope,
                "memory_type": "decision",
                "memory_key": memory_key,
                "title": memory_key,
                "content": content,
                "importance": "critical",
                "confidence": 0.99,
                "agent_id": agent_id,
            }
        ],
    )[0]
    return feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="controlled-fixture"
    )


def _case(
    *,
    case_id: str,
    scenario: str,
    query: str,
    expected: list[str],
    forbidden: list[str],
    expected_decision: str,
    project_id: str = FIXTURE_PROJECT,
    agent_id: str = "optimus",
) -> dict:
    return {
        "id": case_id,
        "scenario": scenario,
        "query": query,
        "user_id": FIXTURE_USER,
        "project_id": project_id,
        "agent_id": agent_id,
        "limit": 10,
        "expected_source_refs": expected,
        "forbidden_source_refs": forbidden,
        "expected_decision": expected_decision,
        "importance": "critical",
        "source_type": "controlled_fixture",
        "variant_key": "integrated_gate_v1",
        "relevance_judgment": "partial",
        "label_status": "verified",
        "verification_method": "controlled_fixture",
    }


def _install_controlled_cases(
    context: ContextRetrievalService,
    feedback: MemoryFeedbackService,
    lifecycle: MemoryLifecycleService,
) -> tuple[list[dict], dict]:
    context.upsert_profile(
        user_id=FIXTURE_USER,
        display_name="Memory Effectiveness Controlled Fixture",
    )

    old = _publish(
        feedback,
        mission_id="integrated-update-v1",
        target_scope="project",
        project_id=FIXTURE_PROJECT,
        memory_key="controlled.update",
        content="controlled-update-token-v1 是已失效的旧版。",
    )
    current = _publish(
        feedback,
        mission_id="integrated-update-v2",
        target_scope="project",
        project_id=FIXTURE_PROJECT,
        memory_key="controlled.update",
        content="controlled-update-token-v2 是当前权威版本。",
    )

    conflict_loser = context.upsert_fact(
        user_id=FIXTURE_USER,
        fact_type="decision",
        fact_key="controlled.conflict",
        fact_value="controlled-conflict-token-old 是冲突败者。",
        source_ref="controlled-conflict-old",
    )
    conflict_winner = _publish(
        feedback,
        mission_id="integrated-conflict-winner",
        target_scope="project",
        project_id=FIXTURE_PROJECT,
        memory_key="controlled.conflict",
        content="controlled-conflict-token-winner 是裁决后的权威值。",
    )
    lifecycle.resolve_conflict(
        winner_ref=conflict_winner["published_ref"],
        loser_ref=f"fact:{conflict_loser['id']}",
        user_id=FIXTURE_USER,
        actor="controlled-fixture",
        rationale="approved project memory wins the controlled conflict",
    )

    expired = _publish(
        feedback,
        mission_id="integrated-expiry",
        target_scope="project",
        project_id=FIXTURE_PROJECT,
        memory_key="controlled.expiry",
        content="controlled-expiry-token 只在到期前有效。",
    )
    lifecycle.schedule_expiry(
        source_ref=expired["published_ref"],
        user_id=FIXTURE_USER,
        valid_until="2026-01-01T00:00:00+00:00",
        actor="controlled-fixture",
    )
    lifecycle.expire_due(
        as_of="2026-01-02T00:00:00+00:00",
        user_id=FIXTURE_USER,
        actor="controlled-fixture",
    )

    forgotten = _publish(
        feedback,
        mission_id="integrated-forget",
        target_scope="agent",
        agent_id="optimus",
        memory_key="controlled.forget",
        content="controlled-forget-token 必须被彻底遗忘。",
    )
    lifecycle.forget(
        source_ref=forgotten["published_ref"],
        user_id=FIXTURE_USER,
        actor="controlled-fixture",
    )

    cases = [
        _case(
            case_id="controlled-update",
            scenario="update",
            query="controlled-update-token-v2 当前版本",
            expected=[current["published_ref"]],
            forbidden=[old["published_ref"]],
            expected_decision="supported",
        ),
        _case(
            case_id="controlled-conflict",
            scenario="conflict",
            query="controlled-conflict-token-winner 权威值",
            expected=[conflict_winner["published_ref"]],
            forbidden=[f"fact:{conflict_loser['id']}"],
            expected_decision="supported",
        ),
        _case(
            case_id="controlled-expiry",
            scenario="expiry",
            query="controlled-expiry-token 还有效吗",
            expected=[],
            forbidden=[expired["published_ref"]],
            expected_decision="abstain",
        ),
        _case(
            case_id="controlled-forget",
            scenario="forget",
            query="controlled-forget-token 记得什么",
            expected=[],
            forbidden=[forgotten["published_ref"]],
            expected_decision="abstain",
        ),
        _case(
            case_id="controlled-abstention",
            scenario="abstention",
            query="controlled-unknown-zephyr-9173 有什么已确认记忆",
            expected=[],
            forbidden=[],
            expected_decision="abstain",
            project_id="",
        ),
    ]
    return cases, lifecycle.verify(user_id=FIXTURE_USER)


def _combined_dataset(base: dict, controlled_cases: list[dict]) -> dict:
    cases = [*list(base.get("cases") or []), *controlled_cases]
    digest_payload = [
        {
            key: case.get(key)
            for key in (
                "id",
                "scenario",
                "query",
                "user_id",
                "project_id",
                "agent_id",
                "expected_source_refs",
                "forbidden_source_refs",
                "expected_decision",
                "label_status",
                "verification_method",
            )
        }
        for case in cases
    ]
    dataset_hash = hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": DATASET_VERSION,
        "dataset_id": f"integrated-memory-gate-{dataset_hash[:12]}",
        "dataset_hash": dataset_hash,
        "owner_user_id": str(base.get("owner_user_id") or "1"),
        "provenance": {
            "authority": "production-snapshot-plus-controlled-fixtures",
            "contains_memory_content": False,
            "production_mutated": False,
            "base_dataset_id": base.get("dataset_id"),
            "base_dataset_hash": base.get("dataset_hash"),
            "controlled_cases": len(controlled_cases),
            "human_verification_required": True,
        },
        "cases": cases,
    }


def run_gate(*, db_path: str, base_dataset_path: str) -> tuple[dict, dict]:
    base = load_dataset(base_dataset_path)
    with tempfile.TemporaryDirectory(prefix="memory-integrated-gate-") as temp_dir:
        cloned_db = str(Path(temp_dir) / "unified-dashboard-copy.db")
        _clone_sqlite(db_path, cloned_db)
        context = ContextRetrievalService(cloned_db)
        feedback = MemoryFeedbackService(cloned_db)
        lifecycle = MemoryLifecycleService(cloned_db)
        controlled_cases, lifecycle_verification = _install_controlled_cases(
            context, feedback, lifecycle
        )
        dataset = _combined_dataset(base, controlled_cases)
        report = evaluate_effectiveness_dataset(context, dataset)
        report["controlled_fixture"] = {
            "environment": "temporary-copy-of-production-sqlite",
            "production_mutated": False,
            "cases": len(controlled_cases),
            "lifecycle_verification": lifecycle_verification,
        }
        return dataset, report


def main() -> int:
    args = parse_args()
    dataset, report = run_gate(
        db_path=str(Path(args.db).expanduser().resolve()),
        base_dataset_path=str(Path(args.base_dataset).expanduser().resolve()),
    )
    if args.dataset_output:
        save_json(args.dataset_output, dataset)
    if args.report_output:
        save_json(args.report_output, report)
    printable = report
    if args.summary_only:
        printable = {
            key: report[key]
            for key in (
                "version",
                "dataset_id",
                "dataset_hash",
                "metrics",
                "by_scenario",
                "quality_checks",
                "data_quality",
                "effectiveness_gate",
                "error_attribution",
                "failure_breakdown",
                "controlled_fixture",
            )
        }
    print(json.dumps(printable, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["controlled_fixture"]["lifecycle_verification"]["consistent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
