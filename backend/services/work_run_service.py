"""Canonical work execution records for Company OS.

The OpenClaw queue is a delivery mechanism.  This service stores the durable
execution truth in ``unified_dashboard.db`` so a task can be resumed, audited,
retried, and verified without depending on queue JSON snapshots.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

from unified_data_manager import UNIFIED_DB_PATH


CANONICAL_WORK_STATUSES = (
    "draft",
    "ready",
    "claimed",
    "running",
    "review",
    "verifying",
    "completed",
    "blocked",
    "failed",
    "cancelled",
)

STATUS_ALIASES = {
    "pending": "ready",
    "todo": "ready",
    "assigned": "ready",
    "in_progress": "running",
    "in-progress": "running",
    "done": "completed",
    "released": "cancelled",
    "skipped": "blocked",
}

ALLOWED_TRANSITIONS = {
    "draft": {"ready", "cancelled"},
    "ready": {"claimed", "blocked", "cancelled"},
    "claimed": {"running", "blocked", "failed", "cancelled"},
    "running": {"review", "blocked", "failed", "cancelled"},
    "review": {"verifying", "completed", "blocked", "failed", "cancelled"},
    "verifying": {"completed", "blocked", "failed", "cancelled"},
    "blocked": {"ready", "cancelled"},
    "failed": {"ready", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

ACTIVE_STATUSES = {"claimed", "running", "review", "verifying"}
ENDED_STATUSES = {"completed", "blocked", "failed", "cancelled"}


class WorkRunError(RuntimeError):
    """Base error for canonical execution records."""


class WorkRunNotFound(WorkRunError):
    pass


class WorkRunLeaseConflict(WorkRunError):
    pass


class InvalidWorkTransition(WorkRunError):
    pass


def normalize_work_status(value: str | None, default: str = "draft") -> str:
    status = str(value or default).strip().lower()
    status = STATUS_ALIASES.get(status, status)
    if status not in CANONICAL_WORK_STATUSES:
        raise InvalidWorkTransition(f"unknown work status: {value}")
    return status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class WorkRunService:
    def __init__(self, db_path: str = UNIFIED_DB_PATH):
        self.db_path = db_path
        self.ensure_schema()

    @contextmanager
    def connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS work_runs (
                    id TEXT PRIMARY KEY,
                    dispatch_id TEXT NOT NULL,
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
                );

                CREATE INDEX IF NOT EXISTS idx_work_runs_dispatch
                    ON work_runs(dispatch_id, attempt DESC);
                CREATE INDEX IF NOT EXISTS idx_work_runs_task
                    ON work_runs(project_id, task_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_work_runs_status_lease
                    ON work_runs(status, lease_expires_at);

                CREATE TABLE IF NOT EXISTS work_run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    actor TEXT,
                    detail TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES work_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_work_run_events_run
                    ON work_run_events(run_id, created_at);

                CREATE TABLE IF NOT EXISTS work_artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    project_id TEXT,
                    task_id TEXT,
                    artifact_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    uri TEXT,
                    checksum TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES work_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_work_artifacts_run
                    ON work_artifacts(run_id, created_at);

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    "005_canonical_work_runs",
                    "Create canonical work runs, events, artifacts, leases, and attempts",
                    _iso(),
                ),
            )

    def claim(
        self,
        *,
        dispatch_id: str,
        agent_id: str,
        executor: str,
        project_id: str = "",
        task_id: str = "",
        development_point_id: str = "",
        workspace: str = "",
        input_context: Optional[dict[str, Any]] = None,
        lease_seconds: int = 900,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        if not dispatch_id:
            raise WorkRunError("dispatch_id is required")
        owner = agent_id or "runner"
        key = idempotency_key or dispatch_id
        now = _now()
        lease_expires = now + timedelta(seconds=max(lease_seconds, 30))
        with self.connect(immediate=True) as conn:
            latest = conn.execute(
                """
                SELECT * FROM work_runs
                WHERE idempotency_key=?
                ORDER BY attempt DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
            if latest and latest["status"] in ACTIVE_STATUSES:
                expires_at = self._parse_iso(latest["lease_expires_at"])
                if latest["lease_owner"] not in {None, "", owner} and expires_at and expires_at > now:
                    raise WorkRunLeaseConflict(
                        f"dispatch {dispatch_id} is leased by {latest['lease_owner']} until {latest['lease_expires_at']}"
                    )
                conn.execute(
                    """
                    UPDATE work_runs
                    SET lease_owner=?, lease_expires_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (owner, _iso(lease_expires), _iso(now), latest["id"]),
                )
                self._insert_event(
                    conn,
                    latest["id"],
                    "lease_reclaimed" if expires_at and expires_at <= now else "lease_renewed",
                    latest["status"],
                    latest["status"],
                    owner,
                    "Runner claimed an existing active run",
                    {"lease_expires_at": _iso(lease_expires)},
                )
                return self._get_run(conn, latest["id"])

            attempt = int(latest["attempt"] or 0) + 1 if latest else 1
            run_id = f"wrun-{uuid.uuid4().hex[:16]}"
            correlation_id = f"work-{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO work_runs
                (id, dispatch_id, project_id, task_id, development_point_id,
                 agent_id, executor, status, attempt, idempotency_key,
                 lease_owner, lease_expires_at, correlation_id, workspace,
                 input_context, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    dispatch_id,
                    project_id or None,
                    task_id or None,
                    development_point_id or None,
                    owner,
                    executor,
                    attempt,
                    key,
                    owner,
                    _iso(lease_expires),
                    correlation_id,
                    workspace or None,
                    _json(input_context or {}),
                    _iso(now),
                    _iso(now),
                ),
            )
            self._insert_event(
                conn,
                run_id,
                "claimed",
                "ready",
                "claimed",
                owner,
                "Runner claimed the delivery queue item",
                {"dispatch_id": dispatch_id, "attempt": attempt},
            )
            self._sync_task_status(conn, task_id, "claimed", _iso(now))
            return self._get_run(conn, run_id)

    def transition(
        self,
        run_id: str,
        status: str,
        *,
        actor: str = "runner",
        detail: str = "",
        prompt_path: str | None = None,
        workspace: str | None = None,
        result_summary: str | None = None,
        failure_code: str | None = None,
        failure_detail: str | None = None,
        execution_result: Optional[dict[str, Any]] = None,
        metrics: Optional[dict[str, Any]] = None,
        lease_seconds: int = 900,
    ) -> dict[str, Any]:
        next_status = normalize_work_status(status)
        now = _now()
        with self.connect(immediate=True) as conn:
            current = conn.execute("SELECT * FROM work_runs WHERE id=?", (run_id,)).fetchone()
            if not current:
                raise WorkRunNotFound(run_id)
            previous = normalize_work_status(current["status"])
            if next_status != previous and next_status not in ALLOWED_TRANSITIONS[previous]:
                raise InvalidWorkTransition(f"invalid work transition: {previous} -> {next_status}")

            values: dict[str, Any] = {
                "status": next_status,
                "updated_at": _iso(now),
            }
            if next_status == "running":
                values["started_at"] = current["started_at"] or _iso(now)
            if next_status in ACTIVE_STATUSES:
                values["lease_expires_at"] = _iso(now + timedelta(seconds=max(lease_seconds, 30)))
            if next_status in ENDED_STATUSES:
                values["ended_at"] = _iso(now)
                values["lease_expires_at"] = None
            optional = {
                "prompt_path": prompt_path,
                "workspace": workspace,
                "result_summary": result_summary,
                "failure_code": failure_code,
                "failure_detail": failure_detail,
                "execution_result": _json(execution_result) if execution_result is not None else None,
                "metrics": _json(metrics) if metrics is not None else None,
            }
            values.update({key: value for key, value in optional.items() if value is not None})
            assignments = ", ".join(f"{key}=?" for key in values)
            conn.execute(
                f"UPDATE work_runs SET {assignments} WHERE id=?",
                (*values.values(), run_id),
            )
            self._insert_event(
                conn,
                run_id,
                "status_changed" if previous != next_status else "status_refreshed",
                previous,
                next_status,
                actor,
                detail,
                {"failure_code": failure_code} if failure_code else {},
            )
            self._sync_task_status(conn, current["task_id"], next_status, _iso(now), result_summary)
            return self._get_run(conn, run_id)

    def heartbeat(self, run_id: str, *, actor: str, lease_seconds: int = 900) -> dict[str, Any]:
        now = _now()
        with self.connect(immediate=True) as conn:
            current = conn.execute("SELECT * FROM work_runs WHERE id=?", (run_id,)).fetchone()
            if not current:
                raise WorkRunNotFound(run_id)
            if current["status"] not in ACTIVE_STATUSES:
                raise WorkRunLeaseConflict(f"run {run_id} is not active")
            if current["lease_owner"] not in {None, "", actor}:
                raise WorkRunLeaseConflict(f"run {run_id} is leased by {current['lease_owner']}")
            expires = now + timedelta(seconds=max(lease_seconds, 30))
            conn.execute(
                "UPDATE work_runs SET lease_owner=?, lease_expires_at=?, updated_at=? WHERE id=?",
                (actor, _iso(expires), _iso(now), run_id),
            )
            return self._get_run(conn, run_id)

    def add_artifact(
        self,
        run_id: str,
        *,
        artifact_type: str,
        title: str,
        uri: str = "",
        checksum: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            run = conn.execute("SELECT * FROM work_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise WorkRunNotFound(run_id)
            artifact_id = f"wart-{uuid.uuid4().hex[:16]}"
            created_at = _iso()
            conn.execute(
                """
                INSERT INTO work_artifacts
                (id, run_id, project_id, task_id, artifact_type, title, uri, checksum, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    run_id,
                    run["project_id"],
                    run["task_id"],
                    artifact_type,
                    title,
                    uri or None,
                    checksum or None,
                    _json(metadata or {}),
                    created_at,
                ),
            )
            self._insert_event(
                conn,
                run_id,
                "artifact_added",
                run["status"],
                run["status"],
                "runner",
                title,
                {"artifact_id": artifact_id, "artifact_type": artifact_type},
            )
            return {
                "id": artifact_id,
                "run_id": run_id,
                "artifact_type": artifact_type,
                "title": title,
                "uri": uri,
                "checksum": checksum,
                "metadata": metadata or {},
                "created_at": created_at,
            }

    def get(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            return self._get_run(conn, run_id)

    def latest_for_dispatch(self, dispatch_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_runs WHERE dispatch_id=? ORDER BY attempt DESC LIMIT 1",
                (dispatch_id,),
            ).fetchone()
            return self._serialize_run(conn, row) if row else None

    def list(
        self,
        *,
        project_id: str = "",
        task_id: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        if task_id:
            clauses.append("task_id=?")
            params.append(task_id)
        if status:
            clauses.append("status=?")
            params.append(normalize_work_status(status))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM work_runs {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [self._serialize_run(conn, row) for row in rows]

    def summary(self, *, limit: int = 200) -> dict[str, Any]:
        runs = self.list(limit=limit)
        counts = {status: 0 for status in CANONICAL_WORK_STATUSES}
        with self.connect() as conn:
            for row in conn.execute("SELECT status, COUNT(*) AS count FROM work_runs GROUP BY status"):
                counts[row["status"]] = int(row["count"])
        return {
            "runs": runs,
            "total": sum(counts.values()),
            "counts": counts,
            "source": "unified_dashboard.db:work_runs",
            "updated_at": _iso(),
        }

    def _get_run(self, conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM work_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise WorkRunNotFound(run_id)
        return self._serialize_run(conn, row)

    def _serialize_run(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["input_context"] = _loads(data.get("input_context"), {})
        data["execution_result"] = _loads(data.get("execution_result"), {})
        data["metrics"] = _loads(data.get("metrics"), {})
        data["events"] = [
            {
                **dict(event),
                "metadata": _loads(event["metadata"], {}),
            }
            for event in conn.execute(
                "SELECT * FROM work_run_events WHERE run_id=? ORDER BY created_at, id",
                (row["id"],),
            ).fetchall()
        ]
        data["artifacts"] = [
            {
                **dict(artifact),
                "metadata": _loads(artifact["metadata"], {}),
            }
            for artifact in conn.execute(
                "SELECT * FROM work_artifacts WHERE run_id=? ORDER BY created_at, id",
                (row["id"],),
            ).fetchall()
        ]
        return data

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        event_type: str,
        from_status: str,
        to_status: str,
        actor: str,
        detail: str,
        metadata: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO work_run_events
            (id, run_id, event_type, from_status, to_status, actor, detail, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"wrev-{uuid.uuid4().hex[:16]}",
                run_id,
                event_type,
                from_status,
                to_status,
                actor,
                detail[:1000],
                _json(metadata),
                _iso(),
            ),
        )

    def _sync_task_status(
        self,
        conn: sqlite3.Connection,
        task_id: str | None,
        status: str,
        updated_at: str,
        result_summary: str | None = None,
    ) -> None:
        if not task_id:
            return
        exists = conn.execute("SELECT 1 FROM project_tasks WHERE id=?", (task_id,)).fetchone()
        if not exists:
            return
        if result_summary is None:
            conn.execute(
                "UPDATE project_tasks SET status=?, updated_at=? WHERE id=?",
                (status, updated_at, task_id),
            )
        else:
            conn.execute(
                "UPDATE project_tasks SET status=?, result_summary=?, updated_at=? WHERE id=?",
                (status, result_summary, updated_at, task_id),
            )

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


work_run_service = WorkRunService()
