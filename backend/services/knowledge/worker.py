"""One bounded ingest step, driven by the existing scheduler or an explicit CLI.

The knowledge lease fences candidate writes. WorkRun is the execution ledger;
cross-store updates are reconciled on subsequent ticks, never claimed atomic.
"""
import logging
import asyncio
import sqlalchemy as sa

from models import knowledge_schema_v1 as t
from services.knowledge.service import KnowledgeError

logger = logging.getLogger(__name__)
_task = None


def start_knowledge_worker():
    global _task
    from services.knowledge.runtime import flag
    if not all(flag(k) for k in ("SECOND_BRAIN_ENABLED", "SECOND_BRAIN_WRITE_ENABLED", "SECOND_BRAIN_WORKER_ENABLED")):
        return
    if _task is None or _task.done():
        _task = asyncio.get_running_loop().create_task(_loop(), name="knowledge-ingest")


async def stop_knowledge_worker():
    global _task
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


async def _loop():
    from services.knowledge.runtime import get_service, require_enabled, flag
    from services.work_run_service import work_run_service
    next_maintenance = 0.0
    while True:
        try:
            require_enabled(write=True)
            if flag("SECOND_BRAIN_WORKER_ENABLED"):
                await asyncio.to_thread(run_once, get_service(), work_run_service)
        except Exception as exc:
            logger.warning("knowledge worker unavailable code=%s", getattr(exc, "code", "authority_unavailable"))
        try:
            if flag("SECOND_BRAIN_PROJECTION_ENABLED"):
                require_enabled(write=True)
                from services.knowledge.runtime import get_projection
                await asyncio.to_thread(get_projection().run_once)
        except Exception as exc:
            logger.warning("knowledge projection unavailable code=%s", getattr(exc, "code", "projection_unavailable"))
        if asyncio.get_running_loop().time() >= next_maintenance:
            next_maintenance = asyncio.get_running_loop().time() + 60
            try:
                if flag("SECOND_BRAIN_WORKER_ENABLED") and flag("SECOND_BRAIN_MAINTENANCE_ENABLED"):
                    from services.knowledge.operations import run_scheduled_once
                    await asyncio.to_thread(run_scheduled_once, get_service(), work_run_service)
            except Exception as exc:
                logger.warning("knowledge maintenance unavailable code=%s", getattr(exc, "code", "authority_unavailable"))
        await asyncio.sleep(3)


def run_once(service, work_runs):
    reconcile_runs(service, work_runs)
    job = service.claim_job()
    if not job:
        return False
    run = None
    try:
        if job["work_run_id"]:
            previous = work_runs.get(job["work_run_id"])
            if previous["status"] not in {"completed", "failed", "cancelled"}:
                work_runs.transition(previous["id"], "failed", actor="knowledge-ingestor",
                    failure_code="knowledge_lease_expired")
        run = work_runs.claim(dispatch_id=job["id"], agent_id="knowledge-ingestor",
            executor="knowledge-extractive-v1", project_id="",
            idempotency_key=f"knowledge:{job['id']}:{job['fence']}",
            input_context={"knowledge_job_id": job["id"], "space_id": job["space_id"],
                "source_version_id": job["source_version_id"], "knowledge_fence": job["fence"]})
        with service.engine.begin() as conn:
            service.space(conn, job["actor"], job["space_id"], lock=True)
            service._fenced_job(conn, job)
            conn.execute(t.jobs.update().where(t.jobs.c.id == job["id"]).values(work_run_id=run["id"]))
        work_runs.transition(run["id"], "running", actor="knowledge-ingestor")
        service.compile_job(job, run["id"])
    except Exception as exc:
        # No source text, credentials or raw exception string in logs.
        logger.warning("knowledge job failed id=%s code=%s", job["id"], getattr(exc, "code", "execution_failed"))
        try:
            service.fail_job(job, exc)
        except KnowledgeError:
            pass  # stale execution cannot change the new attempt
        if run:
            work_runs.transition(run["id"], "failed", actor="knowledge-ingestor",
                failure_code=getattr(exc, "code", "execution_failed"))
    reconcile_runs(service, work_runs)
    return True


def reconcile_runs(service, work_runs):
    with service.engine.connect() as conn:
        refs = [dict(r) for r in conn.execute(sa.select(t.jobs).where(
            t.jobs.c.work_run_id != "", t.jobs.c.stage.in_(["awaiting_review", "completed", "failed", "cancelled"]))).mappings()]
    for job in refs:
        run = work_runs.get(job["work_run_id"])
        target = {"awaiting_review": "review", "completed": "completed", "failed": "failed", "cancelled": "cancelled"}[job["stage"]]
        if run["status"] == target or run["status"] in {"completed", "failed", "cancelled"}:
            continue
        if run["status"] == "claimed":
            work_runs.transition(run["id"], "running", actor="knowledge-ingestor")
        if target == "completed" and run["status"] != "review":
            work_runs.transition(run["id"], "review", actor="knowledge-ingestor")
        work_runs.transition(run["id"], target, actor="knowledge-ingestor",
            result_summary=f"knowledge:{job['stage']}:{job['change_set_id']}")
