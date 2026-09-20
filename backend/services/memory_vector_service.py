"""Vector indexing and retrieval for review-approved long-term memories.

The canonical memory records and the durable indexing queue stay in the
unified SQLite database.  Embeddings are stored in PostgreSQL/pgvector when
explicitly enabled.  This keeps semantic retrieval optional: an unavailable
embedding service or vector database never prevents lexical retrieval.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional, Protocol

from services.memory_retrieval_service import (
    MemoryCandidate,
    RetrievalBatch,
    RetrievalScope,
)
from unified_data_manager import UNIFIED_DB_PATH


VECTOR_INDEX_VERSION = "approved-memory-vector.v2"
VECTOR_JOB_MAX_ATTEMPTS = 8
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:v1.5"
DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_OLLAMA_HOST = "http://192.168.1.5:11434"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _embedding_identity() -> tuple[str, int]:
    model = (
        os.getenv("MEMORY_EMBEDDING_MODEL")
        or os.getenv("LIGHTRAG_EMBEDDING_MODEL")
        or os.getenv("EMBEDDING_MODEL")
        or DEFAULT_EMBEDDING_MODEL
    )
    dimension = int(
        os.getenv("MEMORY_EMBEDDING_DIM")
        or os.getenv("EMBEDDING_DIM")
        or DEFAULT_EMBEDDING_DIMENSION
    )
    return str(model), dimension


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.9g}" for value in values) + "]"


def normalize_postgres_dsn(database_url: str) -> str:
    """Convert SQLAlchemy PostgreSQL URLs into psycopg2-compatible DSNs."""
    value = str(database_url or "").strip()
    for prefix in (
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
    ):
        if value.startswith(prefix):
            return "postgresql://" + value[len(prefix) :]
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


@dataclass(frozen=True)
class MemoryVectorDocument:
    source_ref: str
    source_type: str
    title: str
    content: str
    user_id: str
    project_id: str = ""
    agent_id: str = ""
    importance: str = "normal"
    confidence: float = 1.0
    status: str = "active"
    updated_at: str = ""
    metadata: dict[str, Any] | None = None

    @property
    def embedding_text(self) -> str:
        return f"{self.title.strip()}\n{self.content.strip()}".strip()

    @property
    def content_hash(self) -> str:
        return _hash(
            {
                "source_ref": self.source_ref,
                "title": self.title,
                "content": self.content,
                "scope": [self.user_id, self.project_id, self.agent_id],
                "status": self.status,
            }
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "source_type": self.source_type,
            "title": self.title,
            "content": self.content,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "importance": self.importance,
            "confidence": self.confidence,
            "status": self.status,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata or {}),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MemoryVectorDocument":
        return cls(
            source_ref=str(payload.get("source_ref") or ""),
            source_type=str(payload.get("source_type") or "approved_memory"),
            title=str(payload.get("title") or payload.get("source_ref") or ""),
            content=str(payload.get("content") or ""),
            user_id=str(payload.get("user_id") or ""),
            project_id=str(payload.get("project_id") or ""),
            agent_id=str(payload.get("agent_id") or ""),
            importance=str(payload.get("importance") or "normal"),
            confidence=float(payload.get("confidence") or 1.0),
            status=str(payload.get("status") or "active"),
            updated_at=str(payload.get("updated_at") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )


class EmbeddingProvider(Protocol):
    model: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorMemoryStore(Protocol):
    def upsert(
        self,
        document: MemoryVectorDocument,
        embedding: list[float],
        *,
        model: str,
        dimension: int,
    ) -> None: ...

    def search(
        self,
        embedding: list[float],
        *,
        scope: RetrievalScope,
        limit: int,
        model: str,
    ) -> list[dict[str, Any]]: ...

    def delete(self, source_ref: str, *, user_id: str) -> None: ...

    def inventory(self) -> list[dict[str, Any]]: ...


class OllamaEmbeddingProvider:
    """Small dependency-free client for Ollama's batch embedding endpoint."""

    def __init__(self, *, host: str, model: str, dimension: int, timeout: float = 8.0):
        self.host = host.rstrip("/")
        self.model = model
        self.dimension = int(dimension)
        self.timeout = float(timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        clean = [str(text or "").strip() for text in texts]
        if not clean or any(not text for text in clean):
            raise ValueError("embedding input must not be empty")
        request = urllib.request.Request(
            self.host + "/api/embed",
            data=json.dumps({"model": self.model, "input": clean}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(clean):
            raise RuntimeError("embedding provider returned an invalid batch")
        normalized: list[list[float]] = []
        for embedding in embeddings:
            vector = [float(value) for value in embedding]
            if len(vector) != self.dimension:
                raise RuntimeError(
                    f"embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )
            normalized.append(vector)
        return normalized


class PgVectorMemoryStore:
    """Exact cosine search over a pgvector table with strict tenant filters."""

    def __init__(self, database_url: str, *, dimension: int):
        self.database_url = normalize_postgres_dsn(database_url)
        self.dimension = max(1, int(dimension))
        self._schema_ready = False
        self.allow_runtime_ddl = _enabled(
            os.getenv("MEMORY_VECTOR_RUNTIME_DDL_ENABLED")
        )

    @contextmanager
    def _connect(self):
        try:
            import psycopg2
        except ImportError as exc:  # pragma: no cover - dependency is in requirements
            raise RuntimeError("psycopg2 is required for pgvector retrieval") from exc
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self, conn: Any) -> None:
        if self._schema_ready:
            return
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.approved_memory_vectors') IS NOT NULL"
            )
            table_exists = bool(cursor.fetchone()[0])
            if not table_exists and not self.allow_runtime_ddl:
                raise RuntimeError(
                    "approved_memory_vectors is missing; apply the database migration "
                    "before enabling vector retrieval"
                )
            if not table_exists:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    f"""
                    CREATE TABLE approved_memory_vectors (
                        source_ref TEXT PRIMARY KEY,
                        source_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        project_id TEXT NOT NULL DEFAULT '',
                        agent_id TEXT NOT NULL DEFAULT '',
                        importance TEXT NOT NULL DEFAULT 'normal',
                        confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        status TEXT NOT NULL DEFAULT 'active',
                        content_hash TEXT NOT NULL,
                        embedding_model TEXT NOT NULL,
                        embedding_dimension INTEGER NOT NULL,
                        embedding vector({self.dimension}) NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        memory_updated_at TIMESTAMPTZ,
                        indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX idx_approved_memory_vectors_scope
                    ON approved_memory_vectors(user_id, project_id, agent_id, status)
                    """
                )
        self._schema_ready = True

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)

    def upsert(
        self,
        document: MemoryVectorDocument,
        embedding: list[float],
        *,
        model: str,
        dimension: int,
    ) -> None:
        if len(embedding) != self.dimension or int(dimension) != self.dimension:
            raise ValueError("vector dimension does not match configured pgvector column")
        with self._connect() as conn:
            self._ensure_schema(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO approved_memory_vectors
                    (source_ref, source_type, title, content, user_id, project_id,
                     agent_id, importance, confidence, status, content_hash,
                     embedding_model, embedding_dimension, embedding, metadata,
                     memory_updated_at, indexed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s::vector, %s::jsonb, NULLIF(%s, '')::timestamptz, NOW())
                    ON CONFLICT (source_ref) DO UPDATE SET
                        source_type=EXCLUDED.source_type,
                        title=EXCLUDED.title,
                        content=EXCLUDED.content,
                        user_id=EXCLUDED.user_id,
                        project_id=EXCLUDED.project_id,
                        agent_id=EXCLUDED.agent_id,
                        importance=EXCLUDED.importance,
                        confidence=EXCLUDED.confidence,
                        status=EXCLUDED.status,
                        content_hash=EXCLUDED.content_hash,
                        embedding_model=EXCLUDED.embedding_model,
                        embedding_dimension=EXCLUDED.embedding_dimension,
                        embedding=EXCLUDED.embedding,
                        metadata=EXCLUDED.metadata,
                        memory_updated_at=EXCLUDED.memory_updated_at,
                        indexed_at=NOW()
                    """,
                    (
                        document.source_ref,
                        document.source_type,
                        document.title,
                        document.content,
                        document.user_id,
                        document.project_id,
                        document.agent_id,
                        document.importance,
                        document.confidence,
                        document.status,
                        document.content_hash,
                        model,
                        dimension,
                        _vector_literal(embedding),
                        _json(document.metadata or {}),
                        document.updated_at,
                    ),
                )

    def search(
        self,
        embedding: list[float],
        *,
        scope: RetrievalScope,
        limit: int,
        model: str,
    ) -> list[dict[str, Any]]:
        if len(embedding) != self.dimension:
            raise ValueError("query vector dimension does not match configured pgvector column")
        with self._connect() as conn:
            self._ensure_schema(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source_ref, source_type, title, content, user_id,
                           project_id, agent_id, importance, confidence, status,
                           content_hash, metadata, memory_updated_at,
                           GREATEST(0.0, LEAST(1.0, 1 - (embedding <=> %s::vector))) AS similarity
                    FROM approved_memory_vectors
                    WHERE user_id=%s AND status='active' AND embedding_model=%s
                      AND (project_id='' OR project_id=%s)
                      AND (agent_id='' OR agent_id=%s)
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        _vector_literal(embedding),
                        scope.user_id,
                        model,
                        scope.project_id,
                        scope.agent_id,
                        _vector_literal(embedding),
                        max(1, min(int(limit), 50)),
                    ),
                )
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def delete(self, source_ref: str, *, user_id: str) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM approved_memory_vectors WHERE source_ref=%s AND user_id=%s",
                    (str(source_ref), str(user_id)),
                )

    def inventory(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source_ref, source_type, user_id, project_id, agent_id,
                           status, content_hash, embedding_model,
                           embedding_dimension, indexed_at
                    FROM approved_memory_vectors
                    ORDER BY source_ref
                    """
                )
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]


def ensure_vector_queue_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_vector_index_jobs (
            id TEXT PRIMARY KEY,
            source_ref TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            payload TEXT NOT NULL,
            operation TEXT NOT NULL DEFAULT 'upsert',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL,
            locked_at TEXT,
            lock_owner TEXT,
            lock_token TEXT,
            lease_expires_at TEXT,
            last_error TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE
        );

        CREATE INDEX IF NOT EXISTS idx_memory_vector_jobs_pending
            ON memory_vector_index_jobs(status, next_attempt_at, created_at);

        CREATE TABLE IF NOT EXISTS memory_vector_index_attempts (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            operation TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            owner TEXT NOT NULL,
            lock_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            UNIQUE(job_id, attempt_number)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_vector_attempts_job
            ON memory_vector_index_attempts(job_id, attempt_number);

        CREATE INDEX IF NOT EXISTS idx_memory_vector_attempts_status
            ON memory_vector_index_attempts(status, started_at);
        """
    )


def candidate_vector_document(
    candidate: dict[str, Any], published_ref: str, *, now: str
) -> MemoryVectorDocument:
    target_scope = str(candidate.get("target_scope") or "")
    source_type = {
        "profile": "profile_fact",
        "project": "project_memory",
        "agent": "agent_memory",
    }.get(target_scope)
    if not source_type:
        raise ValueError(f"unsupported approved memory target: {target_scope}")
    return MemoryVectorDocument(
        source_ref=str(published_ref),
        source_type=source_type,
        title=str(
            candidate.get("memory_key")
            if target_scope == "profile"
            else candidate.get("title") or candidate.get("memory_key") or published_ref
        ),
        content=str(candidate.get("content") or ""),
        user_id=str(candidate.get("user_id") or ""),
        project_id=(
            str(candidate.get("project_id") or "")
            if target_scope in {"project", "agent"}
            else ""
        ),
        agent_id=str(candidate.get("agent_id") or "") if target_scope == "agent" else "",
        importance=str(candidate.get("importance") or "normal"),
        confidence=float(candidate.get("confidence") or 1.0),
        updated_at=now,
        metadata={
            "candidate_id": str(candidate.get("id") or ""),
            "memory_key": str(candidate.get("memory_key") or ""),
            "memory_type": str(candidate.get("memory_type") or ""),
            "mission_id": str(candidate.get("mission_id") or ""),
            "evidence_refs": list(candidate.get("evidence_refs") or []),
            "authority": "approved_memory",
        },
    )


def enqueue_vector_document(
    conn: sqlite3.Connection,
    document: MemoryVectorDocument,
    *,
    now: str | None = None,
) -> str:
    ensure_vector_queue_schema(conn)
    queued_at = now or _now()
    embedding_model, embedding_dimension = _embedding_identity()
    idempotency_key = _hash(
        {
            "version": VECTOR_INDEX_VERSION,
            "operation": "upsert",
            "source_ref": document.source_ref,
            "content_hash": document.content_hash,
            "embedding_model": embedding_model,
            "embedding_dimension": embedding_dimension,
        }
    )
    job_id = f"vector-job-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_vector_index_jobs
        (id, source_ref, content_hash, payload, operation, status,
         next_attempt_at, created_at, updated_at, idempotency_key)
        VALUES (?, ?, ?, ?, 'upsert', 'pending', ?, ?, ?, ?)
        """,
        (
            job_id,
            document.source_ref,
            document.content_hash,
            _json(document.as_payload()),
            queued_at,
            queued_at,
            queued_at,
            idempotency_key,
        ),
    )
    row = conn.execute(
        "SELECT id FROM memory_vector_index_jobs WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    if not row:
        raise RuntimeError("failed to enqueue memory vector indexing job")
    return str(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def enqueue_vector_delete(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    user_id: str,
    now: str | None = None,
) -> str:
    ensure_vector_queue_schema(conn)
    queued_at = now or _now()
    payload = {
        "source_ref": str(source_ref),
        "user_id": str(user_id),
        "status": "archived",
        "updated_at": queued_at,
    }
    content_hash = _hash(payload)
    idempotency_key = _hash(
        {
            "version": VECTOR_INDEX_VERSION,
            "operation": "delete",
            "source_ref": source_ref,
            "content_hash": content_hash,
        }
    )
    job_id = f"vector-job-{uuid.uuid4().hex[:12]}"
    # A not-yet-started upsert for this source is obsolete once the canonical
    # record is archived.  A processing upsert is left leased; the scheduler
    # will serialize the later delete behind it.
    conn.execute(
        """
        UPDATE memory_vector_index_jobs
        SET status='superseded', completed_at=?, updated_at=?
        WHERE source_ref=? AND operation='upsert' AND status IN ('pending', 'retry')
        """,
        (queued_at, queued_at, str(source_ref)),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_vector_index_jobs
        (id, source_ref, content_hash, payload, operation, status,
         next_attempt_at, created_at, updated_at, idempotency_key)
        VALUES (?, ?, ?, ?, 'delete', 'pending', ?, ?, ?, ?)
        """,
        (
            job_id,
            str(source_ref),
            content_hash,
            _json(payload),
            queued_at,
            queued_at,
            queued_at,
            idempotency_key,
        ),
    )
    row = conn.execute(
        "SELECT id FROM memory_vector_index_jobs WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    if not row:
        raise RuntimeError("failed to enqueue memory vector delete job")
    return str(row["id"] if isinstance(row, sqlite3.Row) else row[0])


class ApprovedMemoryVectorService:
    """Durable approved-memory indexer and Context Pack VectorRetriever."""

    def __init__(
        self,
        db_path: str = UNIFIED_DB_PATH,
        *,
        provider: Optional[EmbeddingProvider] = None,
        store: Optional[VectorMemoryStore] = None,
        enabled: Optional[bool] = None,
    ):
        self.db_path = db_path
        raw_enabled = os.getenv("MEMORY_VECTOR_ENABLED")
        self._explicitly_disabled = enabled is False or (
            enabled is None and raw_enabled is not None and not _enabled(raw_enabled)
        )
        self.enabled = _enabled(raw_enabled) if enabled is None else enabled
        self.provider = provider
        self.store = store
        self.configuration_error = ""
        if self.enabled and (self.provider is None or self.store is None):
            try:
                self.provider, self.store = self._configured_backends()
            except Exception as exc:
                self.configuration_error = str(exc)

    @contextmanager
    def connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=8)
        conn.row_factory = sqlite3.Row
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

    def _configured_backends(self) -> tuple[EmbeddingProvider, VectorMemoryStore]:
        model, dimension = _embedding_identity()
        host = os.getenv("MEMORY_EMBEDDING_HOST") or os.getenv("EMBEDDING_BINDING_HOST") or os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST
        database_url = os.getenv("MEMORY_VECTOR_DATABASE_URL") or ""
        if not database_url:
            candidate = os.getenv("DATABASE_URL") or ""
            if candidate.startswith(
                (
                    "postgres://",
                    "postgresql://",
                    "postgresql+psycopg2://",
                    "postgresql+psycopg://",
                )
            ):
                database_url = candidate
        if not database_url:
            raise RuntimeError("MEMORY_VECTOR_DATABASE_URL is not configured")
        return (
            OllamaEmbeddingProvider(host=host, model=model, dimension=dimension),
            PgVectorMemoryStore(database_url, dimension=dimension),
        )

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.provider is not None and self.store is not None)

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": "disabled" if self._explicitly_disabled else "not_configured",
                "engine": "pgvector",
                "results": 0,
            }
        if not self.ready:
            return {
                "status": "not_configured",
                "engine": "pgvector",
                "results": 0,
                "degraded_reason": self.configuration_error or "vector backends are incomplete",
            }
        return {
            "status": "ready",
            "engine": "pgvector",
            "provider": "ollama",
            "model": self.provider.model,
            "dimension": self.provider.dimension,
            "results": 0,
        }

    def retrieve_vector(
        self, *, query: str, scope: RetrievalScope, limit: int
    ) -> RetrievalBatch:
        started = time.perf_counter()
        health = self.health()
        if not self.ready:
            return RetrievalBatch("vector", [], health, 0.0)
        try:
            query_vector = self.provider.embed([str(query or "").strip()])[0]
            rows = self.store.search(
                query_vector,
                scope=scope,
                limit=max(1, min(int(limit), 50)),
                model=self.provider.model,
            )
            items: list[MemoryCandidate] = []
            for row in rows:
                score = max(0.0, min(float(row.get("similarity") or 0.0), 1.0))
                metadata = _loads(row.get("metadata"), {})
                items.append(
                    MemoryCandidate(
                        source_type=str(row.get("source_type") or "approved_memory"),
                        source_id="source-approved-memory-vector",
                        source_ref=str(row.get("source_ref") or ""),
                        title=str(row.get("title") or row.get("source_ref") or ""),
                        content=str(row.get("content") or ""),
                        final_score=score,
                        confidence=float(row.get("confidence") or 1.0),
                        channel="vector",
                        scope=RetrievalScope(
                            user_id=str(row.get("user_id") or ""),
                            project_id=str(row.get("project_id") or ""),
                            agent_id=str(row.get("agent_id") or ""),
                            visibility="project" if row.get("project_id") else "private",
                        ),
                        channel_scores={"vector": score},
                        authority_score=0.98 if row.get("project_id") else 0.95,
                        importance=str(row.get("importance") or "normal"),
                        status=str(row.get("status") or "active"),
                        updated_at=row.get("memory_updated_at"),
                        metadata={
                            **metadata,
                            "content_hash": row.get("content_hash"),
                            "embedding_model": self.provider.model,
                        },
                    )
                )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return RetrievalBatch(
                "vector",
                items,
                {**health, "status": "ready", "results": len(items), "latency_ms": latency_ms},
                latency_ms,
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return RetrievalBatch(
                "vector",
                [],
                {
                    **health,
                    "status": "degraded",
                    "results": 0,
                    "latency_ms": latency_ms,
                    "degraded_reason": str(exc)[:500],
                },
                latency_ms,
            )

    def process_pending_jobs(self, *, owner: str = "memory-vector-index", limit: int = 10) -> list[dict[str, Any]]:
        if not self.ready:
            return []
        with self.connect() as conn:
            ensure_vector_queue_schema(conn)
            rows = conn.execute(
                """
                SELECT current.id FROM memory_vector_index_jobs current
                WHERE (
                    (current.status IN ('pending', 'retry') AND current.next_attempt_at <= ?)
                    OR (current.status='processing' AND current.lease_expires_at IS NOT NULL
                        AND current.lease_expires_at <= ?)
                )
                AND NOT EXISTS (
                    SELECT 1 FROM memory_vector_index_jobs earlier
                    WHERE earlier.source_ref=current.source_ref
                      AND earlier.status IN ('pending', 'retry', 'processing')
                      AND (
                          earlier.created_at < current.created_at
                          OR (earlier.created_at=current.created_at AND earlier.id < current.id)
                      )
                )
                ORDER BY current.created_at, current.id LIMIT ?
                """,
                (_now(), _now(), max(1, min(int(limit), 50))),
            ).fetchall()
        processed: list[dict[str, Any]] = []
        for row in rows:
            result = self._process_job(str(row["id"]), owner=owner)
            if result:
                processed.append(result)
        return processed

    def operations_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            ensure_vector_queue_schema(conn)
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM memory_vector_index_jobs GROUP BY status
                """
            ).fetchall()
            oldest = conn.execute(
                """
                SELECT created_at FROM memory_vector_index_jobs
                WHERE status IN ('pending', 'retry', 'processing')
                ORDER BY created_at LIMIT 1
                """
            ).fetchone()
            recent_failures = conn.execute(
                """
                SELECT id, source_ref, status, attempts, last_error, updated_at
                FROM memory_vector_index_jobs
                WHERE status IN ('retry', 'dead')
                ORDER BY updated_at DESC LIMIT 10
                """
            ).fetchall()
            attempt_rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM memory_vector_index_attempts GROUP BY status
                """
            ).fetchall()
            recent_attempts = conn.execute(
                """
                SELECT id, job_id, attempt_number, operation, source_ref, owner,
                       status, started_at, finished_at, error
                FROM memory_vector_index_attempts
                ORDER BY started_at DESC, attempt_number DESC LIMIT 20
                """
            ).fetchall()
        by_status = {str(row["status"]): int(row["count"]) for row in rows}
        attempts_by_status = {
            str(row["status"]): int(row["count"]) for row in attempt_rows
        }
        return {
            "index": self.health(),
            "queue": {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "pending": by_status.get("pending", 0) + by_status.get("retry", 0),
                "processing": by_status.get("processing", 0),
                "completed": by_status.get("completed", 0),
                "dead_letter": by_status.get("dead", 0),
                "oldest_pending_at": oldest["created_at"] if oldest else None,
            },
            "recent_failures": [dict(row) for row in recent_failures],
            "attempt_audit": {
                "total": sum(attempts_by_status.values()),
                "by_status": attempts_by_status,
                "recent": [dict(row) for row in recent_attempts],
            },
            "index_version": VECTOR_INDEX_VERSION,
        }

    def initialize_projection(self) -> dict[str, Any]:
        if not self.ready:
            return {**self.health(), "initialized": False}
        initializer = getattr(self.store, "ensure_schema", None)
        if not callable(initializer):
            raise RuntimeError("configured vector store cannot initialize its schema")
        initializer()
        return {**self.health(), "initialized": True}

    def _process_job(self, job_id: str, *, owner: str) -> Optional[dict[str, Any]]:
        lock_token = uuid.uuid4().hex
        now = _now()
        lease = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        with self.connect(immediate=True) as conn:
            ensure_vector_queue_schema(conn)
            cursor = conn.execute(
                """
                UPDATE memory_vector_index_jobs
                SET status='processing', attempts=attempts+1, locked_at=?,
                    lock_owner=?, lock_token=?, lease_expires_at=?, updated_at=?
                WHERE id=? AND (
                    (status IN ('pending', 'retry') AND next_attempt_at <= ?)
                    OR (status='processing' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
                )
                AND NOT EXISTS (
                    SELECT 1 FROM memory_vector_index_jobs earlier
                    WHERE earlier.source_ref=memory_vector_index_jobs.source_ref
                      AND earlier.status IN ('pending', 'retry', 'processing')
                      AND (
                          earlier.created_at < memory_vector_index_jobs.created_at
                          OR (
                              earlier.created_at=memory_vector_index_jobs.created_at
                              AND earlier.id < memory_vector_index_jobs.id
                          )
                      )
                )
                """,
                (now, owner, lock_token, lease, now, job_id, now, now),
            )
            if cursor.rowcount != 1:
                return None
            row = conn.execute("SELECT * FROM memory_vector_index_jobs WHERE id=?", (job_id,)).fetchone()
            conn.execute(
                """
                UPDATE memory_vector_index_attempts
                SET status='lease_expired', finished_at=?,
                    error=COALESCE(error, 'worker lease expired before completion')
                WHERE job_id=? AND status='processing'
                """,
                (now, job_id),
            )
            conn.execute(
                """
                INSERT INTO memory_vector_index_attempts
                (id, job_id, attempt_number, operation, source_ref, owner,
                 lock_token, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', ?)
                """,
                (
                    f"vector-attempt-{uuid.uuid4().hex[:12]}",
                    job_id,
                    int(row["attempts"] or 0),
                    str(row["operation"]),
                    str(row["source_ref"]),
                    owner,
                    lock_token,
                    now,
                ),
            )

        try:
            payload = _loads(row["payload"], {})
            if row["operation"] == "delete":
                document = None
                self.store.delete(
                    str(payload.get("source_ref") or row["source_ref"]),
                    user_id=str(payload.get("user_id") or ""),
                )
            else:
                document = MemoryVectorDocument.from_payload(payload)
                embedding = self.provider.embed([document.embedding_text])[0]
                self.store.upsert(
                    document,
                    embedding,
                    model=self.provider.model,
                    dimension=self.provider.dimension,
                )
        except Exception as exc:
            attempts = int(row["attempts"] or 0)
            terminal = attempts >= VECTOR_JOB_MAX_ATTEMPTS
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** min(attempts, 8)))).isoformat()
            with self.connect(immediate=True) as conn:
                conn.execute(
                    """
                    UPDATE memory_vector_index_jobs
                    SET status=?, next_attempt_at=?, last_error=?, locked_at=NULL,
                        lock_owner=NULL, lock_token=NULL, lease_expires_at=NULL, updated_at=?
                    WHERE id=? AND lock_token=?
                    """,
                    ("dead" if terminal else "retry", retry_at, str(exc)[:1000], _now(), job_id, lock_token),
                )
                conn.execute(
                    """
                    UPDATE memory_vector_index_attempts
                    SET status='failed', finished_at=?, error=?
                    WHERE lock_token=? AND status='processing'
                    """,
                    (_now(), str(exc)[:1000], lock_token),
                )
            return {"job_id": job_id, "status": "dead" if terminal else "retry", "error": str(exc)}

        completed_at = _now()
        lease_lost = False
        with self.connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                UPDATE memory_vector_index_jobs
                SET status='completed', completed_at=?, last_error=NULL,
                    locked_at=NULL, lock_owner=NULL, lock_token=NULL,
                    lease_expires_at=NULL, updated_at=?
                WHERE id=? AND status='processing' AND lock_token=?
                """,
                (completed_at, completed_at, job_id, lock_token),
            )
            lease_lost = cursor.rowcount != 1
            conn.execute(
                """
                UPDATE memory_vector_index_attempts
                SET status=?, finished_at=?, error=?
                WHERE lock_token=? AND status='processing'
                """,
                (
                    "lease_lost" if lease_lost else "succeeded",
                    completed_at,
                    "job lease was lost before completion" if lease_lost else None,
                    lock_token,
                ),
            )
        if lease_lost:
            raise RuntimeError(f"memory vector job lease was lost: {job_id}")
        return {
            "job_id": job_id,
            "status": "completed",
            "operation": str(row["operation"]),
            "source_ref": str(row["source_ref"]),
        }

    @staticmethod
    def load_approved_documents(
        conn: sqlite3.Connection,
    ) -> list[MemoryVectorDocument]:
        documents: list[MemoryVectorDocument] = []
        profile_rows = conn.execute(
            """
            SELECT f.*, p.user_id FROM profile_facts f
            JOIN user_context_profiles p ON p.id=f.profile_id
            WHERE f.status='active'
            """
        ).fetchall()
        project_rows = conn.execute(
            "SELECT * FROM project_context_memories WHERE status='active'"
        ).fetchall()
        agent_rows = conn.execute(
            "SELECT * FROM agent_memories WHERE status='active'"
        ).fetchall()
        for row in profile_rows:
            metadata = _loads(row["metadata"], {})
            if not metadata.get("candidate_id"):
                continue
            documents.append(MemoryVectorDocument(
                source_ref=f"fact:{row['id']}", source_type="profile_fact",
                title=str(row["fact_key"]), content=str(row["fact_value"]),
                user_id=str(row["user_id"]), importance=str(row["importance"]),
                confidence=float(row["confidence"]), updated_at=str(row["updated_at"]),
                metadata=metadata,
            ))
        for row in project_rows:
            metadata = _loads(row["metadata"], {})
            if not metadata.get("candidate_id"):
                continue
            documents.append(MemoryVectorDocument(
                source_ref=f"project-memory:{row['id']}", source_type="project_memory",
                title=str(row["title"]), content=str(row["content"]),
                user_id=str(row["user_id"]), project_id=str(row["project_id"]),
                importance=str(row["importance"]), confidence=float(row["confidence"]),
                updated_at=str(row["updated_at"]), metadata=metadata,
            ))
        for row in agent_rows:
            metadata = _loads(row["metadata"], {})
            if not metadata.get("candidate_id"):
                continue
            documents.append(MemoryVectorDocument(
                source_ref=f"agent-memory:{row['id']}", source_type="agent_memory",
                title=str(row["title"] or row["memory_key"]), content=str(row["content"]),
                user_id=str(row["user_id"]), project_id=str(row["project_id"]),
                agent_id=str(row["agent_id"]), importance=str(metadata.get("importance") or "normal"),
                confidence=float(metadata.get("confidence") or 1.0),
                updated_at=str(row["updated_at"] or ""), metadata=metadata,
            ))
        return documents

    def enqueue_approved_memories(self) -> int:
        """Backfill approved records produced by the review workflow."""
        with self.connect(immediate=True) as conn:
            ensure_vector_queue_schema(conn)
            documents = self.load_approved_documents(conn)
            for document in documents:
                enqueue_vector_document(conn, document)
        return len(documents)

    def reconcile_projection(self) -> dict[str, Any]:
        if not self.ready:
            return {**self.health(), "consistent": False}
        with self.connect() as conn:
            expected_documents = self.load_approved_documents(conn)
        inventory = getattr(self.store, "inventory", None)
        if not callable(inventory):
            raise RuntimeError("configured vector store cannot report its inventory")
        actual_rows = inventory()
        expected = {document.source_ref: document for document in expected_documents}
        actual = {str(row.get("source_ref") or ""): row for row in actual_rows}
        missing = sorted(set(expected) - set(actual))
        orphaned = sorted(set(actual) - set(expected))
        stale = sorted(
            source_ref
            for source_ref in set(expected) & set(actual)
            if str(actual[source_ref].get("content_hash") or "")
            != expected[source_ref].content_hash
        )
        wrong_model = sorted(
            source_ref
            for source_ref in set(expected) & set(actual)
            if str(actual[source_ref].get("embedding_model") or "")
            != str(self.provider.model)
            or int(actual[source_ref].get("embedding_dimension") or 0)
            != int(self.provider.dimension)
        )
        consistent = not (missing or orphaned or stale or wrong_model)
        return {
            "status": "ready" if consistent else "drifted",
            "consistent": consistent,
            "canonical_count": len(expected),
            "projection_count": len(actual),
            "missing_count": len(missing),
            "orphaned_count": len(orphaned),
            "stale_count": len(stale),
            "wrong_model_count": len(wrong_model),
            "missing_refs": missing[:100],
            "orphaned_refs": orphaned[:100],
            "stale_refs": stale[:100],
            "wrong_model_refs": wrong_model[:100],
            "model": self.provider.model,
            "dimension": self.provider.dimension,
        }
