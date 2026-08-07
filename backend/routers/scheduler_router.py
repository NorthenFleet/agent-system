"""
统一任务调度 API — Airflow 代理网关

将 Airflow 的任务调度能力融合进 3021 系统，前端通过 /api/v2/scheduler/* 统一访问。
"""
from __future__ import annotations

import os
from typing import Optional, List, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/v2/scheduler",
    tags=["scheduler"],
    responses={
        401: {"description": "未登录或 Token 无效"},
        404: {"description": "调度任务不存在"},
    },
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AIRFLOW_URL = os.getenv("AIRFLOW_URL", "http://localhost:8080")
AIRFLOW_USER = os.getenv("AIRFLOW_USER", "airflow")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "airflow")

AUTH = (AIRFLOW_USER, AIRFLOW_PASSWORD)
TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_json(response: httpx.Response) -> Any:
    """Parse JSON or raise HTTPException with upstream error."""
    if response.status_code >= 400:
        detail = response.text[:500] if response.text else f"HTTP {response.status_code}"
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


async def _airflow_get(path: str) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{AIRFLOW_URL}/api/v1{path}", auth=AUTH)
        return _safe_json(resp)


async def _airflow_post(path: str, json: Optional[Dict] = None) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{AIRFLOW_URL}/api/v1{path}", auth=AUTH, json=json or {})
        return _safe_json(resp)


async def _airflow_patch(path: str, json: Optional[Dict] = None) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.patch(f"{AIRFLOW_URL}/api/v1{path}", auth=AUTH, json=json or {})
        return _safe_json(resp)


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------
class SchedulerDagSummary(BaseModel):
    dag_id: str
    dag_display_name: str
    is_paused: bool
    schedule_interval: Optional[str] = None
    last_run_state: Optional[str] = None
    last_run_start: Optional[str] = None
    last_run_end: Optional[str] = None


class SchedulerStatus(BaseModel):
    healthy: bool
    airflow_url: str
    dags: List[SchedulerDagSummary]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=SchedulerStatus, summary="调度系统状态")
async def get_scheduler_status():
    """获取 Airflow 调度系统状态 + 所有 DAG 概览"""
    try:
        dags_resp = await _airflow_get("/dags?limit=100")
    except Exception as e:
        return SchedulerStatus(
            healthy=False,
            airflow_url=AIRFLOW_URL,
            dags=[],
        )

    dag_summaries = []
    for dag in dags_resp.get("dags", []):
        # Get last run for each DAG
        last_run_state = None
        last_run_start = None
        last_run_end = None
        try:
            runs = await _airflow_get(f"/dags/{dag['dag_id']}/dagRuns?limit=1&order_by=-start_date")
            if runs.get("dag_runs"):
                lr = runs["dag_runs"][0]
                last_run_state = lr.get("state")
                last_run_start = lr.get("start_date")
                last_run_end = lr.get("end_date")
        except Exception:
            pass

        schedule = dag.get("schedule_interval", {})
        schedule_val = schedule.get("value") if isinstance(schedule, dict) else str(schedule)

        dag_summaries.append(SchedulerDagSummary(
            dag_id=dag["dag_id"],
            dag_display_name=dag.get("dag_display_name", dag["dag_id"]),
            is_paused=dag.get("is_paused", True),
            schedule_interval=schedule_val,
            last_run_state=last_run_state,
            last_run_start=last_run_start,
            last_run_end=last_run_end,
        ))

    return SchedulerStatus(
        healthy=True,
        airflow_url=AIRFLOW_URL,
        dags=dag_summaries,
    )


@router.get("/dags", summary="获取所有 DAG")
async def list_dags(limit: int = Query(50, ge=1, le=500)):
    """获取所有 DAG 列表"""
    return await _airflow_get(f"/dags?limit={limit}")


@router.get("/dags/{dag_id}", summary="获取 DAG 详情")
async def get_dag(dag_id: str):
    """获取单个 DAG 的详细信息"""
    return await _airflow_get(f"/dags/{dag_id}")


class DagPatchRequest(BaseModel):
    is_paused: bool = Field(..., description="是否暂停调度")

@router.patch("/dags/{dag_id}", summary="暂停/恢复 DAG")
async def patch_dag(dag_id: str, body: DagPatchRequest):
    """暂停或恢复 DAG 调度"""
    return await _airflow_patch(f"/dags/{dag_id}", json={"is_paused": body.is_paused})


@router.get("/dags/{dag_id}/dagRuns", summary="获取 DAG 运行历史")
async def list_dag_runs(
    dag_id: str,
    limit: int = Query(20, ge=1, le=100),
    state: Optional[str] = Query(None),
):
    """获取 DAG 的历史运行记录"""
    params = f"limit={limit}"
    if state:
        params += f"&state={state}"
    return await _airflow_get(f"/dags/{dag_id}/dagRuns?{params}")


@router.post("/dags/{dag_id}/dagRuns", summary="触发 DAG 运行")
async def trigger_dag_run(dag_id: str, note: Optional[str] = None):
    """手动触发一次 DAG 运行"""
    conf = {"triggered_by": "3021_ui"}
    if note:
        conf["note"] = note
    return await _airflow_post(f"/dags/{dag_id}/dagRuns", json={"conf": conf, "note": note})


@router.get("/dags/{dag_id}/dagRuns/{dag_run_id}", summary="获取单次运行详情")
async def get_dag_run(dag_id: str, dag_run_id: str):
    """获取单次 DAG 运行的详细信息"""
    return await _airflow_get(f"/dags/{dag_id}/dagRuns/{dag_run_id}")


@router.get("/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances", summary="获取任务实例")
async def list_task_instances(dag_id: str, dag_run_id: str):
    """获取某次 DAG 运行中所有任务的执行状态"""
    return await _airflow_get(f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")


@router.get("/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}", summary="获取单个任务状态")
async def get_task_instance(dag_id: str, dag_run_id: str, task_id: str):
    """获取单个任务实例的执行状态"""
    return await _airflow_get(f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}")


@router.get("/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs", summary="获取任务日志")
async def get_task_log(dag_id: str, dag_run_id: str, task_id: str, try_number: int = Query(1)):
    """获取任务的运行日志（直接代理到 Airflow webserver）"""
    log_path = f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
    return await _airflow_get(log_path)


@router.get("/queue-summary", summary="任务队列汇总")
async def get_queue_summary():
    """
    汇总 Airflow 调度 + queue.json 的完整任务状态。
    将 queue.json 的状态与 Airflow 的运行状态关联。
    """
    import json
    queue_path = os.path.expanduser("~/.openclaw/workspace/agents/ninja-turtles/dev-loop/queue.json")

    queue_data = {"version": "2.0", "sprint": 0, "tasks": []}
    if os.path.isfile(queue_path):
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                queue_data = json.load(f)
        except Exception:
            pass

    # Group by status
    status_counts: Dict[str, int] = {}
    for task in queue_data.get("tasks", []):
        st = task.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    # Get latest Airflow run info
    try:
        runs = await _airflow_get("/dags/dev_loop_task_pipeline/dagRuns?limit=1&order_by=-start_date")
        latest_run = runs.get("dag_runs", [{}])[0] if runs.get("dag_runs") else {}
    except Exception:
        latest_run = {}

    return {
        "queue_version": queue_data.get("version", "1.0"),
        "sprint": queue_data.get("sprint", 0),
        "total_tasks": len(queue_data.get("tasks", [])),
        "status_breakdown": status_counts,
        "latest_airflow_run": {
            "dag_run_id": latest_run.get("dag_run_id"),
            "state": latest_run.get("state"),
            "start_date": latest_run.get("start_date"),
            "end_date": latest_run.get("end_date"),
        },
    }
