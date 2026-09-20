"""Privacy-minimized persistence and aggregation for hybrid retrieval Shadow runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_RETENTION_DAYS = 30
DEFAULT_MIN_QUERIES = 100
DEFAULT_VECTOR_AVAILABILITY_TARGET = 0.99
DEFAULT_VECTOR_P95_MS = 300.0
DEFAULT_TOTAL_P95_MS = 800.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bounded_float(
    value: Any, default: float, minimum: float, maximum: float
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _fingerprint(value: Any) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(0, min(math.ceil(float(quantile) * len(ordered)) - 1, len(ordered) - 1))
    return round(ordered[index], 2)


def ensure_shadow_metrics_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_retrieval_shadow_events (
            id TEXT PRIMARY KEY,
            pack_id TEXT,
            user_fingerprint TEXT NOT NULL,
            project_fingerprint TEXT NOT NULL,
            query_fingerprint TEXT NOT NULL,
            rollout_mode TEXT NOT NULL,
            served_strategy TEXT NOT NULL,
            candidate_strategy TEXT NOT NULL,
            status TEXT NOT NULL,
            result_count INTEGER NOT NULL DEFAULT 0,
            total_latency_ms REAL NOT NULL DEFAULT 0,
            vector_status TEXT NOT NULL,
            vector_latency_ms REAL,
            top1_changed INTEGER NOT NULL DEFAULT 0,
            topk_k INTEGER NOT NULL DEFAULT 0,
            topk_overlap INTEGER NOT NULL DEFAULT 0,
            topk_overlap_ratio REAL NOT NULL DEFAULT 0,
            mean_rank_displacement REAL NOT NULL DEFAULT 0,
            multi_channel_candidates INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memory_shadow_events_recent
            ON memory_retrieval_shadow_events(created_at DESC, rollout_mode, status);

        CREATE INDEX IF NOT EXISTS idx_memory_shadow_events_query
            ON memory_retrieval_shadow_events(query_fingerprint, created_at DESC);
        """
    )


def record_shadow_observation(
    conn: sqlite3.Connection,
    *,
    pack_id: str,
    payload: dict[str, Any],
    total_latency_ms: float,
    created_at: str | None = None,
) -> str | None:
    """Persist only scalar diagnostics; never store query text or ranked references."""
    health = payload.get("retrieval_health") or {}
    fusion = health.get("hybrid_fusion") or {}
    if str(fusion.get("rollout_mode") or "") != "shadow":
        return None
    ensure_shadow_metrics_schema(conn)
    vector = health.get("vector_memory") or {}
    comparison = fusion.get("comparison") or {}
    vector_status = str(vector.get("status") or "not_configured")
    event_id = f"shadow-retrieval-{uuid.uuid4().hex[:12]}"
    timestamp = created_at or _now()
    conn.execute(
        """
        INSERT INTO memory_retrieval_shadow_events
        (id, pack_id, user_fingerprint, project_fingerprint, query_fingerprint,
         rollout_mode, served_strategy, candidate_strategy, status, result_count,
         total_latency_ms, vector_status, vector_latency_ms, top1_changed,
         topk_k, topk_overlap, topk_overlap_ratio, mean_rank_displacement,
         multi_channel_candidates, created_at)
        VALUES (?, ?, ?, ?, ?, 'shadow', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            str(pack_id or ""),
            _fingerprint(payload.get("user_id")),
            _fingerprint(payload.get("project_id")),
            _fingerprint(payload.get("query")),
            str(fusion.get("served_strategy") or "score-sort-baseline"),
            str(fusion.get("candidate_strategy") or "weighted-rrf.v1"),
            "ready" if vector_status == "ready" else "degraded",
            len(payload.get("items") or []),
            max(0.0, float(total_latency_ms or 0)),
            vector_status,
            (
                max(0.0, float(vector.get("latency_ms") or 0))
                if vector.get("latency_ms") is not None
                else None
            ),
            int(bool(comparison.get("top1_changed"))),
            max(0, int(comparison.get("k") or 0)),
            max(0, int(comparison.get("overlap") or 0)),
            max(0.0, min(float(comparison.get("overlap_ratio") or 0), 1.0)),
            max(0.0, float(comparison.get("mean_rank_displacement") or 0)),
            max(0, int(fusion.get("multi_channel_candidates") or 0)),
            timestamp,
        ),
    )
    retention_days = _bounded_int(
        os.getenv("MEMORY_SHADOW_METRICS_RETENTION_DAYS"),
        DEFAULT_RETENTION_DAYS,
        1,
        365,
    )
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    conn.execute(
        "DELETE FROM memory_retrieval_shadow_events WHERE created_at < ?", (cutoff,)
    )
    return event_id


def summarize_shadow_observations(
    conn: sqlite3.Connection,
    *,
    window_hours: int = 168,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_shadow_metrics_schema(conn)
    current = now or datetime.now(timezone.utc)
    bounded_window = _bounded_int(window_hours, 168, 1, 24 * 90)
    since = (current - timedelta(hours=bounded_window)).isoformat()
    rows = conn.execute(
        """
        SELECT * FROM memory_retrieval_shadow_events
        WHERE rollout_mode='shadow' AND created_at >= ?
        ORDER BY created_at
        """,
        (since,),
    ).fetchall()
    records = [dict(row) for row in rows]
    total = len(records)
    vector_statuses = Counter(str(row["vector_status"]) for row in records)
    served_strategies = Counter(str(row["served_strategy"]) for row in records)
    candidate_strategies = Counter(str(row["candidate_strategy"]) for row in records)
    total_latencies = [float(row["total_latency_ms"] or 0) for row in records]
    vector_latencies = [
        float(row["vector_latency_ms"])
        for row in records
        if row["vector_latency_ms"] is not None
    ]
    ready_count = vector_statuses.get("ready", 0)
    vector_availability = round(ready_count / max(total, 1), 4)
    top1_changes = sum(int(row["top1_changed"] or 0) for row in records)
    mean_overlap = round(
        sum(float(row["topk_overlap_ratio"] or 0) for row in records) / max(total, 1),
        4,
    )
    mean_displacement = round(
        sum(float(row["mean_rank_displacement"] or 0) for row in records)
        / max(total, 1),
        4,
    )
    minimum_queries = _bounded_int(
        os.getenv("MEMORY_SHADOW_MIN_QUERIES"), DEFAULT_MIN_QUERIES, 1, 100000
    )
    availability_target = _bounded_float(
        os.getenv("MEMORY_SHADOW_VECTOR_AVAILABILITY_TARGET"),
        DEFAULT_VECTOR_AVAILABILITY_TARGET,
        0.0,
        1.0,
    )
    vector_p95_target = _bounded_float(
        os.getenv("MEMORY_SHADOW_VECTOR_P95_MS"),
        DEFAULT_VECTOR_P95_MS,
        1.0,
        60000.0,
    )
    total_p95_target = _bounded_float(
        os.getenv("MEMORY_SHADOW_TOTAL_P95_MS"),
        DEFAULT_TOTAL_P95_MS,
        1.0,
        60000.0,
    )
    vector_p95 = _percentile(vector_latencies, 0.95)
    total_p95 = _percentile(total_latencies, 0.95)
    checks = {
        "minimum_queries": total >= minimum_queries,
        "vector_availability": total > 0 and vector_availability >= availability_target,
        "vector_p95_latency": bool(vector_latencies) and vector_p95 <= vector_p95_target,
        "total_p95_latency": bool(total_latencies) and total_p95 <= total_p95_target,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    blockers.append("offline_labeled_evaluation")
    return {
        "status": "ready" if total else "empty",
        "window": {
            "hours": bounded_window,
            "since": since,
            "until": current.isoformat(),
        },
        "samples": {
            "queries": total,
            "distinct_query_fingerprints": len(
                {str(row["query_fingerprint"]) for row in records}
            ),
            "minimum_required": minimum_queries,
            "remaining": max(0, minimum_queries - total),
        },
        "availability": {
            "vector_ready_rate": vector_availability,
            "target": availability_target,
            "by_status": dict(sorted(vector_statuses.items())),
        },
        "latency_ms": {
            "total": {
                "p50": _percentile(total_latencies, 0.50),
                "p95": total_p95,
                "p99": _percentile(total_latencies, 0.99),
                "target_p95": total_p95_target,
            },
            "vector": {
                "samples": len(vector_latencies),
                "p50": _percentile(vector_latencies, 0.50),
                "p95": vector_p95,
                "p99": _percentile(vector_latencies, 0.99),
                "target_p95": vector_p95_target,
            },
        },
        "ranking_change": {
            "top1_changes": top1_changes,
            "top1_change_rate": round(top1_changes / max(total, 1), 4),
            "mean_topk_overlap_ratio": mean_overlap,
            "mean_rank_displacement": mean_displacement,
        },
        "strategies": {
            "served": dict(sorted(served_strategies.items())),
            "candidate": dict(sorted(candidate_strategies.items())),
        },
        "rollout_gate": {
            "online_observation_passed": all(checks.values()),
            "promotion_ready": False,
            "checks": checks,
            "blockers": blockers,
            "offline_requirements": {
                "minimum_labeled_cases": _bounded_int(
                    os.getenv("MEMORY_ROLLOUT_MIN_LABELED_CASES"),
                    30,
                    1,
                    1000,
                ),
                "forbidden_hits": 0,
                "recall_regression_allowed": 0.0,
                "mrr_drop_allowed": 0.02,
            },
        },
        "privacy": {
            "raw_query_stored": False,
            "ranked_references_stored": False,
            "retention_days": _bounded_int(
                os.getenv("MEMORY_SHADOW_METRICS_RETENTION_DAYS"),
                DEFAULT_RETENTION_DAYS,
                1,
                365,
            ),
        },
    }
