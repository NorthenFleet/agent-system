"""Authoritative lifecycle ledger for canonical long-term memories.

The profile/project/agent tables remain the serving authority.  This module
adds an append-only transition ledger and coordinates removals from derived
vector and graph projections whenever a memory leaves the active state.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from services.memory_vector_service import enqueue_vector_delete
from unified_data_manager import UNIFIED_DB_PATH


ACTIVE_STATE = "active"
LIFECYCLE_STATES = {
    "active",
    "superseded",
    "archived",
    "expired",
    "tombstoned",
    "purged",
}
TERMINAL_SERVING_STATES = {
    "superseded",
    "archived",
    "expired",
    "tombstoned",
    "purged",
}
ALLOWED_TRANSITIONS = {
    "active": {"superseded", "archived", "expired", "tombstoned"},
    "superseded": {"archived", "tombstoned"},
    "archived": {"tombstoned"},
    "expired": {"archived", "tombstoned"},
    "tombstoned": {"purged"},
    "purged": set(),
}


class MemoryLifecycleError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def ensure_memory_lifecycle_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_lifecycle_records (
            source_ref TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            project_id TEXT NOT NULL DEFAULT '',
            agent_id TEXT NOT NULL DEFAULT '',
            memory_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            state TEXT NOT NULL,
            supersedes_ref TEXT,
            replaced_by_ref TEXT,
            candidate_id TEXT,
            content_hash TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_type, user_id, project_id, agent_id, memory_key, version)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_lifecycle_scope
            ON memory_lifecycle_records(user_id, project_id, agent_id, state);

        CREATE INDEX IF NOT EXISTS idx_memory_lifecycle_key
            ON memory_lifecycle_records(
                source_type, user_id, project_id, agent_id, memory_key, version DESC
            );

        CREATE INDEX IF NOT EXISTS idx_memory_lifecycle_expiry
            ON memory_lifecycle_records(state, valid_until);

        CREATE TABLE IF NOT EXISTS memory_lifecycle_events (
            id TEXT PRIMARY KEY,
            source_ref TEXT NOT NULL,
            version INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            linked_source_ref TEXT,
            content_hash TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            occurred_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            FOREIGN KEY(source_ref) REFERENCES memory_lifecycle_records(source_ref)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_lifecycle_events_ref
            ON memory_lifecycle_events(source_ref, occurred_at, id);

        CREATE TABLE IF NOT EXISTS memory_conflict_resolutions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            winner_ref TEXT NOT NULL,
            loser_ref TEXT NOT NULL,
            resolution TEXT NOT NULL,
            actor TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            FOREIGN KEY(winner_ref) REFERENCES memory_lifecycle_records(source_ref),
            FOREIGN KEY(loser_ref) REFERENCES memory_lifecycle_records(source_ref)
        );
        """
    )
    if _table_exists(conn, "schema_migrations"):
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
            VALUES (?, ?, ?)
            """,
            (
                "020_memory_lifecycle_ledger",
                "Create authoritative memory lifecycle records, transitions, and conflict resolutions",
                _now(),
            ),
        )


def _canonical_snapshot(
    conn: sqlite3.Connection,
    source_ref: str,
) -> dict[str, Any]:
    prefix, separator, aggregate_id = str(source_ref or "").partition(":")
    if not separator or not aggregate_id:
        raise MemoryLifecycleError(f"invalid canonical memory reference: {source_ref}")

    if prefix == "fact":
        row = conn.execute(
            """
            SELECT f.*, p.user_id
            FROM profile_facts f
            JOIN user_context_profiles p ON p.id=f.profile_id
            WHERE f.id=?
            """,
            (aggregate_id,),
        ).fetchone()
        if not row:
            raise MemoryLifecycleError(f"canonical memory not found: {source_ref}")
        metadata = _loads(row["metadata"], {})
        return {
            "source_ref": source_ref,
            "source_type": "profile_fact",
            "aggregate_type": "profile_fact",
            "aggregate_id": aggregate_id,
            "user_id": str(row["user_id"]),
            "project_id": "",
            "agent_id": "",
            "memory_key": str(row["fact_key"]),
            "title": str(row["fact_key"]),
            "content": str(row["fact_value"]),
            "importance": str(row["importance"]),
            "confidence": float(row["confidence"]),
            "state": str(row["status"]),
            "valid_from": str(row["valid_from"] or row["created_at"]),
            "valid_until": row["valid_until"],
            "candidate_id": str(metadata.get("candidate_id") or ""),
            "metadata": metadata,
        }
    if prefix == "project-memory":
        row = conn.execute(
            "SELECT * FROM project_context_memories WHERE id=?",
            (aggregate_id,),
        ).fetchone()
        if not row:
            raise MemoryLifecycleError(f"canonical memory not found: {source_ref}")
        metadata = _loads(row["metadata"], {})
        return {
            "source_ref": source_ref,
            "source_type": "project_memory",
            "aggregate_type": "project_memory",
            "aggregate_id": aggregate_id,
            "user_id": str(row["user_id"]),
            "project_id": str(row["project_id"]),
            "agent_id": "",
            "memory_key": str(row["memory_key"]),
            "title": str(row["title"]),
            "content": str(row["content"]),
            "importance": str(row["importance"]),
            "confidence": float(row["confidence"]),
            "state": str(row["status"]),
            "valid_from": str(row["created_at"]),
            "valid_until": None,
            "candidate_id": str(metadata.get("candidate_id") or ""),
            "metadata": metadata,
        }
    if prefix == "agent-memory":
        row = conn.execute(
            "SELECT * FROM agent_memories WHERE id=?",
            (aggregate_id,),
        ).fetchone()
        if not row:
            raise MemoryLifecycleError(f"canonical memory not found: {source_ref}")
        metadata = _loads(row["metadata"], {})
        return {
            "source_ref": source_ref,
            "source_type": "agent_memory",
            "aggregate_type": "agent_memory",
            "aggregate_id": aggregate_id,
            "user_id": str(row["user_id"]),
            "project_id": str(row["project_id"]),
            "agent_id": str(row["agent_id"]),
            "memory_key": str(row["memory_key"] or metadata.get("memory_key") or ""),
            "title": str(row["title"] or row["memory_type"] or source_ref),
            "content": str(row["content"] or ""),
            "importance": str(metadata.get("importance") or "normal"),
            "confidence": float(metadata.get("confidence") or 1.0),
            "state": str(row["status"]),
            "valid_from": str(row["created_at"] or row["updated_at"] or _now()),
            "valid_until": None,
            "candidate_id": str(metadata.get("candidate_id") or ""),
            "metadata": metadata,
        }
    raise MemoryLifecycleError(f"unsupported canonical memory reference: {source_ref}")


def _content_hash(snapshot: dict[str, Any]) -> str:
    return _hash(
        {
            "source_ref": snapshot["source_ref"],
            "title": snapshot["title"],
            "content": snapshot["content"],
            "scope": [
                snapshot["user_id"],
                snapshot["project_id"],
                snapshot["agent_id"],
            ],
        }
    )


def _record_event(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    version: int,
    event_type: str,
    from_state: Optional[str],
    to_state: str,
    actor: str,
    reason_code: str,
    content_hash: str,
    linked_source_ref: str = "",
    metadata: Optional[dict[str, Any]] = None,
    occurred_at: Optional[str] = None,
) -> str:
    timestamp = occurred_at or _now()
    idempotency_key = _hash(
        {
            "source_ref": source_ref,
            "version": version,
            "event_type": event_type,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "reason_code": reason_code,
            "linked_source_ref": linked_source_ref,
            "content_hash": content_hash,
        }
    )
    event_id = f"memory-lifecycle-event-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_lifecycle_events
        (id, source_ref, version, event_type, from_state, to_state, actor,
         reason_code, linked_source_ref, content_hash, metadata, occurred_at,
         idempotency_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            source_ref,
            int(version),
            event_type,
            from_state,
            to_state,
            str(actor or "system")[:160],
            str(reason_code or "unspecified")[:160],
            str(linked_source_ref or "") or None,
            content_hash,
            _json(metadata or {}),
            timestamp,
            idempotency_key,
        ),
    )
    row = conn.execute(
        "SELECT id FROM memory_lifecycle_events WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    if not row:
        raise MemoryLifecycleError("failed to record lifecycle event")
    return str(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def register_canonical_memory(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    actor: str = "system",
    reason_code: str = "canonical_observed",
    supersedes_ref: str = "",
    now: Optional[str] = None,
) -> dict[str, Any]:
    ensure_memory_lifecycle_schema(conn)
    existing = conn.execute(
        "SELECT * FROM memory_lifecycle_records WHERE source_ref=?",
        (str(source_ref),),
    ).fetchone()
    if existing:
        return dict(existing)

    snapshot = _canonical_snapshot(conn, str(source_ref))
    if snapshot["state"] not in LIFECYCLE_STATES:
        raise MemoryLifecycleError(
            f"invalid canonical lifecycle state: {snapshot['state']}"
        )
    content_hash = _content_hash(snapshot)
    version_row = conn.execute(
        """
        SELECT COALESCE(MAX(version), 0) AS version
        FROM memory_lifecycle_records
        WHERE source_type=? AND user_id=? AND project_id=? AND agent_id=?
          AND memory_key=?
        """,
        (
            snapshot["source_type"],
            snapshot["user_id"],
            snapshot["project_id"],
            snapshot["agent_id"],
            snapshot["memory_key"],
        ),
    ).fetchone()
    version = int(version_row["version"] if isinstance(version_row, sqlite3.Row) else version_row[0]) + 1
    timestamp = now or _now()
    conn.execute(
        """
        INSERT INTO memory_lifecycle_records
        (source_ref, source_type, aggregate_id, user_id, project_id, agent_id,
         memory_key, version, state, supersedes_ref, candidate_id, content_hash,
         valid_from, valid_until, metadata, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot["source_ref"],
            snapshot["source_type"],
            snapshot["aggregate_id"],
            snapshot["user_id"],
            snapshot["project_id"],
            snapshot["agent_id"],
            snapshot["memory_key"],
            version,
            snapshot["state"],
            str(supersedes_ref or "") or None,
            snapshot["candidate_id"] or None,
            content_hash,
            snapshot["valid_from"] or timestamp,
            snapshot["valid_until"],
            _json(
                {
                    "authority": "canonical_memory",
                    "canonical_metadata": snapshot["metadata"],
                }
            ),
            timestamp,
            timestamp,
        ),
    )
    if supersedes_ref:
        conn.execute(
            """
            UPDATE memory_lifecycle_records
            SET replaced_by_ref=?, updated_at=?
            WHERE source_ref=?
            """,
            (source_ref, timestamp, supersedes_ref),
        )
    event_id = _record_event(
        conn,
        source_ref=source_ref,
        version=version,
        event_type="memory.registered",
        from_state=None,
        to_state=snapshot["state"],
        actor=actor,
        reason_code=reason_code,
        linked_source_ref=supersedes_ref,
        content_hash=content_hash,
        occurred_at=timestamp,
    )
    row = conn.execute(
        "SELECT * FROM memory_lifecycle_records WHERE source_ref=?",
        (source_ref,),
    ).fetchone()
    return {**dict(row), "event_id": event_id}


def record_canonical_revision(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    actor: str,
    reason_code: str,
    now: Optional[str] = None,
) -> dict[str, Any]:
    """Record an in-place canonical revision while preserving hash history."""
    timestamp = now or _now()
    record = register_canonical_memory(
        conn,
        source_ref=source_ref,
        actor=actor,
        reason_code="revision_baseline",
        now=timestamp,
    )
    snapshot = _canonical_snapshot(conn, source_ref)
    next_hash = _content_hash(snapshot)
    if next_hash == str(record["content_hash"]) and snapshot["state"] == record["state"]:
        return {**record, "changed": False, "event_id": None}
    next_version = int(record["version"]) + 1
    conn.execute(
        """
        UPDATE memory_lifecycle_records
        SET version=?, state=?, content_hash=?, valid_from=?, valid_until=?,
            metadata=?, updated_at=?
        WHERE source_ref=?
        """,
        (
            next_version,
            snapshot["state"],
            next_hash,
            snapshot["valid_from"],
            snapshot["valid_until"],
            _json(
                {
                    "authority": "canonical_memory",
                    "canonical_metadata": snapshot["metadata"],
                }
            ),
            timestamp,
            source_ref,
        ),
    )
    event_id = _record_event(
        conn,
        source_ref=source_ref,
        version=next_version,
        event_type="memory.revised",
        from_state=str(record["state"]),
        to_state=str(snapshot["state"]),
        actor=actor,
        reason_code=reason_code,
        content_hash=next_hash,
        metadata={"previous_content_hash": str(record["content_hash"])},
        occurred_at=timestamp,
    )
    updated = conn.execute(
        "SELECT * FROM memory_lifecycle_records WHERE source_ref=?",
        (source_ref,),
    ).fetchone()
    return {**dict(updated), "changed": True, "event_id": event_id}


def _update_canonical_state(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    to_state: str,
    now: str,
) -> None:
    prefix, _, aggregate_id = source_ref.partition(":")
    table = {
        "fact": "profile_facts",
        "project-memory": "project_context_memories",
        "agent-memory": "agent_memories",
    }.get(prefix)
    if not table:
        raise MemoryLifecycleError(f"unsupported canonical memory reference: {source_ref}")
    cursor = conn.execute(
        f"UPDATE {table} SET status=?, updated_at=? WHERE id=?",
        (to_state, now, aggregate_id),
    )
    if cursor.rowcount != 1:
        raise MemoryLifecycleError(f"canonical memory not found: {source_ref}")


def _enqueue_graph_lifecycle_projection(
    conn: sqlite3.Connection,
    *,
    snapshot: dict[str, Any],
    candidate_id: str,
    to_state: str,
    linked_source_ref: str,
    now: str,
) -> Optional[str]:
    if not candidate_id or not _table_exists(conn, "memory_graph_outbox"):
        return None
    event_type = "memory.superseded" if to_state == "superseded" else "memory.archived"
    event_id = f"graph-event-{uuid.uuid4().hex[:12]}"
    idempotency_key = _hash(
        {
            "event_type": event_type,
            "source_ref": snapshot["source_ref"],
            "status": to_state,
            "linked_source_ref": linked_source_ref,
            "content_hash": _content_hash(snapshot),
        }
    )
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "aggregate_type": snapshot["aggregate_type"],
        "aggregate_id": snapshot["aggregate_id"],
        "source_ref": snapshot["source_ref"],
        "user_id": snapshot["user_id"],
        "project_id": snapshot["project_id"],
        "agent_id": snapshot["agent_id"],
        "memory_key": snapshot["memory_key"],
        "title": snapshot["title"],
        "content": snapshot["content"],
        "content_hash": _content_hash(snapshot),
        "importance": snapshot["importance"],
        "confidence": snapshot["confidence"],
        "visibility": (
            "agent"
            if snapshot["agent_id"]
            else "project"
            if snapshot["project_id"]
            else "profile"
        ),
        "status": to_state,
        "supersedes_ref": None,
        "replaced_by_ref": linked_source_ref or None,
        "published_at": now,
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_graph_outbox
        (id, event_type, aggregate_type, aggregate_id, candidate_id, user_id,
         project_id, agent_id, payload, idempotency_key, next_attempt_at,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            snapshot["aggregate_type"],
            snapshot["aggregate_id"],
            candidate_id,
            snapshot["user_id"],
            snapshot["project_id"],
            snapshot["agent_id"],
            _json(payload),
            idempotency_key,
            now,
            now,
            now,
        ),
    )
    row = conn.execute(
        "SELECT id FROM memory_graph_outbox WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    return str(row["id"] if isinstance(row, sqlite3.Row) else row[0]) if row else None


def transition_canonical_memory(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    user_id: str,
    to_state: str,
    actor: str,
    reason_code: str,
    linked_source_ref: str = "",
    metadata: Optional[dict[str, Any]] = None,
    canonical_already_updated: bool = False,
    now: Optional[str] = None,
) -> dict[str, Any]:
    target_state = str(to_state or "").strip().lower()
    if target_state not in LIFECYCLE_STATES:
        raise MemoryLifecycleError(f"invalid lifecycle state: {to_state}")
    ensure_memory_lifecycle_schema(conn)
    timestamp = now or _now()
    record = register_canonical_memory(
        conn,
        source_ref=source_ref,
        actor=actor,
        reason_code="transition_baseline",
        now=timestamp,
    )
    if str(record["user_id"]) != str(user_id):
        raise MemoryLifecycleError("canonical memory belongs to another user")
    from_state = str(record["state"])
    if from_state == target_state:
        return {
            "source_ref": source_ref,
            "from_state": from_state,
            "to_state": target_state,
            "changed": False,
            "event_id": None,
            "vector_job_id": None,
            "graph_outbox_id": None,
        }
    if target_state not in ALLOWED_TRANSITIONS.get(from_state, set()):
        raise MemoryLifecycleError(
            f"invalid lifecycle transition: {from_state} -> {target_state}"
        )
    snapshot = _canonical_snapshot(conn, source_ref)
    if not canonical_already_updated:
        _update_canonical_state(
            conn,
            source_ref=source_ref,
            to_state=target_state,
            now=timestamp,
        )
    conn.execute(
        """
        UPDATE memory_lifecycle_records
        SET state=?, replaced_by_ref=COALESCE(NULLIF(?, ''), replaced_by_ref),
            updated_at=?
        WHERE source_ref=?
        """,
        (target_state, linked_source_ref, timestamp, source_ref),
    )
    event_id = _record_event(
        conn,
        source_ref=source_ref,
        version=int(record["version"]),
        event_type=f"memory.{target_state}",
        from_state=from_state,
        to_state=target_state,
        actor=actor,
        reason_code=reason_code,
        linked_source_ref=linked_source_ref,
        content_hash=str(record["content_hash"]),
        metadata=metadata,
        occurred_at=timestamp,
    )
    vector_job_id = None
    graph_outbox_id = None
    if from_state == ACTIVE_STATE and target_state in TERMINAL_SERVING_STATES:
        candidate_id = str(record.get("candidate_id") or "")
        if candidate_id:
            vector_job_id = enqueue_vector_delete(
                conn,
                source_ref=source_ref,
                user_id=str(user_id),
                now=timestamp,
            )
            graph_outbox_id = _enqueue_graph_lifecycle_projection(
                conn,
                snapshot=snapshot,
                candidate_id=candidate_id,
                to_state=target_state,
                linked_source_ref=linked_source_ref,
                now=timestamp,
            )
    return {
        "source_ref": source_ref,
        "from_state": from_state,
        "to_state": target_state,
        "changed": True,
        "event_id": event_id,
        "vector_job_id": vector_job_id,
        "graph_outbox_id": graph_outbox_id,
    }


class MemoryLifecycleService:
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
            ensure_memory_lifecycle_schema(conn)

    def bootstrap(self, *, user_id: str = "") -> dict[str, Any]:
        refs: list[str] = []
        with self.connect(immediate=True) as conn:
            ensure_memory_lifecycle_schema(conn)
            user_filter = str(user_id or "").strip()
            profile_sql = """
                SELECT f.id FROM profile_facts f
                JOIN user_context_profiles p ON p.id=f.profile_id
            """
            profile_params: tuple[Any, ...] = ()
            if user_filter:
                profile_sql += " WHERE p.user_id=?"
                profile_params = (user_filter,)
            refs.extend(
                f"fact:{row['id']}"
                for row in conn.execute(profile_sql, profile_params).fetchall()
            )
            project_sql = "SELECT id FROM project_context_memories"
            agent_sql = "SELECT id FROM agent_memories WHERE user_id!=''"
            params: tuple[Any, ...] = ()
            if user_filter:
                project_sql += " WHERE user_id=?"
                agent_sql += " AND user_id=?"
                params = (user_filter,)
            refs.extend(
                f"project-memory:{row['id']}"
                for row in conn.execute(project_sql, params).fetchall()
            )
            refs.extend(
                f"agent-memory:{row['id']}"
                for row in conn.execute(agent_sql, params).fetchall()
            )
            created = 0
            for source_ref in refs:
                existed = conn.execute(
                    "SELECT 1 FROM memory_lifecycle_records WHERE source_ref=?",
                    (source_ref,),
                ).fetchone()
                register_canonical_memory(
                    conn,
                    source_ref=source_ref,
                    actor="lifecycle-bootstrap",
                    reason_code="authority_backfill",
                )
                created += int(not bool(existed))
        return {"observed": len(refs), "created": created, "unchanged": len(refs) - created}

    def transition(
        self,
        *,
        source_ref: str,
        user_id: str,
        to_state: str,
        actor: str,
        reason_code: str,
        linked_source_ref: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            return transition_canonical_memory(
                conn,
                source_ref=source_ref,
                user_id=user_id,
                to_state=to_state,
                actor=actor,
                reason_code=reason_code,
                linked_source_ref=linked_source_ref,
                metadata=metadata,
            )

    def schedule_expiry(
        self,
        *,
        source_ref: str,
        user_id: str,
        valid_until: str,
        actor: str,
    ) -> dict[str, Any]:
        try:
            datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise MemoryLifecycleError("valid_until must be an ISO-8601 timestamp") from exc
        with self.connect(immediate=True) as conn:
            record = register_canonical_memory(
                conn,
                source_ref=source_ref,
                actor=actor,
                reason_code="expiry_scheduled",
            )
            if str(record["user_id"]) != str(user_id):
                raise MemoryLifecycleError("canonical memory belongs to another user")
            conn.execute(
                """
                UPDATE memory_lifecycle_records
                SET valid_until=?, updated_at=? WHERE source_ref=?
                """,
                (valid_until, _now(), source_ref),
            )
            if str(source_ref).startswith("fact:"):
                conn.execute(
                    "UPDATE profile_facts SET valid_until=? WHERE id=?",
                    (valid_until, source_ref.split(":", 1)[1]),
                )
            return {
                "source_ref": source_ref,
                "state": record["state"],
                "valid_until": valid_until,
            }

    def expire_due(
        self,
        *,
        as_of: Optional[str] = None,
        user_id: str = "",
        actor: str = "memory-lifecycle-expirer",
    ) -> list[dict[str, Any]]:
        cutoff = as_of or _now()
        with self.connect(immediate=True) as conn:
            params: list[Any] = [cutoff]
            where = "state='active' AND valid_until IS NOT NULL AND valid_until<=?"
            if user_id:
                where += " AND user_id=?"
                params.append(str(user_id))
            rows = conn.execute(
                f"SELECT source_ref, user_id FROM memory_lifecycle_records WHERE {where} ORDER BY valid_until, source_ref",
                tuple(params),
            ).fetchall()
            return [
                transition_canonical_memory(
                    conn,
                    source_ref=str(row["source_ref"]),
                    user_id=str(row["user_id"]),
                    to_state="expired",
                    actor=actor,
                    reason_code="validity_window_elapsed",
                    now=cutoff,
                )
                for row in rows
            ]

    def forget(
        self,
        *,
        source_ref: str,
        user_id: str,
        actor: str,
        reason_code: str = "user_forget_request",
    ) -> dict[str, Any]:
        return self.transition(
            source_ref=source_ref,
            user_id=user_id,
            to_state="tombstoned",
            actor=actor,
            reason_code=reason_code,
        )

    def resolve_conflict(
        self,
        *,
        winner_ref: str,
        loser_ref: str,
        user_id: str,
        actor: str,
        rationale: str,
    ) -> dict[str, Any]:
        if winner_ref == loser_ref:
            raise MemoryLifecycleError("conflict winner and loser must differ")
        with self.connect(immediate=True) as conn:
            winner = register_canonical_memory(
                conn,
                source_ref=winner_ref,
                actor=actor,
                reason_code="conflict_observed",
            )
            loser = register_canonical_memory(
                conn,
                source_ref=loser_ref,
                actor=actor,
                reason_code="conflict_observed",
            )
            if str(winner["user_id"]) != str(user_id) or str(loser["user_id"]) != str(user_id):
                raise MemoryLifecycleError("conflict memory belongs to another user")
            if str(winner["memory_key"]) != str(loser["memory_key"]):
                raise MemoryLifecycleError("conflict memories must share a memory_key")
            if str(winner["state"]) != "active":
                raise MemoryLifecycleError("conflict winner must be active")
            transition = transition_canonical_memory(
                conn,
                source_ref=loser_ref,
                user_id=user_id,
                to_state="superseded",
                actor=actor,
                reason_code="conflict_resolved",
                linked_source_ref=winner_ref,
                metadata={"rationale": str(rationale or "")[:2000]},
            )
            idempotency_key = _hash(
                {
                    "winner_ref": winner_ref,
                    "loser_ref": loser_ref,
                    "actor": actor,
                    "rationale": rationale,
                }
            )
            resolution_id = f"memory-conflict-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_conflict_resolutions
                (id, user_id, memory_key, winner_ref, loser_ref, resolution,
                 actor, rationale, created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, 'winner_selected', ?, ?, ?, ?)
                """,
                (
                    resolution_id,
                    user_id,
                    winner["memory_key"],
                    winner_ref,
                    loser_ref,
                    actor,
                    str(rationale or "")[:4000],
                    _now(),
                    idempotency_key,
                ),
            )
            row = conn.execute(
                "SELECT id FROM memory_conflict_resolutions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            return {
                "id": str(row["id"] if isinstance(row, sqlite3.Row) else row[0]),
                "winner_ref": winner_ref,
                "loser_ref": loser_ref,
                "transition": transition,
            }

    def history(self, *, source_ref: str, user_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            record = conn.execute(
                "SELECT * FROM memory_lifecycle_records WHERE source_ref=? AND user_id=?",
                (source_ref, str(user_id)),
            ).fetchone()
            if not record:
                raise MemoryLifecycleError("lifecycle record not found")
            events = conn.execute(
                """
                SELECT * FROM memory_lifecycle_events
                WHERE source_ref=? ORDER BY occurred_at, id
                """,
                (source_ref,),
            ).fetchall()
            return {"record": dict(record), "events": [dict(row) for row in events]}

    def verify(self, *, user_id: str = "") -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        with self.connect() as conn:
            params: tuple[Any, ...] = (str(user_id),) if user_id else ()
            where = "WHERE user_id=?" if user_id else ""
            records = conn.execute(
                f"SELECT * FROM memory_lifecycle_records {where} ORDER BY source_ref",
                params,
            ).fetchall()
            for record in records:
                source_ref = str(record["source_ref"])
                try:
                    canonical = _canonical_snapshot(conn, source_ref)
                except MemoryLifecycleError:
                    if record["state"] != "purged":
                        violations.append(
                            {"code": "canonical_missing", "source_ref": source_ref}
                        )
                    continue
                if str(canonical["state"]) != str(record["state"]):
                    violations.append(
                        {
                            "code": "state_mismatch",
                            "source_ref": source_ref,
                            "canonical": canonical["state"],
                            "ledger": record["state"],
                        }
                    )
                if record["state"] in TERMINAL_SERVING_STATES and record["candidate_id"]:
                    vector = conn.execute(
                        """
                        SELECT 1 FROM memory_vector_index_jobs
                        WHERE source_ref=? AND operation='delete'
                        LIMIT 1
                        """,
                        (source_ref,),
                    ).fetchone()
                    if not vector:
                        violations.append(
                            {"code": "vector_delete_missing", "source_ref": source_ref}
                        )
                    if _table_exists(conn, "memory_graph_outbox"):
                        graph = conn.execute(
                            """
                            SELECT 1 FROM memory_graph_outbox
                            WHERE aggregate_id=? AND event_type IN ('memory.superseded', 'memory.archived')
                            LIMIT 1
                            """,
                            (record["aggregate_id"],),
                        ).fetchone()
                        if not graph:
                            violations.append(
                                {"code": "graph_retirement_missing", "source_ref": source_ref}
                            )
        return {
            "consistent": not violations,
            "records_checked": len(records),
            "violations": violations,
        }


memory_lifecycle_service = MemoryLifecycleService()
