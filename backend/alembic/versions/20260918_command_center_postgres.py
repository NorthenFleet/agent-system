"""Create PostgreSQL Command Center fact tables.

Revision ID: 20260918_command_center_pg
Revises: 20260916_memory_vector
"""

from alembic import op


revision = "20260918_command_center_pg"
down_revision = "20260916_memory_vector"
branch_labels = None
depends_on = None


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS command_conversations (
        id TEXT PRIMARY KEY, channel TEXT NOT NULL,
        external_conversation_id TEXT NOT NULL, user_external_id TEXT,
        owner_user_id TEXT, profile_user_id TEXT,
        status TEXT NOT NULL DEFAULT 'active', metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(channel, external_conversation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS command_messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, mission_id TEXT,
        direction TEXT NOT NULL, external_message_id TEXT,
        reply_to_external_message_id TEXT, sender_id TEXT, content TEXT NOT NULL,
        message_type TEXT NOT NULL DEFAULT 'text', intent_type TEXT NOT NULL DEFAULT '',
        intent_confidence REAL NOT NULL DEFAULT 0, intent_reason TEXT NOT NULL DEFAULT '',
        execution_requested INTEGER NOT NULL DEFAULT 0, routing_status TEXT NOT NULL DEFAULT '',
        target_agent_id TEXT NOT NULL DEFAULT 'optimus', resolved_project_id TEXT,
        reply_to_command_message_id TEXT, metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(conversation_id) REFERENCES command_conversations(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS command_external_user_bindings (
        id TEXT PRIMARY KEY, channel TEXT NOT NULL, external_user_id TEXT NOT NULL,
        internal_user_id TEXT NOT NULL, profile_user_id TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(channel, external_user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orchestration_missions (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, source_message_id TEXT,
        title TEXT NOT NULL, objective TEXT NOT NULL, status TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'normal', project_id TEXT, mission_type TEXT,
        requested_by TEXT, owner_user_id TEXT, plan_version INTEGER NOT NULL DEFAULT 0,
        current_step_id TEXT, requires_approval INTEGER NOT NULL DEFAULT 1,
        approval_status TEXT NOT NULL DEFAULT 'pending', last_error TEXT,
        context_json TEXT NOT NULL DEFAULT '{}', lease_owner TEXT, lease_expires_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT,
        FOREIGN KEY(conversation_id) REFERENCES command_conversations(id),
        FOREIGN KEY(source_message_id) REFERENCES command_messages(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_runs (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL UNIQUE,
        correlation_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
        active_plan_version INTEGER NOT NULL DEFAULT 0, workflow_run_id TEXT,
        outcome TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_plan_versions (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, version INTEGER NOT NULL,
        summary TEXT NOT NULL, rationale TEXT, risk_level TEXT NOT NULL DEFAULT 'medium',
        raw_plan TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'pending',
        created_by_agent_id TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_steps (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, plan_version INTEGER NOT NULL,
        order_index INTEGER NOT NULL, title TEXT NOT NULL, description TEXT,
        task_type TEXT NOT NULL DEFAULT 'general', agent_id TEXT NOT NULL DEFAULT 'optimus',
        executor TEXT NOT NULL DEFAULT 'openclaw', status TEXT NOT NULL DEFAULT 'draft',
        dependencies_json TEXT NOT NULL DEFAULT '[]', input_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT NOT NULL DEFAULT '{}', work_run_id TEXT, lease_owner TEXT,
        lease_token TEXT, lease_expires_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
        started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, plan_version, order_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_step_approvals (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, plan_version INTEGER NOT NULL,
        step_id TEXT NOT NULL, request_version INTEGER NOT NULL, risk_class TEXT NOT NULL,
        action_summary TEXT NOT NULL, contract_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', requested_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT, comment TEXT,
        consumed_at TEXT, FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(step_id) REFERENCES mission_steps(id), UNIQUE(step_id, request_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_effects (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, plan_version INTEGER NOT NULL, step_id TEXT NOT NULL,
        work_run_id TEXT, effect_key TEXT NOT NULL, resource TEXT NOT NULL,
        action TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL,
        receipt_ref TEXT, evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}', fingerprint TEXT NOT NULL UNIQUE,
        reported_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(step_id) REFERENCES mission_steps(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_compensations (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, plan_version INTEGER NOT NULL, step_id TEXT NOT NULL,
        effect_id TEXT NOT NULL UNIQUE, compensation_type TEXT NOT NULL,
        instructions TEXT NOT NULL, resource TEXT NOT NULL, contract_hash TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending_approval',
        attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 1,
        requested_at TEXT NOT NULL, approved_at TEXT, approved_by TEXT,
        approval_comment TEXT, authorization_expires_at TEXT, lease_owner TEXT,
        lease_token TEXT, lease_expires_at TEXT, result_json TEXT NOT NULL DEFAULT '{}',
        last_error TEXT, started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(step_id) REFERENCES mission_steps(id),
        FOREIGN KEY(effect_id) REFERENCES mission_effects(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_approvals (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, plan_version INTEGER NOT NULL,
        decision TEXT NOT NULL DEFAULT 'pending', requested_at TEXT NOT NULL,
        decided_at TEXT, decided_by TEXT, comment TEXT, external_message_id TEXT,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, plan_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_events (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, run_sequence INTEGER NOT NULL DEFAULT 0,
        event_type TEXT NOT NULL, from_status TEXT, to_status TEXT, actor TEXT,
        detail TEXT, event_key TEXT, metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_context_bindings (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, plan_version INTEGER NOT NULL,
        step_id TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL,
        agent_id TEXT NOT NULL DEFAULT 'optimus', context_pack_id TEXT,
        context_pack_version INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
        query TEXT NOT NULL DEFAULT '', summary TEXT, item_count INTEGER NOT NULL DEFAULT 0,
        citation_count INTEGER NOT NULL DEFAULT 0, source_types_json TEXT NOT NULL DEFAULT '[]',
        citations_json TEXT NOT NULL DEFAULT '[]', retrieval_health_json TEXT NOT NULL DEFAULT '{}',
        error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, plan_version, step_id, purpose)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workflow_runs (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, plan_version INTEGER NOT NULL, runtime TEXT NOT NULL,
        flow_key TEXT NOT NULL DEFAULT 'general', highest_risk TEXT NOT NULL DEFAULT 'L1',
        selection_reason TEXT NOT NULL DEFAULT '', thread_id TEXT NOT NULL,
        checkpoint_namespace TEXT NOT NULL DEFAULT 'pilot', status TEXT NOT NULL,
        input_json TEXT NOT NULL DEFAULT '{}', state_json TEXT NOT NULL DEFAULT '{}',
        resume_payload_json TEXT NOT NULL DEFAULT '{}', checkpoint_json TEXT NOT NULL DEFAULT '{}',
        attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL,
        lease_owner TEXT, lease_token TEXT, lease_expires_at TEXT, last_error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, plan_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_artifacts (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, plan_version INTEGER NOT NULL, step_id TEXT NOT NULL,
        work_run_id TEXT, artifact_type TEXT NOT NULL, title TEXT NOT NULL, uri TEXT NOT NULL,
        content_hash TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(step_id) REFERENCES mission_steps(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_evidence (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, plan_version INTEGER NOT NULL, step_id TEXT NOT NULL,
        artifact_id TEXT, evidence_type TEXT NOT NULL, source_ref TEXT NOT NULL,
        summary TEXT NOT NULL, collected_by TEXT NOT NULL, collected_at TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1, fingerprint TEXT NOT NULL UNIQUE,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(step_id) REFERENCES mission_steps(id),
        FOREIGN KEY(artifact_id) REFERENCES mission_artifacts(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_acceptance_gates (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mission_run_id TEXT,
        correlation_id TEXT, plan_version INTEGER NOT NULL, step_id TEXT NOT NULL DEFAULT '',
        gate_type TEXT NOT NULL, mode TEXT NOT NULL, enforced INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0, score INTEGER NOT NULL DEFAULT 0,
        blockers_json TEXT NOT NULL DEFAULT '[]', warnings_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}', evaluated_by TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        UNIQUE(mission_id, plan_version, step_id, gate_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_outbox (
        id TEXT PRIMARY KEY, mission_id TEXT, conversation_id TEXT, command_message_id TEXT,
        channel TEXT NOT NULL, account_id TEXT NOT NULL DEFAULT 'optimus', target TEXT NOT NULL,
        message_text TEXT NOT NULL, reply_to TEXT, status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL, locked_at TEXT,
        lock_owner TEXT, last_error TEXT, payload TEXT NOT NULL DEFAULT '{}',
        idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, sent_at TEXT,
        FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
        FOREIGN KEY(conversation_id) REFERENCES command_conversations(id),
        FOREIGN KEY(command_message_id) REFERENCES command_messages(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_deliveries (
        id TEXT PRIMARY KEY, outbox_id TEXT NOT NULL, attempt INTEGER NOT NULL,
        success INTEGER NOT NULL, external_message_id TEXT, response TEXT, error TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(outbox_id) REFERENCES notification_outbox(id)
    )
    """,
)


INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_command_external_user_bindings_user ON command_external_user_bindings(internal_user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_command_missions_status ON orchestration_missions(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_command_missions_conversation ON orchestration_missions(conversation_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_command_missions_owner ON orchestration_missions(owner_user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_command_conversations_owner ON command_conversations(owner_user_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_command_messages_intent ON command_messages(intent_type, routing_status, created_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_command_messages_external ON command_messages(conversation_id, external_message_id) WHERE external_message_id IS NOT NULL AND external_message_id != ''",
    "CREATE INDEX IF NOT EXISTS idx_mission_runs_status ON mission_runs(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_mission_steps_ready ON mission_steps(status, lease_expires_at, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_mission_step_approvals_pending ON mission_step_approvals(mission_id, plan_version, status, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_mission_effects_scope ON mission_effects(mission_id, plan_version, step_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_mission_compensations_pending ON mission_compensations(status, lease_expires_at, requested_at)",
    "CREATE INDEX IF NOT EXISTS idx_mission_events_mission ON mission_events(mission_id, created_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_events_key ON mission_events(mission_id, event_key) WHERE event_key IS NOT NULL AND event_key != ''",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_events_run_sequence ON mission_events(mission_run_id, run_sequence) WHERE mission_run_id IS NOT NULL AND mission_run_id != '' AND run_sequence > 0",
    "CREATE INDEX IF NOT EXISTS idx_mission_context_bindings_scope ON mission_context_bindings(mission_id, plan_version, purpose, step_id)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_runs_pending ON workflow_runs(runtime, status, next_attempt_at, lease_expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_mission_artifacts_scope ON mission_artifacts(mission_id, plan_version, step_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_mission_evidence_scope ON mission_evidence(mission_id, plan_version, step_id, evidence_type)",
    "CREATE INDEX IF NOT EXISTS idx_mission_acceptance_scope ON mission_acceptance_gates(mission_id, plan_version, status, enforced)",
    "CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending ON notification_outbox(status, next_attempt_at)",
)


DROP_ORDER = (
    "notification_deliveries",
    "notification_outbox",
    "mission_acceptance_gates",
    "mission_evidence",
    "mission_artifacts",
    "workflow_runs",
    "mission_context_bindings",
    "mission_events",
    "mission_approvals",
    "mission_compensations",
    "mission_effects",
    "mission_step_approvals",
    "mission_steps",
    "mission_plan_versions",
    "mission_runs",
    "orchestration_missions",
    "command_external_user_bindings",
    "command_messages",
    "command_conversations",
)


def upgrade() -> None:
    for statement in SCHEMA_STATEMENTS:
        op.execute(statement)
    for statement in INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in DROP_ORDER:
        op.execute(f'DROP TABLE IF EXISTS "{table}"')

