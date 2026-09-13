#!/usr/bin/env python3
"""Audit every rich-text document and migrate only lossless candidates."""

from __future__ import annotations

import argparse
import json
from typing import Any

from project_manager import project_manager
from services.document_fidelity_service import document_fidelity_service
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service


def _documents(project: dict[str, Any]) -> list[dict[str, Any]]:
    listing = multi_document_service.list_documents(project)
    rows = listing.get("documents", []) if isinstance(listing, dict) else listing
    return [row for row in rows if row.get("kind") == "rich_text"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", action="append", default=[])
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--apply-safe", action="store_true")
    parser.add_argument("--actor", default="content-fidelity-migration")
    args = parser.parse_args()

    selected_projects = set(args.project_id)
    selected_documents = set(args.document_id)
    results: list[dict[str, Any]] = []
    for project in project_manager.list_projects():
        project_id = str(project.get("id") or "")
        if selected_projects and project_id not in selected_projects:
            continue
        for document in _documents(project):
            document_id = str(document.get("id") or "")
            if selected_documents and document_id not in selected_documents:
                continue
            try:
                report = document_fidelity_service._public(
                    document_fidelity_service.audit(project, document_id, persist=True)
                )
                action = "audited"
                if args.apply_safe and report.get("migration_safe") and report.get("status") == "stale":
                    report = document_fidelity_service.migrate(project, document_id, actor=args.actor)
                    action = "migrated"
                results.append({
                    "project_id": project_id,
                    "document_id": document_id,
                    "title": document.get("title"),
                    "action": action,
                    "status": report.get("status"),
                    "migration_safe": report.get("migration_safe"),
                    "source_metrics": report.get("source_metrics"),
                    "structured_metrics": report.get("structured_metrics"),
                })
            except (DocumentWorkspaceError, OSError, ValueError) as exc:
                results.append({
                    "project_id": project_id,
                    "document_id": document_id,
                    "title": document.get("title"),
                    "action": "blocked",
                    "status": "blocked",
                    "error": str(exc),
                })
    summary = {
        "mode": "apply-safe" if args.apply_safe else "audit-only",
        "documents": len(results),
        "migrated": sum(row["action"] == "migrated" for row in results),
        "blocked": sum(row["status"] == "blocked" for row in results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
