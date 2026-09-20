from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.context_router as router_module
from routers.auth_router import get_current_user
from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService


def _client(tmp_path, monkeypatch):
    service = ContextRetrievalService(
        str(tmp_path / "router-context.db"),
        memory_root=str(tmp_path / "memory"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        project_provider=lambda _project_id: None,
    )
    monkeypatch.setattr(router_module, "context_retrieval_service", service)
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "1",
        "username": "admin",
        "role": "admin",
    }
    return TestClient(app), service, app


def test_profile_fact_retrieval_and_pack_contract(tmp_path, monkeypatch):
    client, _service, _app = _client(tmp_path, monkeypatch)
    missing = client.get("/api/v3/context/profile/me")
    assert missing.status_code == 404

    profile = client.put(
        "/api/v3/context/profile/me",
        json={
            "display_name": "孙总",
            "preferred_name": "孙总",
            "summary": "负责智能体协作系统。",
            "work_context": {"active_workstreams": ["OpenClaw"]},
            "business_context": {"domains": ["多智能体协作"]},
            "preferences": {"language": "中文"},
            "constraints": {"approval_required": True},
        },
    )
    assert profile.status_code == 200
    assert profile.json()["user_id"] == "1"

    fact = client.post(
        "/api/v3/context/profile/me/facts",
        json={
            "fact_type": "decision",
            "fact_key": "decision.single_entry",
            "fact_value": "擎天柱是唯一任务入口。",
            "importance": "critical",
            "source_type": "migration",
            "source_ref": "test-bootstrap",
        },
    )
    assert fact.status_code == 201

    retrieved = client.post(
        "/api/v3/context/retrieve",
        json={
            "query": "智能体任务入口",
            "agent_id": "optimus",
            "purpose": "planning",
            "limit": 10,
        },
    )
    assert retrieved.status_code == 200
    pack_id = retrieved.json()["id"]
    assert pack_id.startswith("context-")
    assert any(item["item_type"] == "profile_fact" for item in retrieved.json()["items"])

    packs = client.get("/api/v3/context/packs")
    assert packs.status_code == 200
    assert packs.json()["total"] == 1
    detail = client.get(f"/api/v3/context/packs/{pack_id}")
    assert detail.status_code == 200
    assert detail.json()["user_id"] == "1"

    used = client.post(
        f"/api/v3/context/packs/{pack_id}/effect",
        json={
            "event_type": "used",
            "source_refs": [f"fact:{fact.json()['id']}"],
            "outcome": "accepted",
            "idempotency_key": "router-effect-used",
        },
    )
    assert used.status_code == 201
    outcome = client.post(
        f"/api/v3/context/packs/{pack_id}/effect",
        json={
            "event_type": "task_outcome",
            "outcome": "success",
            "idempotency_key": "router-effect-outcome",
        },
    )
    assert outcome.status_code == 201
    effectiveness = client.get("/api/v3/context/effectiveness/summary")
    assert effectiveness.status_code == 200
    assert effectiveness.json()["funnel"]["selection_to_usage_rate"] == 1.0
    assert effectiveness.json()["outcomes"]["success_rate"] == 1.0

    sources = client.get("/api/v3/context/sources")
    assert sources.status_code == 200
    assert sources.json()["total"] == 4

    health = client.get("/api/v3/context/health")
    assert health.status_code == 200
    assert health.json()["counts"]["profiles"] == 1
    assert health.json()["memory_retrieval"] == {
        "strategy_version": "hybrid-retrieval.v2",
        "fusion_version": "weighted-rrf.v1",
        "fusion_mode": "weighted_rrf",
    }

    archived = client.delete(f"/api/v3/context/profile/me/facts/{fact.json()['id']}")
    assert archived.status_code == 200
    assert client.get("/api/v3/context/profile/me").json()["facts"] == []


def test_context_pack_is_scoped_to_current_user(tmp_path, monkeypatch):
    client, service, app = _client(tmp_path, monkeypatch)
    service.upsert_profile(user_id="1", display_name="用户一")
    pack = service.retrieve(user_id="1", query="测试上下文")

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "2",
        "username": "other",
        "role": "viewer",
    }
    denied = client.get(f"/api/v3/context/packs/{pack['id']}")
    assert denied.status_code == 404
    denied_effect = client.post(
        f"/api/v3/context/packs/{pack['id']}/effect",
        json={"event_type": "task_outcome", "outcome": "success"},
    )
    assert denied_effect.status_code == 404


def test_admin_can_run_graph_memory_evaluation(tmp_path, monkeypatch):
    client, service, _app = _client(tmp_path, monkeypatch)
    service.upsert_profile(user_id="1", display_name="孙总")
    fact = service.upsert_fact(
        user_id="1",
        fact_type="decision",
        fact_key="decision.approval",
        fact_value="计划必须批准后执行。",
        importance="critical",
    )

    response = client.post(
        "/api/v3/context/evaluations/graph-memory",
        json={
            "cases": [
                {
                    "id": "approval-case",
                    "query": "计划审批",
                    "expected_source_refs": [f"fact:{fact['id']}"],
                    "task_outcomes": {"disabled": True},
                }
            ],
            "modes": ["disabled"],
            "persist": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == ""
    assert payload["summary"]["by_mode"]["disabled"]["hit_rate"] == 1.0


def test_admin_can_roll_out_graph_mode_and_inspect_operations(tmp_path, monkeypatch):
    client, service, _app = _client(tmp_path, monkeypatch)
    service.upsert_profile(user_id="1", display_name="孙总")

    configured = client.put(
        "/api/v3/context/graph-memory/rollout",
        json={"graph_mode": "disabled"},
    )
    assert configured.status_code == 200
    assert configured.json()["graph_mode"] == "disabled"

    retrieved = client.post(
        "/api/v3/context/retrieve",
        json={"query": "图谱模式", "persist": False},
    )
    assert retrieved.status_code == 200
    assert retrieved.json()["graph_mode"] == "disabled"
    assert retrieved.json()["retrieval_health"]["graph_memory"]["status"] == "disabled"

    operations = client.get("/api/v3/context/graph-memory/operations")
    assert operations.status_code == 200
    payload = operations.json()
    assert payload["resolved_mode"] == "disabled"
    assert payload["outbox"]["dead_letter"] == 0
    assert any(alert["code"] == "graph_evaluation_missing" for alert in payload["alerts"])


def test_admin_can_inspect_and_backfill_vector_memory(tmp_path, monkeypatch):
    client, service, _app = _client(tmp_path, monkeypatch)
    service.upsert_profile(user_id="1", display_name="孙总")

    operations = client.get("/api/v3/context/vector-memory/operations")
    assert operations.status_code == 200
    assert operations.json()["index"]["status"] == "not_configured"
    assert operations.json()["queue"]["pending"] == 0

    backfill = client.post("/api/v3/context/vector-memory/backfill")
    assert backfill.status_code == 200
    assert backfill.json()["approved_records_scanned"] == 0

    processed = client.post("/api/v3/context/vector-memory/process?limit=5")
    assert processed.status_code == 200
    assert processed.json()["processed"] == []


def test_admin_can_inspect_shadow_metrics(tmp_path, monkeypatch):
    client, service, _app = _client(tmp_path, monkeypatch)
    service._fusion_mode = "shadow"
    service.upsert_profile(user_id="1", display_name="孙总")
    service.retrieve(user_id="1", query="发布前必须审批")

    response = client.get(
        "/api/v3/context/vector-memory/shadow-metrics?window_hours=24"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window"]["hours"] == 24
    assert payload["samples"]["queries"] == 1
    assert payload["privacy"]["raw_query_stored"] is False
    assert payload["rollout_gate"]["promotion_ready"] is False


def test_admin_can_manage_and_run_labeled_retrieval_evaluation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MEMORY_ROLLOUT_MIN_LABELED_CASES", "1")
    client, service, _app = _client(tmp_path, monkeypatch)
    service._fusion_mode = "shadow"
    service.upsert_profile(user_id="1", display_name="孙总")

    created = client.post(
        "/api/v3/context/evaluations/retrieval/cases",
        json={
            "query": "发布审批门禁",
            "forbidden_source_refs": ["memory:forbidden-release-rule"],
            "tags": ["safety"],
            "review_checks": {
                "query_rewritten": True,
                "scope_verified": True,
                "labels_verified": True,
            },
            "reviewer_confidence": "high",
            "status": "active",
        },
    )
    assert created.status_code == 201
    assert created.json()["version"] == 1
    assert created.json()["reviewed_by"] == "admin"

    cases = client.get("/api/v3/context/evaluations/retrieval/cases?status=active")
    assert cases.status_code == 200
    assert cases.json()["total"] == 1

    run = client.post(
        "/api/v3/context/evaluations/retrieval/run",
        json={"case_ids": [created.json()["id"]]},
    )
    assert run.status_code == 200
    assert run.json()["case_count"] == 1
    assert run.json()["status"] == "blocked"
    assert run.json()["assessment"]["checks"]["retrieval_channels_healthy"] is False

    latest = client.get("/api/v3/context/evaluations/retrieval/latest")
    assert latest.status_code == 200
    assert latest.json()["run"]["id"] == run.json()["id"]

    gate = client.get("/api/v3/context/vector-memory/rollout-gate?window_hours=24")
    assert gate.status_code == 200
    assert gate.json()["promotion_ready"] is False
    assert gate.json()["automatic_switch_performed"] is False


def test_admin_can_generate_review_drafts_from_approved_memories(
    tmp_path, monkeypatch
):
    client, service, _app = _client(tmp_path, monkeypatch)
    service.upsert_profile(user_id="1", display_name="孙总")
    feedback = MemoryFeedbackService(service.db_path)
    candidate = feedback.create_candidates(
        user_id="1",
        mission_id="mission-router-draft",
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

    generated = client.post(
        "/api/v3/context/evaluations/retrieval/cases/generate-drafts"
    )
    repeated = client.post(
        "/api/v3/context/evaluations/retrieval/cases/generate-drafts"
    )
    variants = client.post(
        "/api/v3/context/evaluations/retrieval/cases/generate-variants"
    )
    coverage = client.get("/api/v3/context/evaluations/retrieval/coverage")
    review_queue = client.get("/api/v3/context/evaluations/retrieval/review-queue")
    batch = client.post(
        "/api/v3/context/evaluations/retrieval/batches",
        json={"target_count": 5, "name": "首批人工审核"},
    )
    latest_batch = client.get(
        "/api/v3/context/evaluations/retrieval/batches/latest"
    )
    proposed = client.put(
        f"/api/v3/context/evaluations/retrieval/batches/{batch.json()['id']}/proposals",
        json={
            "proposals": [
                {
                    "case_id": generated.json()["created"][0]["id"],
                    "suggested_query": "上线前要完成哪些发布审核？",
                    "suggested_forbidden_source_refs": [],
                    "rationale": "把内部标题改成真实业务问法。",
                }
            ]
        },
    )

    assert generated.status_code == 200
    assert generated.json()["drafts_created"] == 1
    assert generated.json()["automatic_activation"] is False
    assert generated.json()["created"][0]["status"] == "draft"
    assert generated.json()["created"][0]["source_memory_ref"] == published[
        "published_ref"
    ]
    assert repeated.status_code == 200
    assert repeated.json()["drafts_created"] == 0
    assert repeated.json()["drafts_skipped"] == 1
    assert variants.status_code == 200
    assert variants.json()["drafts_created"] == 4
    assert variants.json()["automatic_activation"] is False
    assert coverage.status_code == 200
    assert coverage.json()["approved_sources"] == 1
    assert coverage.json()["cases_total"] == 5
    assert coverage.json()["by_status"]["active"] == 0
    assert coverage.json()["audit_events"] == 5
    assert review_queue.status_code == 200
    assert review_queue.json()["source_count"] == 1
    assert review_queue.json()["sources"][0]["content"] == "发布前必须完成回归测试。"
    case_id = generated.json()["created"][0]["id"]
    events = client.get(
        f"/api/v3/context/evaluations/retrieval/cases/{case_id}/events"
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["event_type"] == "created"
    assert batch.status_code == 201
    assert batch.json()["selected_cases"] == 5
    assert batch.json()["active_cases"] == 0
    assert batch.json()["automatic_activation"] is False
    assert latest_batch.status_code == 200
    assert latest_batch.json()["batch"]["id"] == batch.json()["id"]
    assert proposed.status_code == 200
    assert proposed.json()["proposal_count"] == 1
    assert proposed.json()["review_plan"][0]["proposal"]["status"] == "pending_human_review"
    assert generated.json()["created"][0]["status"] == "draft"
