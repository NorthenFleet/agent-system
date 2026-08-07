#!/usr/bin/env python3
"""Preflight and opt-in migration for structured writing authority."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from project_manager import project_manager  # noqa: E402
from services.document_workspace_service import DocumentWorkspaceError, document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.structured_document_service import structured_document_codec  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


VALIDATION_KEYS = (
    "heading_count",
    "table_count",
    "image_count",
    "citation_count",
    "plain_text_sha256",
)


def _documents(project: dict, requested_id: str) -> list[dict]:
    rows = multi_document_service.list_documents(project).get("documents", [])
    rows = [row for row in rows if row.get("kind") == "rich_text"]
    if requested_id:
        rows = [row for row in rows if row.get("id") == requested_id]
        if not rows:
            raise DocumentWorkspaceError("指定的正文文档不存在")
    return rows


def _preflight(project: dict, document: dict) -> dict:
    document_id = str(document["id"])
    context = multi_document_service.rich_project(project, document_id)
    source = document_workspace_service.fulltext(context)
    markdown = str(source.get("content") or "")
    structured = structured_document_codec.from_markdown(
        markdown,
        namespace=f"{project['id']}/{document_id}",
    )
    projected = structured_document_codec.to_markdown(structured)
    reparsed = structured_document_codec.from_markdown(
        projected,
        namespace=f"{project['id']}/{document_id}/roundtrip",
    )
    before = structured_document_codec.metrics(structured)
    after = structured_document_codec.metrics(reparsed)
    differences = {
        key: {"before": before[key], "after": after[key]}
        for key in VALIDATION_KEYS
        if before[key] != after[key]
    }
    return {
        "document_id": document_id,
        "title": document.get("title") or "",
        "source_revision": int(source.get("version") or 1),
        "source_chars": len(markdown),
        "projected_chars": len(projected),
        "metrics": before,
        "differences": differences,
        "ready": not differences and bool(projected.strip()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移文档为结构化人机双写权威")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--document-id", default="")
    parser.add_argument("--apply", action="store_true", help="通过预检后执行迁移；默认仅预检")
    args = parser.parse_args()

    project = project_manager.get_project(args.project_id)
    if not project:
        print(json.dumps({"error": "project_not_found"}, ensure_ascii=False))
        return 2
    results = []
    try:
        for document in _documents(project, args.document_id):
            result = _preflight(project, document)
            if args.apply and result["ready"]:
                state = writing_collaboration_service.ensure_state(project, result["document_id"])
                result.update({
                    "applied": True,
                    "structured_revision": state.document_revision,
                    "projection_status": state.projection_status,
                })
            else:
                result["applied"] = False
            results.append(result)
    except DocumentWorkspaceError as exc:
        print(json.dumps({"error": str(exc), "results": results}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps({
        "mode": "apply" if args.apply else "dry-run",
        "project_id": args.project_id,
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0 if all(row["ready"] for row in results) else 4


if __name__ == "__main__":
    raise SystemExit(main())
