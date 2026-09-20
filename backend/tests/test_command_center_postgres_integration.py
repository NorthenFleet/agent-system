"""Opt-in PostgreSQL integration gates for Command Center production paths."""

import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from repositories.command_center_repository import PostgresCommandCenterRepository
from services.command_center_service import CommandCenterService
from services.command_center_worker import CommandCenterWorker
from services.workflow_runtime import WorkflowRuntimeRouter


POSTGRES_URL = os.getenv("COMMAND_CENTER_POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="COMMAND_CENTER_POSTGRES_TEST_URL is not configured",
)


def _service(workflow_runtime_selector=None) -> CommandCenterService:
    return CommandCenterService(
        repository=PostgresCommandCenterRepository(POSTGRES_URL),
        project_provider=lambda: [],
        workflow_runtime_selector=workflow_runtime_selector,
    )


def _plan() -> dict:
    return {
        "summary": "PostgreSQL 双 worker 领取门禁",
        "risk_level": "low",
        "steps": [
            {
                "order_index": 1,
                "title": "并发步骤 A",
                "task_type": "coordination",
                "agent_id": "optimus",
                "depends_on": [],
            },
            {
                "order_index": 2,
                "title": "并发步骤 B",
                "task_type": "coordination",
                "agent_id": "optimus",
                "depends_on": [],
            },
        ],
    }


def _cleanup(service: CommandCenterService, mission_id: str, requested_by: str) -> None:
    with service.connect(immediate=True) as connection:
        mission = connection.execute(
            "SELECT conversation_id FROM orchestration_missions WHERE id=?",
            (mission_id,),
        ).fetchone()
        conversation_id = mission["conversation_id"] if mission else None
        outbox = connection.execute(
            "SELECT id FROM notification_outbox WHERE mission_id=?",
            (mission_id,),
        ).fetchall()
        for row in outbox:
            connection.execute(
                "DELETE FROM notification_deliveries WHERE outbox_id=?",
                (row["id"],),
            )
        for table in (
            "notification_outbox",
            "mission_acceptance_gates",
            "mission_evidence",
            "mission_artifacts",
            "mission_compensations",
            "mission_effects",
            "mission_step_approvals",
            "workflow_runs",
            "mission_context_bindings",
            "mission_approvals",
            "mission_events",
            "mission_steps",
            "mission_plan_versions",
            "mission_runs",
        ):
            connection.execute(f"DELETE FROM {table} WHERE mission_id=?", (mission_id,))
        connection.execute("DELETE FROM orchestration_missions WHERE id=?", (mission_id,))
        if conversation_id:
            connection.execute(
                "DELETE FROM command_messages WHERE conversation_id=?",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM command_conversations WHERE id=? AND user_external_id=?",
                (conversation_id, requested_by),
            )


def test_postgres_two_workers_claim_each_mission_and_step_once():
    service = _service()
    requested_by = f"pg-gate-{uuid.uuid4().hex}"
    mission = service.create_mission(
        objective="验证 PostgreSQL 多实例领取",
        requested_by=requested_by,
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            planning_results = list(
                pool.map(
                    lambda owner: _service().claim_planning_mission(owner),
                    ("planner-a", "planner-b"),
                )
            )
        claimed_planning = [item for item in planning_results if item]
        assert len(claimed_planning) == 1
        assert claimed_planning[0]["id"] == mission["id"]

        service.save_plan(mission["id"], _plan())
        service.approve(mission["id"], decided_by="postgres-gate")
        assert service.activate_approved_missions() == 1

        with ThreadPoolExecutor(max_workers=2) as pool:
            step_results = list(
                pool.map(
                    lambda owner: _service().claim_ready_steps(owner, limit=1),
                    ("runner-a", "runner-b"),
                )
            )
        claimed_steps = [step for batch in step_results for step in batch]
        assert len(claimed_steps) == 2
        assert len({step["id"] for step in claimed_steps}) == 2
        assert {step["lease_owner"] for step in claimed_steps} == {
            "runner-a",
            "runner-b",
        }
        for step in claimed_steps:
            service.complete_step(
                step["id"],
                result={"success": True, "output": f"completed by {step['lease_owner']}"},
                success=True,
                actor=step["lease_owner"],
                lease_token=step["lease_token"],
            )

        evaluation = service.claim_evaluation_mission("evaluator-pg")
        assert evaluation["id"] == mission["id"]
        completed = service.complete_mission(
            mission["id"],
            summary="PostgreSQL 多实例领取与闭环验证通过",
            success=True,
        )
        assert completed["status"] == "completed"
        assert completed["mission_run"]["status"] == "completed"
        pool = service.storage_runtime_metrics()["pool"]
        assert pool["max_size"] >= pool["peak_in_use"] >= 1
        assert pool["connection_failures_total"] == 0
        checkpoint = service.workflow_runtime_status()["checkpoint_storage"]
        assert checkpoint["status"] == "ready"
        assert checkpoint["installed_version"] == checkpoint["required_version"]
    finally:
        _cleanup(service, mission["id"], requested_by)


def test_postgres_command_center_and_langgraph_complete_approval_gate():
    def select_langgraph(_plan):
        return {
            "runtime": "langgraph",
            "eligible": True,
            "reason": "postgres_integration_gate",
            "flow_key": "document",
            "highest_risk": "L0",
        }

    service = _service(select_langgraph)
    requested_by = f"pg-langgraph-{uuid.uuid4().hex}"
    mission = service.create_mission(
        objective="验证 PostgreSQL Command Center 与 LangGraph 审批恢复链路",
        requested_by=requested_by,
        mission_type="document",
        context={"business_flow_key": "document"},
    )
    thread_id = ""
    try:
        assert service.claim_planning_mission("planner-pg-langgraph")["id"] == mission["id"]
        planned = service.save_plan(mission["id"], _plan())
        thread_id = planned["workflow_run"]["thread_id"]
        service.approve(mission["id"], decided_by="postgres-gate")

        worker = CommandCenterWorker(
            service=service,
            workflow_runtime=WorkflowRuntimeRouter(
                "/tmp/unused-command-center-checkpoint.sqlite3",
                checkpoint_database_url=POSTGRES_URL,
            ),
        )
        asyncio.run(worker._drain_workflow_runs())
        interrupted = service.get_workflow_run(mission["id"])
        assert interrupted["status"] == "resume_pending"
        assert interrupted["checkpoint"]["next_nodes"] == ["approval_gate"]

        asyncio.run(worker._drain_workflow_runs())
        ready = service.get_workflow_run(mission["id"])
        assert ready["status"] == "ready"
        assert ready["state"]["approval"]["decision"] == "approved"
        assert service.activate_approved_missions() == 1
        assert service.get_mission(mission["id"])["status"] == "running"
    finally:
        if thread_id:
            with service.connect(immediate=True) as connection:
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    connection.execute(
                        f"DELETE FROM {table} WHERE thread_id=?",
                        (thread_id,),
                    )
        _cleanup(service, mission["id"], requested_by)
