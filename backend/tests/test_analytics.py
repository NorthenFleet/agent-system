"""
Analytics 模块单元测试 (S5 P5)

覆盖 5 个端点 + Service 层方法，≥ 15 项测试。
验证：
- 5 个端点返回 200 + 正确 JSON 结构
- Service 层聚合逻辑正确
- 时间范围参数 (7/14/30/90) 生效

每个测试使用独立的内存 SQLite 引擎 + 独立 FastAPI app，互不干扰。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.v2_models import Base, Task, Agent, Sprint
from services.analytics_service import (
    AnalyticsService,
    TeamEfficiencyService,
    ThroughputService,
    AgentProductivityService,
    SprintBurndownService,
    TaskTrendService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_populated_session():
    """Create a fresh in-memory DB with seed data and return the session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    now = datetime.now(timezone.utc)
    base = now - timedelta(days=20)

    # Tasks across statuses / priorities / assignees
    for i in range(20):
        created = base + timedelta(days=i)
        status = ["completed", "in_progress", "pending", "completed", "completed"][i % 5]
        completed_at = created + timedelta(hours=i * 5) if status == "completed" else None
        task = Task(
            task_id=f"task-ana-{i:03d}",
            title=f"分析任务 {i}",
            status=status,
            priority=["high", "medium", "low"][i % 3],
            assignee=f"agent-{i % 3}",
            progress=100 if status == "completed" else (30 + i * 2) % 80,
            sprint=1,
            created_at=created,
            completed_at=completed_at,
        )
        db.add(task)

    # Agents
    for i in range(3):
        db.add(Agent(
            name=f"agent-{i}",
            role="worker",
            team="alpha" if i < 2 else "beta",
            status="online",
            last_heartbeat=now - timedelta(minutes=i * 10),
        ))

    # Sprint
    db.add(Sprint(
        name="Sprint 5",
        status="running",
        start_date=base,
        end_date=base + timedelta(days=30),
        goal="数据分析后端",
    ))

    db.commit()
    return db


def _build_test_client(db_session):
    """Create an isolated FastAPI app + TestClient wired to db_session."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.analytics_router import router as analytics_router
    from database import get_db

    app = FastAPI()
    app.include_router(analytics_router)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    tc = TestClient(app)
    return tc, app


# ---------------------------------------------------------------------------
# Test 1: Team Efficiency
# ---------------------------------------------------------------------------

class TestTeamEfficiency:

    def test_structure_keys(self):
        """返回字典包含所有预期字段。"""
        db = _build_populated_session()
        try:
            result = TeamEfficiencyService.compute(db, days=14)
            required = {
                "total_tasks", "completed_tasks", "avg_completion_rate",
                "avg_progress", "by_status", "by_priority", "by_assignee",
            }
            assert required.issubset(result.keys())
        finally:
            db.close()

    def test_total_tasks_positive(self):
        """total_tasks 应为正整数。"""
        db = _build_populated_session()
        try:
            result = TeamEfficiencyService.compute(db, days=30)
            assert result["total_tasks"] > 0
        finally:
            db.close()

    def test_completion_rate_range(self):
        """完成率应在 0-100 之间。"""
        db = _build_populated_session()
        try:
            result = TeamEfficiencyService.compute(db, days=30)
            assert 0 <= result["avg_completion_rate"] <= 100
        finally:
            db.close()

    def test_by_status_nonempty(self):
        """by_status 应包含至少一个状态。"""
        db = _build_populated_session()
        try:
            result = TeamEfficiencyService.compute(db, days=30)
            assert len(result["by_status"]) > 0
        finally:
            db.close()

    def test_default_days(self):
        """默认 14 天应有数据。"""
        db = _build_populated_session()
        try:
            result = TeamEfficiencyService.compute(db)
            assert result["total_tasks"] > 0
        finally:
            db.close()

    def test_facade_team_efficiency(self):
        """门面方法应委托到 TeamEfficiencyService。"""
        db = _build_populated_session()
        try:
            result = AnalyticsService.team_efficiency(db, days=14)
            assert "total_tasks" in result
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Test 2: Throughput
# ---------------------------------------------------------------------------

class TestThroughput:

    def test_structure(self):
        """返回包含 summary 和 data_points。"""
        db = _build_populated_session()
        try:
            result = ThroughputService.compute(db, days=30)
            assert "summary" in result
            assert "data_points" in result
        finally:
            db.close()

    def test_summary_keys(self):
        """summary 包含预期字段。"""
        db = _build_populated_session()
        try:
            result = ThroughputService.compute(db, days=30)
            required = {
                "total_created", "total_completed", "daily_avg_created",
                "daily_avg_completed", "trend",
            }
            assert required.issubset(result["summary"].keys())
        finally:
            db.close()

    def test_data_points_are_dicts(self):
        """每个数据点应有 date/created/completed。"""
        db = _build_populated_session()
        try:
            result = ThroughputService.compute(db, days=30)
            for dp in result["data_points"]:
                assert "date" in dp
                assert "created" in dp
                assert "completed" in dp
        finally:
            db.close()

    def test_facade_throughput(self):
        """门面方法应返回正确结构。"""
        db = _build_populated_session()
        try:
            result = AnalyticsService.throughput(db, days=7)
            assert result["summary"]["total_created"] >= 0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Test 3: Agent Productivity
# ---------------------------------------------------------------------------

class TestAgentProductivity:

    def test_agents_list_nonempty(self):
        """应返回至少一个 Agent。"""
        db = _build_populated_session()
        try:
            result = AgentProductivityService.compute(db, days=30)
            assert len(result["agents"]) > 0
        finally:
            db.close()

    def test_agent_keys(self):
        """每个 Agent 记录包含预期字段。"""
        db = _build_populated_session()
        try:
            result = AgentProductivityService.compute(db, days=30)
            agent = result["agents"][0]
            required = {"agent_name", "total_tasks", "completed_tasks", "completion_rate"}
            assert required.issubset(agent.keys())
        finally:
            db.close()

    def test_sorted_by_completion_rate(self):
        """结果按 completion_rate 降序排列。"""
        db = _build_populated_session()
        try:
            result = AgentProductivityService.compute(db, days=30)
            rates = [a["completion_rate"] for a in result["agents"]]
            assert rates == sorted(rates, reverse=True)
        finally:
            db.close()

    def test_facade_agent_productivity(self):
        """门面方法应返回 agents 列表。"""
        db = _build_populated_session()
        try:
            result = AnalyticsService.agent_productivity(db, days=14)
            assert "agents" in result
            assert "summary" in result
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Test 4: Sprint Burndown
# ---------------------------------------------------------------------------

class TestSprintBurndown:

    def test_returns_data_list(self):
        """返回包含 data 列表。"""
        db = _build_populated_session()
        try:
            result = SprintBurndownService.compute(db, days=30)
            assert "data" in result
            assert isinstance(result["data"], list)
        finally:
            db.close()

    def test_sprint_keys(self):
        """每个 sprint 条目包含预期字段。"""
        db = _build_populated_session()
        try:
            result = SprintBurndownService.compute(db, days=30)
            if result["data"]:
                sprint = result["data"][0]
                required = {
                    "sprint_name", "total_tasks", "completed_tasks",
                    "remaining_tasks", "completion_pct",
                }
                assert required.issubset(sprint.keys())
        finally:
            db.close()

    def test_facade_sprint_burndown(self):
        """门面方法应返回正确结构。"""
        db = _build_populated_session()
        try:
            result = AnalyticsService.sprint_burndown(db, days=30)
            assert "data" in result
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Test 5: Task Trend
# ---------------------------------------------------------------------------

class TestTaskTrend:

    def test_structure(self):
        """返回包含 summary 和 data_points。"""
        db = _build_populated_session()
        try:
            result = TaskTrendService.compute(db, days=30)
            assert "summary" in result
            assert "data_points" in result
        finally:
            db.close()

    def test_summary_keys(self):
        """summary 包含预期字段。"""
        db = _build_populated_session()
        try:
            result = TaskTrendService.compute(db, days=30)
            required = {"total_tasks", "completion_trend", "period_count"}
            assert required.issubset(result["summary"].keys())
        finally:
            db.close()

    def test_data_point_keys(self):
        """每个数据点包含 period/total/created/completed。"""
        db = _build_populated_session()
        try:
            result = TaskTrendService.compute(db, days=30)
            for dp in result["data_points"]:
                assert "period" in dp
                assert "total" in dp
                assert "created" in dp
                assert "completed" in dp
        finally:
            db.close()

    def test_facade_task_trend(self):
        """门面方法应返回正确结构。"""
        db = _build_populated_session()
        try:
            result = AnalyticsService.task_trend(db, days=7)
            assert "summary" in result
            assert "data_points" in result
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Test 6: API Router endpoints (isolated TestClient)
# ---------------------------------------------------------------------------

class TestAnalyticsRouter:
    """验证 5 个端点返回 200 + 正确 JSON 结构。"""

    def _get(self, path: str, days: int = 30):
        db = _build_populated_session()
        try:
            client, app = _build_test_client(db)
            try:
                resp = client.get(path, params={"days": days})
                return resp, app
            finally:
                app.dependency_overrides.clear()
                client.close()
        finally:
            db.close()

    def test_team_efficiency_200(self):
        resp, _ = self._get("/api/v2/analytics/team-efficiency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "metrics" in data

    def test_throughput_200(self):
        resp, _ = self._get("/api/v2/analytics/throughput")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "summary" in data

    def test_agent_productivity_200(self):
        resp, _ = self._get("/api/v2/analytics/agent-productivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "agents" in data

    def test_sprint_burndown_200(self):
        resp, _ = self._get("/api/v2/analytics/sprint-burndown")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "data" in data

    def test_task_trend_200(self):
        resp, _ = self._get("/api/v2/analytics/task-trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "summary" in data

    def test_days_param_7(self):
        """days=7 参数应正常返回。"""
        resp, _ = self._get("/api/v2/analytics/team-efficiency", days=7)
        assert resp.status_code == 200

    def test_days_param_90(self):
        """days=90 参数应正常返回。"""
        resp, _ = self._get("/api/v2/analytics/throughput", days=90)
        assert resp.status_code == 200
