"""
Agent API 集成测试 — agents_router 全量端点

覆盖端点:
  POST /api/v2/agents/{id}/heartbeat    — Agent 心跳上报
  POST /api/v2/agents/{id}/dispatch     — Agent 任务派发（需 Admin）
  GET  /api/v2/agents/live              — 所有 Agent 最新状态
  GET  /api/v2/agents/{id}/history      — Agent 状态变更历史
  GET  /api/v2/agents/{id}/tasks        — Agent 关联任务列表
  权限 403 — 非 Admin 调用 dispatch 端点

使用 TestClient + 临时 SQLite DB，每个 module 独立隔离。
"""
import pytest
import sys
import os
import tempfile
from datetime import datetime, timezone

# ─── 项目路径 ───
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend")
sys.path.insert(0, BACKEND_DIR)


def _build_test_app():
    """构建最小化 FastAPI 实例，只引入 agents_router。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import models.v2_models as vm
    from services.auth_service import hash_password, create_access_token
    from services.agent_service import AgentService
    from services.task_service import TaskService
    from routers.agents_router import router as agents_router

    # 创建临时 DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    engine = create_engine(f"sqlite:///{tmp.name}")
    vm.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    # 覆写 get_session / get_engine
    _orig_engine = vm.get_engine
    _orig_session = vm.get_session

    def _test_engine():
        return engine

    def _test_session():
        return Session()

    vm.get_engine = _test_engine
    vm.get_session = _test_session

    # 预创建 admin + viewer 用户
    db = Session()
    admin = vm.User(
        username="admin",
        password_hash=hash_password("admin123"),
        display_name="管理员",
        role="admin",
    )
    db.add(admin)
    viewer = vm.User(
        username="viewer1",
        password_hash=hash_password("viewer123"),
        display_name="普通用户",
        role="viewer",
    )
    db.add(viewer)
    db.commit()
    db.close()

    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(agents_router)

    admin_token = create_access_token({
        "sub": "1", "username": "admin", "role": "admin",
    })
    viewer_token = create_access_token({
        "sub": "2", "username": "viewer1", "role": "viewer",
    })

    client = TestClient(app)
    client.admin_token = admin_token
    client.viewer_token = viewer_token
    client._db_tmp = tmp  # keep alive
    client._orig_engine = _orig_engine
    client._orig_session = _orig_session
    return client


@pytest.fixture(scope="module")
def client():
    c = _build_test_app()
    yield c
    # Restore
    import models.v2_models as vm
    vm.get_engine = c._orig_engine
    vm.get_session = c._orig_session


@pytest.fixture
def auth_headers(client):
    return {"Authorization": f"Bearer {client.admin_token}"}


@pytest.fixture
def viewer_headers(client):
    return {"Authorization": f"Bearer {client.viewer_token}"}


# ═══════════════════════════════════════════════
# 1. POST /api/v2/agents/{id}/heartbeat
# ═══════════════════════════════════════════════

class TestHeartbeat:
    """心跳上报端点"""

    def test_heartbeat_success(self, client, auth_headers):
        r = client.post("/api/v2/agents/michelangelo/heartbeat", headers=auth_headers, json={
            "agent_id": "michelangelo",
            "agent_name": "米开朗基罗",
            "status": "busy",
            "team": "ninja-turtles",
            "current_task": "test-P1-T-001",
            "cpu_usage": 45.5,
            "memory_usage": 62.3,
            "task_queue_len": 3,
            "metadata": {"test": True},
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "michelangelo" in body["message"]

    def test_heartbeat_mismatch(self, client, auth_headers):
        """路径 agent_id 与请求体不一致 → 400"""
        r = client.post("/api/v2/agents/leonardo/heartbeat", headers=auth_headers, json={
            "agent_id": "donatello",
            "agent_name": "多纳泰罗",
            "status": "online",
        })
        assert r.status_code == 400

    def test_heartbeat_no_auth(self, client):
        r = client.post("/api/v2/agents/michelangelo/heartbeat", json={
            "agent_id": "michelangelo",
            "agent_name": "米开朗基罗",
            "status": "online",
        })
        assert r.status_code == 401

    def test_heartbeat_invalid_token(self, client):
        r = client.post(
            "/api/v2/agents/michelangelo/heartbeat",
            headers={"Authorization": "Bearer invalid-token"},
            json={
                "agent_id": "michelangelo",
                "agent_name": "米开朗基罗",
                "status": "online",
            }
        )
        assert r.status_code == 401

    def test_heartbeat_minimal_payload(self, client, auth_headers):
        """最小合法请求体"""
        r = client.post("/api/v2/agents/test-agent/heartbeat", headers=auth_headers, json={
            "agent_id": "test-agent",
            "agent_name": "测试 Agent",
            "status": "online",
        })
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_heartbeat_multiple_agents(self, client, auth_headers):
        """连续上报多个 Agent 心跳"""
        for name, aid in [("拉斐尔", "raphael"), ("多纳泰罗", "donatello"), ("李奥纳多", "leonardo")]:
            r = client.post(f"/api/v2/agents/{aid}/heartbeat", headers=auth_headers, json={
                "agent_id": aid,
                "agent_name": name,
                "status": "online",
                "current_task": None,
                "cpu_usage": 10.0,
                "memory_usage": 20.0,
            })
            assert r.status_code == 200


# ═══════════════════════════════════════════════
# 2. GET /api/v2/agents/live
# ═══════════════════════════════════════════════

class TestLive:
    """Agent 实时状态列表"""

    def test_live_empty(self, client, auth_headers):
        r = client.get("/api/v2/agents/live", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "agents" in body
        assert "total" in body

    def test_live_with_heartbeats(self, client, auth_headers):
        # 先上报心跳
        client.post("/api/v2/agents/michelangelo/heartbeat", headers=auth_headers, json={
            "agent_id": "michelangelo",
            "agent_name": "米开朗基罗",
            "status": "busy",
            "current_task": "integration-test",
        })
        r = client.get("/api/v2/agents/live", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        agents = body["agents"]
        assert body["total"] >= 1
        michel = [a for a in agents if a["agent_id"] == "michelangelo"]
        assert len(michel) == 1
        assert michel[0]["agent_name"] == "米开朗基罗"
        assert michel[0]["status"] == "busy"
        assert michel[0]["current_task"] == "integration-test"

    def test_live_no_auth(self, client):
        r = client.get("/api/v2/agents/live")
        assert r.status_code == 401

    def test_live_display_status_timeout(self, client, auth_headers):
        """验证返回包含 seconds_ago、raw_status、status、metadata 字段"""
        client.post("/api/v2/agents/live-test/heartbeat", headers=auth_headers, json={
            "agent_id": "live-test",
            "agent_name": "Live测试",
            "status": "online",
        })
        r = client.get("/api/v2/agents/live", headers=auth_headers)
        assert r.status_code == 200
        agents = r.json()["agents"]
        lt = [a for a in agents if a["agent_id"] == "live-test"]
        assert len(lt) == 1
        assert "seconds_ago" in lt[0]
        assert "raw_status" in lt[0]  # 原始心跳状态
        assert "status" in lt[0]  # 计算后状态（含 timeout/offline）
        assert "metadata" in lt[0]

    def test_live_multiple_heartbeats_latest_wins(self, client, auth_headers):
        """同一 Agent 多次心跳，live 只取最新一条"""
        for task in ["task-1", "task-2", "task-3"]:
            client.post("/api/v2/agents/dup-test/heartbeat", headers=auth_headers, json={
                "agent_id": "dup-test",
                "agent_name": "重复测试",
                "status": "busy",
                "current_task": task,
            })
        r = client.get("/api/v2/agents/live", headers=auth_headers)
        assert r.status_code == 200
        agents = r.json()["agents"]
        dup = [a for a in agents if a["agent_id"] == "dup-test"]
        assert len(dup) == 1


# ═══════════════════════════════════════════════
# 3. GET /api/v2/agents/{id}/history
# ═══════════════════════════════════════════════

class TestHistory:
    """Agent 状态变更历史"""

    def test_history_success(self, client, auth_headers):
        client.post("/api/v2/agents/history-test/heartbeat", headers=auth_headers, json={
            "agent_id": "history-test",
            "agent_name": "历史测试",
            "status": "online",
        })
        r = client.get("/api/v2/agents/history-test/history", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["agent_id"] == "history-test"
        assert "status_history" in body
        assert "heartbeats" in body
        assert "total_history" in body
        assert "total_heartbeats" in body

    def test_history_empty(self, client, auth_headers):
        r = client.get("/api/v2/agents/nonexistent-agent/history", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["agent_id"] == "nonexistent-agent"
        assert body["total_history"] == 0
        assert body["total_heartbeats"] == 0

    def test_history_limit_param(self, client, auth_headers):
        r = client.get(
            "/api/v2/agents/history-test/history?limit=5",
            headers=auth_headers
        )
        assert r.status_code == 200

    def test_history_limit_too_large(self, client, auth_headers):
        r = client.get(
            "/api/v2/agents/history-test/history?limit=999",
            headers=auth_headers
        )
        assert r.status_code == 422

    def test_history_limit_too_small(self, client, auth_headers):
        r = client.get(
            "/api/v2/agents/history-test/history?limit=0",
            headers=auth_headers
        )
        assert r.status_code == 422

    def test_history_no_auth(self, client):
        r = client.get("/api/v2/agents/some-agent/history")
        assert r.status_code == 401


# ═══════════════════════════════════════════════
# 4. GET /api/v2/agents/{id}/tasks
# ═══════════════════════════════════════════════

class TestAgentTasks:
    """Agent 关联任务列表"""

    def test_agent_tasks_success(self, client, auth_headers):
        r = client.get("/api/v2/agents/michelangelo/tasks", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["agent_id"] == "michelangelo"
        assert "tasks" in body
        assert "total" in body

    def test_agent_tasks_with_status_filter(self, client, auth_headers):
        r = client.get(
            "/api/v2/agents/michelangelo/tasks?status=done",
            headers=auth_headers
        )
        assert r.status_code == 200

    def test_agent_tasks_no_auth(self, client):
        r = client.get("/api/v2/agents/michelangelo/tasks")
        assert r.status_code == 401


# ═══════════════════════════════════════════════
# 5. POST /api/v2/agents/{id}/dispatch (Admin only)
# ═══════════════════════════════════════════════

class TestDispatch:
    """Agent 任务派发 — 仅 Admin 可操作"""

    def test_dispatch_admin_success(self, client, auth_headers):
        client.post("/api/v2/agents/dispatch-test/heartbeat", headers=auth_headers, json={
            "agent_id": "dispatch-test",
            "agent_name": "派发测试",
            "status": "idle",
        })
        r = client.post("/api/v2/agents/dispatch-test/dispatch", headers=auth_headers, json={
            "task_id": "task-001",
            "notes": "集成测试派发",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["agent_id"] == "dispatch-test"
        assert body["task_id"] == "task-001"
        assert "dispatch_id" in body

    def test_dispatch_nonexistent_agent(self, client, auth_headers):
        r = client.post("/api/v2/agents/nonexistent-xyz/dispatch", headers=auth_headers, json={
            "task_id": "task-001",
        })
        assert r.status_code == 404

    def test_dispatch_missing_task_id(self, client, auth_headers):
        client.post("/api/v2/agents/dispatch-test/heartbeat", headers=auth_headers, json={
            "agent_id": "dispatch-test",
            "agent_name": "派发测试",
            "status": "idle",
        })
        r = client.post("/api/v2/agents/dispatch-test/dispatch", headers=auth_headers, json={
            "notes": "缺少 task_id",
        })
        assert r.status_code == 422

    def test_dispatch_no_auth(self, client):
        r = client.post("/api/v2/agents/michelangelo/dispatch", json={
            "task_id": "task-001",
        })
        assert r.status_code == 401

    def test_dispatch_viewer_forbidden(self, client, viewer_headers):
        """viewer 角色调用 dispatch → 403"""
        client.post("/api/v2/agents/rbac-test/heartbeat", headers={
            "Authorization": f"Bearer {client.admin_token}"
        }, json={
            "agent_id": "rbac-test",
            "agent_name": "RBAC测试",
            "status": "idle",
        })
        r = client.post("/api/v2/agents/rbac-test/dispatch", headers=viewer_headers, json={
            "task_id": "task-002",
        })
        assert r.status_code == 403

    def test_dispatch_invalid_token(self, client):
        r = client.post(
            "/api/v2/agents/michelangelo/dispatch",
            headers={"Authorization": "Bearer invalid-token"},
            json={"task_id": "task-001"}
        )
        assert r.status_code == 401
