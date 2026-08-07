"""Idempotently adapt the wargame and doctoral writing projects to multi-document workspaces."""

from __future__ import annotations

import json
from pathlib import Path

from project_manager import project_manager
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service


RULES_PROJECT_ID = "proj-c57e28f8e0"
THESIS_PROJECT_ID = "proj-10fbeefae5"
RULES_PROJECT_NAME = "谋战·水面舰艇编队战术手工兵棋"

VAULT = Path("/Users/apple/工作桌面/knowledge")
WARGAME_ROOT = VAULT / "06-项目库-Projects/水面舰艇编队战术兵棋/V2-海空手工兵棋体系"
RULES_WORKBOOK = WARGAME_ROOT / "03-规则手册/比赛手册/手工兵棋推演裁决计算_V4_最新合并版.xlsx"
OPERATOR_WORKBOOK = WARGAME_ROOT / "docs和excel/算子关键属性数据表.xlsx"
THESIS_PRESENTATION = (
    VAULT
    / "10-成果库-Outputs/毕业论文/博士论文/答辩PPT"
    / "博士毕业答辩-海上无人集群智能协同任务规划-整合版.pptx"
)


def require_project(project_id: str) -> dict:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"Project not found: {project_id}")
    return project


def rename_primary(project: dict, title: str) -> dict:
    collection = multi_document_service.list_documents(project)
    primary = next((row for row in collection["documents"] if row.get("is_primary")), None)
    if not primary:
        raise RuntimeError(f"Primary document missing: {project['id']}")
    if primary.get("title") != title:
        multi_document_service.update_document(project, primary["id"], {"title": title})
    return multi_document_service.get_document(project, primary["id"])


def ensure_file_document(project: dict, title: str, kind: str, source: Path) -> dict:
    if not source.is_file():
        raise RuntimeError(f"Source file missing: {source}")
    collection = multi_document_service.list_documents(project)
    existing = next(
        (row for row in collection["documents"] if row.get("title") == title and row.get("kind") == kind),
        None,
    )
    if existing:
        return existing
    return multi_document_service.create_document(project, title, kind, source_path=str(source))


def migrate() -> dict:
    rules = require_project(RULES_PROJECT_ID)
    multi_document_service.ensure_index(rules, primary_title="规则手册")
    rename_primary(rules, "规则手册")
    if rules.get("name") != RULES_PROJECT_NAME:
        rules = project_manager.update_project(RULES_PROJECT_ID, {"name": RULES_PROJECT_NAME}) or rules
    adjudication = ensure_file_document(rules, "裁决表", "workbook", RULES_WORKBOOK)
    operators = ensure_file_document(rules, "算子表", "workbook", OPERATOR_WORKBOOK)

    thesis = require_project(THESIS_PROJECT_ID)
    multi_document_service.ensure_index(thesis, primary_title="博士论文正文")
    thesis_body = rename_primary(thesis, "博士论文正文")
    defense = ensure_file_document(thesis, "博士毕业答辩", "presentation", THESIS_PRESENTATION)

    rules_documents = multi_document_service.list_documents(rules)
    thesis_documents = multi_document_service.list_documents(thesis)
    return {
        "status": "completed",
        "rules_project": {
            "id": rules["id"],
            "name": rules["name"],
            "documents": [
                {"id": row["id"], "title": row["title"], "kind": row["kind"], "stats": row.get("stats", {})}
                for row in rules_documents["documents"]
            ],
            "adjudication_document_id": adjudication["id"],
            "operator_document_id": operators["id"],
        },
        "thesis_project": {
            "id": thesis["id"],
            "name": thesis["name"],
            "documents": [
                {"id": row["id"], "title": row["title"], "kind": row["kind"], "stats": row.get("stats", {})}
                for row in thesis_documents["documents"]
            ],
            "body_document_id": thesis_body["id"],
            "presentation_document_id": defense["id"],
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(migrate(), ensure_ascii=False, indent=2))
    except (DocumentWorkspaceError, RuntimeError) as exc:
        raise SystemExit(f"Migration failed: {exc}") from exc
