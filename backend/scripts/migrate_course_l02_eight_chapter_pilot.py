#!/usr/bin/env python3
"""Install the L02 eight-chapter lesson-plan pilot from frozen authorities."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path("/Users/apple/工作桌面/Workspace/agent-system/backend")
sys.path.insert(0, str(BACKEND))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PROJECT_ID = "proj-16ca49b862"
COURSE_PLAN_ID = "doc-e811bedd87f9"
SCHEDULE_ID = "doc-2a28da7429f0"
DOCUMENT_ID = "doc-6085f649c11a"
DOCUMENT_TITLE = "第2讲：水面舰艇编队战术、推演流程与裁决方法"

COURSE_PLAN_REVISION = 14
COURSE_PLAN_CONTENT_SHA256 = "f315d92c7a21a5ba89503f3dbb2420fb382ef4eff547f590ef5dc8de7bfb5623"
COURSE_PLAN_WORKING_SHA256 = "e681c44bff1f5be27b4a124b4601f7825cab5e6861258b6cf7c365c33d712114"
SCHEDULE_REVISION = 16
SCHEDULE_CONTENT_SHA256 = "b35fd5152f2b25ac119e5d38fc01672a54c044950ce3026cf43fa1f128bbda19"
SCHEDULE_WORKING_SHA256 = "cd3937fe98b3c8b95b358957213ba6505b336ebb1e2f681d7065b730a423cdbf"
L02_BASE_REVISION = 12
L02_BASE_CONTENT_SHA256 = "cf59ca0e586f46ff6d6281aa7a55a2105e48250899bcd41732fabe1a26b0b0b0"
L02_BASE_WORKING_SHA256 = "de2763ea9825857ee7bc1946d68f669299412b6def6894baf62be81ab45d15b5"

SOURCE_WORD = Path(
    "/Users/apple/工作桌面/knowledge/06-项目库-Projects/"
    "水面舰艇作战软件与兵棋推演课程--proj-16ca49b862/教案/第2讲-兵棋推演流程及运用.docx"
)
SOURCE_WORD_SHA256 = "212a7ec7e445badc7844135ba6548ea29aab55f497c7e0835418bb6642ba8856"
CONTENT_FILE = Path(__file__).with_name("course_l02_eight_chapter_pilot.md")
CONTENT_FILE_SHA256 = "420354f2e4f142325bb40b3d581e064dc8f25514907ab64ce3563b89553d81d8"

CONTENT_VERSION = "course-lesson-l02-eight-chapter-pilot-v1"
ACTOR = "course-l02-eight-chapter-pilot"
PHASE_LABEL = "课程教案第五阶段：L02八章样板"
GENERATED_AT = "2026-08-23T09:00:00+00:00"

OTHER_LESSONS = {
    "L01": ("doc-3a9dbb65b9a3", 64, "2021462daed265c26645f297545673ebcd87036a72fa0d01f390bb02f961d220"),
    "L03": ("doc-105f2073f3d9", 10, "31e2d785937fc8a8377c8370ebc081b8d8be03c0728d3b6333b3403a562ce858"),
    "L04": ("doc-9c47a19819ed", 12, "fb53099ea49c040568a13bad8476115dc32a33c2ede5c910a7ee975339cefdca"),
    "L05": ("doc-e542cf30905a", 12, "ff2a3f37a28a34612eb9539872e0429d1ca3784bd0c3451fb2011a0c3c45a973"),
    "L06": ("doc-9df3ab46770c", 12, "f7e6c1af4b30267c9f79406405600c48a6219d10e240902d3176477462898dc3"),
    "L07": ("doc-60e4858f35af", 12, "72836823c3c1500e4f19054252fc70d80f046e0450a67b3915a9b43727245673"),
    "L08": ("doc-8248d6366ec3", 12, "1f71c3163532096563d645fcd7b0f54460d93ae5a4dc02d791697861cf2201cb"),
    "L09": ("doc-729fe58abb5a", 12, "4ea207564e324dbeee3db16f789ea5309e5bcf105e954ff07f5224e2868ace5f"),
    "L10": ("doc-dab8a79a74dc", 12, "0ef36d1d977e56970b6d18fe4a6dbf0b22ef2ee94f2b83598279833c259c6caf"),
}

CHAPTER_TITLES = [
    "第一章 教学定位、目标与达成证据",
    "第二章 学情分析、先修条件与教学准备",
    "第三章 教学重点、难点与关键问题",
    "第四章 教学内容体系与教员讲授提纲",
    "第五章 课堂过程、师生活动与120分钟脚本",
    "第六章 教学方法、组织实施与人机协同边界",
    "第七章 学习成果、评价量规、课后任务与下讲移交",
    "第八章 来源依据、配套材料与课后反思",
]

SOURCE_REFS = [
    {
        "ref_type": "project_document",
        "project_id": "proj-c57e28f8e0",
        "document_id": "doc-0d2362510580",
        "product_id": "",
        "relation": "authoritative_rule",
        "required": True,
        "version": "R1.2/D1.2",
    },
    {
        "ref_type": "project_document",
        "project_id": "proj-c57e28f8e0",
        "document_id": "doc-0522adjud01",
        "product_id": "",
        "relation": "adjudication_rule",
        "required": True,
        "version": "R1.2/D1.2",
    },
    {
        "ref_type": "project_document",
        "project_id": "proj-c57e28f8e0",
        "document_id": "doc-0522operator",
        "product_id": "",
        "relation": "operator_table",
        "required": True,
        "version": "R1.2/D1.2",
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _working_path(project: dict[str, Any], document_id: str) -> Path:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    path = Path(str(manifest.get("working_markdown") or ""))
    if not path.is_file():
        raise RuntimeError(f"工作稿不存在：{document_id} {path}")
    return path


def _state_evidence(project: dict[str, Any], document_id: str) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, document_id)
    path = _working_path(project, document_id)
    return {
        "document_id": document_id,
        "revision": int(state.get("document_revision") or 0),
        "content_sha256": writing_collaboration_service.codec.document_sha256(state["document"]),
        "working_markdown": str(path),
        "working_sha256": _sha256(path),
        "projection_revision": int((state.get("projection") or {}).get("revision") or 0),
        "projection_status": str((state.get("projection") or {}).get("status") or ""),
        "approved_revision": int(state.get("approved_revision") or 0),
        "published_revision": int(state.get("published_revision") or 0),
    }


def _assert_state(evidence: dict[str, Any], revision: int, content_sha: str, working_sha: str) -> None:
    expected = {
        "revision": revision,
        "content_sha256": content_sha,
        "working_sha256": working_sha,
        "projection_revision": revision,
        "projection_status": "current",
        "approved_revision": 0,
        "published_revision": 0,
    }
    mismatches = {key: (evidence.get(key), value) for key, value in expected.items() if evidence.get(key) != value}
    if mismatches:
        raise RuntimeError(f"生产基线已变化，停止迁移：{evidence['document_id']} {mismatches}")


def _validate_frozen_inputs(
    project: dict[str, Any],
    target_content_sha: str,
    target_working_sha: str,
) -> dict[str, Any]:
    plan = _state_evidence(project, COURSE_PLAN_ID)
    schedule = _state_evidence(project, SCHEDULE_ID)
    l02 = _state_evidence(project, DOCUMENT_ID)
    _assert_state(plan, COURSE_PLAN_REVISION, COURSE_PLAN_CONTENT_SHA256, COURSE_PLAN_WORKING_SHA256)
    _assert_state(schedule, SCHEDULE_REVISION, SCHEDULE_CONTENT_SHA256, SCHEDULE_WORKING_SHA256)
    if l02["revision"] == L02_BASE_REVISION:
        _assert_state(l02, L02_BASE_REVISION, L02_BASE_CONTENT_SHA256, L02_BASE_WORKING_SHA256)
    elif not all(
        [
            l02["content_sha256"] == target_content_sha,
            l02["working_sha256"] == target_working_sha,
            l02["projection_revision"] == l02["revision"],
            l02["projection_status"] == "current",
            l02["approved_revision"] == 0,
            l02["published_revision"] == 0,
        ]
    ):
        raise RuntimeError(f"L02不是冻结基线或本脚本目标修订，停止迁移：{l02}")
    if not SOURCE_WORD.is_file() or _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError(f"L02原Word来源已变化：{SOURCE_WORD}")
    if not CONTENT_FILE.is_file() or _sha256(CONTENT_FILE) != CONTENT_FILE_SHA256:
        raise RuntimeError(f"L02目标正文文件已变化：{CONTENT_FILE}")
    return {
        "course_plan": plan,
        "schedule": schedule,
        "l02": l02,
        "source_word_sha256": SOURCE_WORD_SHA256,
        "content_file_sha256": CONTENT_FILE_SHA256,
    }


def _other_lesson_states(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for lesson, (document_id, revision, content_sha) in OTHER_LESSONS.items():
        state = writing_collaboration_service.get_state(project, document_id)
        current_revision = int(state.get("document_revision") or 0)
        current_sha = writing_collaboration_service.codec.document_sha256(state["document"])
        if current_revision != revision or current_sha != content_sha:
            raise RuntimeError(
                f"{lesson}基线已变化，停止L02单文档迁移："
                f"revision={current_revision}, sha={current_sha}"
            )
        result[lesson] = {"document_id": document_id, "revision": revision, "content_sha256": content_sha}
    return result


def _chapter_body(markdown: str, title: str) -> str:
    marker = f"# {title}\n"
    if marker not in markdown:
        return ""
    tail = markdown.split(marker, 1)[1]
    next_heading = re.search(r"(?m)^# ", tail)
    return tail[: next_heading.start()] if next_heading else tail


def _checks(markdown: str) -> dict[str, Any]:
    h1 = [line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")]
    chapters = [title for title in h1 if title in CHAPTER_TITLES]
    intervals = [
        (int(start), int(end))
        for start, end in re.findall(r"(?m)^\| (\d+)-(\d+)分钟 \|", markdown)
    ]
    banned = [
        "水面舰艇指挥决策与兵棋推演",
        "兵棋推演与智能决策",
        "计划学时: 16",
        "Sigma",
        "千年挑战",
        "俄罗斯攻打乌克兰",
        "海湾战争",
        "海湾打击",
        "纳什均衡",
        "大数定理",
        "马尔可夫过程",
        "攻击时命中概率最高",
        "以最小损失获得最大利益",
    ]
    required_outputs = ["编队协同关系图", "裁决流程卡", "命令闭环卡", "L03预习清单"]
    chapter4 = _chapter_body(markdown, CHAPTER_TITLES[3])
    chapter5 = _chapter_body(markdown, CHAPTER_TITLES[4])
    chapter6 = _chapter_body(markdown, CHAPTER_TITLES[5])
    chapter7 = _chapter_body(markdown, CHAPTER_TITLES[6])
    chapter8 = _chapter_body(markdown, CHAPTER_TITLES[7])
    return {
        "content_version": CONTENT_VERSION in markdown,
        "document_title": DOCUMENT_TITLE in markdown,
        "parent_schedule": all(
            token in markdown for token in [SCHEDULE_ID, "parent_revision: 16", SCHEDULE_CONTENT_SHA256]
        ),
        "upstream_plan": COURSE_PLAN_ID in markdown and "upstream_course_plan_revision: 14" in markdown,
        "source_word": SOURCE_WORD_SHA256 in markdown,
        "chapter_count": len(chapters),
        "chapter_order": chapters,
        "chapter_order_valid": chapters == CHAPTER_TITLES,
        "intervals": intervals,
        "intervals_valid": intervals
        == [(0, 8), (8, 25), (25, 42), (42, 58), (58, 75), (75, 95), (95, 110), (110, 120)],
        "minutes_total": sum(end - start for start, end in intervals),
        "required_outputs": {token: markdown.count(token) for token in required_outputs},
        "schedule_outputs_present": all(markdown.count(token) >= 4 for token in required_outputs),
        "diagnostic_not_scored": all(
            token in markdown for token in ["诊断性评价", "诊断、不计分", "不计入课程过程性实作40分"]
        ),
        "quality_sections": all(
            token in markdown
            for token in ["教学目标", "学情分析", "教学重点", "教学难点", "教学内容", "教学方法", "时间分配", "课后任务", "来源依据"]
        ),
        "handoff_l03": all(
            token in chapter7
            for token in ["向L03移交", "组件", "版本确认", "规则", "裁决表", "算子表"]
        ),
        "platform_boundary": all(
            token in chapter6
            for token in [
                "One-Sim仿真平台",
                "AI Planning智能筹划系统",
                "本讲不登录、不操作上述系统",
                "软件不得补造想定信息",
                "不得直接生成课程成绩",
            ]
        ),
        "content_depth": {
            "total_chars": len(markdown),
            "chapter4_chars": len(chapter4),
            "chapter5_chars": len(chapter5),
            "chapter6_chars": len(chapter6),
            "chapter7_chars": len(chapter7),
            "chapter8_chars": len(chapter8),
        },
        "content_depth_valid": all(
            [
                len(markdown) >= 13000,
                len(chapter4) >= 3600,
                len(chapter5) >= 1200,
                len(chapter6) >= 1000,
                len(chapter7) >= 1200,
                len(chapter8) >= 1500,
            ]
        ),
        "source_scope": all(
            token in chapter8
            for token in ["修订14", "修订16", "原Word共16页、7幅内嵌图片", "插图锚点", "课后反思"]
        ),
        "figure_anchors": all(f"L02-F0{index}" in chapter8 for index in range(1, 6)),
        "banned_hits": [token for token in banned if token in markdown],
    }


def _checks_pass(checks: dict[str, Any]) -> bool:
    return all(
        [
            checks["content_version"],
            checks["document_title"],
            checks["parent_schedule"],
            checks["upstream_plan"],
            checks["source_word"],
            checks["chapter_count"] == 8,
            checks["chapter_order_valid"],
            checks["intervals_valid"],
            checks["minutes_total"] == 120,
            checks["schedule_outputs_present"],
            checks["diagnostic_not_scored"],
            checks["quality_sections"],
            checks["handoff_l03"],
            checks["platform_boundary"],
            checks["content_depth_valid"],
            checks["source_scope"],
            checks["figure_anchors"],
            not checks["banned_hits"],
        ]
    )


def _target_hashes(markdown: str) -> tuple[str, str]:
    document = writing_collaboration_service.codec.from_markdown(
        markdown,
        namespace=f"{PROJECT_ID}/{DOCUMENT_ID}/authority-import",
    )
    canonical_markdown = writing_collaboration_service.codec.to_markdown(document)
    return (
        writing_collaboration_service.codec.document_sha256(document),
        hashlib.sha256(canonical_markdown.encode("utf-8")).hexdigest(),
    )


def _lineage(schedule: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": "surface-wargame-course-lessons",
        "edition_label": "schedule-r16",
        "sequence": 2,
        "source_type": "structured_authority",
        "parent_document_id": SCHEDULE_ID,
        "source_checksum": schedule["content_sha256"],
        "generated_at": GENERATED_AT,
        "source_paths": [schedule["working_markdown"]],
    }


def _structure_metadata(inputs: dict[str, Any], target_sha: str) -> dict[str, Any]:
    return {
        "schema": "openclaw.course-lesson-structure.v1",
        "content_version": CONTENT_VERSION,
        "lesson_id": "L02",
        "chapter_count": 8,
        "chapter_titles": CHAPTER_TITLES,
        "direct_parent": {
            "document_id": SCHEDULE_ID,
            "revision": SCHEDULE_REVISION,
            "content_sha256": SCHEDULE_CONTENT_SHA256,
            "working_sha256": SCHEDULE_WORKING_SHA256,
        },
        "upstream_course_plan": {
            "document_id": COURSE_PLAN_ID,
            "revision": COURSE_PLAN_REVISION,
            "content_sha256": COURSE_PLAN_CONTENT_SHA256,
        },
        "source_word": {
            "path": str(SOURCE_WORD),
            "sha256": SOURCE_WORD_SHA256,
            "pages": 16,
            "embedded_images": 7,
            "use_mode": "curated_content_reference",
            "excluded": [
                "old_course_name",
                "old_hours",
                "unverified_history",
                "unverified_ai_model",
                "legacy_layout",
            ],
        },
        "schedule_contract": {
            "input": ["L01诊断成果", "编队作战问题"],
            "objective": ["CO1"],
            "activities": ["编队行动链", "命令闭环", "人工裁决流程分析"],
            "outputs": ["编队协同关系图", "裁决流程卡", "命令闭环卡", "L03预习清单"],
            "evaluation": "diagnostic_not_scored",
            "handoff": "L03组件与规则查用",
        },
        "target_content_sha256": target_sha,
        "generated_at": GENERATED_AT,
        "validated_parent_revision": inputs["schedule"]["revision"],
    }


def _binding_is_current(binding: dict[str, Any]) -> bool:
    return all(
        [
            binding.get("mode") == "derived",
            binding.get("source_document_id") == SCHEDULE_ID,
            binding.get("referenced_document_revision") == f"v{SCHEDULE_REVISION}",
            binding.get("referenced_document_sha256") == SCHEDULE_WORKING_SHA256,
            binding.get("reference_status") == "current",
            binding.get("status") == "aligned",
            binding.get("integrity_status") == "aligned",
            binding.get("mapped_items") == 1,
            not binding.get("unmapped_items"),
            not binding.get("changed_sections"),
        ]
    )


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"项目不存在：{project_id}")

    if not CONTENT_FILE.is_file() or _sha256(CONTENT_FILE) != CONTENT_FILE_SHA256:
        raise RuntimeError(f"L02目标正文文件已变化：{CONTENT_FILE}")
    target = CONTENT_FILE.read_text(encoding="utf-8").strip() + "\n"
    checks = _checks(target)
    if not _checks_pass(checks):
        raise RuntimeError(f"L02目标正文自检未通过：{checks}")
    target_sha, target_working_sha = _target_hashes(target)
    inputs = _validate_frozen_inputs(project, target_sha, target_working_sha)
    other_before = _other_lesson_states(project)

    current_path = _working_path(project, DOCUMENT_ID)
    before = current_path.read_text(encoding="utf-8")
    before_state = writing_collaboration_service.get_state(project, DOCUMENT_ID)
    before_document = multi_document_service.get_document(project, DOCUMENT_ID)
    before_binding = multi_document_service.structure_binding(project, DOCUMENT_ID)
    lineage = _lineage(inputs["schedule"])
    structure_metadata = _structure_metadata(inputs, target_sha)
    metadata = before_document.get("metadata") or {}

    before_content_sha = writing_collaboration_service.codec.document_sha256(before_state["document"])
    content_changed = before_content_sha != target_sha
    catalog_changed = any(
        [
            before_document.get("title") != DOCUMENT_TITLE,
            int(before_document.get("expected_chapters") or 0) != 8,
            before_document.get("rules_version") != "R1.2",
            before_document.get("data_version") != "course-baseline-20h-v4",
            before_document.get("publication_status") != "draft",
            before_document.get("source_refs") != SOURCE_REFS,
            before_document.get("lineage") != lineage,
        ]
    )
    metadata_changed = any(
        [
            metadata.get("last_actor") != ACTOR,
            metadata.get("course_lesson_structure") != structure_metadata,
            metadata.get("content_fidelity_current_status") != "curated_revision_requires_docx_release_qa",
        ]
    )
    binding_changed = not _binding_is_current(before_binding)
    context = copy.deepcopy(project.get("context") or {})
    desired_context = {
        "current_delivery_phase": PHASE_LABEL,
        "course_lesson_pilot_status": "L01_L02_draft_ready_for_review",
        "next_step": "只读审计L03原Word与现有结构化正文的主题错配；在污染边界确认前不迁移L03。",
    }
    context_changed = any(context.get(key) != value for key, value in desired_context.items())

    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "document_id": DOCUMENT_ID,
        "frozen_inputs": inputs,
        "before_revision": int(before_state.get("document_revision") or 0),
        "before_content_sha256": before_content_sha,
        "before_working_sha256": _sha256(current_path),
        "before_chars": len(before),
        "after_chars": len(target),
        "target_content_sha256": target_sha,
        "target_working_sha256": target_working_sha,
        "content_changed": content_changed,
        "catalog_changed": catalog_changed,
        "metadata_changed": metadata_changed,
        "binding_changed": binding_changed,
        "context_changed": context_changed,
        "before_binding": before_binding,
        "other_lessons": other_before,
        "checks": checks,
    }
    if dry_run or not any([content_changed, catalog_changed, metadata_changed, binding_changed, context_changed]):
        return preview

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if content_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            DOCUMENT_ID,
            target,
            label=PHASE_LABEL,
            actor=ACTOR,
        )
        project = project_manager.get_project(project_id) or project

    _validate_frozen_inputs(project, target_sha, target_working_sha)
    if catalog_changed:
        multi_document_service.update_document(
            project,
            DOCUMENT_ID,
            {
                "title": DOCUMENT_TITLE,
                "expected_chapters": 8,
                "rules_version": "R1.2",
                "data_version": "course-baseline-20h-v4",
                "publication_status": "draft",
                "source_refs": SOURCE_REFS,
                "lineage": lineage,
            },
        )
        project = project_manager.get_project(project_id) or project
    if metadata_changed:
        multi_document_service.update_document_metadata(
            project,
            DOCUMENT_ID,
            {
                "last_actor": ACTOR,
                "course_lesson_structure": structure_metadata,
                "content_fidelity_current_status": "curated_revision_requires_docx_release_qa",
            },
        )
        project = project_manager.get_project(project_id) or project
    if binding_changed:
        multi_document_service.set_structure_binding(
            project,
            DOCUMENT_ID,
            {
                "mode": "derived",
                "source_document_id": SCHEDULE_ID,
                "status": "aligned",
                "integrity_status": "aligned",
                "reference_status": "current",
                "mapped_items": 1,
                "unmapped_items": [],
                "changed_sections": [],
            },
        )
        project = project_manager.get_project(project_id) or project
    if context_changed:
        context.update(desired_context)
        project_manager.update_project(
            project_id,
            {"context": context, "current_phase": "course_lesson_l02_eight_chapter_pilot"},
        )

    refreshed = project_manager.get_project(project_id) or project
    document_workspace_service.ensure_workspace(
        multi_document_service.rich_project_context(refreshed, DOCUMENT_ID)
    )
    after_path = _working_path(refreshed, DOCUMENT_ID)
    after = after_path.read_text(encoding="utf-8")
    after_state = writing_collaboration_service.get_state(refreshed, DOCUMENT_ID)
    after_document = multi_document_service.get_document(refreshed, DOCUMENT_ID)
    final_binding = multi_document_service.structure_binding(refreshed, DOCUMENT_ID)
    after_checks = _checks(after)
    other_after = _other_lesson_states(refreshed)

    if not _checks_pass(after_checks):
        raise RuntimeError(f"写入后内容自检未通过：{after_checks}")
    if writing_collaboration_service.codec.document_sha256(after_state["document"]) != target_sha:
        raise RuntimeError("写入后结构化正文SHA与dry-run目标不一致")
    if not _binding_is_current(final_binding):
        raise RuntimeError(f"写入后结构绑定未对齐：{final_binding}")
    if after_document.get("lineage") != lineage:
        raise RuntimeError(f"写入后lineage不一致：{after_document.get('lineage')}")
    if other_after != other_before:
        raise RuntimeError("L01及L03-L10状态发生变化，违反单文档迁移边界")
    if _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError("L02原Word在迁移期间发生变化")
    if _sha256(CONTENT_FILE) != CONTENT_FILE_SHA256:
        raise RuntimeError("L02目标正文文件在迁移期间发生变化")

    return {
        **preview,
        "dry_run": False,
        "snapshot": str(snapshot),
        "after_revision": int(after_state.get("document_revision") or 0),
        "after_content_sha256": writing_collaboration_service.codec.document_sha256(after_state["document"]),
        "after_working_sha256": _sha256(after_path),
        "projection_revision": (after_state.get("projection") or {}).get("revision"),
        "projection_status": (after_state.get("projection") or {}).get("status"),
        "approved_revision": after_state.get("approved_revision"),
        "published_revision": after_state.get("published_revision"),
        "expected_chapters": after_document.get("expected_chapters"),
        "publication_status": after_document.get("publication_status"),
        "lineage": after_document.get("lineage"),
        "binding": final_binding,
        "other_lessons_unchanged": other_after == other_before,
        "source_word_unchanged": _sha256(SOURCE_WORD) == SOURCE_WORD_SHA256,
        "content_file_unchanged": _sha256(CONTENT_FILE) == CONTENT_FILE_SHA256,
        "checks": after_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
