"""Read-only operational status and alert synthesis for graph-memory rollout."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from services.context_retrieval_service import ContextRetrievalService
from services.memory_projection_reconciliation_service import (
    MemoryProjectionReconciliationService,
)


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


class GraphMemoryOperationsService:
    def __init__(self, context_service: ContextRetrievalService):
        self.context_service = context_service

    def status(
        self,
        *,
        user_id: str,
        project_id: str = "",
        reconcile_projection: bool = False,
    ) -> dict[str, Any]:
        db_path = self.context_service.db_path
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with sqlite3.connect(db_path, timeout=8) as conn:
            conn.row_factory = sqlite3.Row
            outbox = self._outbox_counts(conn)
            recent = self._recent_retrieval(conn, str(user_id), cutoff)
            latest_evaluation = self._latest_evaluation(conn, str(user_id))
        resolved_mode = self.context_service.resolve_graph_memory_mode(user_id, project_id)
        alerts: list[dict[str, str]] = []
        if outbox["dead_letter"]:
            alerts.append({"level": "critical", "code": "graph_sync_dead_letter", "message": f"{outbox['dead_letter']} 条图谱投影进入死信队列"})
        if outbox["pending"] + outbox["retry"] > 20:
            alerts.append({"level": "warning", "code": "graph_sync_backlog", "message": "图谱投影同步队列存在积压"})
        if recent["total"] >= 10 and recent["degraded_rate"] > 0.2:
            alerts.append({"level": "warning", "code": "graph_retrieval_degraded", "message": "近 24 小时图谱检索降级率超过 20%"})
        if recent["conflicts"]:
            alerts.append({"level": "warning", "code": "graph_memory_conflicts", "message": f"近 24 小时发现 {recent['conflicts']} 条图谱冲突"})
        if not latest_evaluation:
            alerts.append({"level": "info", "code": "graph_evaluation_missing", "message": "尚无图谱记忆评测报告"})
        projection_reconciliation: dict[str, Any] = {"status": "not_run"}
        if reconcile_projection:
            reconciler = MemoryProjectionReconciliationService(
                db_path,
                vector_service=self.context_service._vector_retriever,
                graph_client=self.context_service._graph_memory_client,
            )
            projection_reconciliation = reconciler.reconcile_graph(user_id=str(user_id))
            if not projection_reconciliation.get("consistent"):
                alerts.append({
                    "level": "critical",
                    "code": "graph_projection_drift",
                    "message": "图谱投影与权威记忆存在差异",
                })
        return {
            "status": "attention" if any(alert["level"] == "critical" for alert in alerts) else "warning" if any(alert["level"] == "warning" for alert in alerts) else "ready",
            "resolved_mode": resolved_mode,
            "rollout_configs": self.context_service.list_graph_memory_modes(user_id),
            "outbox": outbox,
            "recent_retrieval": recent,
            "latest_evaluation": latest_evaluation,
            "projection_reconciliation": projection_reconciliation,
            "alerts": alerts,
        }

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())

    def _outbox_counts(self, conn: sqlite3.Connection) -> dict[str, int]:
        counts = {"pending": 0, "retry": 0, "processing": 0, "delivered": 0, "dead_letter": 0}
        if not self._table_exists(conn, "memory_graph_outbox"):
            return counts
        for row in conn.execute("SELECT status, COUNT(*) AS count FROM memory_graph_outbox GROUP BY status"):
            if row["status"] in counts:
                counts[row["status"]] = int(row["count"])
        return counts

    def _recent_retrieval(self, conn: sqlite3.Connection, user_id: str, cutoff: str) -> dict[str, Any]:
        rows = conn.execute(
            "SELECT retrieval_health FROM context_packs WHERE user_id=? AND created_at>=?",
            (user_id, cutoff),
        ).fetchall()
        total = degraded = conflicts = graph_items = 0
        for row in rows:
            graph = (_loads(row["retrieval_health"], {}).get("graph_memory") or {})
            if not isinstance(graph, dict):
                continue
            total += 1
            degraded += int(graph.get("status") == "degraded")
            conflicts += int(graph.get("conflicts") or 0)
            graph_items += int(graph.get("results") or 0)
        return {
            "window_hours": 24,
            "total": total,
            "degraded": degraded,
            "degraded_rate": round(degraded / total, 4) if total else 0.0,
            "conflicts": conflicts,
            "graph_items": graph_items,
        }

    def _latest_evaluation(self, conn: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
        if not self._table_exists(conn, "graph_memory_evaluation_runs"):
            return None
        row = conn.execute(
            """
            SELECT id, modes, summary, created_at FROM graph_memory_evaluation_runs
            WHERE user_id=? ORDER BY created_at DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {"id": row["id"], "modes": _loads(row["modes"], []), "summary": _loads(row["summary"], {}), "created_at": row["created_at"]}
