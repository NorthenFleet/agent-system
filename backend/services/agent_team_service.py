"""Agent Team domain service for the persistence-contract phase.

This module deliberately does not dispatch work.  It owns team collaboration
facts and validates cross-team references while the existing Mission/WorkRun
path remains authoritative for execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from services.command_center_service import (
    CommandCenterService,
    MissionNotFound,
    command_center_service,
)


TEAM_STATES = {"forming", "active", "draining", "completed", "failed", "cancelled"}
ROLE_STATES = {"active", "draining", "disabled"}
INSTANCE_STATES = {"starting", "idle", "busy", "draining", "stopped", "failed"}
TASK_STATES = {
    "draft", "ready", "claimed", "running", "verifying",
    "completed", "failed", "blocked", "cancelled",
}
CLAIM_STATES = {"claimed", "running", "verifying", "completed", "failed", "expired", "cancelled"}
ACTIVE_CLAIM_STATES = {"claimed", "running", "verifying"}
CONTEXT_STATES = {"active", "consumed", "revoked"}


class AgentTeamError(RuntimeError):
    pass


class AgentTeamNotFound(AgentTeamError):
    pass


class AgentTeamConflict(AgentTeamError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def _clean_list(values: list[str] | None, *, limit: int = 100) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in (values or []) if str(value).strip()))[:limit]


class AgentTeamService:
    def __init__(self, command_center: CommandCenterService):
        self.command_center = command_center

    def connect(self, *, immediate: bool = False):
        return self.command_center.connect(immediate=immediate)

    @staticmethod
    def _require_team(conn: Any, team_id: str) -> Any:
        row = conn.execute("SELECT * FROM agent_teams WHERE id=?", (team_id,)).fetchone()
        if not row:
            raise AgentTeamNotFound(team_id)
        return row

    @staticmethod
    def _require_team_access(conn: Any, team: Any, owner_user_id: str) -> Any:
        mission = conn.execute(
            "SELECT id, owner_user_id, project_id FROM orchestration_missions WHERE id=?",
            (team["mission_id"],),
        ).fetchone()
        if not mission:
            raise MissionNotFound(str(team["mission_id"]))
        if owner_user_id and str(mission["owner_user_id"] or "") != str(owner_user_id):
            raise AgentTeamNotFound(str(team["id"]))
        return mission

    @staticmethod
    def _serialize(row: Any) -> dict[str, Any]:
        item = dict(row)
        for key in tuple(item):
            if key.endswith("_json"):
                item[key[:-5]] = _loads(item.pop(key), [] if key in {
                    "capabilities_json", "required_tools_json", "dependencies_json",
                    "acceptance_criteria_json", "evidence_required_json",
                    "artifact_refs_json", "source_refs_json",
                } else {})
        return item

    def _append_event(
        self,
        conn: Any,
        *,
        team_id: str,
        mission_id: str,
        event_type: str,
        actor: str,
        event_key: str,
        detail: str = "",
        agent_instance_id: str | None = None,
        shared_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = conn.execute(
            "SELECT * FROM team_events WHERE team_id=? AND event_key=?",
            (team_id, event_key),
        ).fetchone()
        if existing:
            return self._serialize(existing)
        # Updating the parent row serializes event sequence allocation on both
        # SQLite and PostgreSQL without introducing a second sequence source.
        cursor = conn.execute(
            "UPDATE agent_teams SET updated_at=updated_at WHERE id=?",
            (team_id,),
        )
        if int(cursor.rowcount or 0) != 1:
            raise AgentTeamNotFound(team_id)
        sequence_row = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM team_events WHERE team_id=?",
            (team_id,),
        ).fetchone()
        sequence = int(sequence_row["sequence"] or 0) + 1
        event_id = f"team-event-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO team_events
            (id, team_id, mission_id, sequence, event_type, actor,
             agent_instance_id, shared_task_id, detail, event_key,
             metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, team_id, mission_id, sequence, event_type,
                actor, agent_instance_id, shared_task_id, str(detail)[:4000],
                event_key, _json(metadata or {}), _now(),
            ),
        )
        return self._serialize(
            conn.execute("SELECT * FROM team_events WHERE id=?", (event_id,)).fetchone()
        )

    def create_team(
        self,
        *,
        mission_id: str,
        name: str,
        actor: str,
        idempotency_key: str,
        owner_user_id: str = "",
        leader_agent_id: str = "optimus",
        max_members: int = 8,
        max_parallel_tasks: int = 4,
        policy_version: str = "agent-team-v1",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not str(idempotency_key).strip():
            raise AgentTeamError("idempotency_key is required")
        with self.connect(immediate=True) as conn:
            existing = conn.execute(
                "SELECT * FROM agent_teams WHERE idempotency_key=?",
                (str(idempotency_key),),
            ).fetchone()
            if existing:
                self._require_team_access(conn, existing, owner_user_id)
                return self._serialize(existing)
            mission = conn.execute(
                "SELECT id, owner_user_id, project_id FROM orchestration_missions WHERE id=?",
                (mission_id,),
            ).fetchone()
            if not mission or (
                owner_user_id
                and str(mission["owner_user_id"] or "") != str(owner_user_id)
            ):
                raise MissionNotFound(mission_id)
            active = conn.execute(
                """
                SELECT id FROM agent_teams WHERE mission_id=?
                AND status NOT IN ('completed', 'failed', 'cancelled')
                """,
                (mission_id,),
            ).fetchone()
            if active:
                raise AgentTeamConflict(f"mission already has active team: {active['id']}")
            generation_row = conn.execute(
                "SELECT COALESCE(MAX(generation), 0) AS generation FROM agent_teams WHERE mission_id=?",
                (mission_id,),
            ).fetchone()
            generation = int(generation_row["generation"] or 0) + 1
            team_id = f"team-{uuid.uuid4().hex[:12]}"
            now = _now()
            conn.execute(
                """
                INSERT INTO agent_teams
                (id, mission_id, generation, name, leader_agent_id, status,
                 policy_version, max_members, max_parallel_tasks, idempotency_key,
                 metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'forming', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team_id, mission_id, generation, str(name).strip()[:200],
                    str(leader_agent_id).strip()[:160] or "optimus",
                    str(policy_version).strip()[:120] or "agent-team-v1",
                    max(1, min(int(max_members), 100)),
                    max(1, min(int(max_parallel_tasks), 100)),
                    str(idempotency_key), _json(metadata or {}), now, now,
                ),
            )
            self._append_event(
                conn, team_id=team_id, mission_id=mission_id,
                event_type="team.created", actor=actor,
                event_key=f"team-created:{idempotency_key}",
                metadata={"generation": generation, "policy_version": policy_version},
            )
            return self._serialize(
                conn.execute("SELECT * FROM agent_teams WHERE id=?", (team_id,)).fetchone()
            )

    def define_role(
        self,
        *,
        team_id: str,
        role_key: str,
        display_name: str,
        actor: str,
        capabilities: list[str] | None = None,
        required_tools: list[str] | None = None,
        min_instances: int = 0,
        max_instances: int = 1,
        metadata: dict[str, Any] | None = None,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        clean_key = str(role_key).strip()
        if not clean_key:
            raise AgentTeamError("role_key is required")
        minimum = max(0, int(min_instances))
        maximum = max(1, int(max_instances))
        if minimum > maximum:
            raise AgentTeamError("min_instances cannot exceed max_instances")
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            self._require_team_access(conn, team, owner_user_id)
            existing = conn.execute(
                "SELECT * FROM agent_team_roles WHERE team_id=? AND role_key=?",
                (team_id, clean_key),
            ).fetchone()
            if existing:
                return self._serialize(existing)
            role_id = f"team-role-{uuid.uuid4().hex[:12]}"
            now = _now()
            conn.execute(
                """
                INSERT INTO agent_team_roles
                (id, team_id, role_key, display_name, capabilities_json,
                 required_tools_json, min_instances, max_instances, status,
                 metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    role_id, team_id, clean_key[:120], str(display_name).strip()[:200],
                    _json(_clean_list(capabilities)), _json(_clean_list(required_tools)),
                    minimum, maximum, _json(metadata or {}), now, now,
                ),
            )
            self._append_event(
                conn, team_id=team_id, mission_id=str(team["mission_id"]),
                event_type="role.defined", actor=actor,
                event_key=f"role-defined:{clean_key}",
                metadata={"role_id": role_id},
            )
            return self._serialize(
                conn.execute("SELECT * FROM agent_team_roles WHERE id=?", (role_id,)).fetchone()
            )

    def register_instance(
        self,
        *,
        team_id: str,
        role_id: str,
        instance_key: str,
        base_agent_id: str,
        actor: str,
        capacity: int = 1,
        context_thread_id: str = "",
        metadata: dict[str, Any] | None = None,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        clean_key = str(instance_key).strip()
        if not clean_key:
            raise AgentTeamError("instance_key is required")
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            self._require_team_access(conn, team, owner_user_id)
            role = conn.execute(
                "SELECT * FROM agent_team_roles WHERE id=? AND team_id=?",
                (role_id, team_id),
            ).fetchone()
            if not role:
                raise AgentTeamError("role does not belong to team")
            existing = conn.execute(
                "SELECT * FROM agent_instances WHERE team_id=? AND instance_key=?",
                (team_id, clean_key),
            ).fetchone()
            if existing:
                return self._serialize(existing)
            instance_id = f"agent-instance-{uuid.uuid4().hex[:12]}"
            now = _now()
            conn.execute(
                """
                INSERT INTO agent_instances
                (id, team_id, role_id, instance_key, base_agent_id, status,
                 capacity, active_claims, context_thread_id, last_seen_at,
                 failure_count, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'starting', ?, 0, ?, ?, 0, ?, ?, ?)
                """,
                (
                    instance_id, team_id, role_id, clean_key[:160],
                    str(base_agent_id).strip()[:160], max(1, min(int(capacity), 100)),
                    str(context_thread_id).strip()[:300] or None,
                    now, _json(metadata or {}), now, now,
                ),
            )
            self._append_event(
                conn, team_id=team_id, mission_id=str(team["mission_id"]),
                event_type="instance.registered", actor=actor,
                event_key=f"instance-registered:{clean_key}",
                agent_instance_id=instance_id, metadata={"role_id": role_id},
            )
            return self._serialize(
                conn.execute("SELECT * FROM agent_instances WHERE id=?", (instance_id,)).fetchone()
            )

    def create_task(
        self,
        *,
        team_id: str,
        task_key: str,
        title: str,
        objective: str,
        actor: str,
        idempotency_key: str,
        mission_step_id: str = "",
        task_type: str = "general",
        priority: int = 50,
        risk_class: str = "L1",
        dependency_ids: list[str] | None = None,
        required_capabilities: list[str] | None = None,
        required_tools: list[str] | None = None,
        input_contract: dict[str, Any] | None = None,
        output_contract: dict[str, Any] | None = None,
        acceptance_criteria: list[str] | None = None,
        evidence_required: list[str] | None = None,
        max_claims: int = 3,
        metadata: dict[str, Any] | None = None,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        clean_key = str(task_key).strip()
        if not clean_key or not str(idempotency_key).strip():
            raise AgentTeamError("task_key and idempotency_key are required")
        dependencies = _clean_list(dependency_ids)
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            mission = self._require_team_access(conn, team, owner_user_id)
            existing = conn.execute(
                "SELECT * FROM shared_tasks WHERE team_id=? AND idempotency_key=?",
                (team_id, str(idempotency_key)),
            ).fetchone()
            if existing:
                return self._serialize(existing)
            for dependency_id in dependencies:
                dependency = conn.execute(
                    "SELECT id FROM shared_tasks WHERE id=? AND team_id=?",
                    (dependency_id, team_id),
                ).fetchone()
                if not dependency:
                    raise AgentTeamError("task dependency does not belong to team")
            task_id = f"shared-task-{uuid.uuid4().hex[:12]}"
            if task_id in dependencies:
                raise AgentTeamError("task cannot depend on itself")
            if mission_step_id:
                step = conn.execute(
                    "SELECT id FROM mission_steps WHERE id=? AND mission_id=?",
                    (mission_step_id, team["mission_id"]),
                ).fetchone()
                if not step:
                    raise AgentTeamError("mission step does not belong to team mission")
            now = _now()
            conn.execute(
                """
                INSERT INTO shared_tasks
                (id, team_id, mission_id, mission_step_id, task_key, title,
                 objective, task_type, status, priority, risk_class,
                 dependencies_json, required_capabilities_json, required_tools_json,
                 input_contract_json, output_contract_json, acceptance_criteria_json,
                 evidence_required_json, max_claims, idempotency_key, metadata_json,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id, team_id, team["mission_id"], mission_step_id or None,
                    clean_key[:160], str(title).strip()[:300], str(objective)[:20000],
                    str(task_type).strip()[:80] or "general",
                    max(0, min(int(priority), 1000)), str(risk_class).strip()[:20] or "L1",
                    _json(dependencies), _json(_clean_list(required_capabilities)),
                    _json(_clean_list(required_tools)), _json(input_contract or {}),
                    _json(output_contract or {}), _json(_clean_list(acceptance_criteria)),
                    _json(_clean_list(evidence_required)), max(1, min(int(max_claims), 100)),
                    str(idempotency_key), _json(metadata or {}), now, now,
                ),
            )
            for dependency_id in dependencies:
                conn.execute(
                    """
                    INSERT INTO shared_task_dependencies
                    (id, team_id, shared_task_id, depends_on_task_id, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"task-dependency-{uuid.uuid4().hex[:12]}", team_id, task_id, dependency_id, now),
                )
            self._append_event(
                conn, team_id=team_id, mission_id=str(team["mission_id"]),
                event_type="task.created", actor=actor,
                event_key=f"task-created:{idempotency_key}",
                shared_task_id=task_id,
                metadata={"task_key": clean_key, "dependencies": dependencies},
            )
            return self._serialize(
                conn.execute("SELECT * FROM shared_tasks WHERE id=?", (task_id,)).fetchone()
            )

    def create_claim_record(
        self,
        *,
        team_id: str,
        shared_task_id: str,
        agent_instance_id: str,
        actor: str,
        idempotency_key: str,
        score: float = 0.0,
        rationale: dict[str, Any] | None = None,
        lease_owner: str = "",
        lease_seconds: int = 300,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        """Record a claim contract without dispatching a WorkRun (stage 1 only)."""
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            self._require_team_access(conn, team, owner_user_id)
            existing = conn.execute(
                "SELECT * FROM task_claims WHERE idempotency_key=?",
                (str(idempotency_key),),
            ).fetchone()
            if existing:
                return self._serialize(existing)
            task = conn.execute(
                "SELECT * FROM shared_tasks WHERE id=? AND team_id=?",
                (shared_task_id, team_id),
            ).fetchone()
            instance = conn.execute(
                "SELECT * FROM agent_instances WHERE id=? AND team_id=?",
                (agent_instance_id, team_id),
            ).fetchone()
            if not task or not instance:
                raise AgentTeamError("task and instance must belong to team")
            active = conn.execute(
                """
                SELECT id FROM task_claims WHERE shared_task_id=?
                AND status IN ('claimed', 'running', 'verifying')
                """,
                (shared_task_id,),
            ).fetchone()
            if active:
                raise AgentTeamConflict(f"task already has active claim: {active['id']}")
            counters = conn.execute(
                """
                SELECT COALESCE(MAX(attempt), 0) AS attempt,
                       COALESCE(MAX(fencing_token), 0) AS fencing_token
                FROM task_claims WHERE shared_task_id=?
                """,
                (shared_task_id,),
            ).fetchone()
            attempt = int(counters["attempt"] or 0) + 1
            fencing_token = int(counters["fencing_token"] or 0) + 1
            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat()
            claim_id = f"task-claim-{uuid.uuid4().hex[:12]}"
            lease_token = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO task_claims
                (id, team_id, shared_task_id, agent_instance_id, attempt,
                 fencing_token, status, score, rationale_json, lease_owner,
                 lease_token, lease_expires_at, idempotency_key, result_json,
                 claimed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    claim_id, team_id, shared_task_id, agent_instance_id,
                    attempt, fencing_token, float(score), _json(rationale or {}),
                    str(lease_owner).strip()[:160] or None, lease_token,
                    (now_dt + timedelta(seconds=max(1, int(lease_seconds)))).isoformat(),
                    str(idempotency_key), now, now,
                ),
            )
            conn.execute(
                "UPDATE shared_tasks SET status='claimed', updated_at=? WHERE id=?",
                (now, shared_task_id),
            )
            self._reconcile_active_claim_counts(conn, team_id)
            self._append_event(
                conn, team_id=team_id, mission_id=str(team["mission_id"]),
                event_type="claim.created", actor=actor,
                event_key=f"claim-created:{idempotency_key}",
                agent_instance_id=agent_instance_id, shared_task_id=shared_task_id,
                metadata={"claim_id": claim_id, "attempt": attempt, "fencing_token": fencing_token},
            )
            return self._serialize(
                conn.execute("SELECT * FROM task_claims WHERE id=?", (claim_id,)).fetchone()
            )

    def close_claim_record(
        self,
        *,
        team_id: str,
        shared_task_id: str,
        claim_id: str,
        fencing_token: int,
        terminal_status: str,
        actor: str,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        """Close only the current active claim; stale fencing tokens are rejected."""
        if terminal_status not in {"completed", "failed", "expired", "cancelled"}:
            raise AgentTeamError("claim terminal_status is invalid")
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            self._require_team_access(conn, team, owner_user_id)
            current = conn.execute(
                """
                SELECT * FROM task_claims
                WHERE team_id=? AND shared_task_id=?
                  AND status IN ('claimed', 'running', 'verifying')
                """,
                (team_id, shared_task_id),
            ).fetchone()
            if (
                not current
                or str(current["id"]) != str(claim_id)
                or int(current["fencing_token"] or 0) != int(fencing_token)
            ):
                raise AgentTeamConflict("stale or non-current claim fencing token")
            now = _now()
            cursor = conn.execute(
                """
                UPDATE task_claims
                SET status=?, updated_at=?
                WHERE id=? AND team_id=? AND shared_task_id=? AND fencing_token=?
                  AND status IN ('claimed', 'running', 'verifying')
                """,
                (
                    terminal_status, now, claim_id, team_id,
                    shared_task_id, int(fencing_token),
                ),
            )
            if int(cursor.rowcount or 0) != 1:
                raise AgentTeamConflict("claim fencing token lost during update")
            conn.execute(
                """
                UPDATE agent_task_context_bindings
                SET status='revoked', revoked_at=?
                WHERE task_claim_id=? AND status='active'
                """,
                (now, claim_id),
            )
            task_status = terminal_status if terminal_status in {"completed", "failed"} else "draft"
            conn.execute(
                "UPDATE shared_tasks SET status=?, updated_at=? WHERE id=? AND team_id=?",
                (task_status, now, shared_task_id, team_id),
            )
            self._reconcile_active_claim_counts(conn, team_id)
            self._append_event(
                conn, team_id=team_id, mission_id=str(team["mission_id"]),
                event_type="claim.closed", actor=actor,
                event_key=(
                    f"claim-closed:{claim_id}:{int(fencing_token)}:{terminal_status}"
                ),
                agent_instance_id=str(current["agent_instance_id"]),
                shared_task_id=shared_task_id,
                metadata={
                    "claim_id": claim_id,
                    "fencing_token": int(fencing_token),
                    "terminal_status": terminal_status,
                },
            )
            return self._serialize(
                conn.execute("SELECT * FROM task_claims WHERE id=?", (claim_id,)).fetchone()
            )

    @staticmethod
    def _reconcile_active_claim_counts(conn: Any, team_id: str) -> None:
        conn.execute(
            """
            UPDATE agent_instances SET active_claims=(
                SELECT COUNT(*) FROM task_claims
                WHERE task_claims.agent_instance_id=agent_instances.id
                  AND task_claims.status IN ('claimed', 'running', 'verifying')
            )
            WHERE team_id=?
            """,
            (team_id,),
        )

    def bind_context_pack(
        self,
        *,
        team_id: str,
        shared_task_id: str,
        task_claim_id: str,
        context_pack_id: str,
        idempotency_key: str,
        source_refs: list[str] | None = None,
        work_run_id: str = "",
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            mission = self._require_team_access(conn, team, owner_user_id)
            existing = conn.execute(
                "SELECT * FROM agent_task_context_bindings WHERE idempotency_key=?",
                (str(idempotency_key),),
            ).fetchone()
            if existing:
                return self._serialize(existing)
            claim = conn.execute(
                """
                SELECT * FROM task_claims
                WHERE id=? AND team_id=? AND shared_task_id=?
                """,
                (task_claim_id, team_id, shared_task_id),
            ).fetchone()
            if not claim or str(claim["status"]) not in ACTIVE_CLAIM_STATES:
                raise AgentTeamError("context pack requires the current active claim")
            binding_id = f"team-context-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO agent_task_context_bindings
                (id, team_id, shared_task_id, task_claim_id, work_run_id,
                 context_pack_id, owner_user_id, project_id, source_refs_json,
                 status, created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    binding_id, team_id, shared_task_id, task_claim_id,
                    str(work_run_id).strip()[:200] or None,
                    str(context_pack_id).strip()[:200],
                    str(mission["owner_user_id"] or ""),
                    str(mission["project_id"] or ""),
                    _json(_clean_list(source_refs, limit=500)), _now(), str(idempotency_key),
                ),
            )
            return self._serialize(
                conn.execute(
                    "SELECT * FROM agent_task_context_bindings WHERE id=?",
                    (binding_id,),
                ).fetchone()
            )

    def send_message(
        self,
        *,
        team_id: str,
        from_instance_id: str,
        message_type: str,
        content: str,
        idempotency_key: str,
        to_instance_id: str = "",
        to_role_id: str = "",
        shared_task_id: str = "",
        artifact_refs: list[str] | None = None,
        requires_ack: bool = False,
        correlation_id: str = "",
        metadata: dict[str, Any] | None = None,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        if bool(to_instance_id) == bool(to_role_id):
            raise AgentTeamError("exactly one message recipient is required")
        with self.connect(immediate=True) as conn:
            team = self._require_team(conn, team_id)
            self._require_team_access(conn, team, owner_user_id)
            existing = conn.execute(
                "SELECT * FROM agent_messages WHERE team_id=? AND idempotency_key=?",
                (team_id, str(idempotency_key)),
            ).fetchone()
            if existing:
                return self._serialize(existing)
            sender = conn.execute(
                "SELECT id FROM agent_instances WHERE id=? AND team_id=?",
                (from_instance_id, team_id),
            ).fetchone()
            recipient = conn.execute(
                "SELECT id FROM agent_instances WHERE id=? AND team_id=?",
                (to_instance_id, team_id),
            ).fetchone() if to_instance_id else conn.execute(
                "SELECT id FROM agent_team_roles WHERE id=? AND team_id=?",
                (to_role_id, team_id),
            ).fetchone()
            task = conn.execute(
                "SELECT id FROM shared_tasks WHERE id=? AND team_id=?",
                (shared_task_id, team_id),
            ).fetchone() if shared_task_id else True
            if not sender or not recipient or not task:
                raise AgentTeamError("message references must belong to team")
            message_id = f"agent-message-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO agent_messages
                (id, team_id, shared_task_id, from_instance_id, to_instance_id,
                 to_role_id, message_type, content, artifact_refs_json,
                 requires_ack, correlation_id, idempotency_key, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id, team_id, shared_task_id or None, from_instance_id,
                    to_instance_id or None, to_role_id or None,
                    str(message_type).strip()[:80], str(content)[:20000],
                    _json(_clean_list(artifact_refs, limit=100)), int(bool(requires_ack)),
                    str(correlation_id).strip()[:200] or None,
                    str(idempotency_key), _json(metadata or {}), _now(),
                ),
            )
            self._append_event(
                conn, team_id=team_id, mission_id=str(team["mission_id"]),
                event_type="message.sent", actor=from_instance_id,
                event_key=f"message-sent:{idempotency_key}",
                agent_instance_id=from_instance_id,
                shared_task_id=shared_task_id or None,
                metadata={"message_id": message_id, "message_type": message_type},
            )
            return self._serialize(
                conn.execute("SELECT * FROM agent_messages WHERE id=?", (message_id,)).fetchone()
            )

    def snapshot(self, team_id: str, *, owner_user_id: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            team = self._require_team(conn, team_id)
            self._require_team_access(conn, team, owner_user_id)
            queries = {
                "roles": "SELECT * FROM agent_team_roles WHERE team_id=? ORDER BY role_key",
                "instances": "SELECT * FROM agent_instances WHERE team_id=? ORDER BY instance_key",
                "tasks": "SELECT * FROM shared_tasks WHERE team_id=? ORDER BY priority DESC, created_at, id",
                "dependencies": "SELECT * FROM shared_task_dependencies WHERE team_id=? ORDER BY created_at, id",
                "claims": "SELECT * FROM task_claims WHERE team_id=? ORDER BY claimed_at, id",
                "context_bindings": "SELECT * FROM agent_task_context_bindings WHERE team_id=? ORDER BY created_at, id",
                "messages": "SELECT * FROM agent_messages WHERE team_id=? ORDER BY created_at, id",
                "events": "SELECT * FROM team_events WHERE team_id=? ORDER BY sequence",
            }
            return {
                "team": self._serialize(team),
                **{
                    key: [self._serialize(row) for row in conn.execute(sql, (team_id,)).fetchall()]
                    for key, sql in queries.items()
                },
            }


agent_team_service = AgentTeamService(command_center_service)
