"""
task-005-P5-2 — pytest 共享 fixture

为所有后端集成测试提供共享的测试数据库和客户端。
"""
import pytest
from fastapi.testclient import TestClient

# TODO: 实现后取消注释
# from database import get_db, init_test_db
# from main import app


@pytest.fixture
def test_client():
    """创建测试客户端"""
    # init_test_db()
    client = TestClient(app)
    yield client
    # 清理测试数据库
    # Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """创建数据库会话"""
    # session = TestingSessionLocal()
    # try:
    #     yield session
    # finally:
    #     session.close()
    pass


@pytest.fixture
def auth_headers():
    """带 JWT token 的请求头"""
    # token = create_test_token()
    # return {"Authorization": f"Bearer {token}"}
    return {}


@pytest.fixture
def admin_headers():
    """admin 角色的请求头"""
    # token = create_test_token(role="admin")
    # return {"Authorization": f"Bearer {token}"}
    return {}


@pytest.fixture
def sample_task():
    """示例任务数据"""
    return {
        "title": "测试任务",
        "assignee": "测试员",
        "description": "这是一个测试任务",
        "priority": "high",
        "type": "backend"
    }


@pytest.fixture
def sample_agent():
    """示例 Agent 数据"""
    return {
        "id": "test-agent-001",
        "name": "测试Agent",
        "role": "worker",
        "status": "online",
        "team": "ninja_turtles"
    }


@pytest.fixture
def sample_device():
    """示例设备数据"""
    return {
        "name": "test-device",
        "ip": "192.168.1.100",
        "type": "mac-mini",
        "status": "online"
    }
