from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.agent_team_router as router_module
from routers.auth_router import get_current_user
from services.agent_team_service import AgentTeamService
from services.command_center_service import CommandCenterService


def _client(tmp_path, monkeypatch):
    command = CommandCenterService(str(tmp_path / "agent-team-api.db"))
    mission = command.create_mission(
        objective="验证 Agent Team API",
        requested_by="user-1",
        profile_user_id="user-1",
        project_id="project-1",
        mission_type="software",
    )
    monkeypatch.setattr(router_module, "agent_team_service", AgentTeamService(command))
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user-1", "username": "user-1", "role": "user",
    }
    return TestClient(app), mission


def test_agent_team_writes_are_disabled_by_default(tmp_path, monkeypatch):
    client, mission = _client(tmp_path, monkeypatch)
    monkeypatch.delenv("AGENT_TEAM_ENABLED", raising=False)
    response = client.post(
        "/api/v3/agent-teams",
        json={
            "mission_id": mission["id"],
            "name": "API 团队",
            "idempotency_key": "api-team-1",
        },
    )
    assert response.status_code == 503


def test_agent_team_stage_one_api_builds_readable_snapshot(tmp_path, monkeypatch):
    client, mission = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_TEAM_ENABLED", "true")
    team_response = client.post(
        "/api/v3/agent-teams",
        json={
            "mission_id": mission["id"],
            "name": "API 团队",
            "idempotency_key": "api-team-1",
        },
    )
    assert team_response.status_code == 200
    team = team_response.json()

    role_response = client.post(
        f"/api/v3/agent-teams/{team['id']}/roles",
        json={
            "role_key": "reviewer",
            "display_name": "审校者",
            "capabilities": ["review"],
        },
    )
    assert role_response.status_code == 200
    role = role_response.json()
    instance_response = client.post(
        f"/api/v3/agent-teams/{team['id']}/instances",
        json={
            "role_id": role["id"],
            "instance_key": "reviewer-1",
            "base_agent_id": "shockwave",
        },
    )
    assert instance_response.status_code == 200
    task_response = client.post(
        f"/api/v3/agent-teams/{team['id']}/tasks",
        json={
            "task_key": "review-contract",
            "title": "复核契约",
            "objective": "复核 Agent Team 契约",
            "idempotency_key": "api-task-1",
        },
    )
    assert task_response.status_code == 200

    snapshot = client.get(f"/api/v3/agent-teams/{team['id']}")
    assert snapshot.status_code == 200
    assert snapshot.json()["team"]["id"] == team["id"]
    assert snapshot.json()["roles"][0]["id"] == role["id"]
    assert snapshot.json()["tasks"][0]["task_key"] == "review-contract"
