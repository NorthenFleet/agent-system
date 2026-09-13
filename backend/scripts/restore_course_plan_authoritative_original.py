#!/usr/bin/env python3
"""Restore the user-confirmed original course plan as the 3021 authority."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select


BACKEND = Path("/Users/apple/工作桌面/Workspace/agent-system/backend")
sys.path.insert(0, str(BACKEND))

from database import SessionLocal  # noqa: E402
from models.writing_collaboration import WritingDocumentVersion  # noqa: E402
from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.document_layout_service import document_layout_service  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PROJECT_ID = "proj-16ca49b862"
DOCUMENT_ID = "doc-e811bedd87f9"
SOURCE_VERSION_ID = "wver-6f5084dc36094a5cb53b65420248ea4e"
SOURCE_VERSION_REVISION = 8
SOURCE_VERSION_CONTENT_SHA256 = "2eaef798f4186f96fe0e92184fd6ea4b758cb3e0a7baa32502361d1c72b6650f"

BASE_REVISION = 14
BASE_CONTENT_SHA256 = "f315d92c7a21a5ba89503f3dbb2420fb382ef4eff547f590ef5dc8de7bfb5623"
BASE_WORKING_SHA256 = "e681c44bff1f5be27b4a124b4601f7825cab5e6861258b6cf7c365c33d712114"

SOURCE_WORD = Path(
    "/Users/apple/工作桌面/knowledge/06-项目库-Projects/"
    "水面舰艇作战软件与兵棋推演课程--proj-16ca49b862/"
    "《兵棋推演与智能决策》-军兵种作战指挥专业-20课时-孙翼.docx"
)
SOURCE_WORD_SHA256 = "625c5adc0d113828d4fa64b3bd7f6ee477cbc1f3335a67af6e9190c9b1347bc4"
TARGET_TITLE = "《兵棋推演与智能决策》课程教学计划（16学时稿）"
CONTENT_VERSION = "course-plan-authoritative-original-word-2025-10-v1"
DATA_VERSION = "source-word-2025-10"
ACTOR = "course-plan-authoritative-original-restore"
PHASE_LABEL = "课程教学计划：恢复用户确认原版Word"
GENERATED_AT = "2026-08-23T16:00:00+08:00"

OTHER_DOCUMENTS = {
    "schedule": ("doc-2a28da7429f0", 16, "b35fd5152f2b25ac119e5d38fc01672a54c044950ce3026cf43fa1f128bbda19"),
    "L01": ("doc-3a9dbb65b9a3", 64, "2021462daed265c26645f297545673ebcd87036a72fa0d01f390bb02f961d220"),
    "L02": ("doc-6085f649c11a", 13, "8531582ac7ae1a073cd47172b46dddb93106a80058536277164d8705644cc139"),
    "L03": ("doc-105f2073f3d9", 10, "31e2d785937fc8a8377c8370ebc081b8d8be03c0728d3b6333b3403a562ce858"),
    "L04": ("doc-9c47a19819ed", 12, "fb53099ea49c040568a13bad8476115dc32a33c2ede5c910a7ee975339cefdca"),
    "L05": ("doc-e542cf30905a", 12, "ff2a3f37a28a34612eb9539872e0429d1ca3784bd0c3451fb2011a0c3c45a973"),
    "L06": ("doc-9df3ab46770c", 12, "f7e6c1af4b30267c9f79406405600c48a6219d10e240902d3176477462898dc3"),
    "L07": ("doc-60e4858f35af", 12, "72836823c3c1500e4f19054252fc70d80f046e0450a67b3915a9b43727245673"),
    "L08": ("doc-8248d6366ec3", 12, "1f71c3163532096563d645fcd7b0f54460d93ae5a4dc02d791697861cf2201cb"),
    "L09": ("doc-729fe58abb5a", 12, "4ea207564e324dbeee3db16f789ea5309e5bcf105e954ff07f5224e2868ace5f"),
    "L10": ("doc-dab8a79a74dc", 12, "0ef36d1d977e56970b6d18fe4a6dbf0b22ef2ee94f2b83598279833c259c6caf"),
}

EXPECTED_METRICS = {
    "block_count": 356,
    "heading_count": 32,
    "table_count": 4,
    "table_cell_count": 158,
    "image_count": 0,
    "math_block_count": 0,
    "math_inline_count": 0,
    "replacement_character_count": 0,
    "citation_count": 1,
    "plain_text_sha256": "edc2dd5a32f28270b5f63be1014f137e87b1539dbb47ed60447c2a1dba72e40a",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _working_path(project: dict[str, Any], document_id: str) -> Path:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    path = Path(str(manifest.get("working_markdown") or ""))
    if not path.is_file():
        raise RuntimeError(f"工作投影不存在：{document_id} {path}")
    return path


def _state(project: dict[str, Any], document_id: str) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, document_id)
    path = _working_path(project, document_id)
    return {
        "document_id": document_id,
        "revision": int(state.get("document_revision") or 0),
        "content_sha256": writing_collaboration_service.codec.document_sha256(state["document"]),
        "working_path": str(path),
        "working_sha256": _sha256(path),
        "projection_revision": int((state.get("projection") or {}).get("revision") or 0),
        "projection_status": str((state.get("projection") or {}).get("status") or ""),
        "approved_revision": int(state.get("approved_revision") or 0),
        "published_revision": int(state.get("published_revision") or 0),
    }


def _other_states(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, (document_id, revision, content_sha) in OTHER_DOCUMENTS.items():
        current = writing_collaboration_service.get_state(project, document_id)
        actual_revision = int(current.get("document_revision") or 0)
        actual_sha = writing_collaboration_service.codec.document_sha256(current["document"])
        if actual_revision != revision or actual_sha != content_sha:
            raise RuntimeError(
                f"{name}基线已变化，停止单文档迁移："
                f"revision={actual_revision}, sha={actual_sha}"
            )
        result[name] = {
            "document_id": document_id,
            "revision": revision,
            "content_sha256": content_sha,
        }
    return result


def _source_version() -> WritingDocumentVersion:
    with SessionLocal() as session:
        row = session.execute(
            select(WritingDocumentVersion).where(
                WritingDocumentVersion.id == SOURCE_VERSION_ID,
                WritingDocumentVersion.project_id == PROJECT_ID,
                WritingDocumentVersion.document_id == DOCUMENT_ID,
            )
        ).scalar_one_or_none()
        if not row:
            raise RuntimeError("原Word保真历史修订不存在")
        if row.document_revision != SOURCE_VERSION_REVISION or row.content_sha256 != SOURCE_VERSION_CONTENT_SHA256:
            raise RuntimeError("原Word保真历史修订标识或哈希变化")
        session.expunge(row)
        return row


def _target() -> tuple[dict[str, Any], str, dict[str, Any], str, str]:
    source = _source_version()
    source_document = copy.deepcopy(source.content_json)
    source_metrics = writing_collaboration_service.codec.metrics(source_document)
    for key, expected in EXPECTED_METRICS.items():
        if source_metrics.get(key) != expected:
            raise RuntimeError(f"原Word保真指标变化：{key}={source_metrics.get(key)} expected={expected}")

    target_document = copy.deepcopy(source_document)
    blocks = target_document.get("content") or []
    if not blocks or blocks[0].get("type") != "rawMarkdown":
        raise RuntimeError("原Word保真修订缺少受控元数据块")
    frontmatter = "\n".join(
        [
            "---",
            f"title: {json.dumps(TARGET_TITLE, ensure_ascii=False)}",
            "status: draft",
            "source_kind: docx",
            f"source_sha256: {SOURCE_WORD_SHA256}",
            f"content_version: {CONTENT_VERSION}",
            "source_fidelity: exact_original_text",
            "---",
        ]
    )
    blocks[0].setdefault("attrs", {})["markdown"] = frontmatter
    target_markdown = writing_collaboration_service.codec.to_markdown(target_document)
    target_metrics = writing_collaboration_service.codec.metrics(target_document)
    for key, expected in EXPECTED_METRICS.items():
        if target_metrics.get(key) != expected:
            raise RuntimeError(f"目标正文不再与原Word文本保真：{key}={target_metrics.get(key)} expected={expected}")

    required = [
        "课程编号：YJZT503",
        "兵棋推演与智能决策",
        "| 学 时： | 16 |",
        "本课程共10学时",
        "| 合计 | 16 | 4 | 12 |  |",
        "形成性考核和终结性考核相结合",
        "本教学计划从2024年9月开始执行",
    ]
    missing = [value for value in required if value not in target_markdown]
    banned = [value for value in ["One-Sim仿真平台", "AI Planning智能筹划系统", "L10综合考核"] if value in target_markdown]
    if missing or banned:
        raise RuntimeError(f"原版关键内容校验失败：missing={missing}, banned={banned}")

    target_content_sha = writing_collaboration_service.codec.document_sha256(target_document)
    target_working_sha = hashlib.sha256(target_markdown.encode("utf-8")).hexdigest()
    return target_document, target_markdown, target_metrics, target_content_sha, target_working_sha


def _root_binding() -> dict[str, Any]:
    return {
        "mode": "mapped",
        "source_document_id": "",
        "source_version": "",
        "source_sha256": "",
        "status": "missing",
        "integrity_status": "missing",
        "reference_status": "current",
        "referenced_document_revision": "",
        "referenced_document_sha256": "",
        "ppt_sha256": "",
        "mapped_items": 0,
        "unmapped_items": [],
        "changed_sections": [],
    }


def _lineage() -> dict[str, Any]:
    return {
        "series_id": "surface-wargame-course-plan-source",
        "edition_label": "authoritative-original-word-2025-10",
        "sequence": 1,
        "source_type": "docx",
        "parent_document_id": "",
        "source_checksum": SOURCE_WORD_SHA256,
        "generated_at": GENERATED_AT,
        "source_paths": [str(SOURCE_WORD)],
    }


def _metadata(current: dict[str, Any], target_revision: int, target_sha: str, metrics: dict[str, Any]) -> dict[str, Any]:
    layout = copy.deepcopy(current.get("layout_binding") or {})
    if layout:
        layout["status"] = "stale"
        layout["changed_reasons"] = ["正文已恢复为用户确认的原版Word，既有候选交付不代表当前正文"]
    fidelity = {
        "schema": "openclaw.document-content-fidelity.v1",
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "document_title": TARGET_TITLE,
        "source_kind": "docx",
        "source_sha256": SOURCE_WORD_SHA256,
        "structured_revision": target_revision,
        "structured_sha256": target_sha,
        "status": "passed",
        "migration_safe": True,
        "source_metrics": metrics,
        "structured_metrics": metrics,
        "differences": {},
        "unresolved_assets": [],
        "empty_formulas": [],
        "warnings": [
            "原版文件名为20课时，封面学时为16，正文另有共10学时表述；本修订按原文保留，不自动消解。"
        ],
        "audited_at": GENERATED_AT,
    }
    return {
        "last_actor": ACTOR,
        "content_fidelity": fidelity,
        "content_fidelity_current_status": "source_exact_text_restored_layout_release_stale",
        "course_plan_structure": {
            "schema": "openclaw.course-plan-source-fidelity.v1",
            "content_version": CONTENT_VERSION,
            "course_name_as_written": "兵棋推演与智能决策",
            "source_word": {"path": str(SOURCE_WORD), "sha256": SOURCE_WORD_SHA256},
            "content_chapters_as_written": 5,
            "implementation_rows_as_written": 8,
            "hours_as_written": {"filename": 20, "cover": 16, "body_statement": 10, "implementation_total": 16},
            "hours_conflict_status": "preserved_requires_human_resolution",
        },
        "source_authority": {
            "status": "user_confirmed_authoritative_original",
            "confirmed_at": GENERATED_AT,
            "path": str(SOURCE_WORD),
            "sha256": SOURCE_WORD_SHA256,
            "restored_from_revision": SOURCE_VERSION_REVISION,
        },
        "notes": [
            "用户确认该Word为正宗原版，当前结构化正文按其已审计内容恢复。",
            "原版内部学时口径并存，等待人工确认后再派生教学进度表与各讲教案。",
        ],
        "layout_binding": layout,
    }


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    if project_id != PROJECT_ID:
        raise RuntimeError("本迁移仅允许作用于冻结课程项目")
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError("课程项目不存在")
    if not SOURCE_WORD.is_file() or _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError("用户确认的原版Word不存在或SHA已变化")

    target_document, target_markdown, target_metrics, target_sha, target_working_sha = _target()
    before_state = _state(project, DOCUMENT_ID)
    before_document = multi_document_service.get_document(project, DOCUMENT_ID)
    other_before = _other_states(project)

    base_matches = all(
        [
            before_state["revision"] == BASE_REVISION,
            before_state["content_sha256"] == BASE_CONTENT_SHA256,
            before_state["working_sha256"] == BASE_WORKING_SHA256,
            before_state["projection_revision"] == BASE_REVISION,
            before_state["projection_status"] == "current",
            before_state["approved_revision"] == 0,
            before_state["published_revision"] == 0,
        ]
    )
    target_matches = all(
        [
            before_state["content_sha256"] == target_sha,
            before_state["working_sha256"] == target_working_sha,
            before_state["projection_revision"] == before_state["revision"],
            before_state["projection_status"] == "current",
            before_state["approved_revision"] == 0,
            before_state["published_revision"] == 0,
        ]
    )
    if not base_matches and not target_matches:
        raise RuntimeError(f"当前教学计划不是冻结r14或本迁移目标：{before_state}")

    target_revision = before_state["revision"] + 1 if not target_matches else before_state["revision"]
    desired_lineage = _lineage()
    desired_binding = _root_binding()
    desired_metadata = _metadata(before_document.get("metadata") or {}, target_revision, target_sha, target_metrics)
    desired_metadata["structure_binding"] = desired_binding
    catalog_patch = {
        "title": TARGET_TITLE,
        "data_source_ids": [],
        "source_refs": [],
        "rules_version": "",
        "data_version": DATA_VERSION,
        "expected_chapters": 0,
        "publication_status": "draft",
        "lineage": desired_lineage,
    }

    content_changed = not target_matches
    catalog_changed = any(before_document.get(key) != value for key, value in catalog_patch.items())
    current_metadata = before_document.get("metadata") or {}
    metadata_changed = any(current_metadata.get(key) != value for key, value in desired_metadata.items())
    binding_changed = multi_document_service.structure_binding(project, DOCUMENT_ID) != desired_binding
    context = copy.deepcopy(project.get("context") or {})
    desired_context = {
        "current_delivery_phase": PHASE_LABEL,
        "course_plan_authority_status": "original_word_restored_draft",
        "course_plan_hours_conflict": "filename20_cover16_body10_table16_requires_human_resolution",
        "next_step": "人工确认原版学时口径后，重新派生教学进度表与各讲教案；确认前不自动改写下游文档。",
    }
    context_changed = any(context.get(key) != value for key, value in desired_context.items())

    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "source_word": str(SOURCE_WORD),
        "source_word_sha256": SOURCE_WORD_SHA256,
        "restored_from_version_id": SOURCE_VERSION_ID,
        "restored_from_revision": SOURCE_VERSION_REVISION,
        "before": before_state,
        "target_revision": target_revision,
        "target_title": TARGET_TITLE,
        "target_content_sha256": target_sha,
        "target_working_sha256": target_working_sha,
        "target_metrics": target_metrics,
        "content_changed": content_changed,
        "catalog_changed": catalog_changed,
        "metadata_changed": metadata_changed,
        "binding_changed": binding_changed,
        "context_changed": context_changed,
        "other_documents": other_before,
    }
    if dry_run or not any([content_changed, catalog_changed, metadata_changed, binding_changed, context_changed]):
        return preview

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if content_changed:
        writing_collaboration_service.replace_authority_from_document(
            project,
            DOCUMENT_ID,
            target_document,
            target_markdown,
            label=PHASE_LABEL,
            actor=ACTOR,
        )
        project = project_manager.get_project(project_id) or project

    if catalog_changed:
        multi_document_service.update_document(project, DOCUMENT_ID, catalog_patch)
        project = project_manager.get_project(project_id) or project
    if metadata_changed:
        multi_document_service.update_document_metadata(project, DOCUMENT_ID, desired_metadata)
        project = project_manager.get_project(project_id) or project
    if context_changed:
        context.update(desired_context)
        project_manager.update_project(
            project_id,
            {"context": context, "current_phase": "course_plan_authoritative_original_restored"},
        )

    refreshed = project_manager.get_project(project_id) or project
    after_state = _state(refreshed, DOCUMENT_ID)
    after_document = multi_document_service.get_document(refreshed, DOCUMENT_ID)
    other_after = _other_states(refreshed)
    after_binding = multi_document_service.structure_binding(refreshed, DOCUMENT_ID)
    schedule_binding = multi_document_service.structure_binding(refreshed, OTHER_DOCUMENTS["schedule"][0])
    layout_state = document_layout_service.state(
        multi_document_service.rich_project_context(refreshed, DOCUMENT_ID)
    )

    if after_state["content_sha256"] != target_sha or after_state["working_sha256"] != target_working_sha:
        raise RuntimeError("写入后正文或投影SHA与dry-run目标不一致")
    if after_state["projection_revision"] != after_state["revision"] or after_state["projection_status"] != "current":
        raise RuntimeError("写入后Markdown投影未对齐")
    if after_document.get("title") != TARGET_TITLE or int(after_document.get("expected_chapters") or 0) != 0:
        raise RuntimeError("写入后目录标题或原版结构声明不一致")
    if after_binding != desired_binding:
        raise RuntimeError(f"写入后原Word权威绑定不一致：{after_binding}")
    if schedule_binding.get("reference_status") != "document_updated":
        raise RuntimeError(f"下游教学进度表未显式进入待重派生状态：{schedule_binding}")
    if other_after != other_before:
        raise RuntimeError("下游进度表或教案正文发生变化，违反单文档迁移边界")
    if (layout_state.get("binding") or {}).get("status") != "stale":
        raise RuntimeError(f"既有Word候选交付未正确标记过期：{layout_state.get('binding')}")
    if _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError("原版Word在迁移期间发生变化")

    return {
        **preview,
        "dry_run": False,
        "snapshot": str(snapshot),
        "after": after_state,
        "catalog_title": after_document.get("title"),
        "expected_chapters": after_document.get("expected_chapters"),
        "publication_status": after_document.get("publication_status"),
        "source_binding": after_binding,
        "schedule_binding": schedule_binding,
        "layout_binding_status": (layout_state.get("binding") or {}).get("status"),
        "layout_changed_reasons": (layout_state.get("binding") or {}).get("changed_reasons"),
        "other_documents_unchanged": other_after == other_before,
        "source_word_unchanged": _sha256(SOURCE_WORD) == SOURCE_WORD_SHA256,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
