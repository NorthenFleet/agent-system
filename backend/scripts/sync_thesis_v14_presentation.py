"""Install the verified v14 defense deck and its generic document-structure binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_manager import project_manager
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service


DEFAULT_PROJECT_ID = "proj-10fbeefae5"
DEFAULT_PRESENTATION_DOCUMENT_ID = "doc-8729ccf99985"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read mapping contract: {path}") from exc
    if not isinstance(mapping, dict) or not isinstance(mapping.get("slides"), list):
        raise RuntimeError("Mapping contract is missing slides")
    return mapping


def backup_current_state(
    project: dict[str, Any],
    presentation_document_id: str,
    backup_root: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_root / f"thesis-v14-ppt-sync-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    workspace_root = multi_document_service._project_root(project)  # noqa: SLF001
    documents_index = workspace_root / "documents.json"
    if documents_index.exists():
        shutil.copy2(documents_index, target / "documents.json")
    presentation_root = multi_document_service._document_root(  # noqa: SLF001
        project, presentation_document_id
    )
    current = presentation_root / "working" / "presentation.pptx"
    if current.exists():
        shutil.copy2(current, target / "presentation-before-sync.pptx")
    manifest = presentation_root / "source" / "presentation-manifest.json"
    if manifest.exists():
        shutil.copy2(manifest, target / "presentation-manifest-before-sync.json")
    project_manifest = workspace_root / "manifest.json"
    if project_manifest.exists():
        shutil.copy2(project_manifest, target / "workspace-manifest.json")
    return target


def sync(
    *,
    project_id: str,
    presentation_document_id: str,
    presentation_path: Path,
    mapping_path: Path,
    backup_root: Path,
) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"Project not found: {project_id}")
    if not presentation_path.is_file():
        raise RuntimeError(f"Presentation not found: {presentation_path}")
    mapping = load_mapping(mapping_path)
    authority = mapping.get("authority") if isinstance(mapping.get("authority"), dict) else {}
    output = (
        authority.get("presentation_output")
        if isinstance(authority.get("presentation_output"), dict)
        else {}
    )
    expected_ppt_sha = str(output.get("sha256") or "").lower()
    actual_ppt_sha = sha256(presentation_path)
    if expected_ppt_sha != actual_ppt_sha:
        raise RuntimeError(
            f"Presentation SHA-256 mismatch: expected {expected_ppt_sha}, got {actual_ppt_sha}"
        )
    slides = mapping["slides"]
    if len(slides) != 53:
        raise RuntimeError(f"Expected 53 mapped slides, got {len(slides)}")
    if int(output.get("main_slide_count") or 0) != 45:
        raise RuntimeError("Expected 45 main defense slides")
    if int(output.get("appendix_slide_count") or 0) != 8:
        raise RuntimeError("Expected 8 appendix slides")
    if int(output.get("notes_count") or 0) != 53:
        raise RuntimeError("Expected 53 speaker notes")

    collection = multi_document_service.list_documents(project)
    presentation = next(
        (
            row
            for row in collection["documents"]
            if row.get("id") == presentation_document_id
        ),
        None,
    )
    if not presentation or presentation.get("kind") != "presentation":
        raise RuntimeError("Target presentation document is missing")

    binding = mapping.get("structure_binding")
    if not isinstance(binding, dict):
        raise RuntimeError("Mapping contract is missing structure_binding")
    source_document_id = str(binding.get("source_document_id") or "")
    source = next(
        (
            row
            for row in collection["documents"]
            if row.get("id") == source_document_id
        ),
        None,
    )
    if not source or source.get("kind") != "rich_text":
        raise RuntimeError("Canonical source document is missing")
    if str(binding.get("source_sha256") or "").lower() != str(
        source.get("source_checksum") or ""
    ).lower():
        raise RuntimeError("Canonical source document SHA-256 does not match v14 contract")

    backup_path = backup_current_state(
        project, presentation_document_id, backup_root
    )
    current_path = multi_document_service.source_file(
        project, presentation_document_id
    )
    if sha256(current_path) != actual_ppt_sha:
        multi_document_service.replace_content(
            project,
            presentation_document_id,
            presentation_path.read_bytes(),
            str(presentation_path),
            "thesis-v14-ppt-linkage",
        )

    multi_document_service.update_document(
        project,
        presentation_document_id,
        {
            "title": "博士毕业答辩",
            "is_output_product": True,
            "output_format": "pptx",
            "publication_status": "draft",
            "print_profile": "widescreen_16_9",
            "rules_version": "结构v14",
            "data_version": "文档v3",
            "expected_chapters": 7,
        },
    )
    evaluated_binding = multi_document_service.set_structure_binding(
        project,
        presentation_document_id,
        binding,
        mapping,
    )
    if evaluated_binding.get("status") != "aligned":
        raise RuntimeError(
            f"Structure binding did not align: {evaluated_binding.get('status')}"
        )
    document = multi_document_service.get_document(
        project, presentation_document_id
    )
    return {
        "status": "completed",
        "backup_path": str(backup_path),
        "project_id": project_id,
        "document": document,
        "structure_binding": evaluated_binding,
        "presentation_sha256": actual_ppt_sha,
        "slide_count": len(slides),
        "main_slide_count": int(output.get("main_slide_count") or 0),
        "appendix_slide_count": int(output.get("appendix_slide_count") or 0),
        "notes_count": int(output.get("notes_count") or 0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument(
        "--presentation-document-id",
        default=DEFAULT_PRESENTATION_DOCUMENT_ID,
    )
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        result = sync(
            project_id=arguments.project_id,
            presentation_document_id=arguments.presentation_document_id,
            presentation_path=arguments.presentation.resolve(),
            mapping_path=arguments.mapping.resolve(),
            backup_root=arguments.backup_root.resolve(),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (DocumentWorkspaceError, RuntimeError) as exc:
        raise SystemExit(f"Sync failed: {exc}") from exc
