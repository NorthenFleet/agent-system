"""Replace Chapter 3 SVG body projections with print-safe PNG assets.

The structured diagram documents remain editable authorities. PNG files are
only the rich-text delivery projection used by Word and PDF export.
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
CHAPTER_ID = "block-2920e5046b81ded487b819cd"
EXPECTED_REVISION = 44
EXPECTED_SHA256 = "80f1eaee9d32cec7b6a1e8de5027912253aa86c8a35dc21adff5f2a70992d02d"
ACTOR = "thesis-ch3-print-projection"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
STAGE2_ROOT = KNOWLEDGE / "output/博士论文-v34第三章配图/07-stage2"
PNG_ROOT = STAGE2_ROOT / "png-projections"
REPORT_PATH = STAGE2_ROOT / "chapter3-stage2-print-projection-report.json"

FIGURES = [
    ("图3-1", "海上无人集群协同任务规划统一总体模型", "doc-e0d8e261bc3f", 2),
    ("图3-2", "作战对象、观测信念与全局评价状态的形成关系", "doc-2ae9d147887a", 2),
    ("图3-3", "统一规划解的构成及其章节衔接关系", "doc-cf2e3fcea68a", 1),
    ("图3-4", "分层约束体系、责任边界与可行域门控", "doc-aaa7d48041b9", 3),
    ("图3-5", "指挥控制、任务规划与执行控制的权责边界", "doc-bf44aa036266", 2),
    ("图3-6", "海上无人集群任务规划的信息流、控制流与证据反馈闭环", "doc-1c3f035db473", 2),
    ("图3-7", "预先规划、执行监控与分级重规划机制", "doc-9a7cfb86a66d", 3),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    for name, value in {
        "structured-state.json": state,
        "document-record.json": multi_document_service.get_document(project, DOCUMENT_ID),
        "backup-manifest.json": {
            "created_at": _now(),
            "project_id": PROJECT_ID,
            "document_id": DOCUMENT_ID,
            "document_revision": state["document_revision"],
            "content_sha256": EXPECTED_SHA256,
            "purpose": "chapter3-svg-to-png-print-projection",
        },
    }.items():
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


def _update_reference_formats() -> list[str]:
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

    missing = [
        str(PNG_ROOT / f"{label}.png")
        for label, *_ in FIGURES
        if not (PNG_ROOT / f"{label}.png").is_file()
    ]
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
                        "title": f"{label} {caption}",
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
            "client_change_id": "thesis-v34-ch3-print-png-projection-v1",
            "operations": operations,
        },
        ACTOR,
    )
    reference_ids = _update_reference_formats()

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
