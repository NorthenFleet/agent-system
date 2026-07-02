import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge_manager import knowledge_manager
from main import app
from project_manager import project_manager


@pytest.fixture
def knowledge_index(tmp_path):
    index_path = tmp_path / "graph-index.json"
    index = {
        "build_time": "2026-06-27T00:00:00",
        "stats": {"nodes": 3, "edges": 2, "entity_types": {"概念": 1, "项目": 1, "文档": 1}},
        "entities": {
            "AI开发系统三层架构": {
                "id": "03-概念库-Concepts/AI开发系统三层架构.md",
                "type": "概念",
                "path": str(tmp_path / "AI开发系统三层架构.md"),
            },
            "团队信息看板": {
                "id": "06-项目库-Projects/AI开发系统/信息看板.md",
                "type": "项目",
                "path": str(tmp_path / "信息看板.md"),
            },
        },
        "relations": [
            {
                "source": "06-项目库-Projects/AI开发系统/信息看板.md",
                "target": "03-概念库-Concepts/AI开发系统三层架构.md",
                "relation": "项目基于概念",
                "source_file": str(tmp_path / "信息看板.md"),
            },
            {
                "source": "06-项目库-Projects/AI开发系统/信息看板.md",
                "target": "_unlinked/任务看板",
                "relation": "关联",
                "source_file": str(tmp_path / "信息看板.md"),
            },
        ],
        "top_concepts": [
            {
                "id": "03-概念库-Concepts/AI开发系统三层架构.md",
                "title": "AI开发系统三层架构",
                "connections": 12,
            }
        ],
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    old_vault = knowledge_manager.vault_path
    old_index = knowledge_manager.index_path
    knowledge_manager.configure(vault_path=str(tmp_path), index_path=str(index_path))
    yield index_path
    knowledge_manager.configure(vault_path=str(old_vault), index_path=str(old_index))


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_knowledge_stats_search_and_neighbors(client, knowledge_index):
    stats = (await client.get("/api/knowledge/stats")).json()
    assert stats["nodes"] == 3
    assert stats["available"] is True

    search = (await client.get("/api/knowledge/search", params={"q": "AI开发"})).json()
    assert search["total"] >= 1
    assert search["nodes"][0]["title"] == "AI开发系统三层架构"

    neighbors = (
        await client.get("/api/knowledge/neighbors/06-项目库-Projects/AI开发系统/信息看板.md")
    ).json()
    assert neighbors["total"] == 2
    assert any(node["title"] == "AI开发系统三层架构" for node in neighbors["neighbors"])


@pytest.mark.asyncio
async def test_project_knowledge_context_uses_project_state(client, knowledge_index, tmp_path):
    old_file = project_manager.file_path
    project_manager.file_path = str(tmp_path / "projects-v3.json")
    Path(project_manager.file_path).write_text(
        json.dumps({"version": 1, "projects": [], "logs": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        project_resp = await client.post(
            "/api/v3/projects",
            json={
                "name": "团队信息看板",
                "description": "AI开发系统任务看板",
                "context": {
                    "knowledge_links": [
                        {
                            "node_id": "03-概念库-Concepts/AI开发系统三层架构.md",
                            "relation": "basis",
                            "reason": "项目架构依据",
                        }
                    ]
                },
            },
        )
        project_id = project_resp.json()["id"]

        context = (await client.get(f"/api/v3/projects/{project_id}/knowledge-context")).json()
        assert context["project_id"] == project_id
        assert context["linked_nodes"][0]["title"] == "AI开发系统三层架构"
        assert any(node["title"] == "团队信息看板" for node in context["suggested_nodes"])

        iteration = (await client.get(f"/api/v3/projects/{project_id}/iteration-context")).json()
        assert "knowledge_context" in iteration
        assert iteration["knowledge_context"]["project_id"] == project_id
    finally:
        project_manager.file_path = old_file



@pytest.mark.asyncio
async def test_knowledge_link_binding_lifecycle(client, knowledge_index, tmp_path):
    old_file = project_manager.file_path
    project_manager.file_path = str(tmp_path / "projects-v3-links.json")
    Path(project_manager.file_path).write_text(
        json.dumps({"version": 1, "projects": [], "logs": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        project_resp = await client.post("/api/v3/projects", json={"name": "知识绑定项目"})
        project_id = project_resp.json()["id"]
        task_resp = await client.post(
            f"/api/v3/projects/{project_id}/tasks",
            json={"title": "知识绑定任务", "development_points": [{"title": "绑定开发要点"}]},
        )
        task = task_resp.json()
        task_id = task["id"]
        point_id = task["development_points"][0]["id"]
        link = {
            "node_id": "03-概念库-Concepts/AI开发系统三层架构.md",
            "title": "AI开发系统三层架构",
            "type": "概念",
            "relation": "basis",
            "reason": "项目架构依据",
            "confirmed_by": "optimus",
        }

        project_link = await client.post(f"/api/v3/projects/{project_id}/knowledge-links", json=link)
        assert project_link.status_code == 201
        assert project_link.json()["knowledge_link"]["node_id"] == link["node_id"]

        task_link = await client.post(f"/api/v3/tasks/{task_id}/knowledge-links", json={**link, "relation": "reference"})
        assert task_link.status_code == 201
        point_link = await client.post(f"/api/v3/points/{point_id}/knowledge-links", json={**link, "relation": "implementation"})
        assert point_link.status_code == 201

        context = (await client.get(f"/api/v3/projects/{project_id}/knowledge-context")).json()
        assert any(node["id"] == link["node_id"] for node in context["linked_nodes"])

        project = (await client.get(f"/api/v3/projects/{project_id}")).json()
        assert project["context"]["knowledge_links"][0]["node_id"] == link["node_id"]
        assert project["tasks"][0]["context"]["knowledge_links"][0]["relation"] == "reference"
        assert project["tasks"][0]["development_points"][0]["context"]["knowledge_links"][0]["relation"] == "implementation"

        delete_resp = await client.delete(
            "/api/v3/knowledge-links",
            params={"target_type": "project", "target_id": project_id, "node_id": link["node_id"]},
        )
        assert delete_resp.status_code == 200
        context = (await client.get(f"/api/v3/projects/{project_id}/knowledge-context")).json()
        assert not any(
            node["id"] == link["node_id"] and node.get("target_type") == "project"
            for node in context["linked_nodes"]
        )
        assert any(
            node["id"] == link["node_id"] and node.get("target_type") in {"task", "point"}
            for node in context["linked_nodes"]
        )
    finally:
        project_manager.file_path = old_file
