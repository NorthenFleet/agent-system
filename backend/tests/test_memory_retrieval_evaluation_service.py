import sqlite3

import pytest

from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService
from services.memory_retrieval_evaluation_service import (
    MemoryRetrievalEvaluationError,
    MemoryRetrievalEvaluationService,
)


class FakeContextService:
    _fusion_mode = "shadow"

    def __init__(self, db_path, *, unsafe=False):
        self.db_path = str(db_path)
        self.unsafe = unsafe
        self.retrieval_users = []

    def retrieve(self, **kwargs):
        self.retrieval_users.append(kwargs["user_id"])
        expected_ref = f"memory:{kwargs['query']}"
        candidate_refs = [expected_ref]
        if self.unsafe:
            candidate_refs.insert(0, "memory:forbidden")
        return {
            "retrieval_health": {
                "vector_memory": {
                    "status": "ready",
                    "model": "test-embedding-v1",
                },
                "hybrid_fusion": {
                    "served_strategy": "score-sort-baseline",
                    "candidate_strategy": "weighted-rrf.v1",
                    "comparison": {
                        "baseline_refs": [],
                        "candidate_refs": candidate_refs,
                    },
                },
            }
        }

    def retrieval_shadow_metrics(self, *, window_hours):
        return {
            "window": {"hours": window_hours},
            "rollout_gate": {
                "online_observation_passed": True,
                "blockers": ["offline_labeled_evaluation"],
            },
        }


def _case(query, *, forbidden=None, notes="", subject_user_id=""):
    return {
        "subject_user_id": subject_user_id,
        "query": query,
        "project_id": "project-1",
        "agent_id": "optimus",
        "limit": 10,
        "expected_source_refs": [f"memory:{query}"],
        "forbidden_source_refs": list(forbidden or []),
        "tags": ["release-gate"],
        "notes": notes,
        "review_checks": {
            "query_rewritten": True,
            "scope_verified": True,
            "labels_verified": True,
        },
        "reviewer_confidence": "high",
        "status": "active",
    }


def test_labeled_evaluation_can_open_gate_and_label_change_makes_run_stale(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MEMORY_ROLLOUT_MIN_LABELED_CASES", "2")
    context = FakeContextService(tmp_path / "evaluation.db")
    evaluator = MemoryRetrievalEvaluationService(context, context.db_path)
    first = evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        payload=_case("approval"),
    )
    evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        payload=_case("release", subject_user_id="user-2"),
    )

    run = evaluator.run(owner_user_id="user-1", requested_by="admin")
    gate = evaluator.rollout_gate(owner_user_id="user-1", window_hours=24)

    assert run["status"] == "passed"
    assert run["baseline"]["recall_at_k"] == 0.0
    assert run["candidate"]["recall_at_k"] == 1.0
    assert run["candidate"]["forbidden_hits"] == 0
    assert run["assessment"]["passed"] is True
    assert sorted(context.retrieval_users) == ["user-1", "user-2"]
    assert gate["promotion_ready"] is True
    assert gate["automatic_switch_performed"] is False

    updated_payload = _case("approval", notes="human label reviewed again")
    updated = evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="reviewer-2",
        payload=updated_payload,
        case_id=first["id"],
    )
    stale_gate = evaluator.rollout_gate(owner_user_id="user-1")

    assert updated["version"] == 2
    assert updated["reviewed_by"] == "reviewer-2"
    assert stale_gate["promotion_ready"] is False
    assert stale_gate["offline"]["checks"]["dataset_current"] is False
    assert "offline:dataset_current" in stale_gate["blockers"]


def test_forbidden_candidate_hit_blocks_offline_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_ROLLOUT_MIN_LABELED_CASES", "1")
    context = FakeContextService(tmp_path / "unsafe.db", unsafe=True)
    evaluator = MemoryRetrievalEvaluationService(context, context.db_path)
    evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        payload=_case("unsafe", forbidden=["memory:forbidden"]),
    )

    run = evaluator.run(owner_user_id="user-1", requested_by="admin")
    gate = evaluator.rollout_gate(owner_user_id="user-1")

    assert run["candidate"]["forbidden_hits"] == 1
    assert run["assessment"]["checks"]["candidate_forbidden_hits_zero"] is False
    assert run["status"] == "blocked"
    assert gate["promotion_ready"] is False
    assert gate["offline"]["checks"]["quality_gate_passed"] is False


def test_approved_memories_generate_idempotent_unreviewed_drafts(tmp_path):
    database = str(tmp_path / "drafts.db")
    context = ContextRetrievalService(
        database,
        memory_root=str(tmp_path / "memory"),
        workspace_root=str(tmp_path / "workspace"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
    )
    context.upsert_profile(user_id="user-1", display_name="孙总")
    feedback = MemoryFeedbackService(database)
    candidate = feedback.create_candidates(
        user_id="user-1",
        mission_id="mission-draft-source",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "decision",
                "memory_key": "decision.release_gate",
                "title": "发布门禁",
                "content": "发布前必须完成回归测试。",
            }
        ],
    )[0]
    published = feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="admin"
    )
    evaluator = MemoryRetrievalEvaluationService(context, database)

    first = evaluator.generate_drafts_from_approved_memories(
        owner_user_id="user-1", requested_by="admin"
    )
    second = evaluator.generate_drafts_from_approved_memories(
        owner_user_id="user-1", requested_by="admin"
    )
    variants = evaluator.generate_variant_drafts(
        owner_user_id="user-1", requested_by="admin"
    )
    repeated_variants = evaluator.generate_variant_drafts(
        owner_user_id="user-1", requested_by="admin"
    )
    drafts = evaluator.list_cases("user-1", status="draft")
    coverage = evaluator.coverage("user-1")
    batch = evaluator.create_review_batch(
        owner_user_id="user-1", requested_by="admin", target_count=5
    )
    repeated_batch = evaluator.create_review_batch(
        owner_user_id="user-1", requested_by="admin", target_count=5
    )

    assert first["approved_memories_scanned"] == 1
    assert first["drafts_created"] == 1
    assert first["automatic_activation"] is False
    assert second["drafts_created"] == 0
    assert second["drafts_skipped"] == 1
    assert variants["drafts_created"] == 4
    assert variants["automatic_activation"] is False
    assert repeated_variants["drafts_created"] == 0
    assert repeated_variants["drafts_skipped"] == 4
    assert len(drafts) == 5
    canonical = next(case for case in drafts if case["variant_key"] == "canonical")
    assert canonical["origin"] == "approved_memory_draft"
    assert {case["variant_key"] for case in drafts} == {
        "canonical",
        "natural",
        "terse",
        "contextual",
        "boundary",
    }
    assert all(case["source_memory_ref"] == published["published_ref"] for case in drafts)
    assert all(case["expected_source_refs"] == [published["published_ref"]] for case in drafts)
    assert all(case["status"] == "draft" for case in drafts)
    assert coverage["approved_sources"] == 1
    assert coverage["sources_with_cases"] == 1
    assert coverage["cases_total"] == 5
    assert coverage["by_status"]["active"] == 0
    assert coverage["by_variant"]["natural"] == 1
    assert coverage["by_confidence"]["unreviewed"] == 5
    assert coverage["audit_events"] == 5
    assert coverage["remaining_active_cases"] == 30
    assert batch["selected_cases"] == 5
    assert batch["active_cases"] == 0
    assert batch["remaining_cases"] == 5
    assert batch["automatic_review"] is False
    assert batch["automatic_activation"] is False
    assert batch["proposal_count"] == 0
    assert batch["by_variant"] == {
        "boundary": 1,
        "canonical": 1,
        "contextual": 1,
        "natural": 1,
        "terse": 1,
    }
    assert repeated_batch["id"] == batch["id"]
    canonical_before = next(
        case for case in drafts if case["variant_key"] == "canonical"
    )
    proposed_batch = evaluator.set_review_proposals(
        owner_user_id="user-1",
        batch_id=batch["id"],
        proposed_by="assistant",
        proposals=[
            {
                "case_id": canonical_before["id"],
                "suggested_query": "发布前需要经过哪些人工审核？",
                "suggested_forbidden_source_refs": [],
                "rationale": "将内部标题改写为真实业务问法。",
            }
        ],
    )
    canonical_after = next(
        case
        for case in evaluator.list_cases("user-1", status="draft")
        if case["id"] == canonical_before["id"]
    )
    proposal = next(
        item["proposal"]
        for item in proposed_batch["review_plan"]
        if item["case_id"] == canonical_before["id"]
    )
    assert proposed_batch["proposal_count"] == 1
    assert proposal["status"] == "pending_human_review"
    assert proposal["proposal_hash"]
    assert canonical_after["query"] == canonical_before["query"]
    assert canonical_after["status"] == "draft"
    assert canonical_after["version"] == canonical_before["version"]
    assert not any(canonical_after["review_checks"].values())
    with pytest.raises(MemoryRetrievalEvaluationError, match="unknown forbidden"):
        evaluator.set_review_proposals(
            owner_user_id="user-1",
            batch_id=batch["id"],
            proposed_by="assistant",
            proposals=[
                {
                    "case_id": canonical_before["id"],
                    "suggested_query": "发布门禁如何执行？",
                    "suggested_forbidden_source_refs": ["memory:unknown"],
                    "rationale": "验证未知来源会被拒绝。",
                }
            ],
        )
    with pytest.raises(MemoryRetrievalEvaluationError, match="no active"):
        evaluator.run(owner_user_id="user-1", requested_by="admin")

    generated = next(case for case in drafts if case["variant_key"] == "natural")
    activation = {
        **generated,
        "status": "active",
        "review_checks": {},
    }
    with pytest.raises(MemoryRetrievalEvaluationError, match="review checks"):
        evaluator.upsert_case(
            owner_user_id="user-1",
            reviewed_by="admin",
            case_id=generated["id"],
            payload=activation,
        )

    activation["origin"] = "manual"
    activation["source_memory_ref"] = "memory:attempted-provenance-bypass"
    activation["review_checks"] = {
        "query_rewritten": True,
        "scope_verified": True,
        "labels_verified": True,
    }
    activation["reviewer_confidence"] = "high"
    activated = evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        case_id=generated["id"],
        payload=activation,
    )
    assert activated["status"] == "active"
    assert activated["origin"] == "approved_memory_variant_draft"
    assert activated["source_memory_ref"] == published["published_ref"]
    assert activated["source_snapshot_hash"]
    assert evaluator.coverage("user-1")["sources_with_active_cases"] == 1
    progressed_batch = evaluator.latest_review_batch("user-1")
    assert progressed_batch["active_cases"] == 1
    assert progressed_batch["remaining_cases"] == 4
    assert progressed_batch["next_case"]["id"] != generated["id"]
    queue = evaluator.review_queue("user-1")
    assert queue["source_count"] == 1
    assert queue["sources"][0]["content"] == "发布前必须完成回归测试。"
    assert queue["stale_case_ids"] == []
    events = evaluator.list_case_events("user-1", generated["id"])
    assert [event["event_type"] for event in events] == [
        "status:draft->active",
        "created",
    ]

    with sqlite3.connect(database) as conn:
        conn.execute(
            "UPDATE profile_facts SET fact_value=?, updated_at=? WHERE id=?",
            ("发布前必须完成完整回归测试。", "2026-09-17T12:00:00Z", published["published_ref"].removeprefix("fact:")),
        )
    drifted = evaluator.review_queue("user-1")
    assert generated["id"] in drifted["stale_case_ids"]
    assert evaluator.coverage("user-1")["source_drift_cases"] == 1
    with pytest.raises(MemoryRetrievalEvaluationError, match="source evidence is stale"):
        evaluator.run(owner_user_id="user-1", requested_by="admin")
    reset = evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        case_id=generated["id"],
        payload={**activated, "status": "draft"},
    )
    assert reset["status"] == "draft"
    assert reset["reviewer_confidence"] == "unreviewed"
    assert not any(reset["review_checks"].values())
    assert reset["source_snapshot_hash"] != activated["source_snapshot_hash"]
    assert generated["id"] not in evaluator.review_queue("user-1")["stale_case_ids"]


def test_phase7_schema_migrates_to_multiple_query_variants(tmp_path):
    database = str(tmp_path / "phase7.db")
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE memory_retrieval_eval_cases (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                subject_user_id TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL DEFAULT 'manual',
                source_memory_ref TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                agent_id TEXT NOT NULL DEFAULT 'optimus',
                result_limit INTEGER NOT NULL DEFAULT 10,
                expected_source_refs TEXT NOT NULL DEFAULT '[]',
                forbidden_source_refs TEXT NOT NULL DEFAULT '[]',
                tags TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                version INTEGER NOT NULL DEFAULT 1,
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX idx_memory_eval_case_source
            ON memory_retrieval_eval_cases(owner_user_id, source_memory_ref)
            WHERE source_memory_ref <> '';
            """
        )
    context = FakeContextService(database)
    evaluator = MemoryRetrievalEvaluationService(context, database)
    base = {
        "subject_user_id": "user-1",
        "origin": "manual",
        "source_memory_ref": "memory:shared",
        "query": "共享记忆怎么处理？",
        "expected_source_refs": ["memory:shared"],
        "forbidden_source_refs": [],
        "tags": [],
        "notes": "",
        "review_checks": {},
        "status": "draft",
    }

    first = evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        payload={**base, "variant_key": "natural"},
    )
    second = evaluator.upsert_case(
        owner_user_id="user-1",
        reviewed_by="admin",
        payload={**base, "variant_key": "boundary", "query": "共享记忆有什么限制？"},
    )

    assert first["variant_key"] == "natural"
    assert second["variant_key"] == "boundary"
    with sqlite3.connect(database) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memory_retrieval_eval_cases)")
        }
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(memory_retrieval_eval_cases)")
        }
    assert {
        "variant_key",
        "review_checks",
        "reviewer_confidence",
        "source_snapshot_hash",
    } <= columns
    assert "idx_memory_eval_case_source" not in indexes
    assert "idx_memory_eval_case_variant" in indexes
