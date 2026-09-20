"""Scope-aware memory introspection for users and OpenClaw agents.

The unified 3021 database is authoritative. OpenClaw files, its lexical index,
and graph-memory are auxiliary retrieval channels whose absence must never be
reported as absence of canonical memory.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from services.context_retrieval_service import ContextRetrievalService


IMPORTANCE_ORDER = "CASE importance WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END"


class MemoryAwarenessService:
    """Build a user-scoped inventory and explain auxiliary channel health."""

    def __init__(
        self,
        context_service: ContextRetrievalService,
        *,
        graph_db_path: str = "~/.openclaw/graph-memory.db",
    ):
        self.context_service = context_service
        self.graph_db_path = Path(os.path.expanduser(graph_db_path))

    def inspect(
        self,
        *,
        user_id: str,
        query: str,
        agent_id: str = "optimus",
        project_id: str = "",
        limit: int = 12,
        persist: bool = True,
    ) -> dict[str, Any]:
        clean_user_id = str(user_id or "").strip()
        clean_query = str(query or "").strip()
        clean_agent_id = re.sub(r"[^A-Za-z0-9_.-]", "", str(agent_id or "optimus")) or "optimus"
        clean_project_id = str(project_id or "").strip()
        clean_limit = max(1, min(int(limit), 50))
        if not clean_user_id:
            raise ValueError("user_id is required")
        if not clean_query:
            raise ValueError("query is required")

        retrieval = self.context_service.retrieve(
            user_id=clean_user_id,
            query=clean_query,
            project_id=clean_project_id,
            agent_id=clean_agent_id,
            purpose="memory_introspection",
            limit=clean_limit,
            persist=persist,
        )
        counts, remembered_items = self._canonical_inventory(
            user_id=clean_user_id,
            agent_id=clean_agent_id,
            project_id=clean_project_id,
            limit=clean_limit,
        )
        local_files = self._local_file_health(clean_agent_id)
        private_graph = self._graph_counts(self._private_graph_path(clean_agent_id))
        global_graph = self._graph_counts(self.graph_db_path)
        retrieval_health = retrieval.get("retrieval_health") or {}
        graph_projection = retrieval_health.get("graph_memory") or {}

        canonical_total = sum(
            int(counts[key])
            for key in ("profile_facts", "project_memories", "agent_memories")
        )
        degraded: list[dict[str, str]] = []
        if str(graph_projection.get("status") or "") in {"degraded", "unavailable", "error"}:
            degraded.append(
                {
                    "channel": "approved_graph_projection",
                    "reason": str(graph_projection.get("reason") or "graph projection retrieval is unavailable")[:500],
                    "impact": "Graph-assisted recall is unavailable; canonical 3021 memory remains available.",
                }
            )
        if local_files["status"] in {"missing", "degraded"}:
            degraded.append(
                {
                    "channel": "local_markdown",
                    "reason": str(local_files.get("reason") or "local Markdown memory is unavailable")[:500],
                    "impact": "Only the auxiliary file channel is affected.",
                }
            )
        if private_graph.get("status") == "ready" and int(private_graph.get("nodes") or 0) == 0:
            degraded.append(
                {
                    "channel": "native_private_graph",
                    "reason": f"{clean_agent_id} private graph has no extracted nodes",
                    "impact": "This does not mean canonical memory is empty.",
                }
            )

        return {
            "schema_version": "memory-introspection.v1",
            "status": "ready" if canonical_total or counts["profile"] else "empty",
            "authority": {
                "system": "3021-unified-memory",
                "source_of_truth": self.context_service.db_path,
                "rule": "Canonical counts and remembered items come from the user-scoped 3021 store; auxiliary channels cannot negate them.",
            },
            "scope": {
                "agent_id": clean_agent_id,
                "project_id": clean_project_id or None,
                "user_scoped": True,
            },
            "counts": counts,
            "remembered_items": remembered_items,
            "retrieval": {
                "pack_id": retrieval.get("id") or None,
                "status": retrieval.get("status"),
                "summary": retrieval.get("summary"),
                "decision": retrieval.get("retrieval_decision") or {},
                "items": retrieval.get("items") or [],
                "citations": retrieval.get("citations") or [],
            },
            "channels": {
                "local_markdown": local_files,
                "openclaw_lexical_index": retrieval_health.get("agent_memory") or {},
                "approved_graph_projection": graph_projection,
                "native_private_graph": {
                    **private_graph,
                    "scope": f"agent:{clean_agent_id}",
                    "authoritative": False,
                },
                "native_global_graph": {
                    **global_graph,
                    "scope": "global-isolated",
                    "authoritative": False,
                    "content_access": "not_used",
                },
            },
            "degraded_channels": degraded,
            "interpretation": {
                "fixed_layer_count": False,
                "private_graph_empty_means_system_empty": False,
                "sandbox_error_means_file_missing": False,
                "guidance": [
                    "Answer memory questions from remembered_items and retrieval citations first.",
                    "Report each auxiliary channel separately with its scope and health.",
                    "Never infer that 3021 memory is empty from gm_stats, a missing daily file, or a sandbox error.",
                ],
            },
        }

    def _canonical_inventory(
        self,
        *,
        user_id: str,
        agent_id: str,
        project_id: str,
        limit: int,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        with self.context_service.connect() as conn:
            profile = conn.execute(
                "SELECT id, summary FROM user_context_profiles WHERE user_id=? AND status='active'",
                (user_id,),
            ).fetchone()
            profile_id = str(profile["id"]) if profile else ""
            facts = conn.execute(
                f"""
                SELECT id, fact_key, fact_value, importance, confidence, source_ref, updated_at
                FROM profile_facts
                WHERE profile_id=? AND status='active'
                ORDER BY {IMPORTANCE_ORDER}, updated_at DESC
                LIMIT ?
                """,
                (profile_id, limit),
            ).fetchall() if profile_id else []
            fact_count = conn.execute(
                "SELECT COUNT(*) AS count FROM profile_facts WHERE profile_id=? AND status='active'",
                (profile_id,),
            ).fetchone()["count"] if profile_id else 0
            project_where = "AND project_id=?" if project_id else ""
            project_args: tuple[Any, ...] = (user_id, project_id, limit) if project_id else (user_id, limit)
            projects = conn.execute(
                f"""
                SELECT id, project_id, memory_key, title, content, importance, confidence,
                       source_ref, updated_at
                FROM project_context_memories
                WHERE user_id=? AND status='active' {project_where}
                ORDER BY {IMPORTANCE_ORDER}, updated_at DESC
                LIMIT ?
                """,
                project_args,
            ).fetchall()
            project_count_args: tuple[Any, ...] = (user_id, project_id) if project_id else (user_id,)
            project_count = conn.execute(
                f"""
                SELECT COUNT(*) AS count FROM project_context_memories
                WHERE user_id=? AND status='active' {project_where}
                """,
                project_count_args,
            ).fetchone()["count"]
            agent_project_where = "AND (project_id='' OR project_id=?)" if project_id else ""
            agent_args: tuple[Any, ...] = (
                (user_id, agent_id, project_id, limit)
                if project_id
                else (user_id, agent_id, limit)
            )
            agents = conn.execute(
                f"""
                SELECT id, project_id, memory_key, memory_type, title, content, source,
                       updated_at, metadata
                FROM agent_memories
                WHERE user_id=? AND agent_id=? AND status='active'
                  AND source LIKE 'mission:%' {agent_project_where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                agent_args,
            ).fetchall()
            agent_count_args: tuple[Any, ...] = (
                (user_id, agent_id, project_id)
                if project_id
                else (user_id, agent_id)
            )
            agent_count = conn.execute(
                f"""
                SELECT COUNT(*) AS count FROM agent_memories
                WHERE user_id=? AND agent_id=? AND status='active'
                  AND source LIKE 'mission:%' {agent_project_where}
                """,
                agent_count_args,
            ).fetchone()["count"]
            pack_count = conn.execute(
                "SELECT COUNT(*) AS count FROM context_packs WHERE user_id=?",
                (user_id,),
            ).fetchone()["count"]

        items: list[dict[str, Any]] = []
        for row in facts:
            items.append(
                {
                    "scope": "profile",
                    "title": row["fact_key"],
                    "content": row["fact_value"],
                    "importance": row["importance"],
                    "confidence": row["confidence"],
                    "source_ref": row["source_ref"] or f"fact:{row['id']}",
                    "updated_at": row["updated_at"],
                }
            )
        for row in projects:
            items.append(
                {
                    "scope": "project",
                    "project_id": row["project_id"],
                    "title": row["title"],
                    "content": row["content"],
                    "importance": row["importance"],
                    "confidence": row["confidence"],
                    "source_ref": row["source_ref"] or f"project-memory:{row['id']}",
                    "updated_at": row["updated_at"],
                }
            )
        for row in agents:
            metadata = self._json_object(row["metadata"])
            items.append(
                {
                    "scope": "agent",
                    "project_id": row["project_id"] or None,
                    "title": row["title"] or row["memory_key"] or row["memory_type"],
                    "content": row["content"],
                    "importance": metadata.get("importance") or "normal",
                    "confidence": metadata.get("confidence") or 0.8,
                    "source_ref": row["source"] or f"agent-memory:{row['id']}",
                    "updated_at": row["updated_at"],
                }
            )
        items.sort(
            key=lambda item: (
                {"critical": 0, "high": 1, "normal": 2, "low": 3}.get(str(item.get("importance")), 4),
                str(item.get("updated_at") or ""),
            )
        )
        counts = {
            "profile": 1 if profile else 0,
            "profile_facts": int(fact_count),
            "project_memories": int(project_count),
            "agent_memories": int(agent_count),
            "context_packs": int(pack_count),
        }
        return counts, items[:limit]

    def _local_file_health(self, agent_id: str) -> dict[str, Any]:
        workspace = self.context_service.workspace_root / agent_id / "workspace"
        try:
            if not workspace.exists():
                return {"status": "missing", "files": 0, "reason": "agent workspace does not exist"}
            candidates = [workspace / "MEMORY.md"]
            memory_dir = workspace / "memory"
            if memory_dir.exists():
                candidates.extend(path for path in memory_dir.rglob("*.md") if path.is_file())
            existing = [path for path in candidates if path.is_file()]
            newest = max((path.stat().st_mtime for path in existing), default=None)
            return {
                "status": "ready" if existing else "missing",
                "files": len(existing),
                "newest_mtime": newest,
                "reason": "" if existing else "no readable Markdown memory files",
            }
        except OSError as exc:
            return {
                "status": "degraded",
                "files": 0,
                "reason": f"workspace access failed: {exc}",
            }

    def _private_graph_path(self, agent_id: str) -> Path:
        return Path(f"{self.graph_db_path}.agents") / f"{agent_id}.sqlite"

    @staticmethod
    def _graph_counts(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"status": "missing", "nodes": 0, "edges": 0, "messages": 0}
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
            try:
                tables = {
                    row[0]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                def count(table: str) -> int:
                    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if table in tables else 0
                return {
                    "status": "ready",
                    "nodes": count("gm_nodes"),
                    "edges": count("gm_edges"),
                    "messages": count("gm_messages"),
                }
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return {"status": "degraded", "nodes": 0, "edges": 0, "messages": 0, "reason": str(exc)[:300]}

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}
