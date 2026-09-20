"""Create PostgreSQL canonical Work Run tables.

Revision ID: 20260919_work_run_pg
Revises: 20260918_command_center_pg
"""

from alembic import op


revision = "20260919_work_run_pg"
down_revision = "20260918_command_center_pg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS work_runs (
            id TEXT PRIMARY KEY,
            dispatch_id TEXT NOT NULL,
            mission_id TEXT,
            mission_run_id TEXT,
            project_id TEXT,
            task_id TEXT,
            development_point_id TEXT,
            agent_id TEXT,
            executor TEXT,
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            idempotency_key TEXT NOT NULL,
            lease_owner TEXT,
            lease_expires_at TEXT,
            correlation_id TEXT NOT NULL,
            workspace TEXT,
            prompt_path TEXT,
            result_summary TEXT,
            failure_code TEXT,
            failure_detail TEXT,
            input_context TEXT NOT NULL DEFAULT '{}',
            execution_result TEXT NOT NULL DEFAULT '{}',
            metrics TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            ended_at TEXT,
            UNIQUE(idempotency_key, attempt)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS work_run_events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES work_runs(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            actor TEXT,
            detail TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS work_artifacts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES work_runs(id) ON DELETE CASCADE,
            project_id TEXT,
            task_id TEXT,
            artifact_type TEXT NOT NULL,
            title TEXT NOT NULL,
            uri TEXT,
            checksum TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_runs_dispatch ON work_runs(dispatch_id, attempt DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_runs_task ON work_runs(project_id, task_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_runs_status_lease ON work_runs(status, lease_expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_runs_mission ON work_runs(mission_run_id, created_at, attempt)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_run_events_run ON work_run_events(run_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_artifacts_run ON work_artifacts(run_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS work_artifacts")
    op.execute("DROP TABLE IF EXISTS work_run_events")
    op.execute("DROP TABLE IF EXISTS work_runs")

