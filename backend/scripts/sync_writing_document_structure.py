"""Synchronize a rich-text document's stored projection with its current Markdown."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from project_manager import project_manager
from services.document_outline_service import build_document_structure_snapshot
from services.document_workspace_service import document_workspace_service
from services.multi_document_service import multi_document_service


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_versioned_artifact(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise RuntimeError(f"交付文件不存在：{source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256(source) != _sha256(destination):
            raise RuntimeError(f"版本化目标已存在但内容不同，停止覆盖：{destination}")
        return destination
    shutil.copy2(source, destination)
    return destination


def _snapshot_current_state(
    project: dict[str, Any],
    document: dict[str, Any],
) -> Path:
    root = document_workspace_service._workspace_root(project)  # noqa: SLF001
    snapshot = root / "snapshots" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-before-structure-sync"
    )
    snapshot.mkdir(parents=True, exist_ok=False)
    (snapshot / "project.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for source in (root / "manifest.json", root / "documents.json"):
        if source.exists():
            shutil.copy2(source, snapshot / source.name)
    manifest = document_workspace_service.ensure_workspace(
        multi_document_service._rich_project(project, document)  # noqa: SLF001
    )
    for source, name in (
        (Path(str(manifest.get("working_markdown") or "")), "working-before-sync.md"),
        (Path(str(manifest.get("source_markdown") or "")), "source-before-sync.md"),
    ):
        if source.is_file():
            shutil.copy2(source, snapshot / name)
    return snapshot


def _planned_workspace(
    project: dict[str, Any],
    document: dict[str, Any],
    workspace: dict[str, Any],
    markdown_input: Path | None,
    target_version: int,
) -> tuple[dict[str, Any], str | None]:
    if markdown_input is None:
        return workspace, None
    if not markdown_input.is_file():
        raise RuntimeError(f"Markdown正文不存在：{markdown_input}")
    try:
        markdown = markdown_input.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Markdown正文必须使用UTF-8编码") from exc
    if not markdown.strip():
        raise RuntimeError("Markdown正文不能为空")
    current_version = int(workspace["manifest"]["version"])
    planned_version = target_version or current_version + 1
    sections = document_workspace_service._parse_sections(markdown)  # noqa: SLF001
    stats = document_workspace_service._stats(markdown, sections)  # noqa: SLF001
    source_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    current_sha256 = str(
        workspace.get("current_structure", {}).get("source_sha256") or ""
    ).lower()
    if (
        planned_version == current_version
        and source_sha256 == current_sha256
    ):
        return workspace, None
    if planned_version <= current_version:
        raise RuntimeError(
            f"目标正文版本必须高于当前版本 v{current_version}"
        )
    planned = copy.deepcopy(workspace)
    planned["manifest"]["version"] = planned_version
    planned["stats"] = stats
    planned["sections"] = [
        {key: value for key, value in row.items() if key != "content"}
        for row in sections
    ]
    planned["current_structure"] = build_document_structure_snapshot(
        sections,
        document_title=str(
            document.get("title") or project.get("name") or "正文文档"
        ),
        version=planned_version,
        source_path=str(markdown_input),
        source_sha256=source_sha256,
        generated_at=_now(),
    )
    return planned, markdown


def _chapter_records(
    project: dict[str, Any],
    workspace: dict[str, Any],
) -> list[dict[str, Any]]:
    existing = (
        project.get("document_spec", {}).get("chapters")
        if isinstance(project.get("document_spec"), dict)
        else []
    )
    existing = existing if isinstance(existing, list) else []
    sections = {
        str(section.get("title") or ""): section
        for section in workspace.get("sections") or []
        if str(section.get("kind") or "") == "chapter"
    }
    records = []
    for index, chapter in enumerate(workspace["current_structure"]["chapters"]):
        section = sections.get(str(chapter.get("title") or ""), {})
        previous = existing[index] if index < len(existing) and isinstance(existing[index], dict) else {}
        outline = chapter.get("outline") or []
        records.append(
            {
                "id": previous.get("id") or f"target-chapter-{index + 1:02d}",
                "project_id": project.get("id"),
                "parent_id": "",
                "title": chapter.get("title") or "",
                "summary": section.get("summary") or "",
                "main_content": (
                    f"{workspace['current_structure']['version']}当前正文共"
                    f"{len(outline)}个节项，{int(section.get('word_count') or 0)}字符。"
                ),
                "key_points": [],
                "outline_items": [
                    str(item.get("title") or "") for item in outline
                ],
                "subsections": [],
                "required_assets": [],
                "images": [],
                "status": "current",
                "assigned_agent": "",
                "order_index": index,
            }
        )
    return records


def _resolve_document(
    project: dict[str, Any],
    requested_document_id: str,
) -> dict[str, Any]:
    documents = multi_document_service.list_documents(project, include_archived=True)[
        "documents"
    ]
    if requested_document_id:
        document = next(
            (row for row in documents if row.get("id") == requested_document_id),
            None,
        )
    else:
        document = next(
            (
                row
                for row in documents
                if row.get("kind") == "rich_text" and row.get("is_primary")
            ),
            None,
        )
    if not document:
        raise RuntimeError("未找到需要同步的正文文档")
    if document.get("kind") != "rich_text":
        raise RuntimeError("结构同步仅支持rich_text正文文档")
    return document


def synchronize(args: argparse.Namespace) -> dict[str, Any]:
    project = project_manager.get_project(args.project_id)
    if not project:
        raise RuntimeError(f"项目不存在：{args.project_id}")
    document = _resolve_document(project, args.document_id)
    workspace = multi_document_service.rich_workspace(project, document["id"])
    markdown_input = (
        Path(args.markdown_input).expanduser().resolve()
        if args.markdown_input
        else None
    )
    workspace, planned_markdown = _planned_workspace(
        project,
        document,
        workspace,
        markdown_input,
        int(args.target_version or 0),
    )
    snapshot: Path | None = None
    if args.apply:
        snapshot = _snapshot_current_state(project, document)
        if planned_markdown is not None:
            multi_document_service.replace_rich_text_markdown(
                project,
                document["id"],
                planned_markdown,
                str(args.actor or "verified-rich-text-structure-sync"),
                target_version=int(workspace["manifest"]["version"]),
            )
            project = project_manager.get_project(args.project_id)
            document = _resolve_document(project, document["id"])
            workspace = multi_document_service.rich_workspace(
                project, document["id"]
            )
    version = int(workspace["manifest"]["version"])
    manifest = document_workspace_service.ensure_workspace(
        multi_document_service._rich_project(project, document)  # noqa: SLF001
    )
    working_path = Path(manifest["working_markdown"])
    source_path = Path(manifest["source_markdown"])
    content_sha256 = (
        hashlib.sha256(planned_markdown.encode("utf-8")).hexdigest()
        if planned_markdown is not None and not args.apply
        else _sha256(working_path)
    )

    artifact_directory = Path(args.artifact_directory).expanduser().resolve()
    source_word_input = Path(args.source_word_input).expanduser().resolve()
    preview_pdf_input = Path(args.preview_pdf_input).expanduser().resolve()
    source_word_target = artifact_directory / args.source_word_name
    preview_pdf_target = artifact_directory / args.preview_pdf_name

    target_structure = copy.deepcopy(workspace["current_structure"])
    target_structure["title"] = (
        args.target_title
        or f"{document.get('title') or project.get('name') or '正文文档'}目标结构"
    )
    target_structure["version"] = f"v{version}"
    target_structure["role"] = "current_target_baseline"

    spec = copy.deepcopy(project.get("document_spec") or {})
    spec.update(
        {
            "outline": [
                str(chapter.get("title") or "")
                for chapter in target_structure["chapters"]
            ],
            "chapters": _chapter_records(project, workspace),
            "target_structure": target_structure,
            "expected_chapters": int(target_structure["chapter_count"]),
            "source_word": {
                "path": str(source_word_target),
                "format": "docx",
                "edition": str(
                    spec.get("current_edition_label")
                    or workspace["manifest"].get("edition")
                    or ""
                ),
                "role": "current_delivery_source",
                "sha256": _sha256(source_word_input),
            },
            "working_markdown": {
                **(
                    spec.get("working_markdown")
                    if isinstance(spec.get("working_markdown"), dict)
                    else {}
                ),
                "path": str(source_path),
                "format": "markdown",
                "edition": str(
                    spec.get("current_edition_label")
                    or workspace["manifest"].get("edition")
                    or ""
                ),
                "chapter_count": int(target_structure["chapter_count"]),
                "sync_status": "connected",
                "role": "current_workdraft",
                "sha256": content_sha256,
            },
            "sync_status": {
                **(
                    spec.get("sync_status")
                    if isinstance(spec.get("sync_status"), dict)
                    else {}
                ),
                "state": "aligned",
                "message": (
                    f"当前正文、目标目录和交付文件已同步至v{version}。"
                ),
                "version": version,
                "source_sha256": content_sha256,
                "source_word": str(source_word_target),
                "source_word_sha256": _sha256(source_word_input),
                "preview_pdf": str(preview_pdf_target),
                "preview_pdf_sha256": _sha256(preview_pdf_input),
                "updated_at": _now(),
            },
            "updated_at": _now(),
        }
    )

    result = {
        "project_id": project.get("id"),
        "document_id": document.get("id"),
        "version": version,
        "publication_status": args.publication_status,
        "working_markdown": str(working_path),
        "working_markdown_sha256": content_sha256,
        "source_word": str(source_word_target),
        "source_word_sha256": _sha256(source_word_input),
        "preview_pdf": str(preview_pdf_target),
        "preview_pdf_sha256": _sha256(preview_pdf_input),
        "target_structure": target_structure,
        "apply": bool(args.apply),
    }
    if not args.apply:
        return result

    _copy_versioned_artifact(source_word_input, source_word_target)
    _copy_versioned_artifact(preview_pdf_input, preview_pdf_target)
    updated_project = project_manager.update_project(
        args.project_id,
        {"document_spec": spec},
    )
    if not updated_project:
        raise RuntimeError("项目结构元数据更新失败")

    with multi_document_service._lock_path(updated_project).open(  # noqa: SLF001
        "w",
        encoding="utf-8",
    ) as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        index = multi_document_service._read_index(updated_project)  # noqa: SLF001
        record = next(
            (
                row
                for row in index.get("documents") or []
                if row.get("id") == document["id"]
            ),
            None,
        )
        if not record:
            raise RuntimeError("项目文档索引中的正文记录不存在")
        metadata = (
            record.get("metadata")
            if isinstance(record.get("metadata"), dict)
            else {}
        )
        metadata.update(
            {
                "artifact_version": version,
                "structure_sync": "aligned",
                "structure_binding": {
                    "mode": "canonical",
                    "source_document_id": str(document["id"]),
                    "source_version": f"v{version}",
                    "source_sha256": content_sha256,
                    "status": "aligned",
                    "mapped_items": int(target_structure["heading_count"]),
                    "unmapped_items": [],
                    "changed_sections": [],
                },
                "source_word": str(source_word_target),
                "source_word_sha256": _sha256(source_word_target),
                "preview_pdf": str(preview_pdf_target),
                "preview_pdf_sha256": _sha256(preview_pdf_target),
            }
        )
        record.update(
            {
                "revision": version,
                "metadata": metadata,
                "publication_status": args.publication_status,
                "output_format": "docx",
                "print_profile": "standard_a4",
                "data_version": f"v{version}",
                "expected_chapters": int(target_structure["chapter_count"]),
                "source_checksum": content_sha256,
                "updated_at": _now(),
            }
        )
        multi_document_service._write_index(updated_project, index)  # noqa: SLF001

    refreshed_project = project_manager.get_project(args.project_id)
    refreshed_workspace = multi_document_service.rich_workspace(
        refreshed_project,
        document["id"],
    )
    after_sha256 = _sha256(working_path)
    if after_sha256 != content_sha256:
        raise RuntimeError("结构同步意外修改了Markdown正文")
    if refreshed_workspace["structure_sync"]["status"] != "aligned":
        raise RuntimeError("同步后当前结构与目标目录仍不一致")
    result.update(
        {
            "snapshot": str(snapshot or ""),
            "structure_sync": refreshed_workspace["structure_sync"],
            "working_markdown_unchanged": True,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--document-id", default="")
    parser.add_argument("--artifact-directory", required=True)
    parser.add_argument("--source-word-input", required=True)
    parser.add_argument("--preview-pdf-input", required=True)
    parser.add_argument("--source-word-name", required=True)
    parser.add_argument("--preview-pdf-name", required=True)
    parser.add_argument("--markdown-input", default="")
    parser.add_argument("--target-version", type=int, default=0)
    parser.add_argument("--actor", default="verified-rich-text-structure-sync")
    parser.add_argument("--target-title", default="")
    parser.add_argument(
        "--publication-status",
        choices=["draft", "review", "approved", "published"],
        default="draft",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(synchronize(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
