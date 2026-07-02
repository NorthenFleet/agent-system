import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import skill_manager
from main import app


TEST_SKILL_ROOT = Path(os.path.expanduser("~/WorkSpace/team-dashboard/data/test-skills-root"))
ORIGINAL_BINDINGS_FILE = None


def setup_module():
    global ORIGINAL_BINDINGS_FILE
    ORIGINAL_BINDINGS_FILE = skill_manager.BINDINGS_FILE
    skill_manager.BINDINGS_FILE = TEST_SKILL_ROOT / "skill-bindings.json"
    skill_dir = TEST_SKILL_ROOT / "backend-api"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: backend-api\n"
        "description: Build backend API endpoints and tests.\n"
        "---\n"
        "# backend-api\n"
        "Use python, pytest and curl for API work.\n",
        encoding="utf-8",
    )
    os.environ["SKILL_ROOTS"] = "test=" + str(TEST_SKILL_ROOT)


def teardown_module():
    skill_manager.BINDINGS_FILE = ORIGINAL_BINDINGS_FILE
    os.environ.pop("SKILL_ROOTS", None)


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_skill_registry_lists_and_binds_agent_skills(client):
    resp = await client.get("/api/v3/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "skill-registry"
    skill = next(row for row in data["skills"] if row["id"] == "backend-api")
    assert skill["status"] == "available"
    assert skill["source"] == "test"
    assert "python" in skill["required_tools"]

    detail_resp = await client.get("/api/v3/skills/backend-api")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["name"] == "backend-api"

    bind_resp = await client.put("/api/v3/agents/raphael/skills", json={"skill_ids": ["backend-api", "missing"]})
    assert bind_resp.status_code == 200
    assert bind_resp.json()["total"] == 1

    agent_resp = await client.get("/api/v3/agents/raphael/skills")
    assert agent_resp.status_code == 200
    assert agent_resp.json()["skills"][0]["id"] == "backend-api"

    dashboard_resp = await client.get("/api/v3/agents/dashboard")
    assert dashboard_resp.status_code == 200
    raphael = next(agent for agent in dashboard_resp.json()["agents"] if agent["id"] == "raphael")
    assert raphael["skill_summary"]["total"] >= 1
    assert any(skill["id"] == "backend-api" for skill in raphael["skills"])
