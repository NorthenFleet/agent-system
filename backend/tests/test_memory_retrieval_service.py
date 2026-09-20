import json
from pathlib import Path

import pytest

from services.memory_retrieval_service import (
    HybridFusionConfig,
    MemoryCandidate,
    RetrievalScope,
    assess_retrieval_rollout,
    build_retrieval_strategy,
    compare_rankings,
    context_item,
    evaluate_retrieval_cases,
    rank_hybrid_items,
)


def test_memory_candidate_contract_is_context_pack_compatible():
    candidate = MemoryCandidate(
        source_type="project",
        source_id="source-approved-memory",
        source_ref="project-memory:decision-1",
        title="审批规则",
        content="计划必须审批后执行。",
        final_score=0.94,
        confidence=0.98,
        channel="lexical",
        scope=RetrievalScope(user_id="1", project_id="project-1", visibility="project"),
        channel_scores={"lexical": 0.82},
        authority_score=0.98,
        importance="critical",
    )

    item = candidate.to_context_item()

    assert item["item_type"] == "project"
    assert item["score"] == 0.94
    retrieval = item["metadata"]["retrieval"]
    assert retrieval["contract_version"] == "memory-candidate.v1"
    assert retrieval["primary_channel"] == "lexical"
    assert retrieval["scores"] == {"lexical": 0.82, "final": 0.94}
    assert retrieval["scope"]["project_id"] == "project-1"
    assert len(retrieval["content_hash"]) == 64


def test_context_item_records_graph_and_lexical_channels():
    graph = context_item(
        item_type="graph_memory",
        source_id="source-graph-memory",
        source_ref="graph:node-1",
        title="关系记忆",
        content="该决策适用于任务规划。",
        score=0.86,
        confidence=0.9,
        metadata={"graph_score": 0.92, "authority": "approved_projection"},
    )
    lexical = context_item(
        item_type="knowledge",
        source_id="source-obsidian",
        source_ref="knowledge:doc-1",
        title="知识资料",
        content="Context Pack 保存检索快照。",
        score=0.72,
        confidence=0.9,
        metadata={},
    )

    assert graph["metadata"]["retrieval"]["scores"]["graph"] == 0.92
    assert lexical["metadata"]["retrieval"]["primary_channel"] == "lexical"


def test_strategy_exposes_vector_gap_without_marking_it_ready():
    item = context_item(
        item_type="profile_fact",
        source_id="source-profile",
        source_ref="fact:1",
        title="审批",
        content="必须审批。",
        score=0.99,
        confidence=1.0,
        metadata={},
    )
    strategy = build_retrieval_strategy(
        {
            "graph_memory": {"status": "disabled"},
            "vector_memory": {"status": "not_configured"},
        },
        [item],
    )

    assert strategy["mode"] == "structured"
    assert strategy["channels"]["vector"] == {
        "status": "not_configured",
        "selected": 0,
    }


def test_weighted_rrf_rewards_cross_channel_corroboration():
    lexical = context_item(
        item_type="project_memory",
        source_id="source-approved-memory",
        source_ref="project-memory:shared",
        title="发布门禁",
        content="发布前必须通过回归测试。",
        score=0.66,
        confidence=0.95,
        metadata={"project_id": "project-1", "importance": "critical"},
    )
    vector = context_item(
        item_type="project_memory",
        source_id="source-approved-memory-vector",
        source_ref="project-memory:shared",
        title="发布门禁",
        content="发布前必须通过回归测试。",
        score=0.76,
        confidence=0.95,
        metadata={"project_id": "project-1", "importance": "critical"},
    )
    graph = context_item(
        item_type="graph_memory",
        source_id="source-graph-memory",
        source_ref="graph:single-high-score",
        title="单通道关系",
        content="可能相关的图谱关系。",
        score=0.95,
        confidence=0.8,
        metadata={"graph_score": 0.95, "authority": "inferred"},
    )

    baseline, _ = rank_hybrid_items(
        [lexical, vector, graph], config=HybridFusionConfig(mode="baseline")
    )
    fused, diagnostics = rank_hybrid_items(
        [lexical, vector, graph], config=HybridFusionConfig(mode="weighted_rrf")
    )

    assert baseline[0]["source_ref"] == "graph:single-high-score"
    assert fused[0]["source_ref"] == "project-memory:shared"
    retrieval = fused[0]["metadata"]["retrieval"]
    assert retrieval["channels"] == ["lexical", "vector"]
    assert retrieval["fusion"]["channel_ranks"] == {"lexical": 1, "vector": 1}
    assert retrieval["fusion"]["strategy"] == "weighted-rrf.v1"
    assert diagnostics["multi_channel_candidates"] == 1

    comparison = compare_rankings(baseline, fused, k=2)
    assert comparison["top1_changed"] is True
    assert comparison["overlap"] == 2


def test_phase1_baseline_dataset_and_metrics_are_reproducible():
    dataset_path = Path(__file__).parents[1] / "evals" / "memory_retrieval_phase1.json"
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    returned = {
        "exact-policy-keyword": ["fact:approval-gate"],
        "exact-technical-term": ["knowledge:context-pack"],
        "cross-profile-isolation": [],
        "superseded-memory-filter": [],
    }

    metrics = evaluate_retrieval_cases(
        payload["cases"],
        lambda case: returned[case["id"]],
        k=10,
    )

    assert metrics["cases"] == 4
    assert metrics["positive_cases"] == 2
    assert metrics["recall_at_k"] == 1.0
    assert metrics["item_recall_at_k"] == 1.0
    assert metrics["mrr_at_k"] == pytest.approx(1.0)
    assert metrics["ndcg_at_k"] == pytest.approx(1.0)
    assert metrics["forbidden_hits"] == 0


def test_rollout_gate_blocks_security_or_recall_regression():
    baseline = {
        "recall_at_k": 0.9,
        "item_recall_at_k": 0.85,
        "mrr_at_k": 0.8,
        "ndcg_at_k": 0.82,
        "forbidden_hits": 0,
    }
    improved = {
        "recall_at_k": 0.92,
        "item_recall_at_k": 0.9,
        "mrr_at_k": 0.83,
        "ndcg_at_k": 0.86,
        "forbidden_hits": 0,
    }
    unsafe = {**improved, "forbidden_hits": 1}

    assert assess_retrieval_rollout(baseline, improved)["passed"] is True
    blocked = assess_retrieval_rollout(baseline, unsafe)
    assert blocked["passed"] is False
    assert blocked["checks"]["forbidden_hits_non_increasing"] is False
