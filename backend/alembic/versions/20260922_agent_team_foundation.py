"""Add Agent Team collaboration foundation.

Revision ID: 20260922_agent_team
Revises: 20260921_worker_registry
"""

from alembic import op


revision = "20260922_agent_team"
down_revision = "20260921_worker_registry"
branch_labels = None
depends_on = None


STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_teams (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
        generation INTEGER NOT NULL DEFAULT 1, name TEXT NOT NULL,
        leader_agent_id TEXT NOT NULL DEFAULT 'optimus',
        status TEXT NOT NULL DEFAULT 'forming',
        policy_version TEXT NOT NULL DEFAULT 'agent-team-v1',
        max_members INTEGER NOT NULL DEFAULT 8,
        max_parallel_tasks INTEGER NOT NULL DEFAULT 4,
        idempotency_key TEXT NOT NULL UNIQUE,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, generation)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_teams_one_active
    ON agent_teams(mission_id)
    WHERE status NOT IN ('completed', 'failed', 'cancelled')
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_team_roles (
        id TEXT PRIMARY KEY, team_id TEXT NOT NULL, role_key TEXT NOT NULL,
        display_name TEXT NOT NULL, capabilities_json TEXT NOT NULL DEFAULT '[]',
        required_tools_json TEXT NOT NULL DEFAULT '[]',
        min_instances INTEGER NOT NULL DEFAULT 0,
        max_instances INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'active',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(team_id) REFERENCES agent_teams(id),
        UNIQUE(team_id, role_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_instances (
        id TEXT PRIMARY KEY, team_id TEXT NOT NULL, role_id TEXT NOT NULL,
        instance_key TEXT NOT NULL, base_agent_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'starting', capacity INTEGER NOT NULL DEFAULT 1,
        active_claims INTEGER NOT NULL DEFAULT 0, context_thread_id TEXT,
        context_pack_id TEXT, last_seen_at TEXT,
        failure_count INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, stopped_at TEXT,
        FOREIGN KEY(team_id) REFERENCES agent_teams(id),
        FOREIGN KEY(role_id) REFERENCES agent_team_roles(id),
        UNIQUE(team_id, instance_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_instances_schedulable
    ON agent_instances(team_id, status, active_claims, last_seen_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS shared_tasks (
        id TEXT PRIMARY KEY, team_id TEXT NOT NULL, mission_id TEXT NOT NULL,
        mission_step_id TEXT, task_key TEXT NOT NULL, title TEXT NOT NULL,
        objective TEXT NOT NULL, task_type TEXT NOT NULL DEFAULT 'general',
        status TEXT NOT NULL DEFAULT 'draft', priority INTEGER NOT NULL DEFAULT 50,
        risk_class TEXT NOT NULL DEFAULT 'L1', dependencies_json TEXT NOT NULL DEFAULT '[]',
        required_capabilities_json TEXT NOT NULL DEFAULT '[]',
        required_tools_json TEXT NOT NULL DEFAULT '[]',
        input_contract_json TEXT NOT NULL DEFAULT '{}',
        output_contract_json TEXT NOT NULL DEFAULT '{}',
        acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
        evidence_required_json TEXT NOT NULL DEFAULT '[]',
        max_claims INTEGER NOT NULL DEFAULT 3, idempotency_key TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, completed_at TEXT,
        FOREIGN KEY(team_id) REFERENCES agent_teams(id),
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(mission_step_id) REFERENCES mission_steps(id),
        UNIQUE(team_id, task_key), UNIQUE(team_id, idempotency_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_shared_tasks_queue
    ON shared_tasks(team_id, status, priority, updated_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS task_claims (
        id TEXT PRIMARY KEY, shared_task_id TEXT NOT NULL,
        agent_instance_id TEXT NOT NULL, attempt INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'claimed', score DOUBLE PRECISION NOT NULL DEFAULT 0,
        rationale_json TEXT NOT NULL DEFAULT '{}', lease_owner TEXT, lease_token TEXT,
        lease_expires_at TEXT, work_run_id TEXT,
        idempotency_key TEXT NOT NULL UNIQUE, result_json TEXT NOT NULL DEFAULT '{}',
        last_error TEXT, claimed_at TEXT NOT NULL, started_at TEXT,
        completed_at TEXT, updated_at TEXT NOT NULL,
        FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
        FOREIGN KEY(agent_instance_id) REFERENCES agent_instances(id),
        UNIQUE(shared_task_id, attempt)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_task_claims_active
    ON task_claims(shared_task_id, status, lease_expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_messages (
        id TEXT PRIMARY KEY, team_id TEXT NOT NULL, shared_task_id TEXT,
        from_instance_id TEXT NOT NULL, to_instance_id TEXT, to_role_id TEXT,
        message_type TEXT NOT NULL, content TEXT NOT NULL,
        artifact_refs_json TEXT NOT NULL DEFAULT '[]',
        requires_ack INTEGER NOT NULL DEFAULT 0, acknowledged_at TEXT,
        correlation_id TEXT, idempotency_key TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        FOREIGN KEY(team_id) REFERENCES agent_teams(id),
        FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
        FOREIGN KEY(from_instance_id) REFERENCES agent_instances(id),
        FOREIGN KEY(to_instance_id) REFERENCES agent_instances(id),
        FOREIGN KEY(to_role_id) REFERENCES agent_team_roles(id),
        UNIQUE(team_id, idempotency_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_messages_route
    ON agent_messages(team_id, to_instance_id, to_role_id, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS team_events (
        id TEXT PRIMARY KEY, team_id TEXT NOT NULL, mission_id TEXT NOT NULL,
        sequence INTEGER NOT NULL, event_type TEXT NOT NULL, actor TEXT NOT NULL,
        agent_instance_id TEXT, shared_task_id TEXT, detail TEXT NOT NULL DEFAULT '',
        event_key TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(team_id) REFERENCES agent_teams(id),
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(agent_instance_id) REFERENCES agent_instances(id),
        FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
        UNIQUE(team_id, sequence), UNIQUE(team_id, event_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_team_events_stream
    ON team_events(team_id, sequence)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "team_events",
        "agent_messages",
        "task_claims",
        "shared_tasks",
        "agent_instances",
        "agent_team_roles",
        "agent_teams",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
