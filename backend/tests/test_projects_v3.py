import json
import os
import shutil

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from project_manager import project_manager


TEST_DATA_DIR = os.path.expanduser("~/WorkSpace/team-dashboard/data/test-projects-v3")
TEST_PROJECTS_FILE = os.path.join(TEST_DATA_DIR, "projects-v3.json")
ORIGINAL_FILE = None


def setup_module():
    global ORIGINAL_FILE
    ORIGINAL_FILE = project_manager.file_path
    project_manager.file_path = TEST_PROJECTS_FILE
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    with open(TEST_PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "projects": [], "logs": []}, f)


def teardown_module():
    project_manager.file_path = ORIGINAL_FILE
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_project_task_point_progress_rollup(client):
    project_resp = await client.post("/api/v3/projects", json={
        "name": "看板 v3",
        "description": "智能体开发迭代项目",
        "owner_agent": "optimus",
    })
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "实现项目任务 API",
        "assignee_agent": "raphael",
        "development_points": [
            {"title": "Project CRUD", "weight": 1},
            {"title": "Progress rollup", "weight": 1},
        ],
    })
    assert task_resp.status_code == 201
    task = task_resp.json()
    task_id = task["id"]
    points = task["development_points"]

    done_resp = await client.put(f"/api/v3/points/{points[0]['id']}", json={
        "status": "done",
        "completion_evidence": "tests pass",
    })
    assert done_resp.status_code == 200

    project = (await client.get(f"/api/v3/projects/{project_id}")).json()
    assert project["tasks"][0]["progress"] == 50.0
    assert project["progress"] == 50.0

    done_resp = await client.put(f"/api/v3/points/{points[1]['id']}", json={"status": "done"})
    assert done_resp.status_code == 200
    project = (await client.get(f"/api/v3/projects/{project_id}")).json()
    assert project["tasks"][0]["progress"] == 100.0
    assert project["tasks"][0]["status"] == "done"
    assert project["progress"] == 100.0


@pytest.mark.asyncio
async def test_iteration_context_and_decompose(client):
    project_resp = await client.post("/api/v3/projects", json={"name": "迭代项目"})
    project_id = project_resp.json()["id"]

    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "前端任务看板",
        "status": "in_progress",
        "development_points": [{"title": "项目列表"}, {"title": "任务详情"}],
    })
    task_id = task_resp.json()["id"]

    context = (await client.get(f"/api/v3/projects/{project_id}/iteration-context")).json()
    assert context["project"]["id"] == project_id
    assert len(context["open_points"]) == 2
    assert "suggested_next_actions" in context

    decompose_resp = await client.post(f"/api/v3/projects/{project_id}/decompose", json={
        "reasoning_summary": "继续拆分前端交互",
        "agent_id": "optimus",
        "new_tasks": [{
            "title": "补充任务详情抽屉",
            "development_points": [{"title": "展示开发要点"}, {"title": "展示日志"}],
        }],
        "new_development_points": [{
            "task_id": task_id,
            "title": "支持进度联动",
        }],
    })
    assert decompose_resp.status_code == 201
    result = decompose_resp.json()
    assert len(result["created_tasks"]) == 1
    assert len(result["created_development_points"]) == 1

    logs = (await client.get(f"/api/v3/projects/{project_id}/logs")).json()["logs"]
    assert any(log["action"] == "project_decomposed" for log in logs)


@pytest.mark.asyncio
async def test_agent_status_projection_matches_project_task_points(client):
    project_resp = await client.post("/api/v3/projects", json={"name": "agent status project"})
    assert project_resp.status_code == 201
    project = project_resp.json()

    task_resp = await client.post("/api/v3/projects/" + project["id"] + "/tasks", json={
        "title": "agent status page",
        "assignee_agent": "donatello",
        "status": "in_progress",
        "development_points": [
            {"title": "projection api", "assigned_agent": "raphael"},
            {"title": "status card", "assigned_agent": "donatello"},
        ],
    })
    assert task_resp.status_code == 201
    task = task_resp.json()
    point = task["development_points"][0]

    status_resp = await client.get("/api/v3/agents/status")
    assert status_resp.status_code == 200
    rows = status_resp.json()["agents"]
    raphael = next(row for row in rows if row["agent_id"] == "raphael")
    assert raphael["status"] == "busy"
    assert raphael["current_project_id"] == project["id"]
    assert raphael["current_task_id"] == task["id"]
    assert raphael["current_development_point_id"] == point["id"]

    current_resp = await client.get("/api/v3/agents/raphael/current-work")
    assert current_resp.status_code == 200
    assert current_resp.json()["current_task_id"] == task["id"]

    missing_resp = await client.get("/api/v3/agents/not-exists/current-work")
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_work_items_and_complete_point(client):
    project_resp = await client.post("/api/v3/projects", json={"name": "智能体执行项目"})
    project_id = project_resp.json()["id"]
    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "实现开发要点执行",
        "assignee_agent": "raphael",
        "development_points": [
            {"title": "读取工作项", "assigned_agent": "raphael"},
            {"title": "完成要点", "assigned_agent": "raphael"},
        ],
    })
    task = task_resp.json()
    points = task["development_points"]

    work_resp = await client.get("/api/v3/agents/raphael/work-items")
    assert work_resp.status_code == 200
    work = work_resp.json()
    assert work["total_tasks"] >= 1
    assert work["total_development_points"] >= 2

    complete_resp = await client.post(f"/api/v3/points/{points[0]['id']}/complete", json={
        "agent_id": "raphael",
        "completion_evidence": "已提交实现并通过测试",
        "result_summary": "完成第一个开发要点",
    })
    assert complete_resp.status_code == 200
    complete = complete_resp.json()
    assert complete["point"]["status"] == "done"
    assert complete["log"]["action"] == "point_completed"

    project = (await client.get(f"/api/v3/projects/{project_id}")).json()
    assert project["tasks"][0]["progress"] == 50.0

    work = (await client.get("/api/v3/agents/raphael/work-items")).json()
    point_ids = [item["point"]["id"] for item in work["development_points"]]
    assert points[0]["id"] not in point_ids
    assert points[1]["id"] in point_ids


@pytest.mark.asyncio
async def test_project_manager_contract_and_decompose_writeback(client):
    project_resp = await client.post("/api/v3/projects", json={
        "name": "pm iteration project",
        "context": {"goal": "close the manager loop"},
    })
    project_id = project_resp.json()["id"]

    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "manager loop",
        "assignee_agent": "optimus",
        "development_points": [
            {"title": "define contract", "assigned_agent": "optimus"},
            {"title": "write back updates", "assigned_agent": "raphael", "status": "blocked"},
        ],
    })
    task = task_resp.json()
    point = task["development_points"][0]

    context_resp = await client.get(f"/api/v3/projects/{project_id}/iteration-context")
    assert context_resp.status_code == 200
    context = context_resp.json()
    assert context["status_summary"]["total_tasks"] == 1
    assert context["status_summary"]["blocked_items"] == 1
    assert context["project_manager_input"]["goal"] == "close the manager loop"
    assert "updated_development_points" in context["project_manager_output_contract"]
    assert any(action["action"] == "resolve_blockers" for action in context["suggested_next_actions"])

    decompose_resp = await client.post(f"/api/v3/projects/{project_id}/decompose", json={
        "reasoning_summary": "move one point to review and open the next task",
        "agent_id": "optimus",
        "project_updates": {
            "current_phase": "manager-writeback",
            "context": {"last_manager_iteration": "contract-test"},
        },
        "updated_development_points": [{
            "point_id": point["id"],
            "status": "review",
            "completion_evidence": "ready for PM review",
        }],
        "new_tasks": [{
            "title": "next implementation slice",
            "assignee_agent": "donatello",
            "development_points": [{"title": "render PM state", "assigned_agent": "donatello"}],
        }],
    })
    assert decompose_resp.status_code == 201
    result = decompose_resp.json()
    assert len(result["created_tasks"]) == 1
    assert result["updated_development_points"][0]["status"] == "review"

    project = (await client.get(f"/api/v3/projects/{project_id}")).json()
    assert project["current_phase"] == "manager-writeback"
    assert project["context"]["last_manager_iteration"] == "contract-test"

    context = (await client.get(f"/api/v3/projects/{project_id}/iteration-context")).json()
    assert context["status_summary"]["review_items"] == 1
    assert any(item["agent_id"] == "donatello" for item in context["agent_workloads"])


@pytest.mark.asyncio
async def test_development_point_transition_state_machine(client):
    project_resp = await client.post("/api/v3/projects", json={"name": "point transition project"})
    project_id = project_resp.json()["id"]
    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "state machine task",
        "development_points": [{"title": "state machine point"}],
    })
    point_id = task_resp.json()["development_points"][0]["id"]

    claim_resp = await client.post(f"/api/v3/points/{point_id}/claim", json={"agent_id": "raphael", "reason": "start work"})
    assert claim_resp.status_code == 200
    assert claim_resp.json()["point"]["status"] == "in_progress"
    assert claim_resp.json()["point"]["assigned_agent"] == "raphael"
    assert claim_resp.json()["log"]["action"] == "point_claimed"

    block_resp = await client.post(f"/api/v3/points/{point_id}/block", json={"agent_id": "raphael", "reason": "missing API contract"})
    assert block_resp.status_code == 200
    assert block_resp.json()["point"]["status"] == "blocked"

    context = (await client.get(f"/api/v3/projects/{project_id}/iteration-context")).json()
    assert context["status_summary"]["blocked_items"] == 1
    assert any(item["type"] == "point" and item["point_id"] == point_id for item in context["blocked_items"])

    release_resp = await client.post(f"/api/v3/points/{point_id}/release", json={"agent_id": "raphael", "reason": "back to pool"})
    assert release_resp.status_code == 200
    assert release_resp.json()["point"]["status"] == "todo"
    assert release_resp.json()["point"]["assigned_agent"] == ""

    review_resp = await client.post(f"/api/v3/points/{point_id}/submit-review", json={"agent_id": "donatello", "completion_evidence": "ready for review"})
    assert review_resp.status_code == 200
    assert review_resp.json()["point"]["status"] == "review"
    assert review_resp.json()["point"]["assigned_agent"] == "donatello"

    context = (await client.get(f"/api/v3/projects/{project_id}/iteration-context")).json()
    assert context["status_summary"]["review_items"] == 1
    assert any(action["action"] == "review_pending_work" for action in context["suggested_next_actions"])

    done_resp = await client.post(f"/api/v3/points/{point_id}/complete", json={"agent_id": "michelangelo", "completion_evidence": "review accepted"})
    assert done_resp.status_code == 200
    assert done_resp.json()["point"]["status"] == "done"

    context = (await client.get(f"/api/v3/projects/{project_id}/iteration-context")).json()
    assert context["status_summary"]["open_points"] == 0



@pytest.mark.asyncio
async def test_project_design_document_lifecycle_and_agent_context(client):
    create_resp = await client.post("/api/v3/projects", json={
        "name": "设计文档项目",
        "description": "创建项目时同步撰写设计内容",
        "design_doc": {
            "summary": "项目从设计文档派生任务",
            "data_structure": {
                "entities": ["Project", "Task", "DevelopmentPoint"],
                "relationships": ["Project has many Task"],
            },
            "system_architecture": {
                "components": ["FastAPI", "Vue", "ProjectManager"],
                "agent_roles": ["project-manager", "developer-agent"],
            },
            "system_functions": ["项目创建", "任务拆解", "开发要点回写"],
            "api_interfaces": [{"method": "GET", "path": "/api/v3/projects/{project_id}/agent-context"}],
            "task_breakdown_guidance": ["先补设计，再拆任务"],
            "risks": ["设计与实现漂移"],
            "author_agent": "optimus",
        },
    })
    assert create_resp.status_code == 201
    project = create_resp.json()
    project_id = project["id"]
    assert project["design_doc"]["summary"] == "项目从设计文档派生任务"
    assert "Project" in project["design_doc"]["data_structure"]["entities"]

    design_resp = await client.get(f"/api/v3/projects/{project_id}/design-doc")
    assert design_resp.status_code == 200
    assert design_resp.json()["project_id"] == project_id

    update_resp = await client.put(f"/api/v3/projects/{project_id}/design-doc", json={
        "summary": "更新后的设计摘要",
        "system_functions": ["项目创建", "设计文档维护"],
        "author_agent": "optimus",
        "change_summary": "补充设计文档维护能力",
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["summary"] == "更新后的设计摘要"
    assert update_resp.json()["changelog"][-1]["summary"] == "补充设计文档维护能力"

    revise_resp = await client.post(f"/api/v3/projects/{project_id}/design-doc/revise", json={
        "agent_id": "optimus",
        "change_summary": "补充 API 接口契约",
        "updates": {
            "api_interfaces": [{"method": "PUT", "path": "/api/v3/projects/{project_id}/design-doc"}],
        },
    })
    assert revise_resp.status_code == 201
    assert revise_resp.json()["design_doc"]["version"] == 2

    approve_resp = await client.post(f"/api/v3/projects/{project_id}/design-doc/approve", json={"agent_id": "optimus"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["design_doc"]["status"] == "approved"
    assert approve_resp.json()["design_doc"]["approved_by"] == "optimus"

    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "按设计实现 agent context",
        "assignee_agent": "raphael",
        "development_points": [{"title": "返回设计文档", "assigned_agent": "raphael"}],
    })
    assert task_resp.status_code == 201

    context_resp = await client.get(f"/api/v3/projects/{project_id}/agent-context?agent_id=raphael")
    assert context_resp.status_code == 200
    context = context_resp.json()
    assert context["design_doc"]["status"] == "approved"
    assert context["agent_id"] == "raphael"
    assert len(context["agent_work"]["development_points"]) == 1



@pytest.mark.asyncio
async def test_agent_dashboard_unifies_sources_and_project_work(client):
    project_resp = await client.post("/api/v3/projects", json={"name": "agent dashboard project"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    task_resp = await client.post(f"/api/v3/projects/{project_id}/tasks", json={
        "title": "dashboard current work",
        "assignee_agent": "wheeljack",
        "status": "in_progress",
        "development_points": [{"title": "dashboard point", "assigned_agent": "wheeljack"}],
    })
    assert task_resp.status_code == 201
    task = task_resp.json()
    point = task["development_points"][0]

    resp = await client.get("/api/v3/agents/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "agents-dashboard"
    assert "updated_at" in data

    wheeljack = next(agent for agent in data["agents"] if agent["id"] == "wheeljack")
    assert wheeljack["status"] == "busy"
    assert "profile" in wheeljack
    assert "runtime" in wheeljack
    assert "source" in wheeljack
    assert "updated_at" in wheeljack
    assert "stale" in wheeljack
    assert wheeljack["source"]["work"] == "projects-v3"
    assert wheeljack["current_work"]["task_id"] == task["id"]
    assert wheeljack["current_work"]["development_point_id"] == point["id"]
    assert wheeljack["current_project_id"] == project_id



@pytest.mark.asyncio
async def test_project_crud_update_and_delete(client):
    create_resp = await client.post("/api/v3/projects", json={
        "name": "crud project",
        "description": "before",
    })
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    update_resp = await client.put(f"/api/v3/projects/{project_id}", json={
        "name": "crud project updated",
        "description": "after",
        "current_phase": "iteration-1",
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "crud project updated"
    assert update_resp.json()["current_phase"] == "iteration-1"

    delete_resp = await client.delete(f"/api/v3/projects/{project_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    missing_resp = await client.get(f"/api/v3/projects/{project_id}")
    assert missing_resp.status_code == 404
