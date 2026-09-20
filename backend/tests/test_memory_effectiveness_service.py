import json
import sqlite3

import pytest

from services.context_retrieval_service import ContextRetrievalService
from services.memory_effectiveness_service import (
    DATASET_VERSION,
    MemoryEffectivenessError,
    build_provisional_dataset,
    evaluate_effectiveness_dataset,
)


def _service(tmp_path):
    return ContextRetrievalService(
        str(tmp_path / "effectiveness.db"),
        memory_root=str(tmp_path / "missing-memory"),
        workspace_root=str(tmp_path / "missing-workspace"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        fusion_mode="baseline",
    )


def test_selection_usage_outcome_and_correction_form_privacy_safe_funnel(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="user-1", display_name="测试用户")
    fact = service.upsert_fact(
        user_id="user-1",
        fact_type="preference",
        fact_key="preference.delivery",
        fact_value="先确认方案再执行。",
        importance="critical",
    )
    pack = service.retrieve(
        user_id="user-1",
        query="这是不能进入效果事件表的原始问题",
        task_id="private-task-1",
        persist=True,
    )
    source_ref = f"fact:{fact['id']}"

    first = service.record_memory_effect(
        pack_id=pack["id"],
        user_id="user-1",
        event_type="used",
        source_refs=[source_ref],
        task_id="private-task-1",
        outcome="accepted",
        metadata={"task_type": "planning", "free_text": "must-not-persist"},
        idempotency_key="effect-test-used",
    )
    repeated = service.record_memory_effect(
        pack_id=pack["id"],
        user_id="user-1",
        event_type="used",
        source_refs=[source_ref],
        task_id="private-task-1",
        outcome="accepted",
        idempotency_key="effect-test-used",
    )
    second_pack = service.retrieve(
        user_id="user-1", query="另一个上下文包", persist=True
    )
    same_caller_key_other_pack = service.record_memory_effect(
        pack_id=second_pack["id"],
        user_id="user-1",
        event_type="used",
        outcome="accepted",
        idempotency_key="effect-test-used",
    )
    service.record_memory_effect(
        pack_id=pack["id"],
        user_id="user-1",
        event_type="task_outcome",
        source_refs=[source_ref],
        outcome="success",
        idempotency_key="effect-test-outcome",
    )
    service.record_memory_effect(
        pack_id=pack["id"],
        user_id="user-1",
        event_type="correction",
        source_refs=[source_ref],
        outcome="corrected",
        reason_code="stale.preference",
        idempotency_key="effect-test-correction",
    )

    assert repeated["id"] == first["id"]
    assert same_caller_key_other_pack["id"] != first["id"]
    summary = service.memory_effectiveness_summary(user_id="user-1")
    assert summary["events"]["by_type"] == {
        "correction": 1,
        "selected": 2,
        "task_outcome": 1,
        "used": 2,
    }
    assert summary["funnel"]["selection_to_usage_rate"] == 1.0
    assert summary["outcomes"]["success_rate"] == 1.0
    assert summary["outcomes"]["correction_rate"] == 0.5
    assert summary["evidence_ready"] is True

    conn = sqlite3.connect(service.db_path)
    stored = " ".join(
        str(value)
        for row in conn.execute("SELECT * FROM memory_effect_events").fetchall()
        for value in row
    )
    metadata = json.loads(
        conn.execute(
            "SELECT metadata FROM memory_effect_events WHERE id=?", (first["id"],)
        ).fetchone()[0]
    )
    conn.close()
    assert "这是不能进入效果事件表的原始问题" not in stored
    assert "先确认方案再执行" not in stored
    assert "private-task-1" not in stored
    assert "free_text" not in metadata
    assert metadata == {"task_type": "planning"}


def test_effect_observation_rejects_cross_pack_references_and_ownership(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="owner", display_name="Owner")
    pack = service.retrieve(user_id="owner", query="empty", persist=True)

    with pytest.raises(MemoryEffectivenessError, match="outside the context pack"):
        service.record_memory_effect(
            pack_id=pack["id"],
            user_id="owner",
            event_type="used",
            source_refs=["fact:forged"],
        )
    with pytest.raises(MemoryEffectivenessError, match="another user"):
        service.record_memory_effect(
            pack_id=pack["id"],
            user_id="attacker",
            event_type="task_outcome",
            outcome="success",
        )


def test_provisional_dataset_is_reproducible_and_does_not_embed_memory_content(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="User")
    service.upsert_fact(
        user_id="1",
        fact_type="decision",
        fact_key="decision.approval",
        fact_value="敏感的原始记忆内容不应出现在数据集快照中。",
        importance="critical",
    )
    with service.connect() as conn:
        first = build_provisional_dataset(conn, owner_user_id="1", target_cases=10)
        second = build_provisional_dataset(conn, owner_user_id="1", target_cases=10)

    assert first["schema_version"] == DATASET_VERSION
    assert first["dataset_hash"] == second["dataset_hash"]
    assert first["provenance"]["contains_memory_content"] is False
    assert first["provenance"]["human_verification_required"] is True
    assert "敏感的原始记忆内容" not in json.dumps(first, ensure_ascii=False)
    assert all(case["label_status"] == "provisional" for case in first["cases"])


class _FakeContext:
    def retrieve(self, **kwargs):
        query = kwargs["query"]
        refs = []
        if query.startswith("hit"):
            refs = ["memory:expected"]
        if query.startswith("leak"):
            refs = ["memory:forbidden"]
        decision = "abstain" if query.startswith("abstain") else "supported"
        return {
            "items": [{"source_ref": ref} for ref in refs],
            "retrieval_decision": {"status": decision},
            "retrieval_health": {
                "profile": {"status": "ready"},
                "approved_memory": {"status": "ready"},
                "vector_memory": {"status": "ready"},
            },
        }


def test_baseline_attributes_retrieval_scope_and_lifecycle_failures():
    dataset = {
        "schema_version": DATASET_VERSION,
        "dataset_id": "test-dataset",
        "dataset_hash": "hash",
        "owner_user_id": "1",
        "provenance": {"contains_memory_content": False},
        "cases": [
            {
                "id": "recall-pass",
                "scenario": "recall",
                "query": "hit recall",
                "expected_source_refs": ["memory:expected"],
                "forbidden_source_refs": [],
                "importance": "critical",
                "label_status": "verified",
            },
            {
                "id": "recall-miss",
                "scenario": "recall",
                "query": "miss recall",
                "expected_source_refs": ["memory:expected"],
                "forbidden_source_refs": [],
                "importance": "high",
                "label_status": "verified",
            },
            {
                "id": "scope-leak",
                "scenario": "user_isolation",
                "query": "leak user",
                "expected_source_refs": [],
                "forbidden_source_refs": ["memory:forbidden"],
                "importance": "critical",
                "label_status": "verified",
            },
            {
                "id": "forgotten-residue",
                "scenario": "forget",
                "query": "leak forgotten",
                "expected_source_refs": [],
                "forbidden_source_refs": ["memory:forbidden"],
                "importance": "critical",
                "label_status": "verified",
            },
            {
                "id": "abstention-pass",
                "scenario": "abstention",
                "query": "abstain unknown subject",
                "expected_source_refs": [],
                "forbidden_source_refs": [],
                "importance": "normal",
                "label_status": "verified",
                "expected_decision": "abstain",
            },
        ],
    }

    report = evaluate_effectiveness_dataset(_FakeContext(), dataset)

    assert report["metrics"]["important_recall"] == 0.5
    assert report["metrics"]["cross_scope_leakage_hits"] == 1
    assert report["metrics"]["stale_recall_hits"] == 1
    assert report["metrics"]["deletion_projection_residue_hits"] == 1
    assert report["metrics"]["abstention_accuracy"] == 1.0
    assert report["metrics"]["false_supports"] == 0
    assert report["error_attribution"]["retrieval_miss"] == 1
    assert report["error_attribution"]["scope_filter_failure"] == 1
    assert report["error_attribution"]["lifecycle_filter_failure"] == 1
    assert report["data_quality"]["ready"] is False
    assert report["effectiveness_gate"]["ready"] is False
