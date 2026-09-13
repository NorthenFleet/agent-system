#!/usr/bin/env python3
"""Register the course's existing Word files as explicit layout authorities.

Only reference-template copies and document metadata are updated.  It never
rewrites a document body, creates a delivery Word/PDF, or changes publication.
Documents without a current Word source are reported for manual upload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from services.document_layout_service import document_layout_service  # noqa: E402
from services.document_workspace_service import DocumentWorkspaceError  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402


COURSE_PROJECT_ID = "proj-16ca49b862"
COURSE_PLAN_ID = "doc-e811bedd87f9"
LESSON_REFERENCE_ID = "doc-3a9dbb65b9a3"
LESSON_PLAN_IDS = (
    LESSON_REFERENCE_ID, "doc-6085f649c11a", "doc-105f2073f3d9",
    "doc-9c47a19819ed", "doc-e542cf30905a", "doc-9df3ab46770c",
    "doc-60e4858f35af", "doc-8248d6366ec3", "doc-729fe58abb5a",
    "doc-dab8a79a74dc",
)
PENDING_REFERENCE_IDS = (
    "doc-2a28da7429f0",  # teaching schedule
    "doc-e6071aa369ed",  # practice guide
    "doc-f7ff5f8fe4f2",  # assessment
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_path(context: dict, document_id: str) -> Path:
    root = document_layout_service._root(context).parent  # document workspace root
    if document_id == COURSE_PLAN_ID:
        return root / "exports" / "水面舰艇作战软件与兵棋推演-课程教学计划-20学时-v14.docx"
    return root.parents[1] / "documents" / LESSON_REFERENCE_ID / "exports" / "第1讲-兵棋基础与-谋战-体系认识-v55.docx"


def register(project_id: str, dry_run: bool) -> dict[str, object]:
    project = project_manager.get_project(project_id)
    if not project:
        raise DocumentWorkspaceError("课程项目不存在")
    collection = multi_document_service.list_documents(project)
    documents = {str(row.get("id") or ""): row for row in collection.get("documents") or []}
    actions: list[dict[str, object]] = []

    for document_id in (COURSE_PLAN_ID, *LESSON_PLAN_IDS):
        if document_id not in documents:
            raise DocumentWorkspaceError(f"受控文档不存在：{document_id}")
        context = multi_document_service.rich_project_context(project, document_id)
        source = _source_path(context, document_id)
        if not source.is_file():
            raise DocumentWorkspaceError(f"当前 Word 参考不存在：{source}")
        action = {
            "document_id": document_id,
            "title": documents[document_id].get("title"),
            "source_word": str(source),
            "source_sha256": _sha256(source),
        }
        if not dry_run:
            profile = document_layout_service.register_reference_template(
                context,
                data=source.read_bytes(),
                filename=source.name,
                profile_name=f"{documents[document_id].get('title')}·当前 Word 模板",
            )
            binding = document_layout_service.binding_patch(context, profile_id=str(profile["id"]))
            multi_document_service.update_document_metadata(project, document_id, {"layout_binding": binding})
            action["profile_id"] = profile["id"]
            action["binding_status"] = binding["status"]
        actions.append(action)

    pending = []
    for document_id in PENDING_REFERENCE_IDS:
        row = documents.get(document_id)
        if row:
            pending.append({
                "document_id": document_id,
                "title": row.get("title"),
                "product_type": row.get("product_type"),
                "status": "reference_word_required",
            })
    return {"project_id": project_id, "dry_run": dry_run, "registered": actions, "pending_reference_word": pending}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=COURSE_PROJECT_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(register(args.project_id, args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
