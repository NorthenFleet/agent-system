"""Offline A/B evaluation for graph-memory context retrieval modes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from services.context_retrieval_service import ContextRetrievalService, GRAPH_RETRIEVAL_MODES
from unified_data_manager import UNIFIED_DB_PATH


class GraphMemoryEvaluationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class GraphMemoryEvaluationService:
    """Compare disabled, retrieval, and rerank graph-memory modes safely."""

    def __init__(
        self,
        context_service: ContextRetrievalService,
        db_path: str = UNIFIED_DB_PATH,
    ):
        self.context_service = context_service
        self.db_path = db_path
        self.ensure_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=8)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=8000")
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
                CREATE TABLE IF NOT EXISTS graph_memory_evaluation_runs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    modes TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_memory_evaluation_cases (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    hit INTEGER,
                    citation_count INTEGER NOT NULL,
                    citation_errors INTEGER NOT NULL,
                    estimated_tokens INTEGER NOT NULL,
                    task_success INTEGER,
                    graph_degraded INTEGER NOT NULL DEFAULT 0,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES graph_memory_evaluation_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_graph_memory_evaluations_run
                    ON graph_memory_evaluation_cases(run_id, mode, case_id);
                """
            )

    def evaluate(
        self,
        *,
        user_id: str,
        requested_by: str,
        cases: list[dict[str, Any]],
        modes: list[str] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        clean_cases = [self._normalize_case(case, index) for index, case in enumerate(cases)]
        if not clean_cases:
            raise GraphMemoryEvaluationError("at least one evaluation case is required")
        if len(clean_cases) > 100:
            raise GraphMemoryEvaluationError("at most 100 evaluation cases are allowed")
        clean_modes = [str(mode).strip().lower() for mode in (modes or ["disabled", "retrieval", "rerank"])]
        if not clean_modes or any(mode not in GRAPH_RETRIEVAL_MODES for mode in clean_modes):
            raise GraphMemoryEvaluationError("modes must use disabled, retrieval, or rerank")
        clean_modes = list(dict.fromkeys(clean_modes))

        rows: list[dict[str, Any]] = []
        for case in clean_cases:
            for mode in clean_modes:
                pack = self.context_service.retrieve(
                    user_id=user_id,
                    query=case["query"],
                    project_id=case["project_id"],
                    agent_id=case["agent_id"],
                    purpose="graph-memory-evaluation",
                    limit=case["limit"],
                    persist=False,
                    graph_mode=mode,
                )
                source_refs = [str(item.get("source_ref") or "") for item in pack.get("items") or []]
                citations = [reference for reference in source_refs if reference]
                expected = set(case["expected_source_refs"])
                forbidden = set(case["forbidden_source_refs"])
                hits = sorted(expected.intersection(citations))
                citation_errors = sorted(forbidden.intersection(citations))
                task_success = case["task_outcomes"].get(mode)
                graph_health = (pack.get("retrieval_health") or {}).get("graph_memory") or {}
                rows.append(
                    {
                        "case_id": case["id"],
                        "mode": mode,
                        "hit": bool(hits) if expected else None,
                        "matched_source_refs": hits,
                        "citations": citations,
                        "citation_errors": citation_errors,
                        "estimated_tokens": self._estimated_tokens(pack.get("items") or []),
                        "task_success": task_success,
                        "graph_degraded": graph_health.get("status") == "degraded",
                        "graph_conflicts": int(graph_health.get("conflicts") or 0),
                    }
                )
        summary = self._summarize(rows, clean_modes)
        result = {
            "id": "",
            "user_id": user_id,
            "modes": clean_modes,
            "cases": rows,
            "summary": summary,
            "dataset_hash": hashlib.sha256(_json(clean_cases).encode("utf-8")).hexdigest(),
        }
        if persist:
            result["id"] = self._persist(result, requested_by)
        return result

    @staticmethod
    def _normalize_case(raw: Any, index: int) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise GraphMemoryEvaluationError(f"case {index + 1} must be an object")
        query = str(raw.get("query") or "").strip()
        if not query:
            raise GraphMemoryEvaluationError(f"case {index + 1} requires query")
        outcomes = raw.get("task_outcomes") or {}
        if not isinstance(outcomes, dict):
            raise GraphMemoryEvaluationError(f"case {index + 1} task_outcomes must be an object")
        normalized_outcomes = {
            str(mode): bool(value)
            for mode, value in outcomes.items()
            if str(mode) in GRAPH_RETRIEVAL_MODES and isinstance(value, bool)
        }
        return {
            "id": str(raw.get("id") or f"case-{index + 1}").strip()[:160],
            "query": query[:20_000],
            "project_id": str(raw.get("project_id") or "").strip()[:160],
            "agent_id": str(raw.get("agent_id") or "optimus").strip()[:160],
            "limit": max(1, min(int(raw.get("limit") or 12), 50)),
            "expected_source_refs": [
                str(value).strip()[:500]
                for value in raw.get("expected_source_refs") or []
                if str(value).strip()
            ][:50],
            "forbidden_source_refs": [
                str(value).strip()[:500]
                for value in raw.get("forbidden_source_refs") or []
                if str(value).strip()
            ][:50],
            "task_outcomes": normalized_outcomes,
        }

    @staticmethod
    def _estimated_tokens(items: list[dict[str, Any]]) -> int:
        return sum((len(str(item.get("content") or "")) + 3) // 4 for item in items)

    @staticmethod
    def _summarize(rows: list[dict[str, Any]], modes: list[str]) -> dict[str, Any]:
        by_mode: dict[str, dict[str, Any]] = {}
        for mode in modes:
            current = [row for row in rows if row["mode"] == mode]
            hit_rows = [row for row in current if row["hit"] is not None]
            outcome_rows = [row for row in current if row["task_success"] is not None]
            citation_count = sum(len(row["citations"]) for row in current)
            citation_errors = sum(len(row["citation_errors"]) for row in current)
            by_mode[mode] = {
                "cases": len(current),
                "hit_rate": round(sum(bool(row["hit"]) for row in hit_rows) / len(hit_rows), 4) if hit_rows else None,
                "citation_error_rate": round(citation_errors / citation_count, 4) if citation_count else 0.0,
                "average_estimated_tokens": round(sum(row["estimated_tokens"] for row in current) / len(current), 2) if current else 0.0,
                "task_completion_rate": round(sum(bool(row["task_success"]) for row in outcome_rows) / len(outcome_rows), 4) if outcome_rows else None,
                "graph_degraded_cases": sum(bool(row["graph_degraded"]) for row in current),
                "graph_conflicts": sum(int(row["graph_conflicts"]) for row in current),
            }
        return {"by_mode": by_mode, "case_count": len({row["case_id"] for row in rows})}

    def _persist(self, result: dict[str, Any], requested_by: str) -> str:
        run_id = f"graph-eval-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO graph_memory_evaluation_runs
                (id, user_id, requested_by, dataset_hash, modes, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, result["user_id"], requested_by[:160], result["dataset_hash"], _json(result["modes"]), _json(result["summary"]), now),
            )
            for row in result["cases"]:
                conn.execute(
                    """
                    INSERT INTO graph_memory_evaluation_cases
                    (id, run_id, case_id, mode, hit, citation_count, citation_errors,
                     estimated_tokens, task_success, graph_degraded, result, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"graph-eval-case-{uuid.uuid4().hex[:12]}", run_id, row["case_id"], row["mode"],
                        None if row["hit"] is None else int(row["hit"]), len(row["citations"]), len(row["citation_errors"]),
                        row["estimated_tokens"], None if row["task_success"] is None else int(row["task_success"]),
                        int(row["graph_degraded"]), _json(row), now,
                    ),
                )
        return run_id
