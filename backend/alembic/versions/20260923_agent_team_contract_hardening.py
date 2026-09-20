"""Harden Agent Team cross-domain persistence contracts.

Revision ID: 20260923_agent_team_hardening
Revises: 20260922_agent_team
"""

from alembic import op


revision = "20260923_agent_team_hardening"
down_revision = "20260922_agent_team"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE task_claims ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE task_claims ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 0"
    )
    op.execute(
        """
        UPDATE task_claims claims
        SET team_id=tasks.team_id
        FROM shared_tasks tasks
        WHERE claims.shared_task_id=tasks.id AND claims.team_id=''
        """
    )
    op.execute(
        "UPDATE task_claims SET fencing_token=attempt WHERE fencing_token=0"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_team_roles_id_team "
        "ON agent_team_roles(id, team_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_instances_id_team "
        "ON agent_instances(id, team_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_shared_tasks_id_team "
        "ON shared_tasks(id, team_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_claims_id_team_task "
        "ON task_claims(id, team_id, shared_task_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_claims_fencing "
        "ON task_claims(shared_task_id, fencing_token)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_task_claims_one_active
        ON task_claims(shared_task_id)
        WHERE status IN ('claimed', 'running', 'verifying')
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_task_dependencies (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            shared_task_id TEXT NOT NULL,
            depends_on_task_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_shared_task_dependency_not_self
                CHECK(shared_task_id <> depends_on_task_id),
            CONSTRAINT uq_shared_task_dependency
                UNIQUE(shared_task_id, depends_on_task_id),
            CONSTRAINT fk_shared_task_dependency_team
                FOREIGN KEY(team_id) REFERENCES agent_teams(id),
            CONSTRAINT fk_shared_task_dependency_task_team
                FOREIGN KEY(shared_task_id, team_id) REFERENCES shared_tasks(id, team_id),
            CONSTRAINT fk_shared_task_dependency_parent_team
                FOREIGN KEY(depends_on_task_id, team_id) REFERENCES shared_tasks(id, team_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_shared_task_dependencies_ready "
        "ON shared_task_dependencies(team_id, shared_task_id, depends_on_task_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_task_context_bindings (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            shared_task_id TEXT NOT NULL,
            task_claim_id TEXT NOT NULL,
            work_run_id TEXT,
            context_pack_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            project_id TEXT NOT NULL DEFAULT '',
            source_refs_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            CONSTRAINT fk_agent_task_context_team
                FOREIGN KEY(team_id) REFERENCES agent_teams(id),
            CONSTRAINT fk_agent_task_context_task_team
                FOREIGN KEY(shared_task_id, team_id) REFERENCES shared_tasks(id, team_id),
            CONSTRAINT fk_agent_task_context_claim_team_task
                FOREIGN KEY(task_claim_id, team_id, shared_task_id)
                REFERENCES task_claims(id, team_id, shared_task_id),
            CONSTRAINT ck_agent_task_context_status
                CHECK(status IN ('active', 'consumed', 'revoked'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_task_context_active "
        "ON agent_task_context_bindings(team_id, shared_task_id, task_claim_id, status)"
    )

    op.execute(
        "ALTER TABLE task_claims ADD CONSTRAINT fk_task_claim_team "
        "FOREIGN KEY(team_id) REFERENCES agent_teams(id)"
    )
    op.execute(
        "ALTER TABLE task_claims ADD CONSTRAINT fk_task_claim_task_team "
        "FOREIGN KEY(shared_task_id, team_id) REFERENCES shared_tasks(id, team_id)"
    )
    op.execute(
        "ALTER TABLE task_claims ADD CONSTRAINT fk_task_claim_instance_team "
        "FOREIGN KEY(agent_instance_id, team_id) REFERENCES agent_instances(id, team_id)"
    )
    op.execute(
        "ALTER TABLE agent_instances ADD CONSTRAINT fk_agent_instance_role_team "
        "FOREIGN KEY(role_id, team_id) REFERENCES agent_team_roles(id, team_id)"
    )
    op.execute(
        "ALTER TABLE agent_messages ADD CONSTRAINT ck_agent_message_one_recipient "
        "CHECK ((to_instance_id IS NOT NULL AND to_role_id IS NULL) "
        "OR (to_instance_id IS NULL AND to_role_id IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE agent_messages ADD CONSTRAINT fk_agent_message_sender_team "
        "FOREIGN KEY(from_instance_id, team_id) REFERENCES agent_instances(id, team_id)"
    )
    op.execute(
        "ALTER TABLE agent_messages ADD CONSTRAINT fk_agent_message_instance_team "
        "FOREIGN KEY(to_instance_id, team_id) REFERENCES agent_instances(id, team_id)"
    )
    op.execute(
        "ALTER TABLE agent_messages ADD CONSTRAINT fk_agent_message_role_team "
        "FOREIGN KEY(to_role_id, team_id) REFERENCES agent_team_roles(id, team_id)"
    )
    op.execute(
        "ALTER TABLE agent_messages ADD CONSTRAINT fk_agent_message_task_team "
        "FOREIGN KEY(shared_task_id, team_id) REFERENCES shared_tasks(id, team_id)"
    )
    op.execute(
        "ALTER TABLE team_events ADD CONSTRAINT fk_team_event_instance_team "
        "FOREIGN KEY(agent_instance_id, team_id) REFERENCES agent_instances(id, team_id)"
    )
    op.execute(
        "ALTER TABLE team_events ADD CONSTRAINT fk_team_event_task_team "
        "FOREIGN KEY(shared_task_id, team_id) REFERENCES shared_tasks(id, team_id)"
    )


def downgrade() -> None:
    for table, constraint in (
        ("team_events", "fk_team_event_task_team"),
        ("team_events", "fk_team_event_instance_team"),
        ("agent_messages", "fk_agent_message_task_team"),
        ("agent_messages", "fk_agent_message_role_team"),
        ("agent_messages", "fk_agent_message_instance_team"),
        ("agent_messages", "fk_agent_message_sender_team"),
        ("agent_messages", "ck_agent_message_one_recipient"),
        ("agent_instances", "fk_agent_instance_role_team"),
        ("task_claims", "fk_task_claim_instance_team"),
        ("task_claims", "fk_task_claim_task_team"),
        ("task_claims", "fk_task_claim_team"),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
    op.execute("DROP TABLE IF EXISTS agent_task_context_bindings")
    op.execute("DROP TABLE IF EXISTS shared_task_dependencies")
    op.execute("DROP INDEX IF EXISTS idx_task_claims_one_active")
    op.execute("DROP INDEX IF EXISTS idx_task_claims_fencing")
    op.execute("DROP INDEX IF EXISTS idx_task_claims_id_team_task")
    op.execute("DROP INDEX IF EXISTS idx_shared_tasks_id_team")
    op.execute("DROP INDEX IF EXISTS idx_agent_instances_id_team")
    op.execute("DROP INDEX IF EXISTS idx_agent_team_roles_id_team")
    op.execute("ALTER TABLE task_claims DROP COLUMN IF EXISTS fencing_token")
    op.execute("ALTER TABLE task_claims DROP COLUMN IF EXISTS team_id")
