#!/usr/bin/env python3
"""Normalize the 20-hour plan to chapter headings recognized by 3021."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


BACKEND = Path("/Users/apple/工作桌面/Workspace/agent-system/backend")
sys.path.insert(0, str(BACKEND))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_course_plan_20h_authority as base  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PROJECT_ID = base.PROJECT_ID
PLAN_ID = base.PLAN_ID
SCHEDULE_ID = base.SCHEDULE_ID
L01_ID = base.L01_ID
L02_ID = base.L02_ID

PLAN_BASE_REVISION = 16
PLAN_BASE_SHA256 = "a4c2fefe1d70bd99f5880c301fd880dbfe16254f4a1dde97fe83ac5a04b91e0e"
SCHEDULE_BASE_REVISION = 17
SCHEDULE_BASE_SHA256 = "d695e9af5fb97ecb7309d9ad71531c53c987fda581f25073ade6a431762c31d7"
L01_BASE_REVISION = 65
L01_BASE_SHA256 = "3e0031e2edc41d0a8c737308df98e1f35f82dea46937f35069d6e5286119b8ce"
L02_BASE_REVISION = 14
L02_BASE_SHA256 = "59ca7631ac585b4783d03a5f3f4b6e019e914bd13b64323da19f4a5cae8fd3b3"

PLAN_CONTENT_VERSION = "course-plan-original-word-resolved-20h-v3"
SCHEDULE_CONTENT_VERSION = "course-schedule-derived-from-plan-r17-20h-v3"
PHASE_LABEL = "课程教学计划：20学时章节结构规范化"
ACTOR = "course-plan-20h-chapter-normalization"
NORMALIZED_AT = "2026-08-24T12:30:00+08:00"


def _plan_markdown(current: str) -> str:
    value = base._replace_exact(  # noqa: SLF001
        current,
        f"content_version: {base.PLAN_CONTENT_VERSION}",
        f"content_version: {PLAN_CONTENT_VERSION}",
        "教学计划内容版本",
    )
    headings = {
        "# 一、教学目标": "# 第一章 教学目标",
        "# 二、课程内容与教学要求": "# 第二章 课程内容与教学要求",
        "# 三、教学设计": "# 第三章 教学设计",
        "# 四、实施过程": "# 第四章 实施过程",
        "# 五、课程实验（实作）实施方案": "# 第五章 课程实验（实作）实施方案",
        "# 六、考核评价": "# 第六章 考核评价",
        "# 七、保障条件": "# 第七章 保障条件",
        "# 八、附录": "# 第八章 附录",
    }
    for old, new in headings.items():
        value = base._replace_exact(value, old, new, old)  # noqa: SLF001
    return value


def _schedule_markdown(current: str, plan_sha: str) -> str:
    value = current
    replacements = {
        f'content_version: "{base.SCHEDULE_CONTENT_VERSION}"': f'content_version: "{SCHEDULE_CONTENT_VERSION}"',
        "parent_revision: 16": "parent_revision: 17",
        f'parent_content_sha256: "{PLAN_BASE_SHA256}"': f'parent_content_sha256: "{plan_sha}"',
        "课程教学计划修订16派生": "课程教学计划修订17派生",
        "| 课程计划权威 | doc-e811bedd87f9，修订16 |": "| 课程计划权威 | doc-e811bedd87f9，修订17 |",
    }
    for old, new in replacements.items():
        value = base._replace_exact(value, old, new, old)  # noqa: SLF001
    return value


def _lesson_markdown(current: str, schedule_sha: str) -> str:
    value = current
    replacements = {
        "parent_revision: 17": "parent_revision: 18",
        f'parent_content_sha256: "{SCHEDULE_BASE_SHA256}"': f'parent_content_sha256: "{schedule_sha}"',
        "upstream_course_plan_revision: 16": "upstream_course_plan_revision: 17",
    }
    for old, new in replacements.items():
        value = base._replace_exact(value, old, new, old)  # noqa: SLF001
    value = base._replace_all(value, "教学进度表修订17", "教学进度表修订18", "教案可见进度表修订")  # noqa: SLF001
    value = base._replace_all(value, "教学计划修订16", "教学计划修订17", "教案可见教学计划修订")  # noqa: SLF001
    old_short = f"{SCHEDULE_BASE_SHA256[:8]}…{SCHEDULE_BASE_SHA256[-8:]}"
    if old_short in value:
        value = value.replace(old_short, f"{schedule_sha[:8]}…{schedule_sha[-8:]}")
    return value


def _assert_plan(markdown: str) -> None:
    headings = [
        "# 第一章 教学目标",
        "# 第二章 课程内容与教学要求",
        "# 第三章 教学设计",
        "# 第四章 实施过程",
        "# 第五章 课程实验（实作）实施方案",
        "# 第六章 考核评价",
        "# 第七章 保障条件",
        "# 第八章 附录",
    ]
    missing = [heading for heading in headings if heading not in markdown]
    stale = [line for line in markdown.splitlines() if line.startswith("# ") and line not in headings]
    if missing or stale:
        raise RuntimeError(f"教学计划章节规范化失败：missing={missing}, stale={stale}")
    base._assert_plan(  # noqa: SLF001
        markdown.replace("# 第一章 教学目标", "# 一、教学目标")
        .replace("# 第二章 课程内容与教学要求", "# 二、课程内容与教学要求")
        .replace("# 第三章 教学设计", "# 三、教学设计")
        .replace("# 第四章 实施过程", "# 四、实施过程")
        .replace("# 第五章 课程实验（实作）实施方案", "# 五、课程实验（实作）实施方案")
        .replace("# 第六章 考核评价", "# 六、考核评价")
        .replace("# 第七章 保障条件", "# 七、保障条件")
        .replace("# 第八章 附录", "# 八、附录")
    )


def _refresh_binding(project: dict[str, Any], document_id: str) -> None:
    base._refresh_binding(project, document_id)  # noqa: SLF001


def _target(document_id: str, markdown: str) -> dict[str, Any]:
    return base._target(document_id, markdown)  # noqa: SLF001


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    if project_id != PROJECT_ID:
        raise RuntimeError("本迁移仅允许作用于冻结课程项目")
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError("课程项目不存在")

    plan_before = base._state(project, PLAN_ID)  # noqa: SLF001
    schedule_before = base._state(project, SCHEDULE_ID)  # noqa: SLF001
    l01_before = base._state(project, L01_ID)  # noqa: SLF001
    l02_before = base._state(project, L02_ID)  # noqa: SLF001

    plan_source = Path(plan_before["working_path"]).read_text(encoding="utf-8")
    plan_markdown = _plan_markdown(plan_source) if plan_before["content_sha256"] == PLAN_BASE_SHA256 else plan_source
    _assert_plan(plan_markdown)
    plan_target = _target(PLAN_ID, plan_markdown)

    schedule_source = Path(schedule_before["working_path"]).read_text(encoding="utf-8")
    schedule_markdown = (
        _schedule_markdown(schedule_source, plan_target["content_sha256"])
        if schedule_before["content_sha256"] == SCHEDULE_BASE_SHA256
        else schedule_source
    )
    required_schedule = ["parent_revision: 17", plan_target["content_sha256"], "课程教学计划修订17派生"]
    if not all(token in schedule_markdown for token in required_schedule):
        raise RuntimeError("教学进度表未对齐教学计划修订17")
    schedule_target = _target(SCHEDULE_ID, schedule_markdown)

    lesson_targets: dict[str, dict[str, Any]] = {}
    for name, document_id, before, base_sha in [
        ("L01", L01_ID, l01_before, L01_BASE_SHA256),
        ("L02", L02_ID, l02_before, L02_BASE_SHA256),
    ]:
        source = Path(before["working_path"]).read_text(encoding="utf-8")
        markdown = _lesson_markdown(source, schedule_target["content_sha256"]) if before["content_sha256"] == base_sha else source
        if "教学计划修订16" in markdown or "教学进度表修订17" in markdown:
            raise RuntimeError(f"{name}仍含过时修订")
        lesson_targets[name] = _target(document_id, markdown)

    checks = {
        "plan": plan_before["content_sha256"] in {PLAN_BASE_SHA256, plan_target["content_sha256"]},
        "schedule": schedule_before["content_sha256"] in {SCHEDULE_BASE_SHA256, schedule_target["content_sha256"]},
        "L01": l01_before["content_sha256"] in {L01_BASE_SHA256, lesson_targets["L01"]["content_sha256"]},
        "L02": l02_before["content_sha256"] in {L02_BASE_SHA256, lesson_targets["L02"]["content_sha256"]},
    }
    if not all(checks.values()):
        raise RuntimeError(f"规范化基线变化：{checks}")

    plan_changed = plan_before["content_sha256"] != plan_target["content_sha256"]
    schedule_changed = schedule_before["content_sha256"] != schedule_target["content_sha256"]
    l01_changed = l01_before["content_sha256"] != lesson_targets["L01"]["content_sha256"]
    l02_changed = l02_before["content_sha256"] != lesson_targets["L02"]["content_sha256"]
    plan_revision = plan_before["revision"] + 1 if plan_changed else plan_before["revision"]
    schedule_revision = schedule_before["revision"] + 1 if schedule_changed else schedule_before["revision"]

    plan_record = multi_document_service.get_document(project, PLAN_ID)
    plan_metadata = copy.deepcopy(plan_record.get("metadata") or {})
    fidelity = copy.deepcopy(plan_metadata.get("content_fidelity") or {})
    fidelity.update(
        {
            "structured_revision": plan_revision,
            "structured_sha256": plan_target["content_sha256"],
            "structured_metrics": plan_target["metrics"],
            "audited_at": NORMALIZED_AT,
        }
    )
    differences = copy.deepcopy(fidelity.get("differences") or {})
    differences["structure"] = "一级标题规范为第一章至第八章，以符合3021章节解析契约"
    fidelity["differences"] = differences
    plan_metadata.update(
        {
            "last_actor": ACTOR,
            "content_fidelity": fidelity,
            "content_fidelity_current_status": "source_based_user_confirmed_20h_revision_chapter_structure_current_layout_release_stale",
        }
    )
    structure = copy.deepcopy(plan_metadata.get("course_plan_structure") or {})
    structure["content_version"] = PLAN_CONTENT_VERSION
    structure["chapter_parser_contract"] = "第一章至第八章"
    plan_metadata["course_plan_structure"] = structure

    schedule_record = multi_document_service.get_document(project, SCHEDULE_ID)
    schedule_metadata = copy.deepcopy(schedule_record.get("metadata") or {})
    schedule_metadata.update(
        {
            "last_actor": ACTOR,
            "parent_authority": {
                "document_id": PLAN_ID,
                "revision": plan_revision,
                "content_sha256": plan_target["content_sha256"],
                "status": "current",
            },
            "notes": ["20学时、10讲实施投影，与章节结构规范化后的课程教学计划修订17对齐。"],
        }
    )

    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "before": {"plan": plan_before, "schedule": schedule_before, "L01": l01_before, "L02": l02_before},
        "targets": {
            "plan": {key: value for key, value in plan_target.items() if key not in {"markdown", "document"}},
            "schedule": {key: value for key, value in schedule_target.items() if key not in {"markdown", "document"}},
            "L01_sha256": lesson_targets["L01"]["content_sha256"],
            "L02_sha256": lesson_targets["L02"]["content_sha256"],
        },
        "changes": {"plan": plan_changed, "schedule": schedule_changed, "L01": l01_changed, "L02": l02_changed},
        "target_revisions": {"plan": plan_revision, "schedule": schedule_revision},
        "target_labels": {"plan": "course-plan-20h-r17", "schedule_and_lessons": "course-schedule-20h-r18"},
    }
    if dry_run:
        return preview

    if not any([plan_changed, schedule_changed, l01_changed, l02_changed]):
        return preview

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if plan_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project, PLAN_ID, plan_markdown, label=PHASE_LABEL, actor=ACTOR
        )
        project = project_manager.get_project(project_id) or project
    multi_document_service.update_document(
        project,
        PLAN_ID,
        {
            "expected_chapters": 8,
            "lineage": base._lineage(  # noqa: SLF001
                "course-plan-20h-r17", "docx_plus_user_resolution", "", base.SOURCE_WORD_SHA256, 3
            ),
        },
    )
    project = project_manager.get_project(project_id) or project
    multi_document_service.update_document_metadata(project, PLAN_ID, plan_metadata)
    project = project_manager.get_project(project_id) or project

    if schedule_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project, SCHEDULE_ID, schedule_markdown, label=PHASE_LABEL, actor=ACTOR
        )
        project = project_manager.get_project(project_id) or project
    multi_document_service.update_document(
        project,
        SCHEDULE_ID,
        {
            "lineage": base._lineage(  # noqa: SLF001
                "course-schedule-20h-r18", "structured_authority", PLAN_ID, plan_target["content_sha256"], 3
            )
        },
    )
    project = project_manager.get_project(project_id) or project
    multi_document_service.update_document_metadata(project, SCHEDULE_ID, schedule_metadata)
    project = project_manager.get_project(project_id) or project
    _refresh_binding(project, SCHEDULE_ID)
    project = project_manager.get_project(project_id) or project

    for name, document_id, changed in [("L01", L01_ID, l01_changed), ("L02", L02_ID, l02_changed)]:
        if changed:
            writing_collaboration_service.replace_authority_from_markdown(
                project, document_id, lesson_targets[name]["markdown"], label=PHASE_LABEL, actor=ACTOR
            )
            project = project_manager.get_project(project_id) or project

    for name, (document_id, _revision, _sha) in base.LESSON_BASES.items():
        record = multi_document_service.get_document(project, document_id)
        lineage = copy.deepcopy(record.get("lineage") or {})
        lineage.update(
            {
                "series_id": "surface-wargame-course-lessons",
                "edition_label": "course-schedule-20h-r18",
                "sequence": int(name[1:]),
                "source_type": "structured_authority",
                "parent_document_id": SCHEDULE_ID,
                "source_checksum": schedule_target["content_sha256"],
                "generated_at": NORMALIZED_AT,
                "source_paths": [schedule_before["working_path"]],
            }
        )
        multi_document_service.update_document(project, document_id, {"lineage": lineage})
        project = project_manager.get_project(project_id) or project
        _refresh_binding(project, document_id)
        project = project_manager.get_project(project_id) or project

    refreshed = project_manager.get_project(project_id) or project
    after = {
        "plan": base._state(refreshed, PLAN_ID),  # noqa: SLF001
        "schedule": base._state(refreshed, SCHEDULE_ID),  # noqa: SLF001
        "L01": base._state(refreshed, L01_ID),  # noqa: SLF001
        "L02": base._state(refreshed, L02_ID),  # noqa: SLF001
    }
    if after["plan"]["content_sha256"] != plan_target["content_sha256"] or after["plan"]["revision"] != plan_revision:
        raise RuntimeError(f"教学计划章节规范化写入失败：{after['plan']}")
    if after["schedule"]["content_sha256"] != schedule_target["content_sha256"] or after["schedule"]["revision"] != schedule_revision:
        raise RuntimeError(f"进度表父修订刷新失败：{after['schedule']}")
    if after["L01"]["content_sha256"] != lesson_targets["L01"]["content_sha256"]:
        raise RuntimeError("L01父修订刷新失败")
    if after["L02"]["content_sha256"] != lesson_targets["L02"]["content_sha256"]:
        raise RuntimeError("L02父修订刷新失败")

    return {**preview, "dry_run": False, "snapshot": str(snapshot), "after": after}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
