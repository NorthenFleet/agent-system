import asyncio
import os
import uuid
from pathlib import Path

import pytest

from services.command_center_service import CommandCenterService
from services.command_center_worker import CommandCenterWorker
from services.workflow_runtime import (
    LangGraphWorkflowRuntime,
    PostgresLangGraphWorkflowRuntime,
    WorkflowRuntimeRouter,
    WorkflowRuntimeResult,
    langgraph_available,
    select_workflow_runtime,
)


def _document_plan():
    return {
        "summary": "低风险文档试点",
        "rationale": "先检索，再撰写，最后审校。",
        "risk_level": "low",
        "steps": [
            {
                "order_index": 1,
                "title": "资料检索",
                "description": "收集资料并保留来源。",
                "task_type": "research",
                "agent_id": "perceptor",
                "depends_on": [],
            },
            {
                "order_index": 2,
                "title": "形成文档",
                "description": "根据已核验资料撰写文档。",
                "task_type": "writing",
                "agent_id": "optimus",
                "depends_on": [1],
            },
            {
                "order_index": 3,
                "title": "独立审校",
                "description": "核对事实、引用与交付要求。",
                "task_type": "review",
                "agent_id": "shockwave",
                "depends_on": [2],
            },
        ],
    }


def _langgraph_selection(plan):
    return {
        "runtime": "langgraph",
        "eligible": True,
        "reason": "test_pilot",
        "flow_key": "document",
        "highest_risk": "L0",
    }


class FakeLangGraphRuntime:
    name = "langgraph"

    def __init__(self):
        self.calls = []

    def start(self, run):
        self.calls.append(("start", run["id"]))
        return WorkflowRuntimeResult(
            status="awaiting_approval",
            state={"status": "awaiting_approval"},
            checkpoint={"next_nodes": ["approval_gate"]},
        )

    def resume(self, run, payload):
        self.calls.append(("resume", payload.get("decision")))
        return WorkflowRuntimeResult(
            status="ready",
            state={"status": "ready", "approval": payload},
            checkpoint={"next_nodes": []},
        )


class FakeRuntimeRouter:
    def __init__(self, runtime):
        self.runtime = runtime

    def get(self, name):
        assert name == "langgraph"
        return self.runtime


def test_runtime_selection_is_safe_by_default_and_risk_bounded(monkeypatch):
    import services.workflow_runtime as runtime_module

    monkeypatch.setenv("COMMAND_CENTER_LANGGRAPH_ENABLED", "true")
    monkeypatch.setenv("COMMAND_CENTER_LANGGRAPH_FLOWS", "document,research")
    monkeypatch.setattr(runtime_module, "langgraph_available", lambda: True)

    selected = select_workflow_runtime(
        {
            "flow_spec": {"flow_key": "document"},
            "risk_assessment": {"highest_risk": "L1"},
        }
    )
    blocked = select_workflow_runtime(
        {
            "flow_spec": {"flow_key": "document"},
            "risk_assessment": {"highest_risk": "L2"},
        }
    )

    assert selected["runtime"] == "langgraph"
    assert blocked["runtime"] == "legacy"
    assert blocked["reason"] == "risk_above_pilot_limit"


def test_langgraph_gate_handles_approval_before_interrupt_and_resumes(tmp_path):
    async def scenario():
        service = CommandCenterService(
            str(tmp_path / "workflow.db"),
            workflow_runtime_selector=_langgraph_selection,
        )
        runtime = FakeLangGraphRuntime()
        worker = CommandCenterWorker(
            service=service,
            workflow_runtime=FakeRuntimeRouter(runtime),
        )
        mission = service.create_mission(
            objective="编写带证据的研究报告",
            requested_by="admin",
            mission_type="document",
            context={"business_flow_key": "document"},
        )
        service.claim_planning_mission("planner")
        planned = service.save_plan(mission["id"], _document_plan())
        assert planned["workflow_run"]["status"] == "start_pending"

        approved = service.approve(mission["id"], decided_by="admin")
        assert approved["status"] == "dispatching"
        assert service.activate_approved_missions() == 0

        await worker._drain_workflow_runs()
        interrupted = service.get_workflow_run(mission["id"])
        assert interrupted["status"] == "resume_pending"
        assert interrupted["checkpoint"]["next_nodes"] == ["approval_gate"]
        assert service.activate_approved_missions() == 0

        await worker._drain_workflow_runs()
        ready = service.get_workflow_run(mission["id"])
        assert ready["status"] == "ready"
        assert ready["state"]["approval"]["decision"] == "approved"
        assert service.activate_approved_missions() == 1
        assert service.get_mission(mission["id"])["status"] == "running"
        assert runtime.calls == [
            ("start", ready["id"]),
            ("resume", "approved"),
        ]

    asyncio.run(scenario())


def test_terminal_runtime_failure_releases_pending_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_CENTER_WORKFLOW_MAX_ATTEMPTS", "1")
    service = CommandCenterService(
        str(tmp_path / "workflow-failure.db"),
        workflow_runtime_selector=_langgraph_selection,
    )
    mission = service.create_mission(
        objective="编写研究报告",
        requested_by="admin",
        mission_type="document",
        context={"business_flow_key": "document"},
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _document_plan())
    run = service.claim_workflow_run("runtime-worker")

    failed = service.fail_workflow_run(
        run["id"],
        lease_token=run["lease_token"],
        error="checkpoint store unavailable",
    )
    refreshed = service.get_mission(mission["id"])

    assert failed["status"] == "failed"
    assert refreshed["status"] == "planning"
    assert refreshed["approval"]["decision"] == "runtime_failed"
    assert service.summary()["pending_approvals"] == 0


def test_legacy_runtime_never_blocks_existing_dispatch(tmp_path):
    service = CommandCenterService(str(tmp_path / "legacy.db"))
    mission = service.create_mission(
        objective="实现普通软件需求",
        requested_by="admin",
    )
    service.claim_planning_mission("planner")
    planned = service.save_plan(
        mission["id"],
        {
            "summary": "软件计划",
            "steps": [
                {
                    "order_index": 1,
                    "title": "分析",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "depends_on": [],
                }
            ],
        },
    )
    assert planned["workflow_run"]["runtime"] == "legacy"
    assert planned["workflow_run"]["status"] == "ready"
    service.approve(mission["id"], decided_by="admin")
    assert service.activate_approved_missions() == 1


@pytest.mark.skipif(not langgraph_available(), reason="LangGraph pilot dependency missing")
def test_real_langgraph_sqlite_checkpoint_is_idempotently_resumable(tmp_path):
    checkpoint_path = str(Path(tmp_path) / "checkpoints.sqlite3")
    runtime = LangGraphWorkflowRuntime(checkpoint_path)
    run = {
        "id": "workflow-real",
        "thread_id": "workflow-real",
        "checkpoint_namespace": "pilot",
        "mission_id": "mission-real",
        "plan_version": 1,
        "input": {
            "flow_key": "document",
            "highest_risk": "L0",
            "context_pack_id": "context-real",
        },
    }

    interrupted = runtime.start(run)
    assert interrupted.status == "awaiting_approval"
    assert interrupted.checkpoint["next_nodes"] == ["approval_gate"]

    restarted_runtime = LangGraphWorkflowRuntime(checkpoint_path)
    resumed = restarted_runtime.resume(
        run,
        {"decision": "approved", "decided_by": "integration-test"},
    )
    repeated = restarted_runtime.resume(
        run,
        {"decision": "approved", "decided_by": "integration-test"},
    )
    assert resumed.status == "ready"
    assert repeated.status == "ready"
    assert resumed.state["approval"]["decided_by"] == "integration-test"


def test_router_selects_postgres_checkpoint_without_runtime_ddl(tmp_path):
    router = WorkflowRuntimeRouter(
        str(tmp_path / "unused.sqlite3"),
        checkpoint_database_url="postgresql:///checkpoint-db",
    )

    assert isinstance(router.get("langgraph"), PostgresLangGraphWorkflowRuntime)
    assert router.catalog()["langgraph"]["checkpoint_backend"] == "postgresql"


@pytest.mark.skipif(
    not os.getenv("LANGGRAPH_POSTGRES_TEST_URL", "").strip(),
    reason="LANGGRAPH_POSTGRES_TEST_URL is not configured",
)
def test_real_langgraph_postgres_checkpoint_is_idempotently_resumable():
    import psycopg

    database_url = os.environ["LANGGRAPH_POSTGRES_TEST_URL"].strip()
    thread_id = f"workflow-pg-{uuid.uuid4().hex}"
    run = {
        "id": thread_id,
        "thread_id": thread_id,
        "checkpoint_namespace": "pilot",
        "mission_id": f"mission-{uuid.uuid4().hex[:12]}",
        "plan_version": 1,
        "input": {
            "flow_key": "document",
            "highest_risk": "L0",
            "context_pack_id": "context-postgres",
        },
    }
    try:
        interrupted = PostgresLangGraphWorkflowRuntime(database_url).start(run)
        assert interrupted.status == "awaiting_approval"
        assert interrupted.checkpoint["next_nodes"] == ["approval_gate"]

        restarted = PostgresLangGraphWorkflowRuntime(database_url)
        resumed = restarted.resume(
            run,
            {"decision": "approved", "decided_by": "postgres-integration-test"},
        )
        repeated = restarted.resume(
            run,
            {"decision": "approved", "decided_by": "postgres-integration-test"},
        )
        assert resumed.status == "ready"
        assert repeated.status == "ready"
        assert resumed.state["approval"]["decided_by"] == "postgres-integration-test"
    finally:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM checkpoint_writes WHERE thread_id=%s", (thread_id,))
                cursor.execute("DELETE FROM checkpoint_blobs WHERE thread_id=%s", (thread_id,))
                cursor.execute("DELETE FROM checkpoints WHERE thread_id=%s", (thread_id,))
