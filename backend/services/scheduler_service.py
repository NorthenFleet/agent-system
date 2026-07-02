"""
调度服务 — Phase 2: APScheduler 集成 + 真实任务执行
负责定时任务的 CRUD、APScheduler 调度、执行引擎对接。

Dev Spec: DEV-SCHEDULED-TASKS v2.0

Phase 2 新增:
- APScheduler AsyncIOScheduler 集成
- 应用启动时自动加载 active 任务
- 任务状态变更时自动 add/remove job
- 通过 OpenClawTaskExecutor 真实执行任务
- 执行结果回写 execution-logs.json
- 优雅关闭调度器
"""

import fcntl
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from croniter import croniter

from models.scheduled_task import (
    ScheduledTask, TaskStatus, TaskRunStatus, Priority, TriggerType,
    TaskStats, TaskExecutionLog,
    CreateTaskRequest, UpdateTaskRequest,
)
from services.openclaw_task_executor import openclaw_task_executor, ExecutionResult
from path_config import data_path

logger = logging.getLogger(__name__)

# ── 数据文件路径 ──
SCHEDULED_TASKS_FILE = data_path("scheduled-tasks.json")
EXECUTION_LOGS_FILE = data_path("execution-logs.json")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _now() -> datetime:
    return datetime.now().astimezone()


# ── 文件锁保护 ──

def _load_json_with_lock(filepath: str, default: dict) -> dict:
    """带文件锁的 JSON 加载"""
    if not os.path.exists(filepath):
        return default.copy()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return default.copy()


def _save_json_with_lock(filepath: str, data: dict):
    """带文件锁的 JSON 保存（原子写入）"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(tmp_path, filepath)  # 原子替换
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _load_tasks_data() -> dict:
    return _load_json_with_lock(SCHEDULED_TASKS_FILE, {
        "managed_by": "震荡波",
        "manager_role": "团队优化师 - 定时任务总调度",
        "last_updated": _now_iso(),
        "tasks": [],
    })


def _save_tasks_data(data: dict):
    data["last_updated"] = _now_iso()
    _save_json_with_lock(SCHEDULED_TASKS_FILE, data)


def _load_logs_data() -> dict:
    return _load_json_with_lock(EXECUTION_LOGS_FILE, {"logs": []})


def _save_logs_data(data: dict):
    _save_json_with_lock(EXECUTION_LOGS_FILE, data)


def _task_to_dict(task: ScheduledTask) -> dict:
    d = {}
    for k, v in task.model_dump().items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        else:
            d[k] = v
    return d


def _dict_to_task(d: dict) -> ScheduledTask:
    for k in ("last_run", "next_run", "created_at", "updated_at"):
        if k in d and d[k] is not None and isinstance(d[k], str):
            try:
                d[k] = datetime.fromisoformat(d[k])
            except (ValueError, TypeError):
                d[k] = None
    if "command_args" not in d or d["command_args"] is None:
        d["command_args"] = {}
    return ScheduledTask(**d)


def _log_to_dict(log: TaskExecutionLog) -> dict:
    d = {}
    for k, v in log.model_dump().items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        else:
            d[k] = v
    return d


def _dict_to_log(d: dict) -> TaskExecutionLog:
    for k in ("started_at", "finished_at"):
        if k in d and d[k] is not None and isinstance(d[k], str):
            try:
                d[k] = datetime.fromisoformat(d[k])
            except (ValueError, TypeError):
                d[k] = None
    return TaskExecutionLog(**d)


# ── Cron 校验增强 ──

def _validate_cron_field(field: str, min_val: int, max_val: int, field_name: str) -> tuple[bool, str]:
    """校验单个 cron 字段"""
    if field == "*":
        return True, ""

    if "/" in field:
        parts = field.split("/", 1)
        base, step = parts
        try:
            step_val = int(step)
        except ValueError:
            return False, f"{field_name} 步进值 '{step}' 不是有效整数"
        if step_val < 1 or step_val > max_val:
            return False, f"{field_name} 步进值 {step_val} 超出范围 1-{max_val}"
        if base == "*":
            return True, ""
        field = base

    if "," in field:
        for part in field.split(","):
            ok, err = _validate_cron_field(part, min_val, max_val, field_name)
            if not ok:
                return ok, err
        return True, ""

    if "-" in field:
        parts = field.split("-", 1)
        try:
            lo, hi = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return False, f"{field_name} 范围 '{field}' 格式无效"
        if lo < min_val or hi > max_val or lo > hi:
            return False, f"{field_name} 范围 {lo}-{hi} 超出 {min_val}-{max_val}"
        return True, ""

    try:
        val = int(field)
    except ValueError:
        return False, f"{field_name} '{field}' 不是有效数字或通配符"
    if val < min_val or val > max_val:
        return False, f"{field_name} 值 {val} 超出范围 {min_val}-{max_val}"
    return True, ""


def _validate_cron(cron: str) -> tuple[bool, str]:
    """
    完整校验 cron 表达式（5 字段: 分钟 小时 日 月 星期）
    """
    if not cron or not cron.strip():
        return False, "Cron 表达式不能为空"

    parts = cron.strip().split()
    if len(parts) != 5:
        return False, f"Cron 表达式必须包含 5 个字段（分钟 小时 日 月 星期），当前 {len(parts)} 个"

    checks = [
        (parts[0], 0, 59, "分钟"),
        (parts[1], 0, 23, "小时"),
        (parts[2], 1, 31, "日"),
        (parts[3], 1, 12, "月"),
        (parts[4], 0, 7, "星期"),
    ]
    for field, min_v, max_v, name in checks:
        ok, err = _validate_cron_field(field, min_v, max_v, name)
        if not ok:
            return False, err

    return True, ""


# ── 状态机 ──

VALID_TRANSITIONS: dict[TaskStatus, list[TaskStatus]] = {
    TaskStatus.paused: [TaskStatus.active, TaskStatus.disabled],
    TaskStatus.active: [TaskStatus.paused, TaskStatus.disabled],
    TaskStatus.disabled: [TaskStatus.paused],
}


def _can_transition(from_status: TaskStatus, to_status: TaskStatus) -> tuple[bool, str]:
    """检查状态转换是否合法"""
    if from_status == to_status:
        return False, f"任务已是 '{from_status.value}' 状态，无需重复操作"
    allowed = VALID_TRANSITIONS.get(from_status, [])
    if to_status not in allowed:
        return False, f"不允许从 '{from_status.value}' 转换到 '{to_status.value}'"
    return True, ""


class SchedulerService:
    """
    调度服务 — Phase 2

    职责：
      - 定时任务 CRUD + JSON 持久化
      - APScheduler 生命周期管理
      - 任务执行引擎对接
      - 执行日志持久化
    """

    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._initialized = False
        self._migrate_legacy_tasks()

    # ── APScheduler 生命周期 ──

    def init_scheduler(self, event_loop=None):
        """
        初始化 APScheduler

        在 FastAPI startup (async context) 使用 AsyncIOScheduler，
        在同步上下文（如测试/脚本）使用 BackgroundScheduler。
        """
        if self._initialized:
            logger.info("调度器已初始化，跳过")
            return

        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }

        # 尝试 AsyncIOScheduler（需要在 running event loop 中）
        try:
            import asyncio
            asyncio.get_running_loop()  # 会抛 RuntimeError 如果没有 running loop
            self._scheduler = AsyncIOScheduler(
                event_loop=event_loop,
                job_defaults=job_defaults,
            )
            self._scheduler.start(paused=False)
            self._initialized = True
            logger.info("APScheduler (AsyncIO) 调度器已启动")
            return
        except RuntimeError:
            pass  # 没有 running event loop，回退到 BackgroundScheduler

        # 使用 BackgroundScheduler（线程安全，适用于同步/测试环境）
        self._scheduler = BackgroundScheduler(job_defaults=job_defaults)
        self._scheduler.start(paused=False)
        self._initialized = True
        logger.info("APScheduler (Background) 调度器已启动")

    def shutdown_scheduler(self, wait: bool = True):
        """
        优雅关闭调度器

        应在 FastAPI shutdown 事件中调用。
        """
        if self._scheduler and self._initialized:
            self._scheduler.shutdown(wait=wait)
            self._initialized = False
            logger.info("APScheduler 调度器已关闭")

    def is_running(self) -> bool:
        """调度器是否运行中"""
        return self._initialized and self._scheduler is not None and self._scheduler.running

    def load_active_tasks(self):
        """
        加载所有 active 任务到调度器

        应在 startup 中调用（init_scheduler 之后）。
        """
        if not self.is_running():
            logger.warning("调度器未运行，无法加载任务")
            return

        data = _load_tasks_data()
        tasks = data.get("tasks", [])
        loaded = 0

        for task_data in tasks:
            if task_data.get("status") == "active":
                try:
                    self._add_job_to_scheduler(task_data)
                    loaded += 1
                except Exception as e:
                    logger.error(f"加载任务 {task_data['id']} 到调度器失败: {e}")

        logger.info(f"已加载 {loaded} 个 active 任务到调度器")

    def _add_job_to_scheduler(self, task_data: dict):
        """将单个任务添加到 APScheduler"""
        task_id = task_data["id"]
        cron_expr = task_data.get("cron_expression", "")

        if not cron_expr:
            logger.warning(f"任务 {task_id} 无 cron 表达式，跳过调度")
            return

        # 解析 cron 表达式为 APScheduler trigger
        parts = cron_expr.split()
        minute, hour, day, month, day_of_week = parts

        # APScheduler cron trigger 的 day_of_week 中 0=周一, 6=周日
        # 而标准 cron 中 0=周日, 6=周六, 7=周日
        # 需要转换
        dow = self._convert_dow(day_of_week)

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=dow,
            timezone="Asia/Shanghai",
        )

        # 计算下次运行时间
        next_run = trigger.get_next_fire_time(None, _now())

        # 根据调度器类型选择 sync/async 执行函数
        exec_func = self._execute_task_sync
        if isinstance(self._scheduler, AsyncIOScheduler):
            exec_func = self._execute_task

        self._scheduler.add_job(
            func=exec_func,
            trigger=trigger,
            args=[task_id],
            id=f"scheduled_task_{task_id}",
            name=task_data.get("name", task_id),
            replace_existing=True,
        )

        # 更新 next_run
        if next_run:
            self._update_task_next_run(task_id, next_run)

        logger.info(
            f"任务 {task_id} 已加入调度器 — cron={cron_expr}, next_run={next_run}"
        )

    def _convert_dow(self, cron_dow: str) -> str:
        """
        将标准 cron 的 day-of-week 转为 APScheduler 格式。

        标准 cron: 0=周日, 1=周一, ..., 6=周六, 7=周日
        APScheduler: 0=周一, 1=周二, ..., 6=周日

        转换规则: new = (old - 1) % 7
        """
        if cron_dow == "*":
            return "*"

        result = []
        for part in cron_dow.split(","):
            if "/" in part:
                base, step = part.split("/", 1)
                if base == "*":
                    result.append(f"*/{step}")
                else:
                    converted = self._convert_single_dow(base)
                    result.append(f"{converted}/{step}")
            elif "-" in part:
                lo, hi = part.split("-", 1)
                converted_lo = self._convert_single_dow(lo)
                converted_hi = self._convert_single_dow(hi)
                result.append(f"{converted_lo}-{converted_hi}")
            else:
                result.append(self._convert_single_dow(part))

        return ",".join(result)

    def _convert_single_dow(self, val: str) -> str:
        """转换单个 day-of-week 值"""
        try:
            num = int(val)
            return str((num - 1) % 7)
        except ValueError:
            return val

    def _remove_job_from_scheduler(self, task_id: str):
        """从调度器移除任务"""
        if self._scheduler and self._scheduler.running:
            job_id = f"scheduled_task_{task_id}"
            try:
                self._scheduler.remove_job(job_id)
                logger.info(f"任务 {task_id} 已从调度器移除")
            except Exception as e:
                logger.debug(f"移除任务 {task_id} 时（可能不存在）: {e}")

    def _update_task_next_run(self, task_id: str, next_run: datetime):
        """更新任务的 next_run 字段"""
        data = _load_tasks_data()
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                t["next_run"] = next_run.isoformat()
                _save_tasks_data(data)
                break

    # ── 任务执行 ──

    def _execute_task_sync(self, task_id: str):
        """
        APScheduler 回调（同步版）：执行一个定时任务

        由 BackgroundScheduler 调用，在独立线程中运行。
        内部使用 asyncio.run() 执行异步任务。
        """
        import asyncio

        async def _run():
            await self._execute_task(task_id)

        try:
            asyncio.run(_run())
        except Exception as e:
            logger.error(f"任务 {task_id} 同步执行包装异常: {e}", exc_info=True)

    async def _execute_task(self, task_id: str):
        """
        APScheduler 回调（异步版）：执行一个定时任务

        由调度器自动触发，不通过 HTTP。
        """
        logger.info(f"⏰ 调度器触发任务执行: {task_id}")

        # 读取最新任务数据
        task = self.get_task(task_id)
        if not task:
            logger.error(f"任务 {task_id} 不存在，无法执行")
            return

        # 记录执行开始
        execution_id = f"EXEC-{uuid.uuid4().hex[:8]}"
        started = _now()

        # 更新 next_run
        try:
            if self._scheduler and self._scheduler.running:
                job = self._scheduler.get_job(f"scheduled_task_{task_id}")
                if job and job.next_run_time:
                    self._update_task_next_run(task_id, job.next_run_time)
        except Exception as e:
            logger.debug(f"更新 next_run 失败: {e}")

        # 真实执行
        try:
            command = task.get("command", "")
            command_args = task.get("command_args", {}) or {}
            timeout_seconds = task.get("timeout_seconds", 300)

            result: ExecutionResult = await openclaw_task_executor.execute(
                command=command,
                command_args=command_args,
                timeout_seconds=timeout_seconds,
            )

            finished = _now()
            duration_ms = int((finished - started).total_seconds() * 1000)

            # 确定运行状态
            if result.success:
                run_status = TaskRunStatus.success
            else:
                run_status = TaskRunStatus.failed

        except Exception as e:
            finished = _now()
            duration_ms = int((finished - started).total_seconds() * 1000)
            result = ExecutionResult(
                success=False,
                error=f"执行异常: {str(e)}",
                duration_ms=duration_ms,
            )
            run_status = TaskRunStatus.failed
            logger.error(f"任务 {task_id} 执行异常: {e}", exc_info=True)

        # 持久化执行日志
        log = TaskExecutionLog(
            id=execution_id,
            task_id=task_id,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            status=run_status,
            output=result.output or "",
            error=result.error or "",
            trigger_type=TriggerType.scheduled,
        )
        self.add_log(log)

        # 更新任务的 last_run 信息
        self._update_task_last_run(task_id, run_status, duration_ms, started)

        status_icon = "✅" if result.success else "❌"
        logger.info(
            f"{status_icon} 任务 {task_id} 执行完成: "
            f"status={run_status.value}, duration={duration_ms}ms, "
            f"output={result.output[:100] if result.output else '(无)'}"
        )

    def _update_task_last_run(
        self, task_id: str, run_status: TaskRunStatus, duration_ms: int, started: datetime
    ):
        """更新任务的 last_run 信息"""
        data = _load_tasks_data()
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                t["last_run"] = started.isoformat()
                t["last_run_status"] = run_status.value
                t["last_run_duration_ms"] = duration_ms

                if run_status == TaskRunStatus.success:
                    t["success_count"] = t.get("success_count", 0) + 1
                elif run_status in (TaskRunStatus.failed, TaskRunStatus.timeout):
                    t["failure_count"] = t.get("failure_count", 0) + 1

                sc = t.get("success_count", 0)
                fc = t.get("failure_count", 0)
                total = sc + fc
                t["success_rate"] = round(sc / total * 100, 1) if total > 0 else 0.0
                t["updated_at"] = _now_iso()
                _save_tasks_data(data)
                break

    # ── CRUD ──

    def _migrate_legacy_tasks(self):
        """将旧 schema 任务迁移到新 schema"""
        cron_map = {
            "每 30 分钟": "*/30 8-21 * * *",
            "每 3 小时": "0 */3 * * *",
            "每 1 小时": "0 * * * *",
        }
        data = _load_tasks_data()
        changed = False
        for t in data.get("tasks", []):
            if not t.get("cron_expression"):
                old_schedule = t.get("schedule", "")
                t["cron_expression"] = cron_map.get(old_schedule, "0 * * * *")
                if not t.get("schedule_display"):
                    t["schedule_display"] = old_schedule
                t.setdefault("priority", "medium")
                t.setdefault("max_retries", 3)
                t.setdefault("retry_interval_seconds", 60)
                t.setdefault("timeout_seconds", 300)
                t.setdefault("command", "")
                t.setdefault("command_args", {})
                t.setdefault("success_count", 0)
                t.setdefault("failure_count", 0)
                t.setdefault("created_at", _now_iso())
                t.setdefault("updated_at", _now_iso())
                t.setdefault("created_by", "")
                t.setdefault("last_run_status", None)
                t.setdefault("last_run_duration_ms", None)
                changed = True
        if changed:
            _save_tasks_data(data)

    def list_tasks(self) -> list[dict]:
        """获取所有任务列表"""
        data = _load_tasks_data()
        return data.get("tasks", [])

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取单个任务"""
        data = _load_tasks_data()
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                return t
        return None

    def create_task(self, req: CreateTaskRequest) -> dict:
        """创建新任务"""
        data = _load_tasks_data()
        tasks = data.get("tasks", [])

        for t in tasks:
            if t.get("name", "").lower() == req.name.strip().lower():
                raise ValueError(f"任务名称 '{req.name}' 已存在")

        existing_ids = {t["id"] for t in tasks}
        next_num = 1
        while f"TASK-{next_num:03d}" in existing_ids:
            next_num += 1
        task_id = f"TASK-{next_num:03d}"

        now = _now()
        schedule_display = req.schedule_display or _cron_to_display(req.cron_expression)

        task = ScheduledTask(
            id=task_id,
            name=req.name.strip(),
            description=req.description or "",
            owner=req.owner,
            owner_emoji=req.owner_emoji,
            cron_expression=req.cron_expression.strip(),
            schedule_display=schedule_display,
            time_slot=req.time_slot,
            command=req.command,
            command_args=req.command_args or {},
            status=TaskStatus.paused,
            priority=req.priority,
            max_retries=req.max_retries,
            retry_interval_seconds=req.retry_interval_seconds,
            timeout_seconds=req.timeout_seconds,
            created_at=now,
            updated_at=now,
            created_by=req.created_by,
        )

        task_dict = _task_to_dict(task)
        tasks.append(task_dict)
        data["tasks"] = tasks
        _save_tasks_data(data)
        return task_dict

    def update_task(self, task_id: str, req: UpdateTaskRequest) -> Optional[dict]:
        """更新任务配置（单次读取）"""
        data = _load_tasks_data()
        now = _now_iso()
        update_fields = req.model_dump(exclude_unset=True)

        for t in data.get("tasks", []):
            if t["id"] == task_id:
                if "name" in update_fields and update_fields["name"]:
                    new_name = update_fields["name"].strip()
                    for other in data.get("tasks", []):
                        if other["id"] != task_id and other.get("name", "").lower() == new_name.lower():
                            raise ValueError(f"任务名称 '{new_name}' 已被其他任务使用")

                for k, v in update_fields.items():
                    if v is not None:
                        if isinstance(v, str):
                            t[k] = v.strip()
                        else:
                            t[k] = v
                t["updated_at"] = now

                if "cron_expression" in update_fields and update_fields.get("schedule_display") is None:
                    t["schedule_display"] = _cron_to_display(t["cron_expression"])

                _save_tasks_data(data)

                # 如果任务处于 active 状态，需要重新调度
                if t.get("status") == "active" and "cron_expression" in update_fields:
                    try:
                        self._remove_job_from_scheduler(task_id)
                        self._add_job_to_scheduler(t)
                    except Exception as e:
                        logger.error(f"重新调度任务 {task_id} 失败: {e}")

                return t
        return None

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        data = _load_tasks_data()
        original_len = len(data.get("tasks", []))
        data["tasks"] = [t for t in data.get("tasks", []) if t["id"] != task_id]
        if len(data["tasks"]) < original_len:
            _save_tasks_data(data)
            self._remove_job_from_scheduler(task_id)
            return True
        return False

    # ── 状态控制（含调度器联动） ──

    def activate_task(self, task_id: str) -> Optional[dict]:
        """激活任务 — 加入调度器"""
        result = self._set_status(task_id, TaskStatus.active)
        if result:
            # 加入调度器
            try:
                self._add_job_to_scheduler(result)
            except Exception as e:
                logger.error(f"激活任务 {task_id} 加入调度器失败: {e}")
        return result

    def pause_task(self, task_id: str) -> Optional[dict]:
        """暂停任务 — 从调度器移除"""
        result = self._set_status(task_id, TaskStatus.paused)
        if result:
            self._remove_job_from_scheduler(task_id)
        return result

    def disable_task(self, task_id: str) -> Optional[dict]:
        """禁用任务 — 从调度器移除"""
        result = self._set_status(task_id, TaskStatus.disabled)
        if result:
            self._remove_job_from_scheduler(task_id)
        return result

    def _set_status(self, task_id: str, target: TaskStatus) -> Optional[dict]:
        data = _load_tasks_data()
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                from_status = TaskStatus(t.get("status", "paused"))
                ok, err = _can_transition(from_status, target)
                if not ok:
                    raise ValueError(err)

                t["status"] = target.value
                t["updated_at"] = _now_iso()
                _save_tasks_data(data)
                return t
        return None

    # ── 统计 ──

    def get_stats(self) -> dict:
        """获取全局统计"""
        data = _load_tasks_data()
        tasks = data.get("tasks", [])

        total = len(tasks)
        active = sum(1 for t in tasks if t.get("status") == "active")
        paused = sum(1 for t in tasks if t.get("status") == "paused")
        disabled = sum(1 for t in tasks if t.get("status") == "disabled")

        total_success = sum(t.get("success_count", 0) for t in tasks)
        total_failure = sum(t.get("failure_count", 0) for t in tasks)
        total_execs = total_success + total_failure
        overall_rate = round(total_success / total_execs * 100, 1) if total_execs > 0 else 0.0

        logs_data = _load_logs_data()
        today = datetime.now().date().isoformat()
        today_count = sum(
            1 for log in logs_data.get("logs", [])
            if log.get("started_at", "").startswith(today)
        )

        # 最近 5 次运行
        all_logs = sorted(
            logs_data.get("logs", []),
            key=lambda x: x.get("started_at", ""),
            reverse=True,
        )[:5]
        next_five = []
        if self._scheduler and self._scheduler.running:
            jobs = self._scheduler.get_jobs()
            for job in jobs:
                if job.next_run_time:
                    next_five.append({
                        "task_id": job.id.replace("scheduled_task_", ""),
                        "name": job.name,
                        "next_run": job.next_run_time.isoformat(),
                    })
            next_five.sort(key=lambda x: x["next_run"])
            next_five = next_five[:5]

        stats = TaskStats(
            total_tasks=total,
            active_tasks=active,
            paused_tasks=paused,
            disabled_tasks=disabled,
            total_executions_today=today_count,
            success_rate_overall=overall_rate,
            next_five_runs=next_five,
        )
        return stats.to_dict()

    # ── 执行日志 ──

    def get_logs(self, task_id: str, limit: int = 20, offset: int = 0) -> dict:
        """获取任务执行历史"""
        logs_data = _load_logs_data()
        all_logs = logs_data.get("logs", [])
        task_logs = [l for l in all_logs if l.get("task_id") == task_id]
        task_logs.reverse()
        total = len(task_logs)
        page = task_logs[offset: offset + limit]
        return {"logs": page, "total": total}

    def add_log(self, log: TaskExecutionLog) -> dict:
        """添加执行日志"""
        logs_data = _load_logs_data()
        log_dict = _log_to_dict(log)
        logs_data.setdefault("logs", []).append(log_dict)
        _save_logs_data(logs_data)
        return log_dict

    def record_execution(
        self,
        task_id: str,
        trigger_type: TriggerType = TriggerType.manual,
        retry_of: Optional[str] = None,
    ) -> dict:
        """
        记录一次任务执行（手动/重试触发）

        Phase 2: 真实执行而非模拟。
        """
        import asyncio

        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务 {task_id} 不存在")

        execution_id = f"EXEC-{uuid.uuid4().hex[:8]}"
        started = _now()

        command = task.get("command", "")
        command_args = task.get("command_args", {}) or {}
        timeout_seconds = task.get("timeout_seconds", 300)

        async def _run():
            return await openclaw_task_executor.execute(
                command=command,
                command_args=command_args,
                timeout_seconds=timeout_seconds,
            )

        try:
            result: ExecutionResult = asyncio.run(_run())
        except RuntimeError:
            # 已有 running event loop（如 FastAPI async 上下文）
            # 需要获取事件并运行
            loop = asyncio.get_event_loop()
            result: ExecutionResult = loop.run_until_complete(_run())

        finished = _now()
        duration_ms = int((finished - started).total_seconds() * 1000)

        run_status = TaskRunStatus.success if result.success else TaskRunStatus.failed

        log = TaskExecutionLog(
            id=execution_id,
            task_id=task_id,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            status=run_status,
            output=result.output or "",
            error=result.error or "",
            trigger_type=trigger_type,
            retry_of=retry_of,
        )
        log_dict = self.add_log(log)

        self._update_task_last_run(task_id, run_status, duration_ms, started)

        return log_dict

    # ── 调度器状态查询 ──

    def get_scheduler_status(self) -> dict:
        """获取调度器当前状态"""
        if not self._scheduler or not self._scheduler.running:
            return {
                "running": False,
                "jobs": [],
                "job_count": 0,
            }

        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })

        return {
            "running": True,
            "jobs": jobs,
            "job_count": len(jobs),
        }


# ── 工具函数 ──

def _cron_to_display(cron: str) -> str:
    """将 cron 表达式转换为人类可读描述"""
    parts = cron.strip().split()
    if len(parts) < 5:
        return cron

    minute, hour, day, month, dow = parts[0], parts[1], parts[2], parts[3], parts[4]

    if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and dow == "*":
        return f"每 {minute[2:]} 分钟"
    if minute == "0" and hour.startswith("*/") and day == "*" and month == "*" and dow == "*":
        return f"每 {hour[2:]} 小时"
    if minute == "0" and hour == "*" and day == "*" and month == "*" and dow == "*":
        return "每 1 小时"
    if minute == "0" and hour.startswith("0/") and day == "*" and month == "*" and dow == "*":
        return f"每 {hour[2:]} 小时"
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and dow == "*":
        return f"每天 {hour.zfill(2)}:{minute.zfill(2)}"
    if minute == "0" and hour.isdigit() and dow != "*":
        dow_names = {
            "0": "周日", "1": "周一", "2": "周二", "3": "周三",
            "4": "周四", "5": "周五", "6": "周六", "7": "周日",
        }
        dow_str = dow_names.get(dow, dow)
        return f"每周{dow_str} {hour.zfill(2)}:00"

    return f"Cron: {cron}"


# 全局单例
scheduler_service = SchedulerService()
