import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from codex_job_service import (
    CODEX_BIN,
    CODEX_REMOTE_HOST,
    CODEX_REMOTE_REPO,
    CODEX_REMOTE_USER,
    CODEX_RUNNER_MODE,
    codex_job_service,
)
from services.development_automation_service import development_automation_service

router = APIRouter(prefix="/api/v2/codex", tags=["codex-jobs"])


class CodexJobCreate(BaseModel):
    agent_id: str
    instruction: str
    repo: Optional[str] = None
    task_id: Optional[str] = None


class CodexLoopCreate(BaseModel):
    task_id: str
    instruction: str
    title: Optional[str] = None
    repo: Optional[str] = None
    developer_agent_id: str = "leonardo"
    planner_agent_id: str = "leonardo"
    evaluator_agent_id: str = "michelangelo"
    max_rounds: int = 2


def _enforce_target_policy(task_id: str) -> None:
    policy = development_automation_service.target_execution_policy(task_id)
    if policy == "document_forbidden":
        raise HTTPException(
            status_code=409,
            detail="文档任务不能进入 one-sim 软件 Codex Runner，请在文档写作工作区推进",
        )
    if policy == "software_requires_plan":
        raise HTTPException(
            status_code=409,
            detail="程序开发任务必须先生成自动化计划并由管理员批准，不能直接启动 Codex 执行",
        )


@router.get("/status")
def codex_status(force: bool = Query(False)):
    runner_mode = "ssh" if CODEX_RUNNER_MODE in {"ssh", "remote"} else "local"
    health = codex_job_service.runner_health(force=force)
    return {
        "codex_bin": CODEX_BIN,
        "available": health["available"],
        "runner": "codex exec",
        "runner_mode": runner_mode,
        "remote_host": CODEX_REMOTE_HOST or None,
        "remote_user": CODEX_REMOTE_USER or None,
        "remote_repo": CODEX_REMOTE_REPO or None,
        "sandbox": "workspace-write",
        "approval": "never",
        "health": health,
    }


@router.get("/jobs")
def list_jobs(agent_id: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    return {"jobs": codex_job_service.list_jobs(agent_id=agent_id, limit=limit)}


@router.get("/loops")
def list_loops(task_id: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    return {"loops": codex_job_service.list_loops(task_id=task_id, limit=limit)}


@router.post("/loops", status_code=201)
def create_loop(request: CodexLoopCreate):
    try:
        _enforce_target_policy(request.task_id)
        return {"loop": codex_job_service.create_loop(
            task_id=request.task_id,
            title=request.title or request.task_id,
            instruction=request.instruction,
            repo=request.repo,
            developer_agent_id=request.developer_agent_id,
            planner_agent_id=request.planner_agent_id,
            evaluator_agent_id=request.evaluator_agent_id,
            max_rounds=request.max_rounds,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loops/{loop_id}")
def get_loop(loop_id: str):
    loop = codex_job_service.get_loop(loop_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Codex Loop 不存在")
    return {"loop": loop}


@router.post("/jobs", status_code=201)
def create_job(request: CodexJobCreate):
    try:
        if request.task_id:
            _enforce_target_policy(request.task_id)
        return {"job": codex_job_service.create_job(
            agent_id=request.agent_id,
            instruction=request.instruction,
            repo=request.repo,
            task_id=request.task_id,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = codex_job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Codex 任务不存在")
    return {"job": job}


@router.get("/jobs/{job_id}/logs")
def get_job_logs(job_id: str, tail: int = Query(400, ge=1, le=2000)):
    try:
        return codex_job_service.get_logs(job_id, tail=tail)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Codex 任务不存在") from exc


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    try:
        return {"job": codex_job_service.cancel_job(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Codex 任务不存在") from exc
