#!/usr/bin/env python3
"""Idempotently reconcile the course's document-to-current-PPT references.

This only updates binding metadata and the matching presentation manifests. It
never creates a document, rewrites a PPTX file, or changes publication state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from services.document_workspace_service import DocumentWorkspaceError  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402


COURSE_PROJECT_ID = "proj-16ca49b862"
EXPECTED_BINDINGS = {
    "doc-5b225b46318f": "doc-e811bedd87f9",
    "doc-67294b2100be": "doc-e6071aa369ed",
}


def reconcile(project_id: str, dry_run: bool) -> dict[str, object]:
    project = project_manager.get_project(project_id)
    if not project:
        raise DocumentWorkspaceError("课程项目不存在")

    collection = multi_document_service.list_documents(project)
    documents = {str(row.get("id") or ""): row for row in collection["documents"]}
    presentations = {
        document_id: row
        for document_id, row in documents.items()
        if row.get("kind") == "presentation"
    }
    if set(presentations) != set(EXPECTED_BINDINGS):
        raise DocumentWorkspaceError("课程 PPT 清单与受控基线不一致，已停止迁移")

    actions: list[dict[str, object]] = []
    for presentation_id, source_document_id in EXPECTED_BINDINGS.items():
        presentation = presentations[presentation_id]
        if source_document_id not in documents:
            raise DocumentWorkspaceError(f"PPT {presentation_id} 的来源文档不存在")
        raw_binding = (
            (presentation.get("metadata") or {}).get("structure_binding")
            if isinstance(presentation.get("metadata"), dict)
            else None
        )
        if not isinstance(raw_binding, dict):
            raise DocumentWorkspaceError(f"PPT {presentation_id} 缺少现有映射，已停止迁移")
        if str(raw_binding.get("source_document_id") or "") != source_document_id:
            raise DocumentWorkspaceError(f"PPT {presentation_id} 的来源绑定不符合受控基线")

        binding = multi_document_service.structure_binding(project, presentation_id)
        actions.append({
            "presentation_id": presentation_id,
            "source_document_id": source_document_id,
            "before": {
                "status": binding.get("status"),
                "integrity_status": binding.get("integrity_status"),
                "reference_status": binding.get("reference_status"),
                "ppt_sha256": binding.get("ppt_sha256"),
            },
        })
        if dry_run:
            continue

        updated = multi_document_service.set_structure_binding(
            project,
            presentation_id,
            raw_binding,
        )
        actions[-1]["after"] = {
            "status": updated.get("status"),
            "integrity_status": updated.get("integrity_status"),
            "reference_status": updated.get("reference_status"),
            "referenced_document_revision": updated.get("referenced_document_revision"),
            "ppt_sha256": updated.get("ppt_sha256"),
        }

    return {
        "project_id": project_id,
        "dry_run": dry_run,
        "presentations": len(presentations),
        "actions": actions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=COURSE_PROJECT_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconcile(args.project_id, args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
