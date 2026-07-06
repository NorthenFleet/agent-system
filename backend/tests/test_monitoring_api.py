"""
监控数据聚合 API 单元测试

测试覆盖:
1. GET /api/v2/monitoring/agents — 认证拦截、返回结构、状态筛选
2. GET /api/v2/monitoring/stats  — 认证拦截、返回结构、聚合正确性
"""
import sys, os, pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app
from models.v2_models import get_session, Base, get_engine
from models.v2_models import AgentHeartbeat, Agent, Task, AgentDispatch, User
from services.auth_service import hash_password


@pytest.fixture(autouse=True)
def _setup_db():
    """每个测试前重建测试数据库"""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _ensure_admin(db):
    """确保测试数据库有 admin 用户可登录"""
    existing = db.query(User).filter(User.username == "admin").first()
    if not existing:
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="管理员",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()


def _seed_heartbeats(db):
    """写入几条心跳记录"""
    now = datetime.now(timezone.utc)
    data = [
        {"agent_id": "leonardo", "agent_name": "李奥纳多", "status": "online",
         "current_task": "task-001", "cpu_usage": 23.5, "memory_usage": 45.2,
         "task_queue_len": 3, "heartbeat_at": now},
        {"agent_id": "donatello", "agent_name": "多纳泰罗", "status": "busy",
         "current_task": "task-002", "cpu_usage": 78.1, "memory_usage": 62.0,
         "task_queue_len": 1, "heartbeat_at": now - timedelta(seconds=30)},
        {"agent_id": "raphael", "agent_name": "拉斐尔", "status": "online",
         "current_task": None, "cpu_usage": 12.0, "memory_usage": 30.5,
         "task_queue_len": 0, "heartbeat_at": now - timedelta(seconds=400)},
    ]
    rows = []
    for d in data:
        hb = AgentHeartbeat(**d)
        db.add(hb)
        rows.append(hb)
    db.commit()
    return rows


def _seed_agents(db):
    """写入 Agent 注册记录"""
    now = datetime.now(timezone.utc)
    agents = [
        Agent(agent_id="leonardo", name="李奥纳多", team="ninjas", status="online",
              role="architect", current_task="task-001", last_heartbeat_at=now),
        Agent(agent_id="donatello", name="多纳泰罗", team="ninjas", status="busy",
              role="frontend", current_task="task-002", last_heartbeat_at=now),
        Agent(agent_id="michelangelo", name="米开朗基罗", team="ninjas", status="offline",
              role="testing", current_task=None, last_heartbeat_at=None),
    ]
    for a in agents:
        db.add(a)
    db.commit()
    return agents


def _seed_tasks(db):
    """写入任务记录"""
    tasks = [
        Task(task_id="task-001", title="架构设计", status="done", priority="high",
             assignee="leonardo", created_at=datetime.now(timezone.utc)),
        Task(task_id="task-002", title="前端开发", status="in_progress", priority="medium",
             assignee="donatello", created_at=datetime.now(timezone.utc)),
        Task(task_id="task-003", title="测试用例", status="pending", priority="low",
             assignee=None, created_at=datetime.now(timezone.utc)),
    ]
    for t in tasks:
        db.add(t)
    db.commit()
    return tasks


def _seed_dispatches(db):
    """写入派发记录"""
    now = datetime.now(timezone.utc)
    dispatches = [
        AgentDispatch(agent_id="leonardo", task_id="task-001", status="completed",
                      dispatcher_id="admin", dispatched_at=now),
        AgentDispatch(agent_id="donatello", task_id="task-002", status="running",
                      dispatcher_id="admin", dispatched_at=now),
    ]
    for d in dispatches:
        db.add(d)
    db.commit()
    return dispatches


def _login():
    """登录并返回 token + client"""
    client = TestClient(app)
    db = get_session()
    _ensure_admin(db)
    db.close()
    resp = client.post("/api/v2/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"], client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 1. 认证拦截
# ============================================================

class TestAuth:
    def test_agents_no_auth_401(self):
        """未认证访问返回 401"""
        client = TestClient(app)
        resp = client.get("/api/v2/monitoring/agents")
        assert resp.status_code == 401

    def test_stats_no_auth_401(self):
        """未认证访问 stats 返回 401"""
        client = TestClient(app)
        resp = client.get("/api/v2/monitoring/stats")
        assert resp.status_code == 401


# ============================================================
# 2. GET /api/v2/monitoring/agents
# ============================================================

class TestMonitoringAgents:
    def test_agents_returns_list(self):
        """返回 agents 列表 + status_counts"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/agents", headers=_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total" in data
        assert "status_counts" in data
        assert "timestamp" in data
        assert data["total"] >= 3

    def test_agents_includes_heartbeat_fields(self):
        """每条记录包含心跳字段"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/agents", headers=_headers(token))
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        leo = [a for a in agents if a["agent_id"] == "leonardo"]
        assert len(leo) == 1
        a = leo[0]
        assert a["agent_name"] == "李奥纳多"
        assert a["cpu_usage"] == 23.5
        assert a["memory_usage"] == 45.2
        assert a["current_task"] == "task-001"
        assert a["status"] == "online"

    def test_agents_offline_detection(self):
        """心跳超过 300s 标记为 offline"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/agents", headers=_headers(token))
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        raph = [a for a in agents if a["agent_id"] == "raphael"]
        assert len(raph) == 1
        assert raph[0]["status"] == "offline"

    def test_agents_busy_detection(self):
        """raw_status=busy 时保持 busy"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/agents", headers=_headers(token))
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        don = [a for a in agents if a["agent_id"] == "donatello"]
        assert len(don) == 1
        assert don[0]["status"] == "busy"

    def test_agents_filter_by_status(self):
        """status_filter 参数正确过滤"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/agents?status_filter=online", headers=_headers(token))
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        for a in agents:
            assert a["status"] == "online"

    def test_agents_includes_unregistered(self):
        """注册但无心跳的 Agent 也出现在结果中 (status=offline)"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        db.close()

        resp = client.get("/api/v2/monitoring/agents", headers=_headers(token))
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        mich = [a for a in agents if a["agent_id"] == "michelangelo"]
        assert len(mich) == 1
        assert mich[0]["status"] == "offline"
        assert mich[0]["last_heartbeat"] is None


# ============================================================
# 3. GET /api/v2/monitoring/stats
# ============================================================

class TestMonitoringStats:
    def test_stats_structure(self):
        """返回结构包含 tasks/agents/dispatches/system"""
        token, client = _login()
        db = get_session()
        _seed_tasks(db)
        _seed_agents(db)
        _seed_heartbeats(db)
        _seed_dispatches(db)
        db.close()

        resp = client.get("/api/v2/monitoring/stats", headers=_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "agents" in data
        assert "dispatches" in data
        assert "system" in data

    def test_stats_task_counts(self):
        """任务统计正确"""
        token, client = _login()
        db = get_session()
        _seed_tasks(db)
        db.close()

        resp = client.get("/api/v2/monitoring/stats", headers=_headers(token))
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert tasks["total"] == 3
        assert tasks["by_status"]["done"] == 1
        assert tasks["by_status"]["in_progress"] == 1
        assert tasks["by_status"]["pending"] == 1

    def test_stats_completion_rate(self):
        """完成率计算正确"""
        token, client = _login()
        db = get_session()
        _seed_tasks(db)
        db.close()

        resp = client.get("/api/v2/monitoring/stats", headers=_headers(token))
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert tasks["completion_rate"] == 33.3

    def test_stats_agent_activity(self):
        """Agent 活跃度统计"""
        token, client = _login()
        db = get_session()
        _seed_agents(db)
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/stats", headers=_headers(token))
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert agents["total_registered"] == 3
        assert agents["total_heartbeats"] == 3
        assert agents["active_5m"] == 2

    def test_stats_dispatch_counts(self):
        """派发统计正确"""
        token, client = _login()
        db = get_session()
        _seed_dispatches(db)
        db.close()

        resp = client.get("/api/v2/monitoring/stats", headers=_headers(token))
        assert resp.status_code == 200
        dispatches = resp.json()["dispatches"]
        assert dispatches["total"] == 2
        assert dispatches["by_status"]["completed"] == 1
        assert dispatches["by_status"]["running"] == 1

    def test_stats_system_metrics(self):
        """系统指标包含 CPU/内存"""
        token, client = _login()
        db = get_session()
        _seed_heartbeats(db)
        db.close()

        resp = client.get("/api/v2/monitoring/stats", headers=_headers(token))
        assert resp.status_code == 200
        system = resp.json()["system"]
        assert "avg_cpu_usage" in system
        assert "avg_memory_usage" in system
        assert "timestamp" in system
        assert system["avg_cpu_usage"] == 37.9
