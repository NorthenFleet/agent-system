import sqlite3

import pytest

from services.context_retrieval_service import ContextRetrievalService
from services.graph_memory_evaluation_service import (
    GraphMemoryEvaluationError,
    GraphMemoryEvaluationService,
)


class FakeGraphMemoryClient:
    def retrieve_context(self, **_kwargs):
        return {
            "items": [
                {
                    "node_id": "node-1",
                    "source_ref": "graph:approval-context",
                    "title": "审批图谱关联",
                    "content": "批准后才可执行项目任务。",
                    "authority": "approved_projection",
                    "visibility": "project",
                    "memory_key": "decision.approval_graph",
                    "score": 0.9,
                    "confidence": 0.9,
                    "freshness_score": 0.8,
                    "relation_relevance": 0.9,
                    "relations": [{"type": "APPLIES_TO", "label": "任务规划", "weight": 0.95}],
                }
            ],
            "health": {"status": "ready", "engine": "graph-memory", "results": 1},
        }

    def health(self):
        return {"status": "configured", "engine": "graph-memory"}


def _service(tmp_path):
    context = ContextRetrievalService(
        str(tmp_path / "evaluation.db"),
        memory_root=str(tmp_path / "memory"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        project_provider=lambda project_id: {"id": project_id, "name": "测试项目"},
        graph_memory_client_instance=FakeGraphMemoryClient(),
    )
    context.upsert_profile(user_id="1", display_name="孙总")
    return context


def test_evaluation_compares_three_graph_modes_and_persists_results(tmp_path):
    context = _service(tmp_path)
    evaluator = GraphMemoryEvaluationService(context, context.db_path)

    report = evaluator.evaluate(
        user_id="1",
        requested_by="admin",
        cases=[
            {
                "id": "approval-case",
                "query": "审批后执行",
                "project_id": "project-1",
                "expected_source_refs": ["graph:approval-context"],
                "forbidden_source_refs": ["memory:unsafe"],
                "task_outcomes": {"disabled": False, "retrieval": True, "rerank": True},
            }
        ],
    )

    assert report["id"].startswith("graph-eval-")
    metrics = report["summary"]["by_mode"]
    assert metrics["disabled"]["hit_rate"] == 0.0
    assert metrics["retrieval"]["hit_rate"] == 1.0
    assert metrics["rerank"]["hit_rate"] == 1.0
    assert metrics["disabled"]["task_completion_rate"] == 0.0
    assert metrics["rerank"]["task_completion_rate"] == 1.0
    assert metrics["rerank"]["citation_error_rate"] == 0.0
    assert metrics["rerank"]["average_estimated_tokens"] > 0

    conn = sqlite3.connect(context.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM graph_memory_evaluation_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM graph_memory_evaluation_cases").fetchone()[0] == 3
    finally:
        conn.close()


def test_evaluation_rejects_invalid_mode_and_empty_cases(tmp_path):
    context = _service(tmp_path)
    evaluator = GraphMemoryEvaluationService(context, context.db_path)

    with pytest.raises(GraphMemoryEvaluationError, match="at least one"):
        evaluator.evaluate(user_id="1", requested_by="admin", cases=[])
    with pytest.raises(GraphMemoryEvaluationError, match="modes"):
        evaluator.evaluate(
            user_id="1",
            requested_by="admin",
            cases=[{"query": "审批"}],
            modes=["unknown"],
        )
