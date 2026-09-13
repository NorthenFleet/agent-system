#!/usr/bin/env python3
"""Generate non-published candidate DOCX/PDF files from registered Word templates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from services.document_layout_service import document_layout_service  # noqa: E402
from services.document_workspace_service import DocumentWorkspaceError, document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402

COURSE_PROJECT_ID = "proj-16ca49b862"
DEFAULT_DOCUMENT_IDS = ("doc-e811bedd87f9", "doc-3a9dbb65b9a3")


def generate(project_id: str, document_ids: tuple[str, ...]) -> list[dict[str, object]]:
    project = project_manager.get_project(project_id)
    if not project:
        raise DocumentWorkspaceError("课程项目不存在")
    rows: list[dict[str, object]] = []
    for document_id in document_ids:
        context = multi_document_service.rich_project_context(project, document_id)
        binding = context.get("_document_layout_binding") or {}
        if not binding.get("profile_id") or "-layout-" not in str(binding.get("delivery_basename") or ""):
            raise DocumentWorkspaceError(f"{document_id} 缺少安全的候选交付命名，拒绝覆盖历史 Word")
        docx_path = document_workspace_service.export(context, "docx")
        pdf_path = document_workspace_service.export(context, "pdf")
        if docx_path.suffix.lower() != ".docx" or pdf_path.suffix.lower() != ".pdf":
            raise DocumentWorkspaceError("候选交付文件类型异常")
        updated_binding = document_layout_service.delivery_patch(context, docx_path, pdf_path)
        multi_document_service.update_document_metadata(project, document_id, {"layout_binding": updated_binding})
        rows.append({
            "document_id": document_id,
            "profile_id": binding["profile_id"],
            "docx": str(docx_path),
            "pdf": str(pdf_path),
            "audit_score": updated_binding["latest_delivery"]["audit_score"],
            "audit_status": document_layout_service.audit_document(context, docx_path, pdf_path)["status"],
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=COURSE_PROJECT_ID)
    parser.add_argument("--document-id", action="append", dest="document_ids")
    args = parser.parse_args()
    document_ids = tuple(args.document_ids or DEFAULT_DOCUMENT_IDS)
    print(json.dumps(generate(args.project_id, document_ids), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
