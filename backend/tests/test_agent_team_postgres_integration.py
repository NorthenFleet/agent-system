"""Opt-in PostgreSQL gate for Agent Team persistence invariants."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from repositories.command_center_repository import PostgresCommandCenterRepository
from services.agent_team_service import AgentTeamConflict, AgentTeamService
from services.command_center_service import CommandCenterService


POSTGRES_URL = os.getenv("COMMAND_CENTER_POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="COMMAND_CENTER_POSTGRES_TEST_URL is not configured",
)


def _command() -> CommandCenterService:
    return CommandCenterService(
        repository=PostgresCommandCenterRepository(POSTGRES_URL),
        project_provider=lambda: [],
    )


def _cleanup(command: CommandCenterService, mission_id: str) -> None:
    with command.connect(immediate=True) as conn:
        mission = conn.execute(
            "SELECT conversation_id FROM orchestration_missions WHERE id=?",
            (mission_id,),
        ).fetchone()
        conversation_id = mission["conversation_id"] if mission else None
        team_rows = conn.execute(
            "SELECT id FROM agent_teams WHERE mission_id=?",
            (mission_id,),
        ).fetchall()
        for row in team_rows:
            team_id = row["id"]
            for table in (
                "team_events",
                "agent_messages",
                "agent_task_context_bindings",
                "task_claims",
                "shared_task_dependencies",
                "shared_tasks",
                "agent_instances",
                "agent_team_roles",
            ):
                conn.execute(f"DELETE FROM {table} WHERE team_id=?", (team_id,))
            conn.execute("DELETE FROM agent_teams WHERE id=?", (team_id,))
        for table in (
            "notification_outbox", "mission_acceptance_gates", "mission_evidence",
            "mission_artifacts", "mission_compensations", "mission_effects",
            "mission_step_approvals", "workflow_runs", "mission_context_bindings",
            "mission_approvals", "mission_events", "mission_steps",
            "mission_plan_versions", "mission_runs",
        ):
            conn.execute(f"DELETE FROM {table} WHERE mission_id=?", (mission_id,))
        conn.execute("DELETE FROM orchestration_missions WHERE id=?", (mission_id,))
        if conversation_id:
            conn.execute("DELETE FROM command_messages WHERE conversation_id=?", (conversation_id,))
            conn.execute("DELETE FROM command_conversations WHERE id=?", (conversation_id,))


def test_postgres_agent_team_contract_and_single_active_claim():
    command = _command()
    owner = f"agent-team-pg-{uuid.uuid4().hex}"
    mission = command.create_mission(
        objective="Agent Team PostgreSQL 门禁",
        requested_by=owner,
        profile_user_id=owner,
        project_id="project-agent-team-gate",
        mission_type="software",
    )
    service = AgentTeamService(command)
    try:
        team = service.create_team(
            mission_id=mission["id"], name="PostgreSQL 团队", actor=owner,
            owner_user_id=owner, idempotency_key=f"team:{mission['id']}",
        )
        role = service.define_role(
            team_id=team["id"], role_key="worker", display_name="执行者",
            actor=owner, owner_user_id=owner,
        )
        instance = service.register_instance(
            team_id=team["id"], role_id=role["id"], instance_key="worker-1",
            base_agent_id="optimus", actor=owner, owner_user_id=owner,
        )
        task = service.create_task(
            team_id=team["id"], task_key="gate", title="门禁任务",
            objective="验证单一有效认领", actor=owner, owner_user_id=owner,
            idempotency_key=f"task:{mission['id']}",
        )

        def claim(index: int):
            try:
                return AgentTeamService(_command()).create_claim_record(
                    team_id=team["id"], shared_task_id=task["id"],
                    agent_instance_id=instance["id"], actor=owner,
                    owner_user_id=owner,
                    idempotency_key=f"claim:{mission['id']}:{index}",
                )
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(claim, (1, 2)))
        successful = [item for item in outcomes if item]
        assert len(successful) == 1

        snapshot = service.snapshot(team["id"], owner_user_id=owner)
        assert len(snapshot["claims"]) == 1
        assert snapshot["claims"][0]["fencing_token"] == 1
        assert snapshot["instances"][0]["active_claims"] == 1

        service.close_claim_record(
            team_id=team["id"], shared_task_id=task["id"],
            claim_id=successful[0]["id"],
            fencing_token=successful[0]["fencing_token"],
            terminal_status="expired", actor=owner, owner_user_id=owner,
        )
        replacement = service.create_claim_record(
            team_id=team["id"], shared_task_id=task["id"],
            agent_instance_id=instance["id"], actor=owner,
            owner_user_id=owner,
            idempotency_key=f"claim:{mission['id']}:replacement",
        )
        assert replacement["fencing_token"] == 2
        with pytest.raises(AgentTeamConflict, match="fencing token"):
            service.close_claim_record(
                team_id=team["id"], shared_task_id=task["id"],
                claim_id=successful[0]["id"],
                fencing_token=successful[0]["fencing_token"],
                terminal_status="completed", actor="late-worker",
                owner_user_id=owner,
            )
    finally:
        _cleanup(command, mission["id"])
