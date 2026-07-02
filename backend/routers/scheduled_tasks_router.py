"""
定时任务管理 API Router — 完整 CRUD + 状态控制 + 执行 + 日志
Dev Spec: DEV-SCHEDULED-TASKS v1.0

增强修复:
- ValueError 统一捕获为 400
- 执行端点记录真实日志
- 重试端点查找最近失败记录
- 输入校验错误返回清晰提示

API 端点:
  GET    /api/scheduled-tasks              任务列表 + 统计
  GET    /api/scheduled-tasks/stats         全局统计
  POST   /api/scheduled-tasks/cron/parse    Cron 解析
  GET    /api/scheduled-tasks/{task_id}     任务详情
  POST   /api/scheduled-tasks              创建任务
  PUT    /api/scheduled-tasks/{task_id}     更新任务
  DELETE /api/scheduled-tasks/{task_id}     删除任务
  POST   /api/scheduled-tasks/{task_id}/activate  激活
  POST   /api/scheduled-tasks/{task_id}/pause     暂停
  POST   /api/scheduled-tasks/{task_id}/disable   禁用
  POST   /api/scheduled-tasks/{task_id}/execute   手动执行
  POST   /api/scheduled-tasks/{task_id}/retry     重试
  GET    /api/scheduled-tasks/{task_id}/logs      执行历史
  GET    /api/scheduled-tasks/{task_id}/logs/{log_id}  日志详情
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
import uuid

from models.scheduled_task import (
    CreateTaskRequest, UpdateTaskRequest,
    CronParseRequest, CronParseResponse,
    TaskRunStatus, TriggerType,
)
from services.scheduler_service import (
    scheduler_service, _validate_cron, _cron_to_display,
)

router = APIRouter(prefix="/api", tags=["scheduled_tasks"])


def _handle_value_error(e: ValueError) -> HTTPException:
    """将 ValueError 转为 400 HTTPException"""
    return HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────
# ⚠️ 静态路由（/stats, /cron/parse）必须放在
# 动态路由（/{task_id}）之前，否则会被 {task_id} 捕获
# ──────────────────────────────────────────────

# ── 工具（静态路由，必须在 CRUD 之前） ──

@router.get("/scheduled-tasks/stats")
def get_global_stats(period: str = Query(default="today")):
    """获取全局统计（dashboard 概览用）"""
    stats = scheduler_service.get_stats()
    stats["period"] = period
    return stats


@router.post("/scheduled-tasks/cron/parse")
def parse_cron(req: CronParseRequest):
    """解析 cron 表达式，返回人类可读描述和最近执行时间"""
    valid, error = _validate_cron(req.cron_expression)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    display = _cron_to_display(req.cron_expression)

    # Phase 1: 返回占位执行时间，后续用 croniter 计算
    now = datetime.now().astimezone()
    next_runs = [now.isoformat()]

    return {
        "cron_expression": req.cron_expression,
        "display": display,
        "next_runs": next_runs,
        "valid": True,
    }


# ── CRUD ──

@router.get("/scheduled-tasks")
def list_scheduled_tasks():
    """获取所有定时任务列表 + 统计信息"""
    tasks = scheduler_service.list_tasks()
    stats = scheduler_service.get_stats()
    return {"tasks": tasks, "stats": stats}


@router.get("/scheduled-tasks/{task_id}")
def get_scheduled_task(task_id: str):
    """获取单个任务详情"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return task


@router.post("/scheduled-tasks", status_code=201)
def create_scheduled_task(req: CreateTaskRequest):
    """创建新定时任务"""
    # 验证 cron 表达式
    valid, error = _validate_cron(req.cron_expression)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    try:
        task = scheduler_service.create_task(req)
    except ValueError as e:
        raise _handle_value_error(e)
    return task


@router.put("/scheduled-tasks/{task_id}")
def update_scheduled_task(task_id: str, req: UpdateTaskRequest):
    """更新任务配置"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    # 如果更新 cron，先验证
    if req.cron_expression:
        valid, error = _validate_cron(req.cron_expression)
        if not valid:
            raise HTTPException(status_code=400, detail=error)

    try:
        updated = scheduler_service.update_task(task_id, req)
    except ValueError as e:
        raise _handle_value_error(e)
    if not updated:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 更新失败")
    return updated


@router.delete("/scheduled-tasks/{task_id}")
def delete_scheduled_task(task_id: str):
    """删除任务"""
    success = scheduler_service.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return {"ok": True, "message": f"任务 {task_id} 已删除"}


# ── 状态控制 ──

@router.post("/scheduled-tasks/{task_id}/activate")
def activate_task_endpoint(task_id: str):
    """激活任务（active 状态，加入调度器）"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    try:
        result = scheduler_service.activate_task(task_id)
    except ValueError as e:
        raise _handle_value_error(e)
    if not result:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return result


@router.post("/scheduled-tasks/{task_id}/pause")
def pause_task_endpoint(task_id: str):
    """暂停任务（paused 状态，从调度器移除）"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    try:
        result = scheduler_service.pause_task(task_id)
    except ValueError as e:
        raise _handle_value_error(e)
    if not result:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return result


@router.post("/scheduled-tasks/{task_id}/disable")
def disable_task_endpoint(task_id: str):
    """禁用任务（disabled 状态，保留数据但不参与调度）"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    try:
        result = scheduler_service.disable_task(task_id)
    except ValueError as e:
        raise _handle_value_error(e)
    if not result:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return result


# ── 执行 ──

@router.post("/scheduled-tasks/{task_id}/execute")
def execute_task_manually(task_id: str):
    """手动触发一次执行（立即执行，不受 cron 限制）"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    try:
        log = scheduler_service.record_execution(
            task_id, trigger_type=TriggerType.manual
        )
    except ValueError as e:
        raise _handle_value_error(e)

    return {
        "execution_id": log["id"],
        "task_id": task_id,
        "status": log["status"],
        "started_at": log["started_at"],
        "finished_at": log["finished_at"],
        "duration_ms": log["duration_ms"],
        "message": "手动执行已完成",
    }


@router.post("/scheduled-tasks/{task_id}/retry")
def retry_task(task_id: str):
    """对最近一次失败的任务进行重试"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    # 查找最近一次失败的日志
    logs_result = scheduler_service.get_logs(task_id, limit=10)
    last_failed = None
    for log in logs_result.get("logs", []):
        if log.get("status") in ("failed", "timeout"):
            last_failed = log
            break

    try:
        log = scheduler_service.record_execution(
            task_id,
            trigger_type=TriggerType.retry,
            retry_of=last_failed["id"] if last_failed else None,
        )
    except ValueError as e:
        raise _handle_value_error(e)

    return {
        "execution_id": log["id"],
        "task_id": task_id,
        "status": log["status"],
        "retry_of": last_failed["id"] if last_failed else None,
        "message": "重试已完成" if last_failed else "重试已执行（未找到失败记录）",
    }


# ── 日志 ──

@router.get("/scheduled-tasks/{task_id}/logs")
def get_task_logs(
    task_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """获取任务执行历史"""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    result = scheduler_service.get_logs(task_id, limit=limit, offset=offset)
    return result


@router.get("/scheduled-tasks/{task_id}/logs/{log_id}")
def get_task_log_detail(task_id: str, log_id: str):
    """获取单次执行的完整日志"""
    logs_data = scheduler_service.get_logs(task_id, limit=500)
    for log in logs_data.get("logs", []):
        if log.get("id") == log_id:
            return log
    raise HTTPException(status_code=404, detail=f"日志 {log_id} 不存在")
