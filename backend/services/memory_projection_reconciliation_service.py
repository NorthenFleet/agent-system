"""Read-only reconciliation across canonical, lifecycle, vector and graph memory."""

from __future__ import annotations

import sqlite3
from typing import Any

from services.graph_memory_client import GraphMemoryClient, graph_memory_client
from services.memory_lifecycle_service import MemoryLifecycleService
from services.memory_vector_service import ApprovedMemoryVectorService, MemoryVectorDocument
from unified_data_manager import UNIFIED_DB_PATH


class MemoryProjectionReconciliationService:
    def __init__(
        self,
        db_path: str = UNIFIED_DB_PATH,
        *,
        vector_service: ApprovedMemoryVectorService | None = None,
        graph_client: GraphMemoryClient | None = None,
        lifecycle_service: MemoryLifecycleService | None = None,
    ):
        self.db_path = db_path
        self.vector_service = vector_service or ApprovedMemoryVectorService(db_path)
        self.graph_client = graph_client or graph_memory_client
        self.lifecycle_service = lifecycle_service or MemoryLifecycleService(db_path)

    @staticmethod
    def _visibility(document: MemoryVectorDocument) -> str:
        return "agent" if document.agent_id else "project" if document.project_id else "profile"

    def canonical_documents(self, *, user_id: str = "") -> list[MemoryVectorDocument]:
        with self.vector_service.connect() as conn:
            documents = self.vector_service.load_approved_documents(conn)
        if user_id:
            documents = [item for item in documents if item.user_id == str(user_id)]
        return documents

    def reconcile_graph(
        self,
        *,
        user_id: str = "",
        documents: list[MemoryVectorDocument] | None = None,
    ) -> dict[str, Any]:
        expected_documents = documents if documents is not None else self.canonical_documents(user_id=user_id)
        expected = {item.source_ref: item for item in expected_documents}
        try:
            inventory = self.graph_client.projection_inventory(user_id=user_id, limit=5000)
        except Exception as exc:
            return {
                "status": "degraded",
                "consistent": False,
                "canonical_count": len(expected),
                "projection_count": 0,
                "error": str(exc)[:500],
                "missing_count": len(expected),
                "missing_refs": sorted(expected)[:100],
            }
        actual = {str(row.get("source_ref") or ""): row for row in inventory if row.get("source_ref")}
        active_actual = {
            ref: row for ref, row in actual.items() if str(row.get("status") or "") == "active"
        }
        missing = sorted(set(expected) - set(active_actual))
        orphaned_active = sorted(set(active_actual) - set(expected))
        stale = sorted(
            ref for ref in set(expected) & set(active_actual)
            if str(active_actual[ref].get("content_hash") or "") != expected[ref].content_hash
        )
        scope_drift = sorted(
            ref for ref in set(expected) & set(active_actual)
            if (
                str(active_actual[ref].get("owner_user_id") or "") != expected[ref].user_id
                or str(active_actual[ref].get("project_id") or "") != expected[ref].project_id
                or str(active_actual[ref].get("agent_id") or "") != expected[ref].agent_id
                or str(active_actual[ref].get("visibility") or "") != self._visibility(expected[ref])
            )
        )
        consistent = not (missing or orphaned_active or stale or scope_drift)
        return {
            "status": "ready" if consistent else "drifted",
            "consistent": consistent,
            "canonical_count": len(expected),
            "projection_count": len(actual),
            "active_projection_count": len(active_actual),
            "missing_count": len(missing),
            "orphaned_active_count": len(orphaned_active),
            "stale_count": len(stale),
            "scope_drift_count": len(scope_drift),
            "missing_refs": missing[:100],
            "orphaned_active_refs": orphaned_active[:100],
            "stale_refs": stale[:100],
            "scope_drift_refs": scope_drift[:100],
        }

    def queue_status(self) -> dict[str, Any]:
        counts = {
            "graph": {"pending": 0, "retry": 0, "processing": 0, "delivered": 0, "dead_letter": 0},
            "vector": {"pending": 0, "processing": 0, "completed": 0, "dead_letter": 0},
        }
        vector_operations = self.vector_service.operations_status()
        vector_queue = vector_operations.get("queue") or {}
        counts["vector"].update({
            key: int(vector_queue.get(key) or 0)
            for key in counts["vector"]
        })
        with sqlite3.connect(self.db_path, timeout=8) as conn:
            conn.row_factory = sqlite3.Row
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_graph_outbox'"
            ).fetchone()
            if exists:
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM memory_graph_outbox GROUP BY status"
                ):
                    status = "dead_letter" if str(row["status"]) == "dead" else str(row["status"])
                    if status in counts["graph"]:
                        counts["graph"][status] = int(row["count"])
        return counts

    def reconcile(self, *, user_id: str = "") -> dict[str, Any]:
        documents = self.canonical_documents(user_id=user_id)
        vector = self.vector_service.reconcile_projection()
        if user_id and vector.get("consistent"):
            # The vector service performs the stronger global reconciliation;
            # retain that evidence rather than weakening it to a scoped sample.
            vector = {**vector, "scope": "global", "requested_user_id": user_id}
        graph = self.reconcile_graph(user_id=user_id, documents=documents)
        lifecycle = self.lifecycle_service.verify(user_id=user_id)
        queues = self.queue_status()
        queues_clear = all(
            queues[engine][key] == 0
            for engine, keys in {
                "graph": ("pending", "retry", "processing", "dead_letter"),
                "vector": ("pending", "processing", "dead_letter"),
            }.items()
            for key in keys
        )
        consistent = bool(
            vector.get("consistent")
            and graph.get("consistent")
            and lifecycle.get("consistent")
            and queues_clear
        )
        return {
            "status": "ready" if consistent else "drifted",
            "consistent": consistent,
            "user_id": str(user_id or ""),
            "canonical_active_count": len(documents),
            "vector": vector,
            "graph": graph,
            "lifecycle": lifecycle,
            "queues": queues,
            "queues_clear": queues_clear,
        }
