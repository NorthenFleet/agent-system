"""Run a read-only final audit of the Chapter 4 diagram publication."""

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

from scripts.publish_thesis_ch4_diagrams_stage2 import FIGURES, PARAGRAPH_UPDATES


PROJECT_ID = "proj-10fbeefae5"
DOCUMENT_ID = "doc-0cdb6e81aebb"
PARENT_DOCUMENT_ID = "doc-15def56e2401"
CHAPTER_ID = "block-4a968344ba557fa3b76fa27a"
EXPECTED_REVISION = 66
EXPECTED_SHA256 = "2d7996576bfdbfcca6d9a1dd8edbc9ee000d397bd362b843092cc340a54bed60"
REPORT_PATH = Path(
    "/Users/apple/工作桌面/knowledge/output/博士论文-v34第四章配图/"
    "07-stage2/chapter4-final-structural-audit.json"
)


def _text(node: dict[str, Any]) -> str:
    return str(node.get("text") or "") + "".join(
        _text(child)
        for child in node.get("content") or []
        if isinstance(child, dict)
    )


def _search_text(block: dict[str, Any]) -> str:
    attrs = block.get("attrs") or {}
    return "\n".join(
        value
        for value in (
            _text(block),
            str(attrs.get("markdown") or ""),
            str(attrs.get("src") or ""),
            str(attrs.get("title") or ""),
        )
        if value
    )


def _chapter_sha256(state: dict[str, Any]) -> str:
    payload = json.dumps(
        (state.get("document") or {}).get("content") or [],
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")

    record = multi_document_service.get_document(project, DOCUMENT_ID)
    parent = multi_document_service.get_document(project, PARENT_DOCUMENT_ID)
    chapter_state = writing_collaboration_service.get_state(project, DOCUMENT_ID, CHAPTER_ID)
    full_state = writing_collaboration_service.get_state(project, DOCUMENT_ID)
    blocks = (chapter_state.get("document") or {}).get("content") or []
    block_map = {
        str((block.get("attrs") or {}).get("blockId") or ""): block
        for block in blocks
        if (block.get("attrs") or {}).get("blockId")
    }
    searchable = "\n".join(_search_text(block) for block in blocks)
    full_sha = writing_collaboration_service.codec.document_sha256(full_state["document"])

    figures: dict[str, Any] = {}
    for spec in FIGURES:
        label = str(spec["label"])
        image_rows = [
            block
            for block in blocks
            if block.get("type") == "image"
            and str((block.get("attrs") or {}).get("artifactKind") or "") == "figure"
            and str((block.get("attrs") or {}).get("artifactLabel") or "") == label
        ]
        caption_rows = [
            block
            for block in blocks
            if str((block.get("attrs") or {}).get("artifactKind") or "")
            == "figure-caption"
            and str((block.get("attrs") or {}).get("artifactLabel") or "") == label
        ]
        references = [
            row
            for row in diagram_service.list_references(project, str(spec["document_id"]))
            if row.get("target_document_id") == DOCUMENT_ID
            and row.get("target_section_id") == CHAPTER_ID
            and int(row.get("diagram_revision") or 0) == int(spec["revision"])
            and row.get("status") == "current"
        ]
        image_attrs = (image_rows[0].get("attrs") or {}) if len(image_rows) == 1 else {}
        figures[label] = {
            "image_count": len(image_rows),
            "caption_count": len(caption_rows),
            "image_src": image_attrs.get("src"),
            "image_title": image_attrs.get("title"),
            "caption_text": _text(caption_rows[0]).strip() if len(caption_rows) == 1 else "",
            "current_reference_count": len(references),
            "reference_formats": [row.get("export_format") for row in references],
            "passed": (
                len(image_rows) == 1
                and len(caption_rows) == 1
                and str(image_attrs.get("src") or "").endswith(".png")
                and image_attrs.get("title") == f"{label} {spec['caption']}"
                and _text(caption_rows[0]).strip() == f"{label} {spec['caption']}"
                and len(references) == 1
                and references[0].get("export_format") == "png"
            ),
        }

    report = {
        "status": "completed",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "document_revision": chapter_state.get("document_revision"),
        "document_sha256": full_sha,
        "chapter_sha256": _chapter_sha256(chapter_state),
        "projection": chapter_state.get("projection") or {},
        "authority": {
            "target_is_primary": bool(record.get("is_primary")),
            "target_edit_policy": record.get("edit_policy"),
            "parent_document_id": (record.get("lineage") or {}).get("parent_document_id"),
            "parent_edit_policy": parent.get("edit_policy"),
        },
        "figures": figures,
        "paragraph_checks": {
            block_id: _text(block_map.get(block_id) or {}).strip() == expected
            for block_id, expected in PARAGRAPH_UPDATES.items()
        },
        "old_assets_still_referenced": {
            name: name in searchable
            for name in (
                "ch4-mission-input-structure-v23.svg",
                "ch4-kill-chain-task-mapping-v27.svg",
                "ch4-reverse-task-decomposition-v23.svg",
                "ch4-marta-allocation-model-v27.svg",
            )
        },
        "forbidden_development_terms": {
            term: term in searchable
            for term in ("3021", "5130", "localhost", "document_id", "revision-")
        },
    }
    report["passed"] = (
        int(report["document_revision"] or 0) == EXPECTED_REVISION
        and report["document_sha256"] == EXPECTED_SHA256
        and (report["projection"] or {}).get("status") == "current"
        and report["authority"]
        == {
            "target_is_primary": True,
            "target_edit_policy": "editable",
            "parent_document_id": PARENT_DOCUMENT_ID,
            "parent_edit_policy": "read_only",
        }
        and all(row["passed"] for row in figures.values())
        and all(report["paragraph_checks"].values())
        and not any(report["old_assets_still_referenced"].values())
        and not any(report["forbidden_development_terms"].values())
    )
    if not report["passed"]:
        report["status"] = "failed"

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
