"""Review-gated memory candidates distilled from completed missions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

from unified_data_manager import UNIFIED_DB_PATH


IMPORTANCE_SCORES = {
    "critical": 1.0,
    "high": 0.9,
    "normal": 0.72,
    "low": 0.5,
}
MEMORY_TARGETS = {"profile", "project", "agent"}
MEMORY_CANDIDATE_STATUSES = {"pending_review", "published", "rejected"}


class MemoryFeedbackError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class MemoryFeedbackService:
    def __init__(self, db_path: str = UNIFIED_DB_PATH):
        self.db_path = db_path
        self.ensure_schema()

    @contextmanager
    def connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=8)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=8000")
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
                CREATE TABLE IF NOT EXISTS project_context_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance TEXT NOT NULL DEFAULT 'normal',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    source_type TEXT NOT NULL DEFAULT 'mission_result',
                    source_ref TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, project_id, memory_key, source_ref)
                );

                CREATE INDEX IF NOT EXISTS idx_project_context_memories_lookup
                    ON project_context_memories(user_id, project_id, status, importance);

                CREATE TABLE IF NOT EXISTS agent_memories (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    memory_key TEXT NOT NULL DEFAULT '',
                    memory_type TEXT,
                    title TEXT,
                    content TEXT,
                    source TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT,
                    updated_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    profile_id TEXT,
                    mission_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL DEFAULT 0,
                    project_id TEXT,
                    step_id TEXT,
                    agent_id TEXT,
                    target_scope TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'lesson',
                    memory_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    importance TEXT NOT NULL DEFAULT 'normal',
                    confidence REAL NOT NULL DEFAULT 0.7,
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    source_ref TEXT NOT NULL,
                    source_snapshot TEXT NOT NULL DEFAULT '{}',
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    proposed_by TEXT NOT NULL DEFAULT 'optimus',
                    reviewed_by TEXT,
                    review_comment TEXT,
                    reviewed_at TEXT,
                    published_ref TEXT,
                    published_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES user_context_profiles(id),
                    UNIQUE(user_id, fingerprint)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_candidates_review
                    ON memory_candidates(status, created_at DESC, user_id);

                CREATE TABLE IF NOT EXISTS memory_candidate_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL DEFAULT 0,
                    project_id TEXT,
                    proposed_by TEXT NOT NULL DEFAULT 'optimus',
                    candidates_json TEXT NOT NULL,
                    source_snapshot TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    locked_at TEXT,
                    lock_owner TEXT,
                    lock_token TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(mission_id, plan_version)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_candidate_jobs_pending
                    ON memory_candidate_jobs(status, next_attempt_at, created_at);

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL DEFAULT 'system',
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    before_state TEXT,
                    after_state TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    description TEXT,
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
                    "014_memory_feedback_loop",
                    "Create review-gated memory candidates, durable extraction jobs, and project memories",
                    _now(),
                ),
            )
            self._ensure_column(conn, "memory_candidate_jobs", "lock_token", "TEXT")
            self._ensure_column(
                conn,
                "memory_candidate_jobs",
                "lease_expires_at",
                "TEXT",
            )
            conn.execute(
                """
                UPDATE memory_candidate_jobs
                SET status='retry', locked_at=NULL, lock_owner=NULL,
                    lock_token=NULL, lease_expires_at=NULL,
                    next_attempt_at=?, updated_at=?
                WHERE status='processing'
                  AND (
                    lock_token IS NULL OR lock_token=''
                    OR lease_expires_at IS NULL OR lease_expires_at=''
                  )
                """,
                (_now(), _now()),
            )
            self._ensure_column(
                conn,
                "agent_memories",
                "user_id",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "agent_memories",
                "project_id",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "agent_memories",
                "memory_key",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "agent_memories",
                "status",
                "TEXT NOT NULL DEFAULT 'active'",
            )
            self._canonicalize_active_memories(conn)
            if self._table_exists(conn, "profile_facts"):
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_facts_active_key
                    ON profile_facts(profile_id, fact_key)
                    WHERE status='active'
                    """
                )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_project_memories_active_key
                ON project_context_memories(user_id, project_id, memory_key)
                WHERE status='active'
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memories_active_key
                ON agent_memories(agent_id, user_id, project_id, memory_key)
                WHERE status='active' AND user_id!='' AND memory_key!=''
                """
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _canonicalize_active_memories(conn: sqlite3.Connection) -> None:
        now = _now()
        for row in conn.execute(
            """
            SELECT id, metadata FROM agent_memories
            WHERE source LIKE 'mission:%'
              AND (user_id='' OR memory_key='')
            """
        ).fetchall():
            metadata = _loads(row["metadata"], {})
            conn.execute(
                """
                UPDATE agent_memories
                SET user_id=?, project_id=?, memory_key=?
                WHERE id=?
                """,
                (
                    str(metadata.get("user_id") or ""),
                    str(metadata.get("project_id") or ""),
                    str(metadata.get("memory_key") or ""),
                    row["id"],
                ),
            )
        duplicate_specs = (
            (
                "profile_facts",
                ("profile_id", "fact_key"),
                "status='active'",
            ),
            (
                "project_context_memories",
                ("user_id", "project_id", "memory_key"),
                "status='active'",
            ),
            (
                "agent_memories",
                ("agent_id", "user_id", "project_id", "memory_key"),
                "status='active' AND user_id!='' AND memory_key!=''",
            ),
        )
        for table, keys, active_where in duplicate_specs:
            if not MemoryFeedbackService._table_exists(conn, table):
                continue
            key_sql = ", ".join(keys)
            groups = conn.execute(
                f"""
                SELECT {key_sql}, COUNT(*) AS count
                FROM {table}
                WHERE {active_where}
                GROUP BY {key_sql}
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for group in groups:
                clauses = " AND ".join(f"{key}=?" for key in keys)
                values = tuple(group[key] for key in keys)
                rows = conn.execute(
                    f"""
                    SELECT id FROM {table}
                    WHERE {clauses} AND status='active'
                    ORDER BY updated_at DESC, id DESC
                    """,
                    values,
                ).fetchall()
                for duplicate in rows[1:]:
                    conn.execute(
                        f"UPDATE {table} SET status='superseded', updated_at=? WHERE id=?",
                        (now, duplicate["id"]),
                    )

    def enqueue_candidate_job(
        self,
        *,
        user_id: str,
        mission_id: str,
        plan_version: int,
        candidates: list[dict[str, Any]],
        project_id: str = "",
        proposed_by: str = "optimus",
        source_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        clean_user_id = str(user_id or "").strip()
        clean_mission_id = str(mission_id or "").strip()
        if not clean_user_id or not clean_mission_id:
            raise MemoryFeedbackError("user_id and mission_id are required")
        if not isinstance(candidates, list) or not candidates:
            raise MemoryFeedbackError("candidate job requires at least one candidate")
        now = _now()
        with self.connect(immediate=True) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_candidate_jobs
                (id, user_id, mission_id, plan_version, project_id, proposed_by,
                 candidates_json, source_snapshot, next_attempt_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"memory-job-{uuid.uuid4().hex[:12]}",
                    clean_user_id,
                    clean_mission_id,
                    int(plan_version or 0),
                    str(project_id or "").strip() or None,
                    str(proposed_by or "optimus").strip()[:160] or "optimus",
                    _json(candidates[:8]),
                    _json(source_snapshot or {}),
                    now,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM memory_candidate_jobs
                WHERE mission_id=? AND plan_version=?
                """,
                (clean_mission_id, int(plan_version or 0)),
            ).fetchone()
            return self._serialize_job(row)

    def process_candidate_job(
        self,
        job_id: str,
        *,
        owner: str = "memory-feedback",
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_expires_at = (
            now_dt + timedelta(seconds=max(60, int(lease_seconds)))
        ).isoformat()
        lock_token = f"memory-lease-{uuid.uuid4().hex}"
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM memory_candidate_jobs WHERE id=?",
                (str(job_id),),
            ).fetchone()
            if not row:
                raise MemoryFeedbackError(f"memory candidate job not found: {job_id}")
            if row["status"] == "completed":
                return {"job": self._serialize_job(row), "candidates": []}
            if row["status"] == "dead":
                raise MemoryFeedbackError(f"memory candidate job is dead: {job_id}")
            cursor = conn.execute(
                """
                UPDATE memory_candidate_jobs
                SET status='processing', attempts=attempts+1, locked_at=?,
                    lock_owner=?, lock_token=?, lease_expires_at=?, updated_at=?
                WHERE id=?
                  AND (
                    (status IN ('pending', 'retry') AND next_attempt_at <= ?)
                    OR
                    (status='processing' AND lease_expires_at IS NOT NULL
                     AND lease_expires_at <= ?)
                  )
                """,
                (
                    now,
                    str(owner or "memory-feedback")[:160],
                    lock_token,
                    lease_expires_at,
                    now,
                    str(job_id),
                    now,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                raise MemoryFeedbackError(f"memory candidate job is already leased: {job_id}")
            claimed = conn.execute(
                "SELECT * FROM memory_candidate_jobs WHERE id=?",
                (str(job_id),),
            ).fetchone()

        try:
            created = self.create_candidates(
                user_id=claimed["user_id"],
                mission_id=claimed["mission_id"],
                plan_version=int(claimed["plan_version"] or 0),
                candidates=_loads(claimed["candidates_json"], []),
                project_id=str(claimed["project_id"] or ""),
                proposed_by=str(claimed["proposed_by"] or "optimus"),
                source_snapshot=_loads(claimed["source_snapshot"], {}),
            )
        except Exception as exc:
            with self.connect(immediate=True) as conn:
                current = conn.execute(
                    "SELECT attempts FROM memory_candidate_jobs WHERE id=?",
                    (str(job_id),),
                ).fetchone()
                attempts = int(current["attempts"] or 0) if current else 1
                next_status = "dead" if attempts >= 6 else "retry"
                retry_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=min(300, 2 ** min(attempts, 8)))
                ).isoformat()
                conn.execute(
                    """
                    UPDATE memory_candidate_jobs
                    SET status=?, next_attempt_at=?,
                        locked_at=NULL, lock_owner=NULL, lock_token=NULL,
                        lease_expires_at=NULL, last_error=?, updated_at=?
                    WHERE id=? AND status='processing' AND lock_token=?
                    """,
                    (
                        next_status,
                        retry_at,
                        str(exc)[:4000],
                        _now(),
                        str(job_id),
                        lock_token,
                    ),
                )
            raise

        with self.connect(immediate=True) as conn:
            completed_at = _now()
            cursor = conn.execute(
                """
                UPDATE memory_candidate_jobs
                SET status='completed', locked_at=NULL, lock_owner=NULL,
                    lock_token=NULL, lease_expires_at=NULL,
                    last_error=NULL, completed_at=?, updated_at=?
                WHERE id=? AND status='processing' AND lock_token=?
                """,
                (completed_at, completed_at, str(job_id), lock_token),
            )
            completed = conn.execute(
                "SELECT * FROM memory_candidate_jobs WHERE id=?",
                (str(job_id),),
            ).fetchone()
            if cursor.rowcount != 1 and completed["status"] != "completed":
                raise MemoryFeedbackError(
                    f"memory candidate job lease was lost: {job_id}"
                )
        return {"job": self._serialize_job(completed), "candidates": created}

    def process_pending_jobs(
        self,
        *,
        owner: str = "memory-feedback",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM memory_candidate_jobs
                WHERE (
                    status IN ('pending', 'retry') AND next_attempt_at <= ?
                ) OR (
                    status='processing' AND lease_expires_at IS NOT NULL
                    AND lease_expires_at <= ?
                )
                ORDER BY created_at
                LIMIT ?
                """,
                (_now(), _now(), max(1, min(int(limit), 20))),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                results.append(self.process_candidate_job(row["id"], owner=owner))
            except Exception:
                continue
        return results

    def create_candidates(
        self,
        *,
        user_id: str,
        mission_id: str,
        plan_version: int,
        candidates: list[dict[str, Any]],
        project_id: str = "",
        proposed_by: str = "optimus",
        source_snapshot: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        clean_user_id = str(user_id or "").strip()
        clean_mission_id = str(mission_id or "").strip()
        if not clean_user_id or not clean_mission_id:
            raise MemoryFeedbackError("user_id and mission_id are required")
        if not isinstance(candidates, list):
            raise MemoryFeedbackError("candidates must be a list")

        created: list[dict[str, Any]] = []
        with self.connect(immediate=True) as conn:
            profile = conn.execute(
                "SELECT * FROM user_context_profiles WHERE user_id=?",
                (clean_user_id,),
            ).fetchone()
            for raw in candidates[:8]:
                normalized = self._normalize_candidate(raw)
                if not normalized:
                    continue
                fingerprint = _hash(
                    {
                        "mission_id": clean_mission_id,
                        "plan_version": int(plan_version or 0),
                        "target_scope": normalized["target_scope"],
                        "memory_key": normalized["memory_key"],
                        "content": normalized["content"],
                        "agent_id": (
                            normalized["agent_id"]
                            if normalized["target_scope"] == "agent"
                            else ""
                        ),
                    }
                )
                source_ref = (
                    f"mission:{clean_mission_id}:plan:{int(plan_version or 0)}:"
                    f"memory:{fingerprint[:16]}"
                )
                now = _now()
                candidate_id = f"memory-candidate-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_candidates
                    (id, user_id, profile_id, mission_id, plan_version, project_id,
                     step_id, agent_id, target_scope, memory_type, memory_key,
                     title, content, rationale, importance, confidence,
                     evidence_refs, source_ref, source_snapshot, fingerprint,
                     proposed_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate_id,
                        clean_user_id,
                        profile["id"] if profile else None,
                        clean_mission_id,
                        int(plan_version or 0),
                        str(project_id or "").strip() or None,
                        normalized["step_id"] or None,
                        normalized["agent_id"] or None,
                        normalized["target_scope"],
                        normalized["memory_type"],
                        normalized["memory_key"],
                        normalized["title"],
                        normalized["content"],
                        normalized["rationale"],
                        normalized["importance"],
                        normalized["confidence"],
                        _json(normalized["evidence_refs"]),
                        source_ref,
                        _json(source_snapshot or {}),
                        fingerprint,
                        str(proposed_by or "optimus").strip()[:160] or "optimus",
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM memory_candidates WHERE user_id=? AND fingerprint=?",
                    (clean_user_id, fingerprint),
                ).fetchone()
                if row:
                    item = self._serialize(row)
                    if item["id"] == candidate_id:
                        self._record_audit(
                            conn,
                            actor=proposed_by,
                            action="memory_candidate_created",
                            target_id=candidate_id,
                            before_state=None,
                            after_state=item,
                            metadata={"mission_id": clean_mission_id},
                        )
                    created.append(item)
        return created

    def list_candidates(
        self,
        *,
        user_id: str = "",
        status: str = "",
        mission_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if user_id:
            clauses.append("user_id=?")
            params.append(str(user_id))
        if status:
            if status not in MEMORY_CANDIDATE_STATUSES:
                raise MemoryFeedbackError(f"invalid candidate status: {status}")
            clauses.append("status=?")
            params.append(status)
        if mission_id:
            clauses.append("mission_id=?")
            params.append(str(mission_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 200)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_candidates
                {where}
                ORDER BY
                    CASE status WHEN 'pending_review' THEN 1 ELSE 2 END,
                    created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._serialize(row) for row in rows]

    def get_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_candidates WHERE id=?",
                (str(candidate_id),),
            ).fetchone()
            return self._serialize(row) if row else None

    def stats(self, *, user_id: str = "") -> dict[str, Any]:
        where = "WHERE user_id=?" if user_id else ""
        params = (str(user_id),) if user_id else ()
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT status, COUNT(*) AS count
                FROM memory_candidates {where}
                GROUP BY status
                """,
                params,
            ).fetchall()
            by_status = {row["status"]: int(row["count"]) for row in rows}
            return {
                "total": sum(by_status.values()),
                "pending_review": by_status.get("pending_review", 0),
                "published": by_status.get("published", 0),
                "rejected": by_status.get("rejected", 0),
                "by_status": by_status,
            }

    def review_candidate(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewed_by: str,
        comment: str = "",
        title: str = "",
        content: str = "",
        memory_key: str = "",
        importance: str = "",
    ) -> dict[str, Any]:
        clean_decision = str(decision or "").strip().lower()
        if clean_decision not in {"approve", "reject"}:
            raise MemoryFeedbackError(f"invalid review decision: {decision}")
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM memory_candidates WHERE id=?",
                (str(candidate_id),),
            ).fetchone()
            if not row:
                raise MemoryFeedbackError(f"memory candidate not found: {candidate_id}")
            before = self._serialize(row)
            expected_status = "published" if clean_decision == "approve" else "rejected"
            if row["status"] != "pending_review":
                if row["status"] == expected_status:
                    return {**before, "review_changed": False}
                raise MemoryFeedbackError(
                    f"memory candidate {candidate_id} is already {row['status']}"
                )

            final_title = str(title or row["title"]).strip()[:300]
            final_content = str(content or row["content"]).strip()[:12000]
            final_key = str(memory_key or row["memory_key"]).strip()[:200]
            final_importance = str(importance or row["importance"]).strip().lower()
            if final_importance not in IMPORTANCE_SCORES:
                final_importance = row["importance"]
            if clean_decision == "approve" and (not final_content or not final_key):
                raise MemoryFeedbackError("approved memory requires content and memory_key")

            now = _now()
            published_ref = None
            if clean_decision == "approve":
                published_ref = self._publish(
                    conn,
                    row,
                    title=final_title,
                    content=final_content,
                    memory_key=final_key,
                    importance=final_importance,
                    now=now,
                )
            conn.execute(
                """
                UPDATE memory_candidates
                SET title=?, content=?, memory_key=?, importance=?, status=?,
                    reviewed_by=?, review_comment=?, reviewed_at=?,
                    published_ref=?, published_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    final_title,
                    final_content,
                    final_key,
                    final_importance,
                    expected_status,
                    str(reviewed_by or "admin")[:160],
                    str(comment or "")[:4000],
                    now,
                    published_ref,
                    now if published_ref else None,
                    now,
                    str(candidate_id),
                ),
            )
            after = self._serialize(
                conn.execute(
                    "SELECT * FROM memory_candidates WHERE id=?",
                    (str(candidate_id),),
                ).fetchone()
            )
            self._record_audit(
                conn,
                actor=reviewed_by,
                action=(
                    "memory_candidate_published"
                    if clean_decision == "approve"
                    else "memory_candidate_rejected"
                ),
                target_id=str(candidate_id),
                before_state=before,
                after_state=after,
                metadata={
                    "mission_id": row["mission_id"],
                    "published_ref": published_ref,
                    "comment": str(comment or "")[:1000],
                },
            )
            return {**after, "review_changed": True}

    @staticmethod
    def _normalize_candidate(raw: Any) -> Optional[dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        target_scope = str(raw.get("target_scope") or "").strip().lower()
        content = str(raw.get("content") or "").strip()
        memory_key = str(raw.get("memory_key") or "").strip()
        if target_scope not in MEMORY_TARGETS or not content or not memory_key:
            return None
        importance = str(raw.get("importance") or "normal").strip().lower()
        if importance not in IMPORTANCE_SCORES:
            importance = "normal"
        try:
            confidence_value = float(raw.get("confidence") or 0.7)
        except (TypeError, ValueError):
            confidence_value = 0.7
        return {
            "target_scope": target_scope,
            "memory_type": str(raw.get("memory_type") or "lesson").strip()[:80] or "lesson",
            "memory_key": memory_key[:200],
            "title": str(raw.get("title") or memory_key).strip()[:300],
            "content": content[:12000],
            "rationale": str(raw.get("rationale") or "").strip()[:4000],
            "importance": importance,
            "confidence": max(0.0, min(confidence_value, 1.0)),
            "agent_id": str(raw.get("agent_id") or "optimus").strip()[:160],
            "step_id": str(raw.get("step_id") or "").strip()[:160],
            "evidence_refs": [
                str(item).strip()[:300]
                for item in (raw.get("evidence_refs") or [])
                if str(item).strip()
            ][:20],
        }

    def _publish(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        title: str,
        content: str,
        memory_key: str,
        importance: str,
        now: str,
    ) -> str:
        metadata = {
            "candidate_id": row["id"],
            "user_id": row["user_id"],
            "mission_id": row["mission_id"],
            "plan_version": row["plan_version"],
            "project_id": row["project_id"],
            "step_id": row["step_id"],
            "evidence_refs": _loads(row["evidence_refs"], []),
            "importance": importance,
            "confidence": row["confidence"],
        }
        if row["target_scope"] == "profile":
            return self._publish_profile(
                conn, row, content, memory_key, importance, metadata, now
            )
        if row["target_scope"] == "project":
            return self._publish_project(
                conn, row, title, content, memory_key, importance, metadata, now
            )
        if row["target_scope"] == "agent":
            return self._publish_agent(
                conn, row, title, content, memory_key, metadata, now
            )
        raise MemoryFeedbackError(f"unsupported memory target: {row['target_scope']}")

    @staticmethod
    def _publish_profile(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        content: str,
        memory_key: str,
        importance: str,
        metadata: dict[str, Any],
        now: str,
    ) -> str:
        profile = conn.execute(
            "SELECT * FROM user_context_profiles WHERE user_id=?",
            (row["user_id"],),
        ).fetchone()
        if not profile:
            raise MemoryFeedbackError(f"profile not found: {row['user_id']}")
        existing = conn.execute(
            """
            SELECT * FROM profile_facts
            WHERE profile_id=? AND fact_key=? AND source_ref=?
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (profile["id"], memory_key, row["source_ref"]),
        ).fetchone()
        if not existing:
            existing = conn.execute(
                """
                SELECT * FROM profile_facts
                WHERE profile_id=? AND fact_key=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (profile["id"], memory_key),
            ).fetchone()
        fact_id = existing["id"] if existing else f"fact-{uuid.uuid4().hex[:12]}"
        if existing:
            conn.execute(
                """
                UPDATE profile_facts
                SET status='superseded', updated_at=?
                WHERE profile_id=? AND fact_key=? AND status='active' AND id!=?
                """,
                (now, profile["id"], memory_key, fact_id),
            )
            conn.execute(
                """
                UPDATE profile_facts
                SET fact_type=?, fact_value=?, importance=?, confidence=?,
                    source_type='mission_result', source_ref=?, status='active', metadata=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    row["memory_type"],
                    content,
                    importance,
                    row["confidence"],
                    row["source_ref"],
                    _json(metadata),
                    now,
                    fact_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO profile_facts
                (id, profile_id, fact_type, fact_key, fact_value, importance,
                 confidence, source_type, source_ref, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'mission_result', ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    profile["id"],
                    row["memory_type"],
                    memory_key,
                    content,
                    importance,
                    row["confidence"],
                    row["source_ref"],
                    _json(metadata),
                    now,
                    now,
                ),
            )
        return f"fact:{fact_id}"

    @staticmethod
    def _publish_project(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        title: str,
        content: str,
        memory_key: str,
        importance: str,
        metadata: dict[str, Any],
        now: str,
    ) -> str:
        project_id = str(row["project_id"] or "").strip()
        if not project_id:
            raise MemoryFeedbackError("project memory requires project_id")
        existing = conn.execute(
            """
            SELECT * FROM project_context_memories
            WHERE user_id=? AND project_id=? AND memory_key=? AND source_ref=?
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (row["user_id"], project_id, memory_key, row["source_ref"]),
        ).fetchone()
        if not existing:
            existing = conn.execute(
                """
                SELECT * FROM project_context_memories
                WHERE user_id=? AND project_id=? AND memory_key=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (row["user_id"], project_id, memory_key),
            ).fetchone()
        memory_id = (
            existing["id"] if existing else f"project-memory-{uuid.uuid4().hex[:12]}"
        )
        if existing:
            conn.execute(
                """
                UPDATE project_context_memories
                SET status='superseded', updated_at=?
                WHERE user_id=? AND project_id=? AND memory_key=?
                  AND status='active' AND id!=?
                """,
                (now, row["user_id"], project_id, memory_key, memory_id),
            )
            conn.execute(
                """
                UPDATE project_context_memories
                SET title=?, content=?, importance=?, confidence=?, status='active',
                    source_ref=?, metadata=?, updated_at=?
                WHERE id=?
                """,
                (
                    title,
                    content,
                    importance,
                    row["confidence"],
                    row["source_ref"],
                    _json(metadata),
                    now,
                    memory_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO project_context_memories
                (id, user_id, project_id, memory_key, title, content, importance,
                 confidence, source_type, source_ref, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'mission_result', ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    row["user_id"],
                    project_id,
                    memory_key,
                    title,
                    content,
                    importance,
                    row["confidence"],
                    row["source_ref"],
                    _json(metadata),
                    now,
                    now,
                ),
            )
        return f"project-memory:{memory_id}"

    @staticmethod
    def _publish_agent(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        title: str,
        content: str,
        memory_key: str,
        metadata: dict[str, Any],
        now: str,
    ) -> str:
        agent_id = str(row["agent_id"] or "optimus").strip() or "optimus"
        project_id = str(row["project_id"] or "")
        existing = conn.execute(
            """
            SELECT * FROM agent_memories
            WHERE agent_id=? AND user_id=? AND project_id=? AND memory_key=?
              AND source=?
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (
                agent_id,
                row["user_id"],
                project_id,
                memory_key,
                row["source_ref"],
            ),
        ).fetchone()
        if not existing:
            existing = conn.execute(
                """
                SELECT * FROM agent_memories
                WHERE agent_id=? AND user_id=? AND project_id=? AND memory_key=?
                  AND status='active'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (agent_id, row["user_id"], project_id, memory_key),
            ).fetchone()
        memory_id = existing["id"] if existing else f"agent-memory-{uuid.uuid4().hex[:12]}"
        agent_metadata = {**metadata, "memory_key": memory_key}
        if existing:
            conn.execute(
                """
                UPDATE agent_memories
                SET status='superseded', updated_at=?
                WHERE agent_id=? AND user_id=? AND project_id=? AND memory_key=?
                  AND status='active' AND id!=?
                """,
                (
                    now,
                    agent_id,
                    row["user_id"],
                    project_id,
                    memory_key,
                    memory_id,
                ),
            )
            conn.execute(
                """
                UPDATE agent_memories
                SET memory_type=?, title=?, content=?, source=?, status='active',
                    updated_at=?, metadata=?
                WHERE id=?
                """,
                (
                    row["memory_type"],
                    title,
                    content,
                    row["source_ref"],
                    now,
                    _json(agent_metadata),
                    memory_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO agent_memories
                (id, agent_id, user_id, project_id, memory_key, memory_type,
                 title, content, source, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    memory_id,
                    agent_id,
                    row["user_id"],
                    project_id,
                    memory_key,
                    row["memory_type"],
                    title,
                    content,
                    row["source_ref"],
                    now,
                    now,
                    _json(agent_metadata),
                ),
            )
        return f"agent-memory:{memory_id}"

    @staticmethod
    def _record_audit(
        conn: sqlite3.Connection,
        *,
        actor: str,
        action: str,
        target_id: str,
        before_state: Any,
        after_state: Any,
        metadata: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_logs
            (id, actor, action, target_type, target_id, before_state,
             after_state, metadata, created_at)
            VALUES (?, ?, ?, 'memory_candidate', ?, ?, ?, ?, ?)
            """,
            (
                f"audit-{uuid.uuid4().hex}",
                str(actor or "system")[:160],
                action,
                target_id,
                _json(before_state) if before_state is not None else None,
                _json(after_state) if after_state is not None else None,
                _json(metadata),
                _now(),
            ),
        )

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["evidence_refs"] = _loads(item.get("evidence_refs"), [])
        item["source_snapshot"] = _loads(item.get("source_snapshot"), {})
        return item

    @staticmethod
    def _serialize_job(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["candidates"] = _loads(item.pop("candidates_json", ""), [])
        item["source_snapshot"] = _loads(item.get("source_snapshot"), {})
        return item


memory_feedback_service = MemoryFeedbackService()
