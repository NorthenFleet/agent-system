"""Print the current Chapter 2 structured blocks needed for diagram publication."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager
from services.writing_collaboration_service import writing_collaboration_service


PROJECT_ID = "proj-10fbeefae5"
DEFAULT_DOCUMENT_ID = "doc-0cdb6e81aebb"


def _text(node: dict[str, Any]) -> str:
    return str(node.get("text") or "") + "".join(
        _text(child)
        for child in node.get("content") or []
        if isinstance(child, dict)
    )


def main() -> None:
    document_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DOCUMENT_ID
    project = project_manager.get_project(PROJECT_ID)
    state = writing_collaboration_service.get_state(project, document_id)
    rows = []
    headings = []
    selected_sections: dict[str, list[dict[str, Any]]] = {}
    active = False
    for index, block in enumerate((state.get("document") or {}).get("content") or []):
        text = _text(block).strip()
        if block.get("type") == "heading":
            headings.append(
                {
                    "index": index,
                    "block_id": (block.get("attrs") or {}).get("blockId"),
                    "level": (block.get("attrs") or {}).get("level"),
                    "text": text,
                }
            )
        is_chapter_heading = (
            block.get("type") == "heading"
            and int((block.get("attrs") or {}).get("level") or 0) == 1
        )
        active = active or (is_chapter_heading and text.startswith("第2章"))
        if not active:
            continue
        attrs = block.get("attrs") or {}
        if (
            block.get("type") in {"heading", "image"}
            or "如图2-" in text
            or str(attrs.get("artifactLabel") or "").startswith("图2-")
            or text.startswith("图2-")
        ):
            rows.append(
                {
                    "index": index,
                    "type": block.get("type"),
                    "block_id": attrs.get("blockId"),
                    "block_revision": attrs.get("blockRevision"),
                    "artifact_kind": attrs.get("artifactKind"),
                    "artifact_label": attrs.get("artifactLabel"),
                    "src": attrs.get("src"),
                    "text": text,
                }
            )
        if is_chapter_heading and text.startswith("第3章"):
            break

    blocks = (state.get("document") or {}).get("content") or []
    section_titles = {
        "2.2.1 指挥控制闭环中的任务规划定位",
        "2.2.2 指挥决心向规划变量和任务图的映射",
        "2.3.3 集中、分层与分布式协同方式",
        "2.4.6 优势场及其多层级投影机制",
        "2.5.4 三类模型向后续算法章节的映射",
    }
    for heading in headings:
        title = str(heading.get("text") or "")
        if title not in section_titles:
            continue
        start = int(heading["index"])
        level = int(heading.get("level") or 3)
        end = next(
            (
                int(candidate["index"])
                for candidate in headings
                if int(candidate["index"]) > start
                and int(candidate.get("level") or 9) <= level
            ),
            len(blocks),
        )
        selected_sections[title] = []
        for index in range(start, end):
            block = blocks[index]
            attrs = block.get("attrs") or {}
            selected_sections[title].append(
                {
                    "index": index,
                    "type": block.get("type"),
                    "block_id": attrs.get("blockId"),
                    "block_revision": attrs.get("blockRevision"),
                    "artifact_kind": attrs.get("artifactKind"),
                    "artifact_label": attrs.get("artifactLabel"),
                    "src": attrs.get("src"),
                    "text": _text(block).strip(),
                    "attrs": attrs,
                }
            )
    selected_only = "--selected" in sys.argv[2:]
    print(
        json.dumps(
            {
                "document_id": document_id,
                "document_revision": state.get("document_revision"),
                "headings": [] if selected_only else headings,
                "rows": [] if selected_only else rows,
                "selected_sections": selected_sections,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
