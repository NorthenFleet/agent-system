#!/usr/bin/env python3
"""Idempotently backfill already-published memory candidates into graph-memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.graph_memory_client import GraphMemoryClient, graph_memory_client  # noqa: E402
from services.memory_vector_service import candidate_vector_document  # noqa: E402
from unified_data_manager import UNIFIED_DB_PATH  # noqa: E402


def _loads(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def projection_payload(row: sqlite3.Row) -> dict[str, Any]:
    published_ref = str(row["published_ref"] or "").strip()
    target_scope = str(row["target_scope"])
    aggregate_type = {
        "profile": "profile_fact",
        "project": "project_memory",
        "agent": "agent_memory",
    }[target_scope]
    row_dict = dict(row)
    row_dict["evidence_refs"] = list(_loads(row["evidence_refs"], []))
    document = candidate_vector_document(
        row_dict,
        published_ref,
        now=str(row["published_at"] or row["updated_at"] or ""),
    )
    digest = hashlib.sha256(
        (
            "approved-projection.v2\n"
            f"{published_ref}\n{target_scope}\n{document.agent_id}\n{document.content_hash}"
        ).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "event_id": f"graph-backfill-{digest}",
        "event_type": "memory.published",
        "aggregate_type": aggregate_type,
        "aggregate_id": published_ref.split(":", 1)[-1],
        "source_ref": published_ref,
        "user_id": str(row["user_id"]),
        "project_id": document.project_id,
        "agent_id": document.agent_id,
        "memory_key": str(row["memory_key"]),
        "memory_type": str(row["memory_type"]),
        "version": int(row["plan_version"] or 0),
        "supersedes_ref": None,
        "title": document.title,
        "content": document.content,
        "content_hash": document.content_hash,
        "importance": str(row["importance"]),
        "confidence": float(row["confidence"]),
        "visibility": target_scope,
        "status": "active",
        "evidence_refs": list(_loads(row["evidence_refs"], [])),
        "mission_id": str(row["mission_id"] or ""),
        "published_at": str(row["published_at"] or row["updated_at"] or ""),
    }


def backfill(
    *,
    db_path: str,
    client: GraphMemoryClient = graph_memory_client,
    user_id: str = "",
    limit: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where = "status='published' AND published_ref IS NOT NULL AND published_ref!=''"
        args: list[Any] = []
        if user_id:
            where += " AND user_id=?"
            args.append(user_id)
        args.append(max(1, min(int(limit), 5000)))
        rows = conn.execute(
            f"SELECT * FROM memory_candidates WHERE {where} ORDER BY published_at, id LIMIT ?",
            args,
        ).fetchall()
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for row in rows:
        payload = projection_payload(row)
        if dry_run:
            results.append({"source_ref": payload["source_ref"], "status": "dry_run"})
            continue
        try:
            outcome = client.upsert_projection(payload)
            results.append({"source_ref": payload["source_ref"], **outcome})
        except Exception as exc:
            failures.append({"source_ref": payload["source_ref"], "error": str(exc)[:500]})
    return {
        "scanned": len(rows),
        "projected": len(results),
        "failed": len(failures),
        "results": results,
        "failures": failures,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=UNIFIED_DB_PATH)
    parser.add_argument("--user-id", default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = backfill(
        db_path=args.db_path,
        user_id=args.user_id,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
