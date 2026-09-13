"""Archive the superseded first-title candidate for Chapter 3 figure 3-3."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager
from services.diagram_service import diagram_service
from services.multi_document_service import multi_document_service


PROJECT_ID = "proj-10fbeefae5"
DOCUMENT_ID = "doc-32ac7033b33a"
EXPECTED_TITLE = "图3-3 统一规划解的组成与章节级接口契约"
ARCHIVED_TITLE = "归档候选：图3-3 统一规划解的组成与章节级接口契约"


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    resource = diagram_service.get(project, DOCUMENT_ID)
    document = resource.get("document") or {}
    diagram = resource.get("diagram") or {}
    if document.get("status") == "archived":
        print(json.dumps({"document_id": DOCUMENT_ID, "status": "already-archived"}, ensure_ascii=False))
        return
    if document.get("title") != EXPECTED_TITLE or diagram.get("diagram_type") != "plan-solution-contract":
        raise SystemExit("待归档图表身份与预期不一致，拒绝操作")
    references = diagram_service.list_references(project, DOCUMENT_ID)
    if references:
        raise SystemExit("待归档图表已被正文引用，拒绝操作")
    updated = multi_document_service.update_document(
        project,
        DOCUMENT_ID,
        {"title": ARCHIVED_TITLE, "status": "archived"},
    )
    print(
        json.dumps(
            {
                "document_id": DOCUMENT_ID,
                "status": updated.get("status"),
                "title": updated.get("title"),
                "references": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
