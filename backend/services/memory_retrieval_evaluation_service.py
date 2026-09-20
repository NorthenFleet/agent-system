"""Versioned labeled evaluation and promotion gate for hybrid memory retrieval."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from services.memory_retrieval_service import (
    assess_retrieval_rollout,
    evaluate_retrieval_cases,
)
from services.memory_vector_service import ApprovedMemoryVectorService
from unified_data_manager import UNIFIED_DB_PATH


EVALUATION_VERSION = "memory-retrieval-eval.v3"
CASE_STATUSES = {"draft", "active", "archived"}
REVIEWER_CONFIDENCE_LEVELS = {"unreviewed", "medium", "high"}
REQUIRED_REVIEW_CHECKS = ("query_rewritten", "scope_verified", "labels_verified")
VARIANT_TEMPLATES = ("natural", "terse", "contextual", "boundary")
REVIEW_VARIANT_ORDER = ("canonical", "natural", "terse", "contextual", "boundary")


class MemoryRetrievalEvaluationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


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


def _minimum_cases() -> int:
    try:
        value = int(os.getenv("MEMORY_ROLLOUT_MIN_LABELED_CASES") or 30)
    except ValueError:
        value = 30
    return max(1, min(value, 1000))


class MemoryRetrievalEvaluationService:
    def __init__(self, context_service: Any, db_path: str = UNIFIED_DB_PATH):
        self.context_service = context_service
        self.db_path = db_path
        self.ensure_schema()

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

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_retrieval_eval_cases (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    subject_user_id TEXT NOT NULL DEFAULT '',
                    origin TEXT NOT NULL DEFAULT 'manual',
                    source_memory_ref TEXT NOT NULL DEFAULT '',
                    variant_key TEXT NOT NULL DEFAULT 'canonical',
                    query TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    agent_id TEXT NOT NULL DEFAULT 'optimus',
                    result_limit INTEGER NOT NULL DEFAULT 10,
                    expected_source_refs TEXT NOT NULL DEFAULT '[]',
                    forbidden_source_refs TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    review_checks TEXT NOT NULL DEFAULT '{}',
                    reviewer_confidence TEXT NOT NULL DEFAULT 'unreviewed',
                    source_snapshot_hash TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    version INTEGER NOT NULL DEFAULT 1,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_retrieval_eval_cases_scope
                    ON memory_retrieval_eval_cases(owner_user_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS memory_retrieval_eval_runs (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    evaluation_version TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    case_count INTEGER NOT NULL,
                    baseline_metrics TEXT NOT NULL,
                    candidate_metrics TEXT NOT NULL,
                    assessment TEXT NOT NULL,
                    details TEXT NOT NULL,
                    strategy_metadata TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_retrieval_eval_runs_recent
                    ON memory_retrieval_eval_runs(owner_user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS memory_retrieval_eval_case_events (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT NOT NULL DEFAULT '',
                    to_status TEXT NOT NULL,
                    case_version INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    source_snapshot_hash TEXT NOT NULL DEFAULT '',
                    case_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_eval_case_events_case
                    ON memory_retrieval_eval_case_events(case_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS memory_retrieval_eval_batches (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    target_case_count INTEGER NOT NULL,
                    case_ids TEXT NOT NULL,
                    review_plan TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'in_review',
                    requested_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_eval_batches_recent
                    ON memory_retrieval_eval_batches(owner_user_id, created_at DESC);
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(memory_retrieval_eval_cases)"
                ).fetchall()
            }
            if "subject_user_id" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN subject_user_id TEXT NOT NULL DEFAULT ''
                    """
                )
            if "origin" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'
                    """
                )
            if "source_memory_ref" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN source_memory_ref TEXT NOT NULL DEFAULT ''
                    """
                )
            if "variant_key" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN variant_key TEXT NOT NULL DEFAULT 'canonical'
                    """
                )
            if "review_checks" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN review_checks TEXT NOT NULL DEFAULT '{}'
                    """
                )
            if "reviewer_confidence" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN reviewer_confidence TEXT NOT NULL DEFAULT 'unreviewed'
                    """
                )
            if "source_snapshot_hash" not in columns:
                conn.execute(
                    """
                    ALTER TABLE memory_retrieval_eval_cases
                    ADD COLUMN source_snapshot_hash TEXT NOT NULL DEFAULT ''
                    """
                )
            conn.execute("DROP INDEX IF EXISTS idx_memory_eval_case_source")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_eval_case_variant
                ON memory_retrieval_eval_cases(
                    owner_user_id, source_memory_ref, variant_key
                )
                WHERE source_memory_ref <> ''
                """
            )
            migration_table = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='schema_migrations'
                """
            ).fetchone()
            if migration_table:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        "014_memory_retrieval_evaluation",
                        "Create versioned labeled memory retrieval evaluations",
                        _now(),
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        "015_memory_retrieval_evaluation_variants",
                        "Add query variants, review checks, and dataset coverage",
                        _now(),
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        "016_memory_retrieval_evaluation_evidence",
                        "Add source evidence snapshots, reviewer confidence, and audit events",
                        _now(),
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        "017_memory_retrieval_annotation_batches",
                        "Add balanced human review batches without automatic activation",
                        _now(),
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        "018_memory_retrieval_review_proposals",
                        "Add AI-assisted review proposals separated from human labels",
                        _now(),
                    ),
                )
            unaudited_rows = conn.execute(
                """
                SELECT cases.* FROM memory_retrieval_eval_cases AS cases
                WHERE NOT EXISTS (
                    SELECT 1 FROM memory_retrieval_eval_case_events AS events
                    WHERE events.case_id=cases.id
                )
                """
            ).fetchall()
            for row in unaudited_rows:
                serialized = self._serialize_case(row)
                conn.execute(
                    """
                    INSERT INTO memory_retrieval_eval_case_events
                    (id, case_id, owner_user_id, event_type, from_status, to_status,
                     case_version, actor, source_snapshot_hash, case_hash, created_at)
                    VALUES (?, ?, ?, 'imported', '', ?, ?, 'schema-migration', ?, ?, ?)
                    """,
                    (
                        f"memory-eval-event-bootstrap-{row['id']}",
                        str(row["id"]),
                        str(row["owner_user_id"]),
                        str(row["status"]),
                        int(row["version"] or 1),
                        str(row["source_snapshot_hash"] or ""),
                        _hash(serialized),
                        str(row["updated_at"] or _now()),
                    ),
                )

    @staticmethod
    def _normalize_refs(values: Any) -> list[str]:
        if not isinstance(values, list):
            raise MemoryRetrievalEvaluationError("source references must be a list")
        return list(
            dict.fromkeys(
                str(value).strip()[:500]
                for value in values
                if str(value).strip()
            )
        )[:50]

    @classmethod
    def _normalize_case(cls, raw: dict[str, Any]) -> dict[str, Any]:
        query = str(raw.get("query") or "").strip()
        if not query:
            raise MemoryRetrievalEvaluationError("evaluation query is required")
        expected = cls._normalize_refs(raw.get("expected_source_refs") or [])
        forbidden = cls._normalize_refs(raw.get("forbidden_source_refs") or [])
        if not expected and not forbidden:
            raise MemoryRetrievalEvaluationError(
                "at least one expected or forbidden source reference is required"
            )
        status = str(raw.get("status") or "draft").strip().lower()
        if status not in CASE_STATUSES:
            raise MemoryRetrievalEvaluationError(
                "case status must be draft, active, or archived"
            )
        tags = raw.get("tags") or []
        if not isinstance(tags, list):
            raise MemoryRetrievalEvaluationError("tags must be a list")
        review_checks = raw.get("review_checks") or {}
        if not isinstance(review_checks, dict):
            raise MemoryRetrievalEvaluationError("review_checks must be an object")
        reviewer_confidence = str(
            raw.get("reviewer_confidence") or "unreviewed"
        ).strip().lower()
        if reviewer_confidence not in REVIEWER_CONFIDENCE_LEVELS:
            raise MemoryRetrievalEvaluationError(
                "reviewer_confidence must be unreviewed, medium, or high"
            )
        return {
            "subject_user_id": str(
                raw.get("subject_user_id") or raw.get("user_id") or ""
            ).strip()[:160],
            "origin": str(raw.get("origin") or "manual").strip()[:80],
            "source_memory_ref": str(raw.get("source_memory_ref") or "").strip()[:500],
            "variant_key": str(raw.get("variant_key") or "canonical").strip()[:80],
            "query": query[:20_000],
            "project_id": str(raw.get("project_id") or "").strip()[:160],
            "agent_id": str(raw.get("agent_id") or "optimus").strip()[:160],
            "limit": max(1, min(int(raw.get("limit") or 10), 50)),
            "expected_source_refs": expected,
            "forbidden_source_refs": forbidden,
            "tags": list(
                dict.fromkeys(str(tag).strip()[:80] for tag in tags if str(tag).strip())
            )[:20],
            "notes": str(raw.get("notes") or "").strip()[:4000],
            "review_checks": {
                name: bool(review_checks.get(name)) for name in REQUIRED_REVIEW_CHECKS
            },
            "reviewer_confidence": reviewer_confidence,
            "source_snapshot_hash": "",
            "status": status,
        }

    @staticmethod
    def _document_map(
        conn: sqlite3.Connection, owner_user_id: str
    ) -> dict[str, Any]:
        try:
            documents = ApprovedMemoryVectorService.load_approved_documents(conn)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            documents = []
        return {
            document.source_ref: document
            for document in documents
            if str(document.user_id) == str(owner_user_id)
        }

    @staticmethod
    def _event_type(existing: sqlite3.Row | None, to_status: str) -> str:
        if not existing:
            return "created"
        from_status = str(existing["status"] or "")
        if from_status != to_status:
            return f"status:{from_status}->{to_status}"
        return "updated"

    def upsert_case(
        self,
        *,
        owner_user_id: str,
        reviewed_by: str,
        payload: dict[str, Any],
        case_id: str = "",
    ) -> dict[str, Any]:
        normalized = self._normalize_case(payload)
        now = _now()
        clean_id = str(case_id or payload.get("id") or "").strip()[:160]
        with self.connect(immediate=True) as conn:
            existing = None
            if clean_id:
                existing = conn.execute(
                    "SELECT * FROM memory_retrieval_eval_cases WHERE id=?",
                    (clean_id,),
                ).fetchone()
                if existing and str(existing["owner_user_id"]) != str(owner_user_id):
                    raise MemoryRetrievalEvaluationError(
                        "evaluation case belongs to another user"
                    )
            if not clean_id:
                clean_id = f"memory-eval-case-{uuid.uuid4().hex[:12]}"
            version = int(existing["version"] or 0) + 1 if existing else 1
            if existing:
                normalized["source_memory_ref"] = str(existing["source_memory_ref"] or "")
                normalized["origin"] = str(existing["origin"] or "manual")
                normalized["variant_key"] = str(existing["variant_key"] or "canonical")
            generated = normalized["origin"].startswith("approved_memory_")
            document = self._document_map(conn, str(owner_user_id)).get(
                normalized["source_memory_ref"]
            ) if generated else None
            previous_snapshot = (
                str(existing["source_snapshot_hash"] or "") if existing else ""
            )
            source_drifted = bool(
                document
                and previous_snapshot
                and previous_snapshot != document.content_hash
            )
            if source_drifted and normalized["status"] == "active":
                raise MemoryRetrievalEvaluationError(
                    "source memory changed; save as draft and repeat the review"
                )
            if source_drifted and normalized["status"] == "draft":
                normalized["review_checks"] = {
                    name: False for name in REQUIRED_REVIEW_CHECKS
                }
                normalized["reviewer_confidence"] = "unreviewed"
            if generated and normalized["status"] == "active" and not document:
                raise MemoryRetrievalEvaluationError(
                    "approved source memory is missing or outside the reviewer's scope"
                )
            if normalized["status"] == "active" and not all(
                normalized["review_checks"].get(name)
                for name in REQUIRED_REVIEW_CHECKS
            ):
                raise MemoryRetrievalEvaluationError(
                    "query, scope, and label review checks are required before activation"
                )
            if (
                normalized["status"] == "active"
                and normalized["reviewer_confidence"] not in {"medium", "high"}
            ):
                raise MemoryRetrievalEvaluationError(
                    "medium or high reviewer confidence is required before activation"
                )
            if document and (
                normalized["status"] == "active"
                or any(normalized["review_checks"].values())
                or source_drifted
            ):
                normalized["source_snapshot_hash"] = document.content_hash
            else:
                normalized["source_snapshot_hash"] = previous_snapshot
            reviewer = str(reviewed_by or "admin")[:160]
            reviewed_at = now if normalized["status"] == "active" else None
            conn.execute(
                """
                INSERT INTO memory_retrieval_eval_cases
                (id, owner_user_id, subject_user_id, origin, source_memory_ref, variant_key,
                 query, project_id, agent_id, result_limit,
                 expected_source_refs, forbidden_source_refs, tags, notes, review_checks,
                 reviewer_confidence, source_snapshot_hash, status,
                 version, reviewed_by, reviewed_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    subject_user_id=excluded.subject_user_id,
                    origin=excluded.origin,
                    source_memory_ref=excluded.source_memory_ref,
                    variant_key=excluded.variant_key,
                    query=excluded.query,
                    project_id=excluded.project_id,
                    agent_id=excluded.agent_id,
                    result_limit=excluded.result_limit,
                    expected_source_refs=excluded.expected_source_refs,
                    forbidden_source_refs=excluded.forbidden_source_refs,
                    tags=excluded.tags,
                    notes=excluded.notes,
                    review_checks=excluded.review_checks,
                    reviewer_confidence=excluded.reviewer_confidence,
                    source_snapshot_hash=excluded.source_snapshot_hash,
                    status=excluded.status,
                    version=excluded.version,
                    reviewed_by=excluded.reviewed_by,
                    reviewed_at=excluded.reviewed_at,
                    updated_at=excluded.updated_at
                """,
                (
                    clean_id,
                    str(owner_user_id),
                    normalized["subject_user_id"],
                    normalized["origin"],
                    normalized["source_memory_ref"],
                    normalized["variant_key"],
                    normalized["query"],
                    normalized["project_id"],
                    normalized["agent_id"],
                    normalized["limit"],
                    _json(normalized["expected_source_refs"]),
                    _json(normalized["forbidden_source_refs"]),
                    _json(normalized["tags"]),
                    normalized["notes"],
                    _json(normalized["review_checks"]),
                    normalized["reviewer_confidence"],
                    normalized["source_snapshot_hash"],
                    normalized["status"],
                    version,
                    reviewer if normalized["status"] == "active" else None,
                    reviewed_at,
                    str(existing["created_at"]) if existing else now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM memory_retrieval_eval_cases WHERE id=?", (clean_id,)
            ).fetchone()
            serialized = self._serialize_case(row)
            conn.execute(
                """
                INSERT INTO memory_retrieval_eval_case_events
                (id, case_id, owner_user_id, event_type, from_status, to_status,
                 case_version, actor, source_snapshot_hash, case_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"memory-eval-event-{uuid.uuid4().hex[:16]}",
                    clean_id,
                    str(owner_user_id),
                    self._event_type(existing, normalized["status"]),
                    str(existing["status"] or "") if existing else "",
                    normalized["status"],
                    version,
                    reviewer,
                    normalized["source_snapshot_hash"],
                    _hash(serialized),
                    now,
                ),
            )
        return serialized

    @staticmethod
    def _draft_query(source_type: str, title: str) -> str:
        clean_title = str(title or "该记忆").strip()
        if source_type == "project_memory":
            return f"关于项目中的“{clean_title}”，当前有效规则是什么？"
        if source_type == "agent_memory":
            return f"智能体处理“{clean_title}”时应遵循什么？"
        return f"在当前工作中，“{clean_title}”应如何处理？"

    @staticmethod
    def _variant_query(source_type: str, title: str, variant_key: str) -> str:
        clean_title = str(title or "该记忆").strip()
        if variant_key == "natural":
            return f"我现在遇到“{clean_title}”相关的问题，应该怎么处理？"
        if variant_key == "terse":
            return f"{clean_title}怎么处理？"
        if variant_key == "contextual":
            if source_type == "project_memory":
                return f"在这个项目里，{clean_title}具体有哪些要求？"
            if source_type == "agent_memory":
                return f"让智能体处理{clean_title}时，需要遵守哪些规则？"
            return f"按我的工作约定，{clean_title}应该怎么执行？"
        return f"涉及{clean_title}时，有哪些限制、例外或注意事项？"

    def generate_drafts_from_approved_memories(
        self, *, owner_user_id: str, requested_by: str
    ) -> dict[str, Any]:
        with self.connect() as conn:
            documents = ApprovedMemoryVectorService.load_approved_documents(conn)
            existing_rows = conn.execute(
                """
                SELECT source_memory_ref, variant_key FROM memory_retrieval_eval_cases
                WHERE owner_user_id=? AND source_memory_ref <> ''
                """,
                (str(owner_user_id),),
            ).fetchall()
        documents = [
            document
            for document in documents
            if str(document.user_id) == str(owner_user_id)
        ]
        existing = {
            str(row["source_memory_ref"])
            for row in existing_rows
            if str(row["variant_key"] or "canonical") == "canonical"
        }
        created: list[dict[str, Any]] = []
        skipped: list[str] = []
        for document in documents:
            if document.source_ref in existing:
                skipped.append(document.source_ref)
                continue
            deterministic_id = "memory-eval-draft-" + _hash(
                {
                    "owner_user_id": str(owner_user_id),
                    "source_ref": document.source_ref,
                }
            )[:16]
            case = self.upsert_case(
                owner_user_id=str(owner_user_id),
                reviewed_by=str(requested_by or "admin"),
                case_id=deterministic_id,
                payload={
                    "subject_user_id": str(owner_user_id),
                    "origin": "approved_memory_draft",
                    "source_memory_ref": document.source_ref,
                    "variant_key": "canonical",
                    "query": self._draft_query(document.source_type, document.title),
                    "project_id": document.project_id,
                    "agent_id": document.agent_id or "optimus",
                    "limit": 10,
                    "expected_source_refs": [document.source_ref],
                    "forbidden_source_refs": [],
                    "tags": ["auto-draft", document.source_type],
                    "notes": (
                        "从已审核长期记忆自动生成。激活前必须将问题改写为"
                        "真实业务表达，并核验期望与禁止来源。"
                    ),
                    "review_checks": {},
                    "status": "draft",
                },
            )
            created.append(case)
            existing.add(document.source_ref)
        return {
            "approved_memories_scanned": len(documents),
            "drafts_created": len(created),
            "drafts_skipped": len(skipped),
            "created": created,
            "skipped_source_refs": skipped,
            "automatic_activation": False,
        }

    def generate_variant_drafts(
        self, *, owner_user_id: str, requested_by: str
    ) -> dict[str, Any]:
        with self.connect() as conn:
            documents = ApprovedMemoryVectorService.load_approved_documents(conn)
            existing_rows = conn.execute(
                """
                SELECT source_memory_ref, variant_key
                FROM memory_retrieval_eval_cases
                WHERE owner_user_id=? AND source_memory_ref <> ''
                """,
                (str(owner_user_id),),
            ).fetchall()
        documents = [
            document
            for document in documents
            if str(document.user_id) == str(owner_user_id)
        ]
        existing = {
            (str(row["source_memory_ref"]), str(row["variant_key"]))
            for row in existing_rows
        }
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for document in documents:
            for variant_key in VARIANT_TEMPLATES:
                identity = (document.source_ref, variant_key)
                if identity in existing:
                    skipped.append(
                        {"source_memory_ref": document.source_ref, "variant_key": variant_key}
                    )
                    continue
                deterministic_id = "memory-eval-variant-" + _hash(
                    {
                        "owner_user_id": str(owner_user_id),
                        "source_ref": document.source_ref,
                        "variant_key": variant_key,
                    }
                )[:16]
                case = self.upsert_case(
                    owner_user_id=str(owner_user_id),
                    reviewed_by=str(requested_by or "admin"),
                    case_id=deterministic_id,
                    payload={
                        "subject_user_id": str(owner_user_id),
                        "origin": "approved_memory_variant_draft",
                        "source_memory_ref": document.source_ref,
                        "variant_key": variant_key,
                        "query": self._variant_query(
                            document.source_type, document.title, variant_key
                        ),
                        "project_id": document.project_id,
                        "agent_id": document.agent_id or "optimus",
                        "limit": 10,
                        "expected_source_refs": [document.source_ref],
                        "forbidden_source_refs": [],
                        "tags": [
                            "auto-draft",
                            "query-variant",
                            variant_key,
                            document.source_type,
                        ],
                        "notes": (
                            "自动生成的问法变体，仅用于人工标注起点。"
                            "激活前必须完成问法改写、作用域和来源标签核对。"
                        ),
                        "review_checks": {},
                        "status": "draft",
                    },
                )
                created.append(case)
                existing.add(identity)
        return {
            "approved_memories_scanned": len(documents),
            "variants_per_memory": len(VARIANT_TEMPLATES),
            "drafts_created": len(created),
            "drafts_skipped": len(skipped),
            "created": created,
            "skipped": skipped,
            "automatic_activation": False,
        }

    def coverage(self, owner_user_id: str) -> dict[str, Any]:
        cases = self.list_cases(owner_user_id, limit=1000)
        with self.connect() as conn:
            documents = self._document_map(conn, owner_user_id)
            audit_events = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM memory_retrieval_eval_case_events
                    WHERE owner_user_id=?
                    """,
                    (str(owner_user_id),),
                ).fetchone()[0]
            )
        by_status = {
            status: sum(case["status"] == status for case in cases)
            for status in sorted(CASE_STATUSES)
        }
        by_variant: dict[str, int] = {}
        by_confidence: dict[str, int] = {}
        for case in cases:
            key = str(case.get("variant_key") or "canonical")
            by_variant[key] = by_variant.get(key, 0) + 1
            confidence = str(case.get("reviewer_confidence") or "unreviewed")
            by_confidence[confidence] = by_confidence.get(confidence, 0) + 1
        approved_sources = set(documents)
        sources_with_cases = {
            str(case["source_memory_ref"])
            for case in cases
            if case.get("source_memory_ref")
        }
        active_sources = {
            str(case["source_memory_ref"])
            for case in cases
            if case["status"] == "active" and case.get("source_memory_ref")
        }
        review_ready_drafts = sum(
            case["status"] == "draft"
            and all((case.get("review_checks") or {}).get(name) for name in REQUIRED_REVIEW_CHECKS)
            and case.get("reviewer_confidence") in {"medium", "high"}
            and (
                not case["origin"].startswith("approved_memory_")
                or bool(case.get("source_snapshot_hash"))
            )
            for case in cases
        )
        integrity = self._source_integrity(owner_user_id, cases=cases, documents=documents)
        safety_negative_cases = sum(bool(case["forbidden_source_refs"]) for case in cases)
        active_safety_negative_cases = sum(
            case["status"] == "active" and bool(case["forbidden_source_refs"])
            for case in cases
        )
        minimum = _minimum_cases()
        return {
            "approved_sources": len(approved_sources),
            "sources_with_cases": len(approved_sources & sources_with_cases),
            "sources_with_active_cases": len(approved_sources & active_sources),
            "uncovered_source_refs": sorted(approved_sources - sources_with_cases),
            "cases_total": len(cases),
            "by_status": by_status,
            "by_variant": dict(sorted(by_variant.items())),
            "by_confidence": dict(sorted(by_confidence.items())),
            "review_ready_drafts": review_ready_drafts,
            "safety_negative_cases": safety_negative_cases,
            "active_safety_negative_cases": active_safety_negative_cases,
            "source_drift_cases": len(integrity["stale_case_ids"]),
            "missing_source_cases": len(integrity["missing_case_ids"]),
            "audit_events": audit_events,
            "minimum_active_cases": minimum,
            "remaining_active_cases": max(0, minimum - by_status["active"]),
            "automatic_activation": False,
        }

    def _source_integrity(
        self,
        owner_user_id: str,
        *,
        cases: list[dict[str, Any]] | None = None,
        documents: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if cases is None:
            cases = self.list_cases(owner_user_id, limit=1000)
        if documents is None:
            with self.connect() as conn:
                documents = self._document_map(conn, owner_user_id)
        stale_case_ids: list[str] = []
        missing_case_ids: list[str] = []
        for case in cases:
            if not str(case.get("origin") or "").startswith("approved_memory_"):
                continue
            document = documents.get(str(case.get("source_memory_ref") or ""))
            if not document:
                missing_case_ids.append(str(case["id"]))
                if case["status"] == "active":
                    stale_case_ids.append(str(case["id"]))
                continue
            snapshot = str(case.get("source_snapshot_hash") or "")
            if snapshot and snapshot != document.content_hash:
                stale_case_ids.append(str(case["id"]))
            elif case["status"] == "active" and not snapshot:
                stale_case_ids.append(str(case["id"]))
        return {
            "stale_case_ids": sorted(set(stale_case_ids)),
            "missing_case_ids": sorted(set(missing_case_ids)),
            "passed": not stale_case_ids,
        }

    def review_queue(self, owner_user_id: str) -> dict[str, Any]:
        cases = self.list_cases(owner_user_id, limit=1000)
        with self.connect() as conn:
            documents = self._document_map(conn, owner_user_id)
        integrity = self._source_integrity(
            owner_user_id, cases=cases, documents=documents
        )
        stale_ids = set(integrity["stale_case_ids"])
        grouped: dict[str, list[dict[str, Any]]] = {}
        for case in cases:
            grouped.setdefault(str(case.get("source_memory_ref") or "manual"), []).append(case)
        sources: list[dict[str, Any]] = []
        for source_ref in sorted(set(documents) | (set(grouped) - {"manual"})):
            document = documents.get(source_ref)
            source_cases = grouped.get(source_ref, [])
            sources.append(
                {
                    "source_ref": source_ref,
                    "source_type": document.source_type if document else "missing",
                    "title": document.title if document else "来源已缺失",
                    "content": document.content if document else "",
                    "user_id": document.user_id if document else "",
                    "project_id": document.project_id if document else "",
                    "agent_id": document.agent_id if document else "",
                    "content_hash": document.content_hash if document else "",
                    "updated_at": document.updated_at if document else "",
                    "case_count": len(source_cases),
                    "draft_count": sum(case["status"] == "draft" for case in source_cases),
                    "active_count": sum(case["status"] == "active" for case in source_cases),
                    "safety_case_count": sum(
                        bool(case["forbidden_source_refs"]) for case in source_cases
                    ),
                    "stale_case_ids": sorted(
                        str(case["id"]) for case in source_cases if case["id"] in stale_ids
                    ),
                }
            )
        return {
            "sources": sources,
            "source_count": len(sources),
            "cases_total": len(cases),
            "stale_case_ids": integrity["stale_case_ids"],
            "missing_case_ids": integrity["missing_case_ids"],
            "automatic_activation": False,
        }

    def list_case_events(
        self, owner_user_id: str, case_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            owned = conn.execute(
                """
                SELECT 1 FROM memory_retrieval_eval_cases
                WHERE id=? AND owner_user_id=?
                """,
                (str(case_id), str(owner_user_id)),
            ).fetchone()
            if not owned:
                raise MemoryRetrievalEvaluationError("evaluation case not found")
            rows = conn.execute(
                """
                SELECT * FROM memory_retrieval_eval_case_events
                WHERE case_id=? AND owner_user_id=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (str(case_id), str(owner_user_id), max(1, min(int(limit), 500))),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _balanced_review_selection(
        cases: list[dict[str, Any]], target_count: int
    ) -> list[dict[str, Any]]:
        variant_rank = {
            key: index for index, key in enumerate(REVIEW_VARIANT_ORDER)
        }
        grouped: dict[str, list[dict[str, Any]]] = {}
        for case in cases:
            if case["status"] == "archived":
                continue
            source_key = str(case.get("source_memory_ref") or case["id"])
            grouped.setdefault(source_key, []).append(case)
        for source_cases in grouped.values():
            source_cases.sort(
                key=lambda case: (
                    variant_rank.get(str(case.get("variant_key") or ""), 999),
                    str(case["id"]),
                )
            )
        selected: list[dict[str, Any]] = []
        source_keys = sorted(grouped)
        while len(selected) < target_count:
            added = False
            for source_key in source_keys:
                if len(selected) >= target_count:
                    break
                source_cases = grouped[source_key]
                if source_cases:
                    selected.append(source_cases.pop(0))
                    added = True
            if not added:
                break
        return selected

    def _serialize_batch(
        self,
        row: sqlite3.Row,
        *,
        cases: list[dict[str, Any]] | None = None,
        documents: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owner_user_id = str(row["owner_user_id"])
        if cases is None:
            cases = self.list_cases(owner_user_id, limit=1000)
        if documents is None:
            with self.connect() as conn:
                documents = self._document_map(conn, owner_user_id)
        case_map = {str(case["id"]): case for case in cases}
        case_ids = [str(value) for value in _loads(row["case_ids"], [])]
        review_plan = _loads(row["review_plan"], [])
        selected = [case_map[case_id] for case_id in case_ids if case_id in case_map]
        active = [case for case in selected if case["status"] == "active"]
        archived = [case for case in selected if case["status"] == "archived"]
        active_sources = {
            str(case.get("source_memory_ref") or "")
            for case in active
            if case.get("source_memory_ref")
        }
        approved_sources = set(documents)
        safety_active = sum(bool(case["forbidden_source_refs"]) for case in active)
        target_count = int(row["target_case_count"])
        checks = {
            "target_active_cases": len(active) >= target_count,
            "approved_source_coverage": bool(
                not approved_sources or approved_sources <= active_sources
            ),
            "safety_negative_coverage": bool(
                not approved_sources or safety_active > 0
            ),
        }
        next_case = next(
            (case_map.get(case_id) for case_id in case_ids if case_map.get(case_id, {}).get("status") == "draft"),
            None,
        )
        by_variant: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for case in selected:
            variant = str(case.get("variant_key") or "canonical")
            source_ref = str(case.get("source_memory_ref") or "manual")
            by_variant[variant] = by_variant.get(variant, 0) + 1
            by_source[source_ref] = by_source.get(source_ref, 0) + 1
        plan_map = {
            str(item.get("case_id") or ""): item
            for item in review_plan
            if isinstance(item, dict)
        }
        proposal_count = sum(
            bool(item.get("proposal"))
            for item in review_plan
            if isinstance(item, dict)
        )
        return {
            "id": str(row["id"]),
            "owner_user_id": owner_user_id,
            "name": str(row["name"]),
            "target_case_count": target_count,
            "case_ids": case_ids,
            "review_plan": review_plan,
            "proposal_count": proposal_count,
            "status": "completed" if all(checks.values()) else "in_review",
            "selected_cases": len(selected),
            "active_cases": len(active),
            "archived_cases": len(archived),
            "remaining_cases": max(0, target_count - len(active)),
            "covered_approved_sources": len(approved_sources & active_sources),
            "approved_sources": len(approved_sources),
            "active_safety_negative_cases": safety_active,
            "checks": checks,
            "blockers": [name for name, passed in checks.items() if not passed],
            "by_variant": dict(sorted(by_variant.items())),
            "by_source": dict(sorted(by_source.items())),
            "next_case": next_case,
            "next_plan": plan_map.get(str(next_case["id"])) if next_case else None,
            "requested_by": str(row["requested_by"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "automatic_review": False,
            "automatic_activation": False,
        }

    def set_review_proposals(
        self,
        *,
        owner_user_id: str,
        batch_id: str,
        proposed_by: str,
        proposals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not proposals:
            raise MemoryRetrievalEvaluationError("at least one proposal is required")
        if len(proposals) > 100:
            raise MemoryRetrievalEvaluationError("at most 100 proposals are allowed")
        cases = self.list_cases(owner_user_id, limit=1000)
        case_map = {str(case["id"]): case for case in cases}
        now = _now()
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_retrieval_eval_batches
                WHERE id=? AND owner_user_id=?
                """,
                (str(batch_id), str(owner_user_id)),
            ).fetchone()
            if not row:
                raise MemoryRetrievalEvaluationError("review batch not found")
            review_plan = _loads(row["review_plan"], [])
            plan_map = {
                str(item.get("case_id") or ""): item
                for item in review_plan
                if isinstance(item, dict)
            }
            documents = self._document_map(conn, owner_user_id)
            allowed_source_refs = set(documents)
            seen: set[str] = set()
            for raw in proposals:
                case_id = str(raw.get("case_id") or "").strip()
                if not case_id or case_id in seen:
                    raise MemoryRetrievalEvaluationError(
                        "proposal case IDs must be present and unique"
                    )
                seen.add(case_id)
                if case_id not in plan_map or case_id not in case_map:
                    raise MemoryRetrievalEvaluationError(
                        f"proposal case is not part of the review batch: {case_id}"
                    )
                query = str(raw.get("suggested_query") or "").strip()
                if not query:
                    raise MemoryRetrievalEvaluationError(
                        "proposal suggested_query is required"
                    )
                if query == str(case_map[case_id]["query"]).strip():
                    raise MemoryRetrievalEvaluationError(
                        f"proposal must rewrite the current query: {case_id}"
                    )
                forbidden_refs = self._normalize_refs(
                    raw.get("suggested_forbidden_source_refs") or []
                )
                invalid_refs = sorted(set(forbidden_refs) - allowed_source_refs)
                if invalid_refs:
                    raise MemoryRetrievalEvaluationError(
                        "proposal contains unknown forbidden source references: "
                        + ", ".join(invalid_refs[:5])
                    )
                expected_refs = set(case_map[case_id]["expected_source_refs"])
                if expected_refs & set(forbidden_refs):
                    raise MemoryRetrievalEvaluationError(
                        f"proposal cannot forbid an expected source: {case_id}"
                    )
                rationale = str(raw.get("rationale") or "").strip()[:1000]
                if not rationale:
                    raise MemoryRetrievalEvaluationError(
                        "proposal rationale is required"
                    )
                proposal = {
                    "suggested_query": query[:20_000],
                    "suggested_forbidden_source_refs": forbidden_refs,
                    "rationale": rationale,
                    "proposed_by": str(proposed_by or "assistant")[:160],
                    "proposed_at": now,
                    "status": "pending_human_review",
                }
                proposal["proposal_hash"] = _hash(proposal)
                plan_map[case_id]["proposal"] = proposal
            conn.execute(
                """
                UPDATE memory_retrieval_eval_batches
                SET review_plan=?, updated_at=?
                WHERE id=? AND owner_user_id=?
                """,
                (_json(review_plan), now, str(batch_id), str(owner_user_id)),
            )
            updated = conn.execute(
                "SELECT * FROM memory_retrieval_eval_batches WHERE id=?",
                (str(batch_id),),
            ).fetchone()
        return self._serialize_batch(updated, cases=cases, documents=documents)

    def create_review_batch(
        self,
        *,
        owner_user_id: str,
        requested_by: str,
        target_count: int = 30,
        name: str = "",
    ) -> dict[str, Any]:
        target = max(1, min(int(target_count), 100))
        cases = self.list_cases(owner_user_id, limit=1000)
        with self.connect(immediate=True) as conn:
            existing = conn.execute(
                """
                SELECT * FROM memory_retrieval_eval_batches
                WHERE owner_user_id=? AND status='in_review'
                ORDER BY created_at DESC LIMIT 1
                """,
                (str(owner_user_id),),
            ).fetchone()
            if existing:
                documents = self._document_map(conn, owner_user_id)
                return self._serialize_batch(
                    existing, cases=cases, documents=documents
                )
            selected = self._balanced_review_selection(cases, target)
            if len(selected) < target:
                raise MemoryRetrievalEvaluationError(
                    f"only {len(selected)} review candidates are available; {target} required"
                )
            documents = self._document_map(conn, owner_user_id)
            source_refs = sorted(documents)
            review_plan: list[dict[str, Any]] = []
            for index, case in enumerate(selected, start=1):
                own_ref = str(case.get("source_memory_ref") or "")
                suggested_forbidden = (
                    [value for value in source_refs if value != own_ref][:3]
                    if case.get("variant_key") == "boundary"
                    else []
                )
                review_plan.append(
                    {
                        "order": index,
                        "case_id": str(case["id"]),
                        "source_memory_ref": own_ref,
                        "variant_key": str(case.get("variant_key") or "canonical"),
                        "suggested_forbidden_source_refs": suggested_forbidden,
                        "suggestion_requires_human_verification": bool(
                            suggested_forbidden
                        ),
                    }
                )
            identity = {
                "owner_user_id": str(owner_user_id),
                "case_ids": [case["id"] for case in selected],
                "target_count": target,
            }
            batch_id = f"memory-eval-batch-{_hash(identity)[:16]}"
            now = _now()
            conn.execute(
                """
                INSERT INTO memory_retrieval_eval_batches
                (id, owner_user_id, name, target_case_count, case_ids, review_plan,
                 status, requested_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'in_review', ?, ?, ?)
                """,
                (
                    batch_id,
                    str(owner_user_id),
                    str(name or f"可信标注批次 {now[:10]}")[:200],
                    target,
                    _json([case["id"] for case in selected]),
                    _json(review_plan),
                    str(requested_by or "admin")[:160],
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM memory_retrieval_eval_batches WHERE id=?",
                (batch_id,),
            ).fetchone()
        return self._serialize_batch(row, cases=cases, documents=documents)

    def latest_review_batch(self, owner_user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_retrieval_eval_batches
                WHERE owner_user_id=? ORDER BY created_at DESC LIMIT 1
                """,
                (str(owner_user_id),),
            ).fetchone()
        return self._serialize_batch(row) if row else None

    def list_cases(
        self, owner_user_id: str, *, status: str = "", limit: int = 200
    ) -> list[dict[str, Any]]:
        clean_status = str(status or "").strip().lower()
        if clean_status and clean_status not in CASE_STATUSES:
            raise MemoryRetrievalEvaluationError("invalid evaluation case status")
        with self.connect() as conn:
            if clean_status:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_retrieval_eval_cases
                    WHERE owner_user_id=? AND status=?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (str(owner_user_id), clean_status, max(1, min(int(limit), 1000))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_retrieval_eval_cases
                    WHERE owner_user_id=? ORDER BY updated_at DESC LIMIT ?
                    """,
                    (str(owner_user_id), max(1, min(int(limit), 1000))),
                ).fetchall()
        return [self._serialize_case(row) for row in rows]

    @staticmethod
    def _serialize_case(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["limit"] = result.pop("result_limit")
        for field in ("expected_source_refs", "forbidden_source_refs", "tags"):
            result[field] = _loads(result.get(field), [])
        result["review_checks"] = _loads(result.get("review_checks"), {})
        return result

    @staticmethod
    def _dataset_hash(cases: list[dict[str, Any]]) -> str:
        stable = [
            {
                "id": case["id"],
                "version": case["version"],
                "subject_user_id": case["subject_user_id"],
                "origin": case["origin"],
                "source_memory_ref": case["source_memory_ref"],
                "variant_key": case["variant_key"],
                "query": case["query"],
                "project_id": case["project_id"],
                "agent_id": case["agent_id"],
                "limit": case["limit"],
                "expected_source_refs": case["expected_source_refs"],
                "forbidden_source_refs": case["forbidden_source_refs"],
                "reviewer_confidence": case["reviewer_confidence"],
                "source_snapshot_hash": case["source_snapshot_hash"],
            }
            for case in sorted(cases, key=lambda item: item["id"])
        ]
        return _hash(stable)

    def _active_cases(
        self, owner_user_id: str, case_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        cases = self.list_cases(owner_user_id, status="active", limit=1000)
        selected = {str(case_id) for case_id in case_ids or [] if str(case_id)}
        if selected:
            cases = [case for case in cases if case["id"] in selected]
            missing = sorted(selected - {case["id"] for case in cases})
            if missing:
                raise MemoryRetrievalEvaluationError(
                    f"active evaluation cases not found: {', '.join(missing[:5])}"
                )
        integrity = self._source_integrity(owner_user_id, cases=cases)
        if integrity["stale_case_ids"]:
            raise MemoryRetrievalEvaluationError(
                "active evaluation source evidence is stale: "
                + ", ".join(integrity["stale_case_ids"][:5])
            )
        return sorted(cases, key=lambda item: item["id"])

    def run(
        self,
        *,
        owner_user_id: str,
        requested_by: str,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        cases = self._active_cases(owner_user_id, case_ids)
        if not cases:
            raise MemoryRetrievalEvaluationError("no active evaluation cases")
        if len(cases) > 100:
            raise MemoryRetrievalEvaluationError(
                "at most 100 active evaluation cases can be run at once"
            )
        observations: dict[str, dict[str, Any]] = {}
        degraded_cases = 0
        models: set[str] = set()
        served_strategies: set[str] = set()
        candidate_strategies: set[str] = set()
        for case in cases:
            try:
                pack = self.context_service.retrieve(
                    user_id=str(case.get("subject_user_id") or owner_user_id),
                    query=case["query"],
                    project_id=case["project_id"],
                    agent_id=case["agent_id"],
                    purpose="memory-retrieval-evaluation",
                    limit=case["limit"],
                    persist=False,
                    graph_mode="disabled",
                )
                health = pack.get("retrieval_health") or {}
                vector = health.get("vector_memory") or {}
                fusion = health.get("hybrid_fusion") or {}
                comparison = fusion.get("comparison") or {}
                baseline_refs = [
                    str(value) for value in comparison.get("baseline_refs") or []
                ]
                candidate_refs = [
                    str(value) for value in comparison.get("candidate_refs") or []
                ]
                vector_status = str(vector.get("status") or "not_configured")
                degraded = vector_status != "ready"
                degraded_cases += int(degraded)
                if vector.get("model"):
                    models.add(str(vector["model"]))
                served_strategies.add(
                    str(fusion.get("served_strategy") or "score-sort-baseline")
                )
                candidate_strategies.add(
                    str(fusion.get("candidate_strategy") or "weighted-rrf.v1")
                )
                observations[case["id"]] = {
                    "baseline_refs": baseline_refs,
                    "candidate_refs": candidate_refs,
                    "vector_status": vector_status,
                    "degraded": degraded,
                }
            except Exception as exc:
                degraded_cases += 1
                observations[case["id"]] = {
                    "baseline_refs": [],
                    "candidate_refs": [],
                    "vector_status": "error",
                    "degraded": True,
                    "error": str(exc)[:500],
                }

        baseline = evaluate_retrieval_cases(
            cases,
            lambda case: observations[case["id"]]["baseline_refs"],
            k=10,
        )
        candidate = evaluate_retrieval_cases(
            cases,
            lambda case: observations[case["id"]]["candidate_refs"],
            k=10,
        )
        assessment = assess_retrieval_rollout(
            baseline,
            candidate,
            max_recall_drop=0.0,
            max_mrr_drop=0.02,
        )
        checks = {
            **assessment["checks"],
            "minimum_labeled_cases": len(cases) >= _minimum_cases(),
            "candidate_forbidden_hits_zero": int(candidate["forbidden_hits"]) == 0,
            "retrieval_channels_healthy": degraded_cases == 0,
        }
        assessment = {
            **assessment,
            "passed": all(checks.values()),
            "checks": checks,
            "minimum_labeled_cases": _minimum_cases(),
            "degraded_cases": degraded_cases,
        }
        run_id = f"memory-retrieval-eval-{uuid.uuid4().hex[:12]}"
        dataset_hash = self._dataset_hash(cases)
        strategy_metadata = {
            "models": sorted(models),
            "served_strategies": sorted(served_strategies),
            "candidate_strategies": sorted(candidate_strategies),
        }
        details = [
            {
                "case_id": case["id"],
                "case_version": case["version"],
                **observations[case["id"]],
            }
            for case in cases
        ]
        status = "passed" if assessment["passed"] else "blocked"
        created_at = _now()
        with self.connect(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO memory_retrieval_eval_runs
                (id, owner_user_id, requested_by, evaluation_version, dataset_hash,
                 case_count, baseline_metrics, candidate_metrics, assessment,
                 details, strategy_metadata, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(owner_user_id),
                    str(requested_by or "admin")[:160],
                    EVALUATION_VERSION,
                    dataset_hash,
                    len(cases),
                    _json(baseline),
                    _json(candidate),
                    _json(assessment),
                    _json(details),
                    _json(strategy_metadata),
                    status,
                    created_at,
                ),
            )
        return {
            "id": run_id,
            "owner_user_id": str(owner_user_id),
            "evaluation_version": EVALUATION_VERSION,
            "dataset_hash": dataset_hash,
            "case_count": len(cases),
            "baseline": baseline,
            "candidate": candidate,
            "assessment": assessment,
            "details": details,
            "strategy_metadata": strategy_metadata,
            "status": status,
            "created_at": created_at,
        }

    def latest_run(self, owner_user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_retrieval_eval_runs
                WHERE owner_user_id=? ORDER BY created_at DESC LIMIT 1
                """,
                (str(owner_user_id),),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["baseline"] = _loads(result.pop("baseline_metrics"), {})
        result["candidate"] = _loads(result.pop("candidate_metrics"), {})
        for field in ("assessment", "details", "strategy_metadata"):
            result[field] = _loads(result.get(field), {} if field != "details" else [])
        return result

    def rollout_gate(
        self, *, owner_user_id: str, window_hours: int = 168
    ) -> dict[str, Any]:
        online = self.context_service.retrieval_shadow_metrics(
            window_hours=window_hours
        )
        all_cases = self.list_cases(owner_user_id, limit=1000)
        active_cases = [case for case in all_cases if case["status"] == "active"]
        integrity = self._source_integrity(owner_user_id, cases=active_cases)
        with self.connect() as conn:
            approved_sources = set(self._document_map(conn, owner_user_id))
        active_sources = {
            str(case.get("source_memory_ref") or "")
            for case in active_cases
            if case.get("source_memory_ref")
        }
        active_hash = self._dataset_hash(active_cases)
        latest = self.latest_run(owner_user_id)
        offline_checks = {
            "evaluation_exists": latest is not None,
            "minimum_labeled_cases": len(active_cases) >= _minimum_cases(),
            "dataset_current": bool(
                latest and str(latest.get("dataset_hash")) == active_hash
            ),
            "quality_gate_passed": bool(
                latest and (latest.get("assessment") or {}).get("passed")
            ),
            "source_evidence_current": bool(integrity["passed"]),
            "approved_source_coverage": bool(
                not approved_sources or approved_sources <= active_sources
            ),
            "safety_negative_coverage": bool(
                not approved_sources
                or any(case["forbidden_source_refs"] for case in active_cases)
            ),
        }
        shadow_mode_active = (
            str(getattr(self.context_service, "_fusion_mode", "")) == "shadow"
        )
        online_passed = bool(
            (online.get("rollout_gate") or {}).get("online_observation_passed")
        )
        promotion_ready = (
            shadow_mode_active
            and online_passed
            and all(offline_checks.values())
        )
        blockers: list[str] = []
        if not shadow_mode_active:
            blockers.append("shadow_mode_not_active")
        if not online_passed:
            blockers.extend(
                f"online:{value}"
                for value in (online.get("rollout_gate") or {}).get("blockers") or []
                if value != "offline_labeled_evaluation"
            )
        blockers.extend(
            f"offline:{name}"
            for name, passed in offline_checks.items()
            if not passed
        )
        return {
            "promotion_ready": promotion_ready,
            "recommended_action": (
                "switch_to_weighted_rrf"
                if promotion_ready
                else "continue_shadow_and_resolve_blockers"
            ),
            "fusion_mode": str(
                getattr(self.context_service, "_fusion_mode", "unknown")
            ),
            "online": online,
            "offline": {
                "active_cases": len(active_cases),
                "minimum_required": _minimum_cases(),
                "dataset_hash": active_hash,
                "checks": offline_checks,
                "stale_case_ids": integrity["stale_case_ids"],
                "approved_sources": len(approved_sources),
                "covered_approved_sources": len(approved_sources & active_sources),
                "active_safety_negative_cases": sum(
                    bool(case["forbidden_source_refs"]) for case in active_cases
                ),
                "latest_run": latest,
            },
            "blockers": list(dict.fromkeys(blockers)),
            "automatic_switch_performed": False,
        }
