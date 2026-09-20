#!/usr/bin/env python3
"""Run isolated update/conflict/expiry/forget lifecycle acceptance fixtures."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService
from services.memory_lifecycle_service import MemoryLifecycleService


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
        user_id="fixture-user",
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
                "confidence": 0.98,
                "agent_id": agent_id,
            }
        ],
    )[0]
    return feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="fixture-reviewer"
    )


def run_fixture() -> dict:
    with tempfile.TemporaryDirectory(prefix="memory-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        context = ContextRetrievalService(
            str(root / "fixture.db"),
            memory_root=str(root / "memory"),
            workspace_root=str(root / "agents"),
            knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        )
        context.upsert_profile(user_id="fixture-user", display_name="Fixture User")
        feedback = MemoryFeedbackService(context.db_path)
        lifecycle = MemoryLifecycleService(context.db_path)

        old = _publish(
            feedback,
            mission_id="fixture-update-v1",
            target_scope="project",
            project_id="fixture-project",
            memory_key="decision.release_gate",
            content="旧规则允许直接发布。",
        )
        current = _publish(
            feedback,
            mission_id="fixture-update-v2",
            target_scope="project",
            project_id="fixture-project",
            memory_key="decision.release_gate",
            content="新规则要求完整回归后发布。",
        )
        update_refs = {
            item["source_ref"]
            for item in context.retrieve(
                user_id="fixture-user",
                query="完整回归后发布",
                project_id="fixture-project",
                persist=False,
            )["items"]
        }
        update_passed = (
            current["published_ref"] in update_refs
            and old["published_ref"] not in update_refs
            and current["superseded_refs"] == [old["published_ref"]]
        )

        lifecycle.schedule_expiry(
            source_ref=current["published_ref"],
            user_id="fixture-user",
            valid_until="2026-01-01T00:00:00+00:00",
            actor="fixture",
        )
        expiry_results = lifecycle.expire_due(
            as_of="2026-01-02T00:00:00+00:00",
            user_id="fixture-user",
            actor="fixture",
        )
        expiry_refs = {
            item["source_ref"]
            for item in context.retrieve(
                user_id="fixture-user",
                query="完整回归后发布",
                project_id="fixture-project",
                persist=False,
            )["items"]
        }
        expiry_passed = (
            [item["source_ref"] for item in expiry_results]
            == [current["published_ref"]]
            and current["published_ref"] not in expiry_refs
        )

        forgotten = _publish(
            feedback,
            mission_id="fixture-forget",
            target_scope="agent",
            agent_id="optimus",
            memory_key="lesson.forget",
            content="这条隔离夹具记忆应该被遗忘。",
        )
        lifecycle.forget(
            source_ref=forgotten["published_ref"],
            user_id="fixture-user",
            actor="fixture",
        )
        forget_refs = {
            item["source_ref"]
            for item in context.retrieve(
                user_id="fixture-user",
                query="隔离夹具记忆",
                agent_id="optimus",
                persist=False,
            )["items"]
        }
        forget_passed = forgotten["published_ref"] not in forget_refs

        loser = context.upsert_fact(
            user_id="fixture-user",
            fact_type="decision",
            fact_key="decision.conflict",
            fact_value="冲突旧值。",
            source_ref="fixture-conflict",
        )
        winner = _publish(
            feedback,
            mission_id="fixture-conflict-winner",
            target_scope="project",
            project_id="fixture-project",
            memory_key="decision.conflict",
            content="冲突裁决后的权威值。",
        )
        resolution = lifecycle.resolve_conflict(
            winner_ref=winner["published_ref"],
            loser_ref=f"fact:{loser['id']}",
            user_id="fixture-user",
            actor="fixture",
            rationale="经审批的项目记忆更新。",
        )
        conflict_passed = (
            resolution["transition"]["to_state"] == "superseded"
            and lifecycle.history(
                source_ref=f"fact:{loser['id']}", user_id="fixture-user"
            )["record"]["replaced_by_ref"]
            == winner["published_ref"]
        )

        verification = lifecycle.verify(user_id="fixture-user")
        scenarios = {
            "update": {
                "passed": update_passed,
                "old_ref_retired": old["published_ref"] not in update_refs,
                "new_ref_recalled": current["published_ref"] in update_refs,
            },
            "conflict": {
                "passed": conflict_passed,
                "winner_ref": winner["published_ref"],
                "loser_state": resolution["transition"]["to_state"],
            },
            "expiry": {
                "passed": expiry_passed,
                "expired_count": len(expiry_results),
                "expired_ref_recalled": current["published_ref"] in expiry_refs,
            },
            "forget": {
                "passed": forget_passed,
                "forgotten_ref_recalled": forgotten["published_ref"] in forget_refs,
            },
        }
        return {
            "schema_version": "memory-lifecycle-fixture.v1",
            "environment": "isolated-temporary-sqlite",
            "mutates_production_memory": False,
            "scenarios": scenarios,
            "verification": verification,
            "passed": all(item["passed"] for item in scenarios.values())
            and verification["consistent"],
        }


def main() -> int:
    report = run_fixture()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
