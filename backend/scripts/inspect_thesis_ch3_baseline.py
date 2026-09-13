"""Capture a read-only Chapter 3 structured-document and figure baseline."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager
from services.diagram_service import diagram_service
from services.multi_document_service import multi_document_service
from services.writing_collaboration_service import writing_collaboration_service


PROJECT_ID = "proj-10fbeefae5"
DOCUMENT_ID = "doc-0cdb6e81aebb"
OUTPUT = Path(
    "/Users/apple/工作桌面/knowledge/output/博士论文-v34第三章配图/01-baseline/"
    "chapter3-structured-baseline.json"
)


def _text(node: dict[str, Any]) -> str:
    return str(node.get("text") or "") + "".join(
        _text(child)
        for child in node.get("content") or []
        if isinstance(child, dict)
    )


def _chapter_slice(blocks: list[dict[str, Any]]) -> tuple[int, int]:
    start = next(
        index
        for index, block in enumerate(blocks)
        if block.get("type") == "heading"
        and int((block.get("attrs") or {}).get("level") or 0) == 1
        and _text(block).strip().startswith("第3章")
    )
    end = next(
        index
        for index in range(start + 1, len(blocks))
        if blocks[index].get("type") == "heading"
        and int((blocks[index].get("attrs") or {}).get("level") or 0) == 1
    )
    return start, end


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    record = multi_document_service.get_document(project, DOCUMENT_ID)
    state = writing_collaboration_service.get_state(project, DOCUMENT_ID)
    blocks = list((state.get("document") or {}).get("content") or [])
    start, end = _chapter_slice(blocks)
    chapter = blocks[start:end]
    chapter_id = str((chapter[0].get("attrs") or {}).get("blockId") or "")

    rows: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    figure_mentions: list[dict[str, Any]] = []
    for local_index, block in enumerate(chapter):
        attrs = dict(block.get("attrs") or {})
        text = _text(block).strip()
        row = {
            "index": start + local_index,
            "chapter_index": local_index,
            "type": block.get("type"),
            "block_id": attrs.get("blockId"),
            "block_revision": attrs.get("blockRevision"),
            "text": text,
            "attrs": attrs,
        }
        rows.append(row)
        if block.get("type") == "image":
            images.append(row)
        if "图3-" in text or str(attrs.get("artifactLabel") or "").startswith("图3-"):
            figure_mentions.append(row)

    references: list[dict[str, Any]] = []
    diagram_ids = {
        str((row.get("attrs") or {}).get("diagramDocumentId") or "")
        for row in images
    }
    for diagram_id in sorted(value for value in diagram_ids if value):
        references.extend(
            row
            for row in diagram_service.list_references(project, diagram_id)
            if row.get("target_document_id") == DOCUMENT_ID
        )

    chapter_payload = json.dumps(chapter, ensure_ascii=False, sort_keys=True).encode("utf-8")
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "document": {
            key: record.get(key)
            for key in (
                "id",
                "title",
                "is_primary",
                "edit_policy",
                "parent_document_id",
                "publication_status",
            )
        },
        "document_revision": state.get("document_revision"),
        "document_sha256": writing_collaboration_service.codec.document_sha256(
            state["document"]
        ),
        "projection": state.get("projection") or {},
        "chapter": {
            "id": chapter_id,
            "title": _text(chapter[0]).strip(),
            "start_index": start,
            "end_index_exclusive": end,
            "block_count": len(chapter),
            "sha256": hashlib.sha256(chapter_payload).hexdigest(),
            "type_counts": {
                block_type: sum(1 for row in rows if row["type"] == block_type)
                for block_type in sorted({str(row["type"]) for row in rows})
            },
        },
        "headings": [row for row in rows if row["type"] == "heading"],
        "images": images,
        "figure_mentions": figure_mentions,
        "diagram_references": references,
        "blocks": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(OUTPUT)
    print(json.dumps(report["chapter"], ensure_ascii=False))
    print(f"images={len(images)} mentions={len(figure_mentions)} refs={len(references)}")


if __name__ == "__main__":
    main()
