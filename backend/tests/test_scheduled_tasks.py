"""
定时任务管理 API 测试
Phase 2 — 完整 CRUD + 状态控制 + 执行 + 日志
Dev Spec: DEV-SCHEDULED-TASKS v1.0
"""

import pytest
from httpx import ASGITransport, AsyncClient
from main import app
import json
import os
import shutil

# ── 测试数据文件路径（隔离） ──
TEST_DATA_DIR = os.path.expanduser("~/WorkSpace/team-dashboard/data/test")
TEST_TASKS_FILE = os.path.join(TEST_DATA_DIR, "scheduled-tasks.json")
TEST_LOGS_FILE = os.path.join(TEST_DATA_DIR, "test-execution-logs.json")

# ── 辅助函数 ──
TASKS_FILE_ORIG = None
LOGS_FILE_ORIG = None


def setup_module():
    """测试开始前：备份原文件，创建测试文件"""
    global TASKS_FILE_ORIG, LOGS_FILE_ORIG
    import services.scheduler_service as ss
    TASKS_FILE_ORIG = ss.SCHEDULED_TASKS_FILE
    LOGS_FILE_ORIG = ss.EXECUTION_LOGS_FILE
    ss.SCHEDULED_TASKS_FILE = TEST_TASKS_FILE
    ss.EXECUTION_LOGS_FILE = TEST_LOGS_FILE
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    # 初始空数据
    with open(TEST_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump({"managed_by": "test", "tasks": []}, f)
    with open(TEST_LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"logs": []}, f)
    # 重新初始化 service — 强制从测试文件加载空数据
    ss.scheduler_service = ss.SchedulerService()


def teardown_module():
    """测试结束后：恢复原文件路径"""
    global TASKS_FILE_ORIG, LOGS_FILE_ORIG
    import services.scheduler_service as ss
    ss.SCHEDULED_TASKS_FILE = TASKS_FILE_ORIG
    ss.EXECUTION_LOGS_FILE = LOGS_FILE_ORIG
    # 清理测试文件
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


@pytest.fixture
def client():
    """创建测试客户端"""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


import uuid

_task_counter = [0]


def _unique_name(base="测试任务"):
    """生成唯一任务名，避免测试间冲突"""
    _task_counter[0] += 1
    return f"{base}-{_task_counter[0]}-{uuid.uuid4().hex[:4]}"


@pytest.fixture
def create_task_data():
    """创建任务的默认数据（每次调用生成唯一名称）"""
    return {
        "name": _unique_name("测试任务"),
        "description": "测试用任务",
        "owner": "michelangelo",
        "owner_emoji": "🟧",
        "cron_expression": "0 2 * * *",
        "command": "echo test",
        "command_args": {"target": "/tmp"},
        "priority": "high",
        "max_retries": 3,
        "timeout_seconds": 600,
        "created_by": "michelangelo",
    }


# ==================== 1. 创建任务 ====================

@pytest.mark.asyncio
async def test_create_task(client, create_task_data):
    """测试创建任务"""
    response = await client.post("/api/scheduled-tasks", json=create_task_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"].startswith("测试任务")
    assert data["status"] == "paused"  # 新任务默认 paused
    assert data["priority"] == "high"
    assert data["cron_expression"] == "0 2 * * *"
    assert data["id"].startswith("TASK-")


@pytest.mark.asyncio
async def test_create_task_invalid_cron(client):
    """测试创建任务 — 无效 cron"""
    response = await client.post("/api/scheduled-tasks", json={
        "name": "无效任务",
        "owner": "test",
        "cron_expression": "invalid",
        "command": "echo test",
        "created_by": "test",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_task_missing_fields(client):
    """测试创建任务 — 缺少必填字段"""
    response = await client.post("/api/scheduled-tasks", json={
        "name": "缺少字段",
    })
    assert response.status_code == 422


# ==================== 2. 读取任务 ====================

@pytest.mark.asyncio
async def test_list_tasks(client, create_task_data):
    """测试获取任务列表"""
    # 先创建一个任务
    await client.post("/api/scheduled-tasks", json=create_task_data)

    response = await client.get("/api/scheduled-tasks")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert "stats" in data
    assert len(data["tasks"]) >= 1


@pytest.mark.asyncio
async def test_get_task(client, create_task_data):
    """测试获取任务详情"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.get(f"/api/scheduled-tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == task_id
    assert data["name"].startswith("测试任务")


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    """测试获取不存在的任务"""
    response = await client.get("/api/scheduled-tasks/NOTEXIST")
    assert response.status_code == 404


# ==================== 3. 更新任务 ====================

@pytest.mark.asyncio
async def test_update_task(client, create_task_data):
    """测试更新任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.put(f"/api/scheduled-tasks/{task_id}", json={
        "description": "已更新描述",
        "priority": "medium",
        "max_retries": 5,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "已更新描述"
    assert data["priority"] == "medium"
    assert data["max_retries"] == 5


@pytest.mark.asyncio
async def test_update_task_invalid_cron(client, create_task_data):
    """测试更新任务 — 无效 cron"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.put(f"/api/scheduled-tasks/{task_id}", json={
        "cron_expression": "bad cron"
    })
    assert response.status_code == 400


# ==================== 4. 删除任务 ====================

@pytest.mark.asyncio
async def test_delete_task(client, create_task_data):
    """测试删除任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.delete(f"/api/scheduled-tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # 确认已删除
    response = await client.get(f"/api/scheduled-tasks/{task_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client):
    """测试删除不存在的任务"""
    response = await client.delete("/api/scheduled-tasks/NOTEXIST")
    assert response.status_code == 404


# ==================== 5. 状态控制 ====================

@pytest.mark.asyncio
async def test_activate_task(client, create_task_data):
    """测试激活任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.post(f"/api/scheduled-tasks/{task_id}/activate")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


@pytest.mark.asyncio
async def test_pause_task(client, create_task_data):
    """测试暂停任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    # 先激活
    await client.post(f"/api/scheduled-tasks/{task_id}/activate")
    response = await client.post(f"/api/scheduled-tasks/{task_id}/pause")
    assert response.status_code == 200
    assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_disable_task(client, create_task_data):
    """测试禁用任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.post(f"/api/scheduled-tasks/{task_id}/disable")
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"


# ==================== 6. 手动执行 ====================

@pytest.mark.asyncio
async def test_execute_task(client, create_task_data):
    """测试手动执行任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.post(f"/api/scheduled-tasks/{task_id}/execute")
    assert response.status_code == 200
    data = response.json()
    assert "execution_id" in data
    assert data["status"] in ("queued", "success")


@pytest.mark.asyncio
async def test_execute_task_not_found(client):
    """测试执行不存在的任务"""
    response = await client.post("/api/scheduled-tasks/NOTEXIST/execute")
    assert response.status_code == 404


# ==================== 7. 重试 ====================

@pytest.mark.asyncio
async def test_retry_task(client, create_task_data):
    """测试重试任务"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.post(f"/api/scheduled-tasks/{task_id}/retry")
    assert response.status_code == 200
    data = response.json()
    assert "execution_id" in data
    assert data["status"] in ("queued", "success")


# ==================== 8. 执行日志 ====================

@pytest.mark.asyncio
async def test_get_logs(client, create_task_data):
    """测试获取执行日志"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.get(f"/api/scheduled-tasks/{task_id}/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_logs_with_pagination(client, create_task_data):
    """测试日志分页"""
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    task_id = resp.json()["id"]

    response = await client.get(f"/api/scheduled-tasks/{task_id}/logs?limit=5&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 0


# ==================== 9. Cron 解析 ====================

@pytest.mark.asyncio
async def test_parse_cron(client):
    """测试 Cron 解析"""
    response = await client.post("/api/scheduled-tasks/cron/parse", json={
        "cron_expression": "0 9 * * *"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "display" in data


@pytest.mark.asyncio
async def test_parse_cron_invalid(client):
    """测试无效 Cron 解析"""
    response = await client.post("/api/scheduled-tasks/cron/parse", json={
        "cron_expression": "not a cron"
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_parse_cron_every_30min(client):
    """测试 Cron 解析 — 每 30 分钟"""
    response = await client.post("/api/scheduled-tasks/cron/parse", json={
        "cron_expression": "*/30 * * * *"
    })
    assert response.status_code == 200
    data = response.json()
    assert "每 30 分钟" in data["display"]


# ==================== 10. 统计 ====================

@pytest.mark.asyncio
async def test_get_stats(client, create_task_data):
    """测试获取全局统计"""
    # 创建几个不同状态的任务
    await client.post("/api/scheduled-tasks", json=create_task_data)
    task2 = create_task_data.copy()
    task2["name"] = "第二个任务"
    resp2 = await client.post("/api/scheduled-tasks", json=task2)
    task_id2 = resp2.json()["id"]
    await client.post(f"/api/scheduled-tasks/{task_id2}/activate")

    response = await client.get("/api/scheduled-tasks/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tasks"] >= 2
    assert data["active_tasks"] >= 1


# ==================== 11. 端到端流程 ====================

@pytest.mark.asyncio
async def test_full_lifecycle(client, create_task_data):
    """测试完整生命周期：创建 → 激活 → 执行 → 暂停 → 删除"""
    # 创建
    resp = await client.post("/api/scheduled-tasks", json=create_task_data)
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # 激活
    resp = await client.post(f"/api/scheduled-tasks/{task_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # 手动执行
    resp = await client.post(f"/api/scheduled-tasks/{task_id}/execute")
    assert resp.status_code == 200

    # 暂停
    resp = await client.post(f"/api/scheduled-tasks/{task_id}/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    # 禁用
    resp = await client.post(f"/api/scheduled-tasks/{task_id}/disable")
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    # 删除
    resp = await client.delete(f"/api/scheduled-tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 确认删除
    resp = await client.get(f"/api/scheduled-tasks/{task_id}")
    assert resp.status_code == 404
