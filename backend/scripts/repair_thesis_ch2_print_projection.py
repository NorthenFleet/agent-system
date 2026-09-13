"""Replace Chapter 2 SVG body projections with print-safe PNG assets.

Structured diagram documents remain the editable authority. The PNGs are only
the rich-text delivery projection used by Word/PDF exporters that cannot render
Office SVG relationships reliably.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.writing_collaboration import WritingDiagramReference
from project_manager import project_manager
from services.diagram_service import diagram_service
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service
from services.writing_collaboration_service import writing_collaboration_service


PROJECT_ID = "proj-10fbeefae5"
DOCUMENT_ID = "doc-0cdb6e81aebb"
CHAPTER_ID = "block-fa8d20d69818624b091fbbe9"
EXPECTED_REVISION = 29
EXPECTED_SHA256 = "c24acda6cf4644af06edb029affc4ffa4551c79bfd98c90ee32a3a8b304a64bb"
ACTOR = "thesis-ch2-print-projection"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
STAGE2_ROOT = KNOWLEDGE / "output/博士论文-v34第二章配图/05-stage2"
PNG_ROOT = STAGE2_ROOT / "png-projections"
REPORT_PATH = STAGE2_ROOT / "chapter2-stage2-print-projection-report.json"

FIGURES = [
    ("图2-1", "指挥控制闭环中的任务规划定位及多流关系", "doc-dcd1c8b24825", 1),
    ("图2-2", "指挥决心向规划变量和任务图的映射关系", "doc-a3c0266ac5aa", 2),
    ("图2-3", "集中式、分层式与分布式协同控制及授权边界", "doc-e5d1bd0ab4e6", 1),
    ("图2-4", "战术知识约束的全局态势价值、优势场与分层投影", "doc-33b23d121e10", 2),
    ("图2-5", "三类任务规划模型的耦合关系及章节映射", "doc-4e06a50b09e7", 2),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _block_map(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str((block.get("attrs") or {}).get("blockId") or ""): block
        for block in (state.get("document") or {}).get("content") or []
        if (block.get("attrs") or {}).get("blockId")
    }


def _figure_image(state: dict[str, Any], label: str) -> dict[str, Any]:
    rows = [
        block
        for block in (state.get("document") or {}).get("content") or []
        if block.get("type") == "image"
        and str((block.get("attrs") or {}).get("artifactKind") or "") == "figure"
        and str((block.get("attrs") or {}).get("artifactLabel") or "") == label
    ]
    if len(rows) != 1:
        raise DocumentWorkspaceError(f"{label}正文图片块数量异常：{len(rows)}")
    return rows[0]


def _backup(project: dict[str, Any], state: dict[str, Any]) -> Path:
    root = STAGE2_ROOT / "backups" / f"print-projection-before-r{EXPECTED_REVISION:06d}"
    root.mkdir(parents=True, exist_ok=True)
    snapshots = {
        "structured-state.json": state,
        "document-record.json": multi_document_service.get_document(project, DOCUMENT_ID),
        "backup-manifest.json": {
            "created_at": _now(),
            "project_id": PROJECT_ID,
            "document_id": DOCUMENT_ID,
            "document_revision": state["document_revision"],
            "content_sha256": EXPECTED_SHA256,
            "purpose": "chapter2-svg-to-png-print-projection",
        },
    }
    for name, value in snapshots.items():
        path = root / name
        if not path.exists():
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
    document_root = multi_document_service._document_root(project, DOCUMENT_ID)  # noqa: SLF001
    for relative in ("source/document.md", "working/document.md", "manifest.json"):
        source = document_root / relative
        target = root / relative.replace("/", "-")
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)
    index = multi_document_service._index_path(project)  # noqa: SLF001
    if index.is_file() and not (root / "documents.json").exists():
        shutil.copy2(index, root / "documents.json")
    return root


def _update_reference_formats(project: dict[str, Any]) -> list[str]:
    changed = []
    with diagram_service.session_factory() as session:
        for label, _, diagram_id, revision in FIGURES:
            row = session.execute(
                select(WritingDiagramReference).where(
                    WritingDiagramReference.project_id == PROJECT_ID,
                    WritingDiagramReference.diagram_document_id == diagram_id,
                    WritingDiagramReference.diagram_revision == revision,
                    WritingDiagramReference.target_document_id == DOCUMENT_ID,
                    WritingDiagramReference.target_section_id == CHAPTER_ID,
                    WritingDiagramReference.status == "current",
                )
            ).scalar_one_or_none()
            if not row:
                raise DocumentWorkspaceError(f"{label}当前图表引用不存在")
            if row.export_format != "png":
                row.export_format = "png"
                changed.append(row.id)
        session.commit()
    return changed


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    record = multi_document_service.get_document(project, DOCUMENT_ID)
    if not record.get("is_primary") or record.get("edit_policy") != "editable":
        raise DocumentWorkspaceError("目标不再是当前可编辑主文档")

    state = writing_collaboration_service.get_state(project, DOCUMENT_ID, CHAPTER_ID)
    full = writing_collaboration_service.get_state(project, DOCUMENT_ID)
    content_sha256 = writing_collaboration_service.codec.document_sha256(full["document"])
    if int(state.get("document_revision") or 0) != EXPECTED_REVISION:
        raise DocumentWorkspaceError(
            f"正文修订已变化：当前{state.get('document_revision')}，预期{EXPECTED_REVISION}"
        )
    if content_sha256 != EXPECTED_SHA256:
        raise DocumentWorkspaceError("正文内容哈希已变化，停止打印投影修复")
    if str((state.get("projection") or {}).get("status") or "") != "current":
        raise DocumentWorkspaceError("Markdown投影不是current")

    missing = [str(PNG_ROOT / f"{label}.png") for label, *_ in FIGURES if not (PNG_ROOT / f"{label}.png").is_file()]
    if missing:
        raise DocumentWorkspaceError("打印PNG缺失：" + "、".join(missing))

    images = {label: _figure_image(state, label) for label, *_ in FIGURES}
    for label, _, diagram_id, revision in FIGURES:
        current_src = str((images[label].get("attrs") or {}).get("src") or "")
        marker = f"{diagram_id}-r{revision}-"
        if marker not in current_src or not current_src.endswith(".svg"):
            raise DocumentWorkspaceError(f"{label}当前SVG投影不符合预期")

    backup = _backup(project, full)
    assets: dict[str, dict[str, Any]] = {}
    operations = []
    for label, caption, diagram_id, revision in FIGURES:
        png = PNG_ROOT / f"{label}.png"
        asset = multi_document_service.upload_rich_text_asset(
            project,
            DOCUMENT_ID,
            png.read_bytes(),
            f"{diagram_id}-r{revision}-print.png",
            "image/png",
            actor=ACTOR,
        )
        assets[label] = {**asset, "source_png_sha256": _sha_file(png)}
        block = images[label]
        attrs = block.get("attrs") or {}
        full_caption = f"{label} {caption}"
        operations.append(
            {
                "op": "replace",
                "block_id": str(attrs.get("blockId") or ""),
                "expected_block_revision": int(attrs.get("blockRevision") or 1),
                "node": {
                    "type": "image",
                    "attrs": {
                        "src": asset["path"],
                        "alt": "",
                        "title": full_caption,
                        "width": "145mm",
                        "artifactKind": "figure",
                        "artifactLabel": label,
                        "artifactTitle": caption,
                    },
                },
            }
        )

    updated = writing_collaboration_service.patch_draft(
        project,
        DOCUMENT_ID,
        {
            "section_id": CHAPTER_ID,
            "expected_revision": EXPECTED_REVISION,
            "client_change_id": "thesis-v34-ch2-print-png-projection-v1",
            "operations": operations,
        },
        ACTOR,
    )
    reference_ids = _update_reference_formats(project)

    final_state = writing_collaboration_service.get_state(project, DOCUMENT_ID, CHAPTER_ID)
    final_images = {label: _figure_image(final_state, label) for label, *_ in FIGURES}
    references = {
        label: [
            row
            for row in diagram_service.list_references(project, diagram_id)
            if row.get("target_document_id") == DOCUMENT_ID
            and row.get("target_section_id") == CHAPTER_ID
            and int(row.get("diagram_revision") or 0) == revision
        ]
        for label, _, diagram_id, revision in FIGURES
    }
    report = {
        "stage": "2-print-projection-repair",
        "status": "completed",
        "completed_at": _now(),
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "backup": str(backup),
        "before_revision": EXPECTED_REVISION,
        "before_sha256": EXPECTED_SHA256,
        "after_revision": final_state.get("document_revision"),
        "after_sha256": writing_collaboration_service.codec.document_sha256(
            writing_collaboration_service.get_state(project, DOCUMENT_ID)["document"]
        ),
        "projection": final_state.get("projection") or {},
        "applied_operations": updated.get("applied_operations"),
        "assets": assets,
        "reference_ids_updated": reference_ids,
        "verification": {
            label: {
                "image_src": (final_images[label].get("attrs") or {}).get("src"),
                "alt": (final_images[label].get("attrs") or {}).get("alt"),
                "title": (final_images[label].get("attrs") or {}).get("title"),
                "reference_formats": [row.get("export_format") for row in references[label]],
                "reference_statuses": [row.get("status") for row in references[label]],
            }
            for label, *_ in FIGURES
        },
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
