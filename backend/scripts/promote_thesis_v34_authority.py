#!/usr/bin/env python3
"""Promote the audited v34 thesis candidate as the editable body authority.

The migration imports only the v25 front matter that is absent from v34.  The
v25 DOCX/PDF delivery remains frozen; v33 remains the deliverable rollback
baseline until a separate manuscript-freeze export is approved.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import SessionLocal  # noqa: E402
from models.writing_collaboration import WritingWorkspacePreference  # noqa: E402
from project_manager import project_manager  # noqa: E402
from services.document_fidelity_service import document_fidelity_service  # noqa: E402
from services.document_workspace_service import DocumentWorkspaceError  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.pandoc_document_importer import pandoc_docx_importer  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402

PROJECT_ID = "proj-10fbeefae5"
V33_ID = "doc-15def56e2401"
V34_ID = "doc-0cdb6e81aebb"
PRESENTATION_ID = "doc-8729ccf99985"
V25_DOCX = Path(
    "/Users/apple/工作桌面/knowledge/10-成果库-Outputs/毕业论文/博士论文/"
    "博士论文-第三版-七章工作稿-v25-排版R4.1.docx"
)
PREFLIGHT = Path(
    "/Users/apple/工作桌面/knowledge/06-项目库-Projects/博士论文/_workspace/"
    "backups/v25-to-v34-authority-20260809T102239Z/v25-v34-preflight.json"
)
MARKER = "<!-- v34:v25-front-matter -->"
ACTOR = "v25-v34-authority-promotion"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(data: bytes | str) -> str:
    value = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(value).hexdigest()


def _node_text(node: dict[str, Any]) -> str:
    if node.get("type") == "text":
        return str(node.get("text") or "")
    return "".join(_node_text(child) for child in node.get("content") or [])


def _first_node_text(nodes: list[dict[str, Any]], value: str) -> str:
    for node in nodes:
        text = _node_text(node).strip()
        if text == value:
            return text
    raise DocumentWorkspaceError(f"v25 Word 缺少前置字段：{value}")


def _paragraph_after(nodes: list[dict[str, Any]], label: str) -> str:
    for index, node in enumerate(nodes[:-1]):
        if _node_text(node).strip() != label:
            continue
        for candidate in nodes[index + 1 :]:
            text = _node_text(candidate).strip()
            if text:
                return text
    raise DocumentWorkspaceError(f"v25 Word 缺少前置内容：{label}")


def _v34_abstracts(chinese: str, english: str) -> tuple[str, str]:
    chinese_old = (
        "任务技能包将感知、火力和机动能力组织为可调用、可追踪、可回退的任务内部结构，"
        "并以动作所有权隔离规则技能与学习技能；机动技能采用"
    )
    chinese_new = (
        "任务技能包将感知、火力和机动能力组织为可调用、可追踪、可回退的任务内部结构；"
        "其中，基于规则的武器运用策略负责目标威胁排序、交战可行性判断、武器选择、"
        "火力分配、发射授权与再攻击，强化学习策略仅负责目标点、编队与速度等机动决策；"
        "机动技能采用"
    )
    english_old = (
        "the task skill package organizes sensing, fire, and maneuver capabilities into an invocable, "
        "traceable, and recoverable intra-task structure, with action ownership separating rule skills "
        "from learned skills; the maneuver skill employs"
    )
    english_new = (
        "the task skill package organizes sensing, fire, and maneuver capabilities into an invocable, "
        "traceable, and recoverable intra-task structure. The rule-based weapon-employment policy owns "
        "threat ranking, engagement feasibility, weapon selection, fire allocation, release authorization, "
        "and re-attack, while reinforcement learning owns only maneuver decisions such as goal points, "
        "formation, and speed; the maneuver skill employs"
    )
    if chinese_old not in chinese or english_old not in english:
        raise DocumentWorkspaceError("v25 摘要与已审计基线不一致，已阻止自动改写")
    return chinese.replace(chinese_old, chinese_new), english.replace(english_old, english_new)


def build_front_matter(source: dict[str, Any]) -> tuple[str, dict[str, str]]:
    nodes = list(source.get("document", {}).get("content") or [])
    _first_node_text(nodes, "摘 要")
    _first_node_text(nodes, "ABSTRACT")
    chinese, english = _v34_abstracts(
        _paragraph_after(nodes, "摘 要"),
        _paragraph_after(nodes, "ABSTRACT"),
    )
    keywords_zh = next(
        (_node_text(node).strip() for node in nodes if _node_text(node).strip().startswith("关键词：")),
        "",
    )
    keywords_en = next(
        (_node_text(node).strip() for node in nodes if _node_text(node).strip().startswith("Key words:")),
        "",
    )
    if not keywords_zh or not keywords_en:
        raise DocumentWorkspaceError("v25 Word 缺少中英文关键词")
    keywords_zh = "关键词：海上无人集群；任务规划；指挥控制；优势熵；火力分配；强化学习；分级重规划"
    keywords_en = (
        "Key words: maritime unmanned swarm; mission planning; command and control; advantage entropy; "
        "fire allocation; reinforcement learning; leveled replanning"
    )
    markdown = (
        f"{MARKER}\n\n# 摘 要\n\n{chinese}\n\n**{keywords_zh}**\n\n"
        f"# ABSTRACT\n\n{english}\n\n**{keywords_en}**\n"
    )
    return markdown, {
        "abstract_zh": chinese,
        "abstract_en": english,
        "keywords_zh": keywords_zh.removeprefix("关键词："),
        "keywords_en": keywords_en.removeprefix("Key words: "),
    }


def _update_header(document: dict[str, Any]) -> None:
    for node in document.get("content") or []:
        if node.get("type") != "rawMarkdown":
            break
        attrs = node.get("attrs") or {}
        markdown = str(attrs.get("markdown") or "")
        if "workspace_version:" not in markdown:
            continue
        lines = []
        for line in markdown.splitlines():
            if line.startswith("workspace_version:"):
                line = "workspace_version: 34"
            elif line.startswith("status:"):
                line = "status: working"
            elif line.startswith("stage_lock:"):
                line = "stage_lock: thesis-v34-active-authority-20260809"
            lines.append(line)
        attrs["markdown"] = "\n".join(lines)
        return


def merge_front_matter(document: dict[str, Any], front_markdown: str) -> tuple[dict[str, Any], bool]:
    value = copy.deepcopy(document)
    _update_header(value)
    current_markdown = writing_collaboration_service.codec.to_markdown(value)
    if MARKER in current_markdown:
        return value, False
    front = writing_collaboration_service.codec.from_markdown(
        front_markdown,
        namespace=f"{PROJECT_ID}/{V34_ID}/v25-front-matter",
    )
    nodes = list(value.get("content") or [])
    insert_at = 0
    while insert_at < len(nodes) and nodes[insert_at].get("type") == "rawMarkdown":
        insert_at += 1
    value["content"] = [*nodes[:insert_at], *(front.get("content") or []), *nodes[insert_at:]]
    writing_collaboration_service.codec.ensure_block_ids(
        value,
        namespace=f"{PROJECT_ID}/{V34_ID}/v25-merge",
    )
    writing_collaboration_service.codec.validate_document(value)
    return value, True


def _chapter_count(document: dict[str, Any]) -> int:
    return sum(
        1
        for node in document.get("content") or []
        if node.get("type") == "heading"
        and int((node.get("attrs") or {}).get("level") or 0) == 1
        and _node_text(node).strip().startswith("第")
        and "章" in _node_text(node)
    )


def _migrate_preferences() -> int:
    changed = 0
    with SessionLocal() as session:
        rows = session.execute(select(WritingWorkspacePreference).where(
            WritingWorkspacePreference.project_id == PROJECT_ID
        )).scalars().all()
        for row in rows:
            preference = copy.deepcopy(row.preference_json or {})
            row_changed = False
            for pane in (preference.get("panes") or {}).values():
                if isinstance(pane, dict) and pane.get("resource_id") == V33_ID:
                    pane["resource_id"] = V34_ID
                    pane.pop("section_id", None)
                    row_changed = True
            if row_changed:
                row.preference_json = preference
                row.schema_version = 2
                row.revision += 1
                row.updated_at = datetime.now(timezone.utc)
                changed += 1
        session.commit()
    return changed


def _record(documents: list[dict[str, Any]], document_id: str) -> dict[str, Any]:
    row = next((item for item in documents if item.get("id") == document_id), None)
    if not row:
        raise DocumentWorkspaceError(f"文档不存在：{document_id}")
    return row


def promote(*, apply: bool) -> dict[str, Any]:
    if not V25_DOCX.is_file() or not PREFLIGHT.is_file():
        raise DocumentWorkspaceError("v25 权威 Word 或预检报告不存在")
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    source_sha = _sha(V25_DOCX.read_bytes())
    source_report = preflight.get("source") if isinstance(preflight.get("source"), dict) else {}
    expected_sha = str(
        preflight.get("v25_source_sha256")
        or preflight.get("source_sha256")
        or source_report.get("sha256")
        or ""
    )
    if expected_sha and source_sha != expected_sha:
        raise DocumentWorkspaceError("v25 Word 校验和变化，已阻止迁移")

    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise DocumentWorkspaceError("博士论文项目不存在")
    documents = multi_document_service.list_documents(project, include_archived=True).get("documents") or []
    v33 = _record(documents, V33_ID)
    v34 = _record(documents, V34_ID)
    presentation = _record(documents, PRESENTATION_ID)
    state = writing_collaboration_service.get_state(project, V34_ID)
    source = pandoc_docx_importer.convert(V25_DOCX.read_bytes(), "博士论文 v25")
    front_markdown, front_fields = build_front_matter(source)
    merged_document, inserted = merge_front_matter(state["document"], front_markdown)
    metrics = writing_collaboration_service.codec.metrics(merged_document)
    report: dict[str, Any] = {
        "project_id": PROJECT_ID,
        "v25_source_sha256": source_sha,
        "v33_document_id": V33_ID,
        "v34_document_id": V34_ID,
        "v34_revision_before": int(state.get("document_revision") or 0),
        "front_matter_inserted": inserted,
        "chapter_count": _chapter_count(merged_document),
        "metrics": metrics,
        "apply": apply,
    }
    if report["chapter_count"] != 7:
        raise DocumentWorkspaceError("v34 七章结构校验失败")
    for key, expected in {"image_count": 32, "citation_count": 181, "replacement_character_count": 0}.items():
        if int(metrics.get(key) or 0) != expected:
            raise DocumentWorkspaceError(f"v34 指标校验失败：{key}")
    if not apply:
        report["status"] = "ready"
        return report

    if inserted or "workspace_version: 34" not in writing_collaboration_service.codec.to_markdown(state["document"]):
        merged_markdown = writing_collaboration_service.codec.to_markdown(merged_document)
        state = writing_collaboration_service.replace_authority_from_document(
            project,
            V34_ID,
            merged_document,
            merged_markdown,
            label="v34 合并 v25 前置信息并切换正文权威",
            actor=ACTOR,
        )
    content_sha = writing_collaboration_service.codec.document_sha256(state["document"])

    layout = copy.deepcopy((v33.get("metadata") or {}).get("layout_binding") or {})
    layout.update({
        "content_version": 34,
        "content_sha256": content_sha,
        "delivery_basename": "博士论文-第三版-v34-七章工作稿",
        "status": "stale",
        "status_reason": "v34 已成为正文权威；Word/PDF 仍冻结在 v25 R4.1，待人工确认定稿后统一重排。",
        "bound_at": _now(),
    })
    layout["frontmatter"] = {
        "abstract_zh": "authoritative_v34_structured_body",
        "abstract_en": "authoritative_v34_structured_body",
        "keywords_zh": "authoritative_v34_structured_body",
        "keywords_en": "authoritative_v34_structured_body",
        "toc": "regenerate_on_manuscript_freeze",
    }
    multi_document_service.update_document_metadata(project, V34_ID, {
        "thesis_stage": 7,
        "thesis_version": 34,
        "artifact_version": 25,
        "layout_binding": layout,
        "frontmatter_authority": front_fields,
        "merged_from_v25": {
            "source_path": str(V25_DOCX),
            "source_sha256": source_sha,
            "preflight_report": str(PREFLIGHT),
            "scope": "cover_metadata_abstracts_keywords_layout_profile",
            "body_merge_policy": "review_only_no_bulk_overwrite",
            "merged_at": _now(),
        },
        "last_actor": ACTOR,
    })
    lineage = dict(v34.get("lineage") or {})
    lineage.update({
        "series_id": "doctoral-thesis",
        "edition_label": "第三版·v34工作稿",
        "sequence": 4,
        "source_type": "structured_authority",
        "parent_document_id": V33_ID,
        "source_checksum": content_sha,
        "generated_at": lineage.get("generated_at") or _now(),
        "source_paths": list(dict.fromkeys([
            *(lineage.get("source_paths") or []),
            str(V25_DOCX),
        ])),
    })
    multi_document_service.update_document(project, V33_ID, {
        "is_primary": False,
        "edit_policy": "read_only",
        "delivery_role": "deliverable",
        "required_for_release": False,
    })
    multi_document_service.update_document(project, V34_ID, {
        "title": "博士论文·第三版 v34（七章工作稿）",
        "status": "active",
        "sort_order": 2,
        "is_primary": True,
        "is_output_product": True,
        "output_format": "docx",
        "required_for_release": False,
        "expected_chapters": 7,
        "edit_policy": "editable",
        "delivery_role": "candidate",
        "publication_status": "draft",
        "data_version": "v34",
        "lineage": lineage,
    })

    presentation_binding = dict(presentation.get("structure_binding") or {})
    frozen_ppt_source_sha = str(
        ((v33.get("metadata") or {}).get("layout_binding") or {}).get("content_sha256")
        or presentation_binding.get("source_sha256")
        or ""
    )
    presentation_binding.update({
        "source_document_id": V34_ID,
        "source_version": "v25",
        "source_sha256": frozen_ppt_source_sha,
        "status": "stale",
    })
    evaluated_binding = multi_document_service.set_structure_binding(
        project,
        PRESENTATION_ID,
        presentation_binding,
    )
    preference_count = _migrate_preferences()
    fidelity = document_fidelity_service._public(
        document_fidelity_service.audit(project, V34_ID, persist=True)
    )
    if fidelity.get("status") != "passed":
        raise DocumentWorkspaceError("v34 内容保真审计未通过，未完成权威迁移")

    final_documents = multi_document_service.list_documents(project, include_archived=True).get("documents") or []
    final_v33 = _record(final_documents, V33_ID)
    final_v34 = _record(final_documents, V34_ID)
    if not final_v34.get("is_primary") or final_v34.get("edit_policy") != "editable":
        raise DocumentWorkspaceError("v34 主稿状态校验失败")
    if final_v33.get("is_primary") or final_v33.get("edit_policy") != "read_only":
        raise DocumentWorkspaceError("v33 回退基线状态校验失败")
    if evaluated_binding.get("status") != "stale":
        raise DocumentWorkspaceError("v25 PPT 未正确标记为待同步")
    report.update({
        "status": "promoted",
        "v34_revision_after": int(state.get("document_revision") or 0),
        "v34_content_sha256": content_sha,
        "v34_is_primary": True,
        "v34_delivery_role": final_v34.get("delivery_role"),
        "v33_edit_policy": final_v33.get("edit_policy"),
        "v33_delivery_role": final_v33.get("delivery_role"),
        "presentation_binding": evaluated_binding,
        "workbench_preferences_migrated": preference_count,
        "fidelity": fidelity,
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(promote(apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
