import json

import pytest

from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService
from services.memory_lifecycle_service import (
    MemoryLifecycleError,
    MemoryLifecycleService,
)


def _services(tmp_path):
    context = ContextRetrievalService(
        str(tmp_path / "lifecycle.db"),
        memory_root=str(tmp_path / "memory"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
    )
    context.upsert_profile(user_id="user-1", display_name="Lifecycle User")
    feedback = MemoryFeedbackService(context.db_path)
    lifecycle = MemoryLifecycleService(context.db_path)
    return context, feedback, lifecycle


def _publish(
    feedback,
    *,
    mission_id,
    target_scope,
    memory_key,
    content,
    project_id="",
    agent_id="optimus",
):
    candidate = feedback.create_candidates(
        user_id="user-1",
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
        candidate["id"], decision="approve", reviewed_by="lifecycle-test"
    )


def test_controlled_update_expiry_forget_and_conflict_lifecycle(tmp_path):
    context, feedback, lifecycle = _services(tmp_path)

    first = _publish(
        feedback,
        mission_id="mission-update-v1",
        target_scope="project",
        project_id="project-1",
        memory_key="decision.release_gate",
        content="旧规则：允许直接发布。",
    )
    second = _publish(
        feedback,
        mission_id="mission-update-v2",
        target_scope="project",
        project_id="project-1",
        memory_key="decision.release_gate",
        content="新规则：发布前必须通过完整回归。",
    )

    assert first["published_ref"] != second["published_ref"]
    assert second["superseded_refs"] == [first["published_ref"]]
    old_history = lifecycle.history(
        source_ref=first["published_ref"], user_id="user-1"
    )
    new_history = lifecycle.history(
        source_ref=second["published_ref"], user_id="user-1"
    )
    assert old_history["record"]["state"] == "superseded"
    assert old_history["record"]["replaced_by_ref"] == second["published_ref"]
    assert new_history["record"]["version"] == 2
    assert new_history["record"]["supersedes_ref"] == first["published_ref"]
    assert [event["to_state"] for event in old_history["events"]] == [
        "active",
        "superseded",
    ]

    retrieved = context.retrieve(
        user_id="user-1",
        query="发布前完整回归",
        project_id="project-1",
        agent_id="optimus",
        persist=False,
    )
    refs = [item["source_ref"] for item in retrieved["items"]]
    assert second["published_ref"] in refs
    assert first["published_ref"] not in refs

    lifecycle.schedule_expiry(
        source_ref=second["published_ref"],
        user_id="user-1",
        valid_until="2026-01-01T00:00:00+00:00",
        actor="lifecycle-test",
    )
    expired = lifecycle.expire_due(
        as_of="2026-01-02T00:00:00+00:00", user_id="user-1"
    )
    assert [item["source_ref"] for item in expired] == [second["published_ref"]]
    assert lifecycle.history(
        source_ref=second["published_ref"], user_id="user-1"
    )["record"]["state"] == "expired"

    forgotten = _publish(
        feedback,
        mission_id="mission-forget",
        target_scope="agent",
        agent_id="optimus",
        memory_key="lesson.private_token",
        content="这条受控夹具记忆必须被遗忘。",
    )
    forgot = lifecycle.forget(
        source_ref=forgotten["published_ref"],
        user_id="user-1",
        actor="lifecycle-test",
    )
    assert forgot["to_state"] == "tombstoned"

    loser = context.upsert_fact(
        user_id="user-1",
        fact_type="decision",
        fact_key="decision.conflict",
        fact_value="冲突旧值。",
        source_ref="controlled-conflict",
    )
    winner = _publish(
        feedback,
        mission_id="mission-conflict-winner",
        target_scope="project",
        project_id="project-1",
        memory_key="decision.conflict",
        content="冲突裁决后的权威值。",
    )
    resolution = lifecycle.resolve_conflict(
        winner_ref=winner["published_ref"],
        loser_ref=f"fact:{loser['id']}",
        user_id="user-1",
        actor="lifecycle-test",
        rationale="项目审批记录比旧档案事实更新。",
    )
    assert resolution["transition"]["to_state"] == "superseded"

    after = context.retrieve(
        user_id="user-1",
        query="旧规则 直接发布 私有夹具 冲突旧值",
        project_id="project-1",
        agent_id="optimus",
        persist=False,
    )
    after_refs = {item["source_ref"] for item in after["items"]}
    assert first["published_ref"] not in after_refs
    assert second["published_ref"] not in after_refs
    assert forgotten["published_ref"] not in after_refs
    assert f"fact:{loser['id']}" not in after_refs

    with feedback.connect() as conn:
        first_delete = conn.execute(
            """
            SELECT status FROM memory_vector_index_jobs
            WHERE source_ref=? AND operation='delete'
            """,
            (first["published_ref"],),
        ).fetchone()
        retired_payload = conn.execute(
            """
            SELECT payload FROM memory_graph_outbox
            WHERE aggregate_id=? AND event_type='memory.superseded'
            """,
            (first["published_ref"].split(":", 1)[1],),
        ).fetchone()
    assert first_delete["status"] == "pending"
    assert json.loads(retired_payload["payload"])["replaced_by_ref"] == second[
        "published_ref"
    ]
    assert lifecycle.verify(user_id="user-1") == {
        "consistent": True,
        "records_checked": 5,
        "violations": [],
    }


def test_lifecycle_rejects_cross_user_and_invalid_transition(tmp_path):
    context, feedback, lifecycle = _services(tmp_path)
    published = _publish(
        feedback,
        mission_id="mission-transition-guard",
        target_scope="profile",
        memory_key="constraint.guard",
        content="受保护的生命周期状态。",
    )

    with pytest.raises(MemoryLifecycleError, match="another user"):
        lifecycle.forget(
            source_ref=published["published_ref"],
            user_id="user-2",
            actor="lifecycle-test",
        )

    lifecycle.forget(
        source_ref=published["published_ref"],
        user_id="user-1",
        actor="lifecycle-test",
    )
    with pytest.raises(MemoryLifecycleError, match="invalid lifecycle transition"):
        lifecycle.transition(
            source_ref=published["published_ref"],
            user_id="user-1",
            to_state="active",
            actor="lifecycle-test",
            reason_code="illegal_reactivation",
        )
