import sqlite3

import pytest

from services.agent_team_service import (
    AgentTeamConflict,
    AgentTeamError,
    AgentTeamService,
)
from services.command_center_service import CommandCenterService


def _service(tmp_path, name="agent-team.db", *, owner="user-1"):
    command = CommandCenterService(str(tmp_path / name))
    mission = command.create_mission(
        objective="验证动态团队持久化契约",
        requested_by=owner,
        profile_user_id=owner,
        project_id="project-1",
        mission_type="software",
    )
    return command, AgentTeamService(command), mission


def _team_fixture(tmp_path):
    command, service, mission = _service(tmp_path)
    team = service.create_team(
        mission_id=mission["id"],
        name="契约验证团队",
        actor="user-1",
        owner_user_id="user-1",
        idempotency_key="team-contract-1",
    )
    role = service.define_role(
        team_id=team["id"],
        role_key="builder",
        display_name="构建者",
        actor="user-1",
        owner_user_id="user-1",
        capabilities=["python", "testing"],
    )
    instance = service.register_instance(
        team_id=team["id"],
        role_id=role["id"],
        instance_key="builder-1",
        base_agent_id="donatello",
        actor="user-1",
        owner_user_id="user-1",
        context_thread_id="thread-team-1-builder-1",
    )
    task = service.create_task(
        team_id=team["id"],
        task_key="foundation",
        title="建立领域基础",
        objective="完成 Agent Team 领域持久化契约",
        actor="user-1",
        owner_user_id="user-1",
        idempotency_key="task-foundation-1",
        required_capabilities=["python"],
    )
    return command, service, mission, team, role, instance, task


def test_stage_one_snapshot_is_idempotent_and_restart_safe(tmp_path):
    command, service, mission, team, role, instance, task = _team_fixture(tmp_path)
    duplicate = service.create_team(
        mission_id=mission["id"],
        name="不会重复创建",
        actor="user-1",
        owner_user_id="user-1",
        idempotency_key="team-contract-1",
    )
    assert duplicate["id"] == team["id"]

    dependent = service.create_task(
        team_id=team["id"],
        task_key="verification",
        title="验证领域基础",
        objective="验证重启与引用约束",
        actor="user-1",
        owner_user_id="user-1",
        idempotency_key="task-verification-1",
        dependency_ids=[task["id"]],
    )
    claim = service.create_claim_record(
        team_id=team["id"],
        shared_task_id=task["id"],
        agent_instance_id=instance["id"],
        actor="user-1",
        owner_user_id="user-1",
        idempotency_key="claim-foundation-1",
    )
    binding = service.bind_context_pack(
        team_id=team["id"],
        shared_task_id=task["id"],
        task_claim_id=claim["id"],
        context_pack_id="context-pack-1",
        source_refs=["project-memory:decision-1"],
        owner_user_id="user-1",
        idempotency_key="context-binding-1",
    )
    message = service.send_message(
        team_id=team["id"],
        from_instance_id=instance["id"],
        to_role_id=role["id"],
        shared_task_id=task["id"],
        message_type="review_requested",
        content="请复核领域契约。",
        artifact_refs=["mission-artifact:1"],
        owner_user_id="user-1",
        idempotency_key="message-review-1",
    )

    restarted = AgentTeamService(CommandCenterService(command.db_path))
    snapshot = restarted.snapshot(team["id"], owner_user_id="user-1")

    assert snapshot["team"]["id"] == team["id"]
    assert [item["id"] for item in snapshot["roles"]] == [role["id"]]
    assert snapshot["instances"][0]["active_claims"] == 1
    assert {item["id"] for item in snapshot["tasks"]} == {task["id"], dependent["id"]}
    assert snapshot["dependencies"][0]["depends_on_task_id"] == task["id"]
    assert snapshot["claims"][0]["fencing_token"] == 1
    assert snapshot["context_bindings"][0]["id"] == binding["id"]
    assert snapshot["context_bindings"][0]["source_refs"] == ["project-memory:decision-1"]
    assert snapshot["messages"][0]["id"] == message["id"]
    assert [event["sequence"] for event in snapshot["events"]] == list(
        range(1, len(snapshot["events"]) + 1)
    )


def test_only_one_active_claim_and_fencing_token_is_monotonic(tmp_path):
    _command, service, _mission, team, _role, instance, task = _team_fixture(tmp_path)
    first = service.create_claim_record(
        team_id=team["id"], shared_task_id=task["id"],
        agent_instance_id=instance["id"], actor="user-1",
        owner_user_id="user-1", idempotency_key="claim-1",
    )
    with pytest.raises(AgentTeamConflict, match="active claim"):
        service.create_claim_record(
            team_id=team["id"], shared_task_id=task["id"],
            agent_instance_id=instance["id"], actor="user-1",
            owner_user_id="user-1", idempotency_key="claim-2",
        )

    expired = service.close_claim_record(
        team_id=team["id"], shared_task_id=task["id"], claim_id=first["id"],
        fencing_token=first["fencing_token"], terminal_status="expired",
        actor="user-1", owner_user_id="user-1",
    )
    assert expired["status"] == "expired"
    second = service.create_claim_record(
        team_id=team["id"], shared_task_id=task["id"],
        agent_instance_id=instance["id"], actor="user-1",
        owner_user_id="user-1", idempotency_key="claim-2",
    )
    assert second["attempt"] == 2
    assert second["fencing_token"] == 2

    with pytest.raises(AgentTeamConflict, match="fencing token"):
        service.close_claim_record(
            team_id=team["id"], shared_task_id=task["id"], claim_id=first["id"],
            fencing_token=first["fencing_token"], terminal_status="completed",
            actor="late-worker", owner_user_id="user-1",
        )

    with service.connect(immediate=True) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO task_claims
                (id, team_id, shared_task_id, agent_instance_id, attempt,
                 fencing_token, status, score, rationale_json, idempotency_key,
                 result_json, claimed_at, updated_at)
                VALUES ('claim-invalid', ?, ?, ?, 3, 3, 'running', 0, '{}',
                        'claim-invalid-key', '{}', ?, ?)
                """,
                (team["id"], task["id"], instance["id"], second["claimed_at"], second["updated_at"]),
            )


def test_cross_team_references_and_invalid_message_routes_are_rejected(tmp_path):
    _command, service, _mission, team, role, instance, task = _team_fixture(tmp_path)
    command_2, service_2, mission_2 = _service(tmp_path, "agent-team.db", owner="user-2")
    # _service reopened the same database and created a second mission.
    assert command_2.db_path == service.command_center.db_path
    team_2 = service_2.create_team(
        mission_id=mission_2["id"], name="第二团队", actor="user-2",
        owner_user_id="user-2", idempotency_key="team-contract-2",
    )

    with pytest.raises(AgentTeamError, match="role does not belong"):
        service.register_instance(
            team_id=team_2["id"], role_id=role["id"], instance_key="foreign-role",
            base_agent_id="optimus", actor="user-2", owner_user_id="user-2",
        )
    with pytest.raises(AgentTeamError, match="exactly one"):
        service.send_message(
            team_id=team["id"], from_instance_id=instance["id"],
            to_instance_id=instance["id"], to_role_id=role["id"],
            shared_task_id=task["id"], message_type="blocked", content="冲突路由",
            owner_user_id="user-1", idempotency_key="invalid-message",
        )
    with pytest.raises(AgentTeamError, match="references must belong"):
        service.send_message(
            team_id=team_2["id"], from_instance_id=instance["id"],
            to_role_id=role["id"], message_type="blocked", content="跨团队",
            owner_user_id="user-2", idempotency_key="cross-team-message",
        )


def test_context_binding_requires_current_active_claim(tmp_path):
    _command, service, _mission, team, _role, instance, task = _team_fixture(tmp_path)
    claim = service.create_claim_record(
        team_id=team["id"], shared_task_id=task["id"],
        agent_instance_id=instance["id"], actor="user-1",
        owner_user_id="user-1", idempotency_key="claim-context",
    )
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE task_claims SET status='expired' WHERE id=?", (claim["id"],))
    with pytest.raises(AgentTeamError, match="active claim"):
        service.bind_context_pack(
            team_id=team["id"], shared_task_id=task["id"],
            task_claim_id=claim["id"], context_pack_id="stale-context",
            owner_user_id="user-1", idempotency_key="stale-context-binding",
        )
