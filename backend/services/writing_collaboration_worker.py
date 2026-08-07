"""Durable PostgreSQL-backed worker for human-AI writing jobs."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid

from project_manager import project_manager
from services.writing_collaboration_service import (
    WritingCollaborationDisabled,
    writing_collaboration_service,
)
from services.writing_research_service import writing_research_service


logger = logging.getLogger(__name__)


class WritingCollaborationWorker:
    def __init__(self) -> None:
        self.worker_id = f"writing:{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        if os.getenv("WRITING_COLLABORATION_WORKER_ENABLED", "1").strip().lower() in {
            "0", "false", "off", "no"
        }:
            logger.info("Writing collaboration worker disabled")
            return
        if self._task and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.get_running_loop().create_task(
            self._run(), name="writing-collaboration-worker"
        )
        logger.info("Writing collaboration worker started: %s", self.worker_id)

    async def stop(self) -> None:
        self._stopping = True
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        idle_seconds = max(float(os.getenv("WRITING_COLLABORATION_WORKER_INTERVAL", "1")), 0.2)
        while not self._stopping:
            try:
                reference = writing_collaboration_service.next_runnable_ai_job()
                if not reference:
                    stale = writing_collaboration_service.next_stale_projection()
                    if stale:
                        project = project_manager.get_project(stale["project_id"])
                        if project:
                            writing_collaboration_service.refresh_projection(
                                project, stale["document_id"]
                            )
                        await asyncio.sleep(idle_seconds)
                        continue
                    jarvis_run = writing_research_service.claim_next_run(
                        self.worker_id,
                        lease_seconds=300,
                    )
                    if jarvis_run:
                        await writing_research_service.process_run(
                            jarvis_run["id"],
                            self.worker_id,
                        )
                        continue
                    await asyncio.sleep(idle_seconds)
                    continue
                project = project_manager.get_project(reference["project_id"])
                if not project:
                    writing_collaboration_service.fail_ai_job(
                        reference["id"], "AI 写作任务关联项目不存在"
                    )
                    continue
                await writing_collaboration_service.process_ai_job(
                    project,
                    reference["document_id"],
                    reference["id"],
                    worker_id=self.worker_id,
                )
            except WritingCollaborationDisabled:
                await asyncio.sleep(max(idle_seconds, 5.0))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Writing collaboration worker iteration failed")
                await asyncio.sleep(max(idle_seconds, 2.0))


writing_collaboration_worker = WritingCollaborationWorker()


def start_writing_collaboration_worker() -> None:
    writing_collaboration_worker.start()


async def stop_writing_collaboration_worker() -> None:
    await writing_collaboration_worker.stop()
