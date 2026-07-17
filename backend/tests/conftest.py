"""
pytest 共享 fixture — 为所有后端集成测试提供共享的测试数据库和客户端。
"""
import os
import tempfile
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models.v2_models import Base
from main import app

# Test database must be set before any database import
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='_test.db')}"

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def test_engine():
    return create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    Base.metadata.create_all(bind=test_engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session(test_session_factory):
    session = test_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_client(db_session):
    from database import get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    from fastapi.testclient import TestClient
    client = TestClient(app)
    yield client
    client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    from models.v2_models import User
    from services.auth_service import hash_password

    existing = db_session.query(User).filter(User.username == "admin").first()
    if existing:
        return existing

    user = User(
        username="admin",
        password_hash=hash_password("test123"),
        display_name="测试管理员",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_client, admin_user):
    response = test_client.post(
        "/api/v2/auth/login",
        json={"username": "admin", "password": "test123"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_task(db_session):
    from models.v2_models import Task
    from datetime import datetime, timezone

    existing = db_session.query(Task).filter(Task.task_id == "task-test-001").first()
    if existing:
        return existing

    task = Task(
        task_id="task-test-001",
        title="测试任务",
        description="这是一个测试任务",
        type="backend",
        status="pending",
        priority="high",
        assignee="admin",
        sprint=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def sample_agent(db_session):
    from models.v2_models import AgentHeartbeat
    from datetime import datetime, timezone

    heartbeat = AgentHeartbeat(
        agent_id="test-agent-001",
        status="online",
        cpu_usage=25.5,
        memory_usage=60.2,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(heartbeat)
    db_session.commit()
    db_session.refresh(heartbeat)
    return heartbeat
