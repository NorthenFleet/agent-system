"""Install a verified presentation and bind it to its canonical rich-text source."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from project_manager import project_manager
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取PPT联动合同：{path}") from exc
    if not isinstance(mapping, dict) or not isinstance(mapping.get("slides"), list):
        raise RuntimeError("PPT联动合同缺少slides数组")
    return mapping


def _pptx_counts(path: Path) -> tuple[int, int]:
    slide_pattern = re.compile(r"^ppt/slides/slide\d+\.xml$")
    notes_pattern = re.compile(r"^ppt/notesSlides/notesSlide\d+\.xml$")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"PPTX文件损坏：{path}") from exc
    return (
        sum(bool(slide_pattern.match(name)) for name in names),
        sum(bool(notes_pattern.match(name)) for name in names),
    )


def _validate_preview_pdf(
    path: Path,
    preview_contract: dict[str, Any],
    presentation_sha256: str,
    slide_count: int,
) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"PPT静态预览不存在：{path}")
    with path.open("rb") as handle:
        header = handle.read(8)
        handle.seek(max(path.stat().st_size - 2048, 0))
        trailer = handle.read()
    if not header.startswith(b"%PDF-") or b"%%EOF" not in trailer:
        raise RuntimeError("PPT静态预览不是完整PDF文件")
    actual_sha256 = _sha256(path)
    expected_sha256 = str(preview_contract.get("sha256") or "").lower()
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"PPT静态预览SHA-256不一致：合同={expected_sha256}，实际={actual_sha256}"
        )
    source_sha256 = str(
        preview_contract.get("source_presentation_sha256") or ""
    ).lower()
    if source_sha256 and source_sha256 != presentation_sha256:
        raise RuntimeError("PPT静态预览绑定的PPT哈希与当前成品不一致")
    page_count = int(preview_contract.get("page_count") or 0)
    if page_count and page_count != slide_count:
        raise RuntimeError("PPT静态预览声明页数与PPT页数不一致")
    return {
        "sha256": actual_sha256,
        "page_count": page_count or slide_count,
        "size_bytes": path.stat().st_size,
    }


def _install_versioned_artifact(source: Path, target: Path) -> Path:
    """Copy a verified artifact without silently replacing another version."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if _sha256(target) != _sha256(source):
            raise RuntimeError(f"正式成品已存在且内容不同：{target}")
        return target
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)
    if _sha256(target) != _sha256(source):
        raise RuntimeError(f"正式成品复制校验失败：{target}")
    return target


def _backup_current_state(
    project: dict[str, Any],
    presentation_document_id: str,
    backup_root: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_root / f"presentation-binding-sync-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    workspace_root = multi_document_service._project_root(project)  # noqa: SLF001
    for source in (
        workspace_root / "documents.json",
        workspace_root / "manifest.json",
    ):
        if source.exists():
            shutil.copy2(source, target / source.name)
    presentation_root = multi_document_service._document_root(  # noqa: SLF001
        project, presentation_document_id
    )
    for source, name in (
        (
            presentation_root / "working" / "presentation.pptx",
            "presentation-before-sync.pptx",
        ),
        (
            presentation_root / "source" / "presentation-manifest.json",
            "presentation-manifest-before-sync.json",
        ),
        (
            presentation_root / "rendered" / "presentation.pdf",
            "presentation-preview-before-sync.pdf",
        ),
    ):
        if source.exists():
            shutil.copy2(source, target / name)
    return target


def synchronize(args: argparse.Namespace) -> dict[str, Any]:
    project = project_manager.get_project(args.project_id)
    if not project:
        raise RuntimeError(f"项目不存在：{args.project_id}")
    presentation_path = args.presentation.expanduser().resolve()
    mapping_path = args.mapping.expanduser().resolve()
    if not presentation_path.is_file():
        raise RuntimeError(f"PPT文件不存在：{presentation_path}")

    mapping = _load_mapping(mapping_path)
    authority = (
        mapping.get("authority")
        if isinstance(mapping.get("authority"), dict)
        else {}
    )
    output = (
        authority.get("presentation_output")
        if isinstance(authority.get("presentation_output"), dict)
        else {}
    )
    preview_contract = (
        authority.get("presentation_preview")
        if isinstance(authority.get("presentation_preview"), dict)
        else {}
    )
    binding = (
        mapping.get("structure_binding")
        if isinstance(mapping.get("structure_binding"), dict)
        else {}
    )
    expected_sha256 = str(output.get("sha256") or "").lower()
    actual_sha256 = _sha256(presentation_path)
    if not expected_sha256 or expected_sha256 != actual_sha256:
        raise RuntimeError(
            f"PPT SHA-256不一致：合同={expected_sha256 or '缺失'}，实际={actual_sha256}"
        )

    slide_count, notes_count = _pptx_counts(presentation_path)
    mapped_slides = mapping["slides"]
    expected_slide_count = int(output.get("slide_count") or len(mapped_slides))
    expected_notes_count = int(output.get("notes_count") or 0)
    if len(mapped_slides) != expected_slide_count:
        raise RuntimeError(
            f"逐页映射数量不一致：合同={len(mapped_slides)}，声明={expected_slide_count}"
        )
    if slide_count != expected_slide_count:
        raise RuntimeError(
            f"PPT页数不一致：实际={slide_count}，声明={expected_slide_count}"
        )
    if notes_count != expected_notes_count:
        raise RuntimeError(
            f"讲解稿页数不一致：实际={notes_count}，声明={expected_notes_count}"
        )
    main_slide_count = int(output.get("main_slide_count") or slide_count)
    appendix_slide_count = int(output.get("appendix_slide_count") or 0)
    if main_slide_count + appendix_slide_count != slide_count:
        raise RuntimeError("主答辩页数与附录页数之和不等于PPT总页数")
    preview_path = (
        args.preview_pdf.expanduser().resolve()
        if args.preview_pdf
        else None
    )
    if preview_contract and preview_path is None:
        raise RuntimeError("PPT合同声明了静态预览，但未提供--preview-pdf")
    preview_summary = (
        _validate_preview_pdf(
            preview_path,
            preview_contract,
            actual_sha256,
            slide_count,
        )
        if preview_path is not None
        else None
    )

    collection = multi_document_service.list_documents(
        project, include_archived=True
    )
    documents = collection["documents"]
    presentation = next(
        (
            row
            for row in documents
            if row.get("id") == args.presentation_document_id
        ),
        None,
    )
    if not presentation or presentation.get("kind") != "presentation":
        raise RuntimeError("目标PPT文档不存在")
    source_document_id = str(binding.get("source_document_id") or "")
    source = next(
        (row for row in documents if row.get("id") == source_document_id),
        None,
    )
    if not source or source.get("kind") != "rich_text":
        raise RuntimeError("PPT绑定的权威正文不存在")
    if str(binding.get("source_sha256") or "").lower() != str(
        source.get("source_checksum") or ""
    ).lower():
        raise RuntimeError("PPT合同中的正文哈希与当前权威正文不一致")

    result: dict[str, Any] = {
        "project_id": args.project_id,
        "presentation_document_id": args.presentation_document_id,
        "presentation_sha256": actual_sha256,
        "slide_count": slide_count,
        "main_slide_count": main_slide_count,
        "appendix_slide_count": appendix_slide_count,
        "notes_count": notes_count,
        "source_document_id": source_document_id,
        "source_version": str(binding.get("source_version") or ""),
        "preview": preview_summary,
        "apply": bool(args.apply),
    }
    if not args.apply:
        return result

    backup_path = _backup_current_state(
        project,
        args.presentation_document_id,
        args.backup_root.expanduser().resolve(),
    )
    installed_presentation = presentation_path
    installed_mapping = mapping_path
    installed_preview = preview_path
    if args.artifact_directory:
        artifact_directory = args.artifact_directory.expanduser().resolve()
        installed_presentation = _install_versioned_artifact(
            presentation_path,
            artifact_directory
            / (args.presentation_artifact_name or presentation_path.name),
        )
        installed_mapping = _install_versioned_artifact(
            mapping_path,
            artifact_directory / (args.mapping_artifact_name or mapping_path.name),
        )
        if preview_path is not None:
            installed_preview = _install_versioned_artifact(
                preview_path,
                artifact_directory
                / (args.preview_artifact_name or preview_path.name),
            )

    current_path = multi_document_service.source_file(
        project, args.presentation_document_id
    )
    if _sha256(current_path) != actual_sha256:
        multi_document_service.replace_content(
            project,
            args.presentation_document_id,
            installed_presentation.read_bytes(),
            str(installed_presentation),
            str(args.change_note or "verified-presentation-structure-sync"),
        )
    else:
        multi_document_service._update_record(  # noqa: SLF001
            project,
            args.presentation_document_id,
            {
                "source_path": str(installed_presentation),
                "source_checksum": actual_sha256,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    structure_version = str(
        output.get("structure_version")
        or binding.get("source_version")
        or ""
    )
    document_version = str(
        output.get("document_version")
        or f"v{int(presentation.get('revision') or 1) + 1}"
    )
    publication_status = str(
        output.get("publication_status")
        or mapping.get("publication_status")
        or "draft"
    )
    multi_document_service.update_document(
        project,
        args.presentation_document_id,
        {
            "title": args.title or presentation.get("title") or "演示文档",
            "is_output_product": True,
            "output_format": "pptx",
            "publication_status": publication_status,
            "print_profile": "widescreen_16_9",
            "rules_version": (
                structure_version
                if structure_version.startswith("结构")
                else f"结构{structure_version}"
            ),
            "data_version": (
                document_version
                if document_version.startswith("文档")
                else f"文档{document_version}"
            ),
            "expected_chapters": int(
                authority.get("thesis", {}).get("chapter_count") or 0
            ),
        },
    )
    evaluated_binding = multi_document_service.set_structure_binding(
        project,
        args.presentation_document_id,
        binding,
        mapping,
    )
    if evaluated_binding.get("status") != "aligned":
        raise RuntimeError(
            f"PPT结构绑定未对齐：{evaluated_binding.get('status')}"
        )
    if installed_preview is not None and preview_summary is not None:
        preview_target = multi_document_service._presentation_pdf_path(  # noqa: SLF001
            project,
            {"id": args.presentation_document_id},
        )
        preview_target.parent.mkdir(parents=True, exist_ok=True)
        temporary_preview = preview_target.with_suffix(".pdf.tmp")
        shutil.copy2(installed_preview, temporary_preview)
        temporary_preview.replace(preview_target)
        if _sha256(preview_target) != preview_summary["sha256"]:
            raise RuntimeError("PPT静态预览安装后哈希校验失败")
        index, raw_record = multi_document_service._get_record(  # noqa: SLF001
            project, args.presentation_document_id
        )
        metadata = (
            raw_record.get("metadata")
            if isinstance(raw_record.get("metadata"), dict)
            else {}
        )
        metadata["render"] = {
            "status": "completed",
            "source": "verified_static_pdf",
            "slide_count": slide_count,
            "page_count": preview_summary["page_count"],
            "size_bytes": preview_summary["size_bytes"],
            "sha256": preview_summary["sha256"],
        }
        metadata["preview_pdf_sha256"] = preview_summary["sha256"]
        raw_record["metadata"] = metadata
        multi_document_service._write_index(project, index)  # noqa: SLF001
    result.update(
        {
            "status": "completed",
            "backup_path": str(backup_path),
            "installed_presentation": str(installed_presentation),
            "installed_mapping": str(installed_mapping),
            "installed_preview": (
                str(installed_preview) if installed_preview is not None else ""
            ),
            "document": multi_document_service.get_document(
                project, args.presentation_document_id
            ),
            "structure_binding": evaluated_binding,
        }
    )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--presentation-document-id", required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--preview-pdf", type=Path)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--artifact-directory", type=Path)
    parser.add_argument("--presentation-artifact-name", default="")
    parser.add_argument("--mapping-artifact-name", default="")
    parser.add_argument("--preview-artifact-name", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--change-note", default="")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        print(
            json.dumps(
                synchronize(_parse_args()),
                ensure_ascii=False,
                indent=2,
            )
        )
    except (DocumentWorkspaceError, RuntimeError) as exc:
        raise SystemExit(f"同步失败：{exc}") from exc
