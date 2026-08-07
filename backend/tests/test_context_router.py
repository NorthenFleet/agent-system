from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.context_router as router_module
from routers.auth_router import get_current_user
from services.context_retrieval_service import ContextRetrievalService


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

    sources = client.get("/api/v3/context/sources")
    assert sources.status_code == 200
    assert sources.json()["total"] == 4

    health = client.get("/api/v3/context/health")
    assert health.status_code == 200
    assert health.json()["counts"]["profiles"] == 1

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
