from services.context_retrieval_service import ContextRetrievalService
from services.graph_memory_operations_service import GraphMemoryOperationsService
from services.memory_feedback_service import MemoryFeedbackService


def _context(tmp_path):
    service = ContextRetrievalService(
        str(tmp_path / "operations.db"),
        memory_root=str(tmp_path / "memory"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
    )
    service.upsert_profile(user_id="1", display_name="孙总")
    return service


def test_operations_reports_outbox_dead_letter_and_project_rollout_override(tmp_path):
    context = _context(tmp_path)
    context.set_graph_memory_mode(
        user_id="1", graph_mode="retrieval", updated_by="admin"
    )
    context.set_graph_memory_mode(
        user_id="1", project_id="project-1", graph_mode="disabled", updated_by="admin"
    )
    feedback = MemoryFeedbackService(context.db_path)
    candidate = feedback.create_candidates(
        user_id="1",
        mission_id="mission-ops",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_key": "ops.constraint",
                "content": "运维测试记忆。",
            }
        ],
    )[0]
    published = feedback.review_candidate(candidate["id"], decision="approve", reviewed_by="admin")
    with feedback.connect() as conn:
        conn.execute(
            "UPDATE memory_graph_outbox SET status='dead_letter' WHERE id=?",
            (published["graph_outbox_id"],),
        )

    status = GraphMemoryOperationsService(context).status(user_id="1", project_id="project-1")

    assert status["status"] == "attention"
    assert status["resolved_mode"] == "disabled"
    assert status["outbox"]["dead_letter"] == 1
    assert any(alert["code"] == "graph_sync_dead_letter" for alert in status["alerts"])
    assert context.resolve_graph_memory_mode("1", "other-project") == "retrieval"
