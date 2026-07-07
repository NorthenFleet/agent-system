"""
task-P4-B-001 — agents_router heartbeat 端点 WS 推送测试

目标:
1. POST /api/v2/agents/{id}/heartbeat 返回 ws_pushed / ws_clients_notified
2. WS 连接客户端收到 heartbeat_update 推送消息
3. heartbeat_data 包含 agent_id, status, cpu_usage, memory_usage, timestamp
4. 测试覆盖率 80%+

@author 🟥 拉斐尔 (后端开发)
"""
import sys, os, pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app
from models.v2_models import get_session, Base, get_engine, User
from services.auth_service import hash_password
from websocket_manager import manager as ws_manager


@pytest.fixture(autouse=True)
def _reset_ws_manager():
    """每个测试前重置 WS manager 状态（包括限频缓存）"""
    ws_manager._connections.clear()
    ws_manager._ws_to_conn_id.clear()
    ws_manager._conn_id_counter = 0
    ws_manager._last_push_time.clear()
    yield


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


def _login(client):
    """登录并返回 token"""
    db = get_session()
    _ensure_admin(db)
    db.close()
    resp = client.post("/api/v2/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _drain_ws(ws):
    """读取并丢弃所有已到达的 WS 消息，返回最后一条"""
    last = None
    try:
        while True:
            ws.settimeout(0.1)
            msg = ws.receive_json()
            last = msg
    except Exception:
        pass
    return last


class TestHeartbeatWsPush:
    """测试 POST /api/v2/agents/{id}/heartbeat WS 推送"""

    def test_heartbeat_returns_ws_push_fields(self):
        """心跳响应包含 ws_pushed 和 ws_clients_notified 字段"""
        client = TestClient(app)
        token = _login(client)

        resp = client.post("/api/v2/agents/leonardo/heartbeat", json={
            "agent_id": "leonardo",
            "agent_name": "李奥纳多",
            "status": "online",
            "cpu_usage": 25.5,
            "memory_usage": 42.0,
            "task_queue_len": 3,
        }, headers=_headers(token))

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "ws_pushed" in data
        assert "ws_clients_notified" in data
        # 没有 WS 客户端连接时，ws_pushed 应为 False
        assert data["ws_pushed"] is False
        assert data["ws_clients_notified"] == 0

    def test_heartbeat_data_has_required_fields(self):
        """heartbeat_data 包含 agent_id, status, cpu_usage, memory_usage, timestamp"""
        client = TestClient(app)
        token = _login(client)

        with client.websocket_connect("/ws/status") as ws:
            # 接收连接确认消息 (type=connected)
            msg = ws.receive_json()
            assert msg["type"] == "connected"

            # 连接后 WS 端点会 send_to_all status_update，先消耗掉
            msg2 = ws.receive_json()
            assert msg2["type"] == "status_update"

            # 发送心跳
            resp = client.post("/api/v2/agents/raphael/heartbeat", json={
                "agent_id": "raphael",
                "agent_name": "拉斐尔",
                "status": "online",
                "cpu_usage": 18.3,
                "memory_usage": 55.7,
                "task_queue_len": 0,
            }, headers=_headers(token))

            assert resp.status_code == 200
            data = resp.json()
            assert data["ws_pushed"] is True
            assert data["ws_clients_notified"] >= 1

            # WS 客户端应收到 heartbeat_update 推送
            pushed = ws.receive_json()
            assert pushed["type"] == "heartbeat_update", f"Expected heartbeat_update, got {pushed}"
            hb_data = pushed["data"]
            assert hb_data["agent_id"] == "raphael"
            assert hb_data["status"] == "online"
            assert hb_data["cpu_usage"] == 18.3
            assert hb_data["memory_usage"] == 55.7
            # timestamp 在顶层或 data 中
            ts = pushed.get("timestamp") or hb_data.get("timestamp")
            assert ts is not None, "heartbeat 推送消息缺少 timestamp"

    def test_heartbeat_push_multiple_clients(self):
        """多个 WS 客户端都收到心跳推送"""
        client = TestClient(app)
        token = _login(client)

        with client.websocket_connect("/ws/status") as ws1:
            ws1.receive_json()  # connected
            ws1.receive_json()  # status_update

            with client.websocket_connect("/ws/status") as ws2:
                ws2.receive_json()  # connected
                ws2.receive_json()  # status_update

                resp = client.post("/api/v2/agents/donatello/heartbeat", json={
                    "agent_id": "donatello",
                    "agent_name": "多纳泰罗",
                    "status": "busy",
                    "cpu_usage": 75.0,
                    "memory_usage": 80.0,
                    "task_queue_len": 5,
                }, headers=_headers(token))

                assert resp.status_code == 200
                data = resp.json()
                assert data["ws_pushed"] is True
                assert data["ws_clients_notified"] >= 2

                # ws2 connect triggers send_to_all status_update which ws1 also receives;
                # drain non-heartbeat messages, then check for heartbeat_update
                def expect_heartbeat(ws, label):
                    msg = ws.receive_json()
                    if msg["type"] == "heartbeat_update":
                        return msg
                    # drain one more (likely status_update from other client connect)
                    msg2 = ws.receive_json()
                    assert msg2["type"] == "heartbeat_update", f"{label} got {msg2} (after draining {msg['type']})"
                    return msg2

                msg1 = expect_heartbeat(ws1, "ws1")
                msg2 = expect_heartbeat(ws2, "ws2")
                assert msg1["data"]["agent_id"] == "donatello"
                assert msg2["data"]["agent_id"] == "donatello"

    def test_heartbeat_mismatch_agent_id(self):
        """路径 agent_id 与请求体不一致时返回 400"""
        client = TestClient(app)
        token = _login(client)

        resp = client.post("/api/v2/agents/wrong-id/heartbeat", json={
            "agent_id": "leonardo",
            "agent_name": "李奥纳多",
            "status": "online",
        }, headers=_headers(token))

        assert resp.status_code == 400

    def test_heartbeat_requires_auth(self):
        """未认证访问心跳端点返回 401"""
        client = TestClient(app)

        resp = client.post("/api/v2/agents/leonardo/heartbeat", json={
            "agent_id": "leonardo",
            "agent_name": "李奥纳多",
            "status": "online",
        })

        assert resp.status_code == 401


class TestHeartbeatDataCompleteness:
    """测试心跳推送数据的完整性"""

    def test_push_with_optional_fields(self):
        """推送包含可选字段 (current_task, metadata)"""
        client = TestClient(app)
        token = _login(client)

        with client.websocket_connect("/ws/status") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # status_update

            resp = client.post("/api/v2/agents/michelangelo/heartbeat", json={
                "agent_id": "michelangelo",
                "agent_name": "米开朗基罗",
                "status": "busy",
                "current_task": "task-P5-T-001",
                "cpu_usage": 30.0,
                "memory_usage": 45.0,
                "task_queue_len": 2,
                "metadata": {"runner": "pytest", "env": "test"},
            }, headers=_headers(token))

            assert resp.status_code == 200
            pushed = ws.receive_json()
            assert pushed["type"] == "heartbeat_update"
            hb_data = pushed["data"]
            assert hb_data["agent_id"] == "michelangelo"
            assert hb_data["current_task"] == "task-P5-T-001"
            assert hb_data["task_queue_len"] == 2

    def test_push_timestamp_is_iso_format(self):
        """推送消息中的 timestamp 为 ISO 格式"""
        client = TestClient(app)
        token = _login(client)

        with client.websocket_connect("/ws/status") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # status_update

            client.post("/api/v2/agents/test-ts/heartbeat", json={
                "agent_id": "test-ts",
                "agent_name": "测试时间戳",
                "status": "online",
                "cpu_usage": 10.0,
                "memory_usage": 20.0,
            }, headers=_headers(token))

            pushed = ws.receive_json()
            assert pushed["type"] == "heartbeat_update"
            # timestamp 可能在顶层或 data 中
            ts = pushed.get("timestamp") or pushed.get("data", {}).get("timestamp")
            assert ts is not None
            # 验证是 ISO 格式 (包含 T)
            assert "T" in ts

    def test_push_type_is_heartbeat_update(self):
        """推送消息 type 字段必须是 heartbeat_update"""
        client = TestClient(app)
        token = _login(client)

        with client.websocket_connect("/ws/status") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # status_update

            client.post("/api/v2/agents/type-check/heartbeat", json={
                "agent_id": "type-check",
                "agent_name": "类型检查",
                "status": "online",
                "cpu_usage": 5.0,
                "memory_usage": 10.0,
            }, headers=_headers(token))

            pushed = ws.receive_json()
            assert pushed["type"] == "heartbeat_update"
