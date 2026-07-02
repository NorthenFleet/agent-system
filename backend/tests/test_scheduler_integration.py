"""
定时任务调度引擎集成测试
Phase 2: 验证调度器启动、任务加载、真实执行

运行: pytest backend/tests/test_scheduler_integration.py -v
"""

import asyncio
import json
import os
import sys
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

# 添加 backend 到路径
BACKEND_DIR = os.path.expanduser("~/WorkSpace/team-dashboard/backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.scheduler_service import (
    SchedulerService, _validate_cron, _cron_to_display,
    _load_tasks_data, _save_tasks_data, _load_logs_data, _save_logs_data,
    SCHEDULED_TASKS_FILE, EXECUTION_LOGS_FILE,
)
from services.openclaw_task_executor import OpenClawTaskExecutor, ExecutionResult
from models.scheduled_task import TaskStatus, TaskRunStatus, TriggerType


# ── 测试数据 ──

TEST_TASKS_FILE = os.path.expanduser("~/WorkSpace/team-dashboard/data/test-scheduled-tasks.json")
TEST_LOGS_FILE = os.path.expanduser("~/WorkSpace/team-dashboard/data/test-execution-logs.json")

SAMPLE_ACTIVE_TASK = {
    "id": "TEST-001",
    "name": "测试任务 - 每分钟执行",
    "description": "集成测试用任务",
    "owner": "测试",
    "owner_emoji": "🧪",
    "cron_expression": "* * * * *",
    "schedule_display": "每 1 分钟",
    "time_slot": "全天 24 小时",
    "command": "echo",
    "command_args": {"message": "Hello from scheduler test"},
    "status": "active",
    "priority": "medium",
    "max_retries": 3,
    "retry_interval_seconds": 60,
    "timeout_seconds": 30,
    "last_run": None,
    "last_run_status": None,
    "last_run_duration_ms": None,
    "next_run": None,
    "success_count": 0,
    "failure_count": 0,
    "success_rate": 0.0,
    "created_at": datetime.now().astimezone().isoformat(),
    "updated_at": datetime.now().astimezone().isoformat(),
    "created_by": "test",
}

SAMPLE_PAUSED_TASK = {
    **SAMPLE_ACTIVE_TASK,
    "id": "TEST-002",
    "name": "测试任务 - 已暂停",
    "status": "paused",
    "cron_expression": "*/10 * * * *",
}


def _setup_test_data():
    """准备测试数据文件"""
    tasks_data = {
        "managed_by": "test",
        "last_updated": datetime.now().astimezone().isoformat(),
        "tasks": [SAMPLE_ACTIVE_TASK, SAMPLE_PAUSED_TASK],
    }
    _save_json_with_lock_override(TEST_TASKS_FILE, tasks_data)
    _save_json_with_lock_override(TEST_LOGS_FILE, {"logs": []})


def _save_json_with_lock_override(filepath: str, data: dict):
    """测试用简化保存（不使用全局路径）"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_json_override(filepath: str, default: dict) -> dict:
    """测试用简化加载"""
    if not os.path.exists(filepath):
        return default.copy()
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


class TestCronValidation:
    """Cron 表达式校验测试"""

    def test_valid_simple(self):
        assert _validate_cron("* * * * *") == (True, "")
        assert _validate_cron("0 * * * *") == (True, "")
        assert _validate_cron("*/10 * * * *") == (True, "")
        assert _validate_cron("0 */3 * * *") == (True, "")
        assert _validate_cron("*/30 8-21 * * *") == (True, "")
        assert _validate_cron("0 9 * * 1") == (True, "")

    def test_valid_complex(self):
        assert _validate_cron("0,30 9-17 * * 1-5") == (True, "")
        assert _validate_cron("15 2 1,15 * *") == (True, "")
        assert _validate_cron("0 0 1 1 *") == (True, "")

    def test_invalid_empty(self):
        ok, err = _validate_cron("")
        assert not ok
        assert "不能为空" in err

    def test_invalid_fields(self):
        ok, err = _validate_cron("0 * * *")
        assert not ok
        assert "5 个字段" in err

    def test_invalid_value(self):
        ok, err = _validate_cron("60 * * * *")
        assert not ok
        assert "超出范围" in err

        ok, err = _validate_cron("* 25 * * *")
        assert not ok

        ok, err = _validate_cron("* * 32 * *")
        assert not ok

    def test_invalid_step(self):
        ok, err = _validate_cron("*/0 * * * *")
        assert not ok
        assert "超出范围" in err


class TestCronDisplay:
    """Cron 可读化测试"""

    def test_every_n_minutes(self):
        assert "每 30 分钟" in _cron_to_display("*/30 * * * *")
        assert "每 10 分钟" in _cron_to_display("*/10 * * * *")

    def test_every_n_hours(self):
        assert "每 3 小时" in _cron_to_display("0 */3 * * *")
        assert "每 1 小时" in _cron_to_display("0 * * * *")

    def test_daily(self):
        display = _cron_to_display("0 9 * * *")
        assert "每天" in display
        assert "09:00" in display

    def test_weekly(self):
        display = _cron_to_display("0 10 * * 1")
        assert "每周" in display


class TestOpenClawTaskExecutor:
    """OpenClaw 任务执行器测试"""

    @pytest.fixture
    def executor(self):
        return OpenClawTaskExecutor(default_timeout=10)

    @pytest.mark.asyncio
    async def test_execute_echo(self, executor):
        """测试 echo 命令"""
        result = await executor.execute(
            command="echo",
            command_args={"message": "Hello Test"},
            timeout_seconds=10,
        )
        assert result.success
        assert "Hello Test" in result.output
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_empty_command(self, executor):
        """测试空命令（模拟执行）"""
        result = await executor.execute(
            command="",
            command_args={},
            timeout_seconds=10,
        )
        assert result.success
        assert "模拟执行" in result.output

    @pytest.mark.asyncio
    async def test_execute_shell(self, executor):
        """测试 shell 命令"""
        result = await executor.execute(
            command="shell",
            command_args={"command": "echo hello_world"},
            timeout_seconds=10,
        )
        assert result.success
        assert "hello_world" in result.output

    @pytest.mark.asyncio
    async def test_execute_shell_failure(self, executor):
        """测试 shell 命令失败"""
        result = await executor.execute(
            command="shell",
            command_args={"command": "exit 1"},
            timeout_seconds=10,
        )
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_execute_agent_run_no_agent_id(self, executor):
        """测试 agent_run 缺少参数"""
        result = await executor.execute(
            command="agent_run",
            command_args={"message": "test"},
            timeout_seconds=10,
        )
        assert not result.success
        assert "agent_id" in result.error

    @pytest.mark.asyncio
    async def test_execute_agent_run_no_message(self, executor):
        """测试 agent_run 缺少 message"""
        result = await executor.execute(
            command="agent_run",
            command_args={"agent_id": "bumblebee"},
            timeout_seconds=10,
        )
        assert not result.success
        assert "message" in result.error

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self, executor):
        """测试未知命令"""
        result = await executor.execute(
            command="unknown_cmd",
            command_args={},
            timeout_seconds=10,
        )
        assert not result.success
        assert "未知命令" in result.error


class TestSchedulerService:
    """调度服务 CRUD 测试"""

    def test_validate_cron(self):
        ok, _ = _validate_cron("*/10 * * * *")
        assert ok

        ok, err = _validate_cron("invalid")
        assert not ok

    def test_dict_to_task_conversion(self):
        from services.scheduler_service import _dict_to_task

        d = {
            "id": "TEST-001",
            "name": "Test Task",
            "owner": "test",
            "cron_expression": "*/10 * * * *",
            "status": "active",
            "command": "echo",
            "command_args": {"message": "hello"},
            "created_at": datetime.now().astimezone().isoformat(),
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        task = _dict_to_task(d)
        assert task.id == "TEST-001"
        assert task.name == "Test Task"
        assert task.command_args == {"message": "hello"}


class TestSchedulerEngineIntegration:
    """调度引擎集成测试"""

    def test_scheduler_init(self):
        """测试调度器初始化"""
        service = SchedulerService()
        assert not service.is_running()
        assert service._scheduler is None

    def test_scheduler_lifecycle(self):
        """测试调度器启动和关闭"""
        service = SchedulerService()

        # 启动
        service.init_scheduler()
        assert service.is_running()
        assert service._scheduler is not None

        # 关闭
        service.shutdown_scheduler(wait=False)
        assert not service.is_running()

    def test_load_active_tasks_on_startup(self):
        """测试启动时加载 active 任务"""
        service = SchedulerService()

        # 备份原数据
        orig_data = _load_json_override(SCHEDULED_TASKS_FILE, {"tasks": []})

        try:
            # 设置测试数据
            test_data = {
                "managed_by": "test",
                "last_updated": datetime.now().astimezone().isoformat(),
                "tasks": [SAMPLE_ACTIVE_TASK, SAMPLE_PAUSED_TASK],
            }
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, test_data)

            # 启动调度器并加载任务
            service.init_scheduler()
            service.load_active_tasks()

            # 验证任务被加载
            jobs = service._scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            assert "scheduled_task_TEST-001" in job_ids
            # 暂停任务不应被加载
            assert "scheduled_task_TEST-002" not in job_ids

            service.shutdown_scheduler(wait=False)

        finally:
            # 恢复原数据
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, orig_data)

    def test_activate_task_adds_to_scheduler(self):
        """测试激活任务时加入调度器"""
        service = SchedulerService()

        # 备份原数据
        orig_data = _load_json_override(SCHEDULED_TASKS_FILE, {"tasks": []})

        try:
            # 初始数据
            test_data = {
                "managed_by": "test",
                "last_updated": datetime.now().astimezone().isoformat(),
                "tasks": [dict(SAMPLE_PAUSED_TASK)],  # 初始为 paused
            }
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, test_data)

            service.init_scheduler()
            service.load_active_tasks()

            # 初始无 active job
            job_ids = [j.id for j in service._scheduler.get_jobs()]
            assert "scheduled_task_TEST-002" not in job_ids

            # 激活任务
            service.activate_task("TEST-002")

            # 验证任务被加入调度器
            job_ids = [j.id for j in service._scheduler.get_jobs()]
            assert "scheduled_task_TEST-002" in job_ids

            service.shutdown_scheduler(wait=False)

        finally:
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, orig_data)

    def test_pause_task_removes_from_scheduler(self):
        """测试暂停任务时从调度器移除"""
        service = SchedulerService()

        orig_data = _load_json_override(SCHEDULED_TASKS_FILE, {"tasks": []})

        try:
            test_data = {
                "managed_by": "test",
                "last_updated": datetime.now().astimezone().isoformat(),
                "tasks": [dict(SAMPLE_ACTIVE_TASK)],
            }
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, test_data)

            service.init_scheduler()
            service.load_active_tasks()

            # 验证在调度器中
            job_ids = [j.id for j in service._scheduler.get_jobs()]
            assert "scheduled_task_TEST-001" in job_ids

            # 暂停
            service.pause_task("TEST-001")

            # 验证不在调度器中
            job_ids = [j.id for j in service._scheduler.get_jobs()]
            assert "scheduled_task_TEST-001" not in job_ids

            service.shutdown_scheduler(wait=False)

        finally:
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, orig_data)

    def test_task_execution_logs_written(self):
        """测试任务执行日志被正确写入"""
        service = SchedulerService()

        # 备份日志
        orig_logs = _load_json_override(EXECUTION_LOGS_FILE, {"logs": []})

        try:
            _save_json_with_lock_override(EXECUTION_LOGS_FILE, {"logs": []})

            # 模拟执行记录
            log_dict = service.record_execution(
                task_id="TASK-006",  # 现有任务，command="echo test"
                trigger_type=TriggerType.manual,
            )

            assert log_dict["task_id"] == "TASK-006"
            assert log_dict["status"] in ("success", "failed")
            assert log_dict["duration_ms"] >= 0

            # 验证日志文件中有记录
            logs_data = _load_json_override(EXECUTION_LOGS_FILE, {"logs": []})
            task_logs = [l for l in logs_data.get("logs", []) if l["task_id"] == "TASK-006"]
            assert len(task_logs) >= 1

        finally:
            _save_json_with_lock_override(EXECUTION_LOGS_FILE, orig_logs)

    def test_scheduler_status_endpoint(self):
        """测试调度器状态查询"""
        service = SchedulerService()

        # 未启动时
        status = service.get_scheduler_status()
        assert status["running"] is False
        assert status["job_count"] == 0

        # 启动后
        service.init_scheduler()
        status = service.get_scheduler_status()
        assert status["running"] is True

        service.shutdown_scheduler(wait=False)

    def test_get_stats(self):
        """测试统计信息"""
        service = SchedulerService()

        orig_data = _load_json_override(SCHEDULED_TASKS_FILE, {"tasks": []})
        orig_logs = _load_json_override(EXECUTION_LOGS_FILE, {"logs": []})

        try:
            test_data = {
                "managed_by": "test",
                "last_updated": datetime.now().astimezone().isoformat(),
                "tasks": [SAMPLE_ACTIVE_TASK, SAMPLE_PAUSED_TASK],
            }
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, test_data)

            stats = service.get_stats()
            assert stats["total_tasks"] == 2
            assert stats["active_tasks"] == 1
            assert stats["paused_tasks"] == 1

        finally:
            _save_json_with_lock_override(SCHEDULED_TASKS_FILE, orig_data)
            _save_json_with_lock_override(EXECUTION_LOGS_FILE, orig_logs)


class TestExecutionResult:
    """执行结果模型测试"""

    def test_to_dict(self):
        result = ExecutionResult(
            success=True,
            output="Hello",
            error="",
            duration_ms=100,
            exit_code=0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "Hello"
        assert d["duration_ms"] == 100

    def test_repr(self):
        success_result = ExecutionResult(success=True, duration_ms=50)
        assert "✓" in repr(success_result)

        fail_result = ExecutionResult(success=False, error="oops", duration_ms=10)
        assert "✗" in repr(fail_result)
