import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from codex_job_service import CODEX_BIN, codex_job_service

router = APIRouter(prefix="/api/v2/codex", tags=["codex-jobs"])


class CodexJobCreate(BaseModel):
    agent_id: str
    instruction: str
    repo: Optional[str] = None
    task_id: Optional[str] = None


@router.get("/status")
def codex_status():
    return {
        "codex_bin": CODEX_BIN,
        "available": os.path.isfile(CODEX_BIN),
        "runner": "codex exec",
        "sandbox": "workspace-write",
        "approval": "never",
    }


@router.get("/jobs")
def list_jobs(agent_id: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    return {"jobs": codex_job_service.list_jobs(agent_id=agent_id, limit=limit)}


@router.post("/jobs", status_code=201)
def create_job(request: CodexJobCreate):
    try:
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
