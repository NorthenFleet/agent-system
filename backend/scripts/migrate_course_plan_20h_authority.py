#!/usr/bin/env python3
"""Resolve the course plan to the user-confirmed 20-hour authority."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable


BACKEND = Path("/Users/apple/工作桌面/Workspace/agent-system/backend")
sys.path.insert(0, str(BACKEND))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PROJECT_ID = "proj-16ca49b862"
PLAN_ID = "doc-e811bedd87f9"
SCHEDULE_ID = "doc-2a28da7429f0"
L01_ID = "doc-3a9dbb65b9a3"
L02_ID = "doc-6085f649c11a"

PLAN_BASE_REVISION = 15
PLAN_BASE_SHA256 = "9daffd460df88d8959fe54e99a7816822c03a06bdc51a7d005de1edba7870140"
PLAN_BASE_WORKING_SHA256 = "9eda3e043d949bd010140a936e19504cd99a108d2e9fa3edae286119113629e6"
SCHEDULE_BASE_REVISION = 16
SCHEDULE_BASE_SHA256 = "b35fd5152f2b25ac119e5d38fc01672a54c044950ce3026cf43fa1f128bbda19"
SCHEDULE_BASE_WORKING_SHA256 = "cd3937fe98b3c8b95b358957213ba6505b336ebb1e2f681d7065b730a423cdbf"

LESSON_BASES = {
    "L01": (L01_ID, 64, "2021462daed265c26645f297545673ebcd87036a72fa0d01f390bb02f961d220"),
    "L02": (L02_ID, 13, "8531582ac7ae1a073cd47172b46dddb93106a80058536277164d8705644cc139"),
    "L03": ("doc-105f2073f3d9", 10, "31e2d785937fc8a8377c8370ebc081b8d8be03c0728d3b6333b3403a562ce858"),
    "L04": ("doc-9c47a19819ed", 12, "fb53099ea49c040568a13bad8476115dc32a33c2ede5c910a7ee975339cefdca"),
    "L05": ("doc-e542cf30905a", 12, "ff2a3f37a28a34612eb9539872e0429d1ca3784bd0c3451fb2011a0c3c45a973"),
    "L06": ("doc-9df3ab46770c", 12, "f7e6c1af4b30267c9f79406405600c48a6219d10e240902d3176477462898dc3"),
    "L07": ("doc-60e4858f35af", 12, "72836823c3c1500e4f19054252fc70d80f046e0450a67b3915a9b43727245673"),
    "L08": ("doc-8248d6366ec3", 12, "1f71c3163532096563d645fcd7b0f54460d93ae5a4dc02d791697861cf2201cb"),
    "L09": ("doc-729fe58abb5a", 12, "4ea207564e324dbeee3db16f789ea5309e5bcf105e954ff07f5224e2868ace5f"),
    "L10": ("doc-dab8a79a74dc", 12, "0ef36d1d977e56970b6d18fe4a6dbf0b22ef2ee94f2b83598279833c259c6caf"),
}

SOURCE_WORD = Path(
    "/Users/apple/工作桌面/knowledge/06-项目库-Projects/"
    "水面舰艇作战软件与兵棋推演课程--proj-16ca49b862/"
    "《兵棋推演与智能决策》-军兵种作战指挥专业-20课时-孙翼.docx"
)
SOURCE_WORD_SHA256 = "625c5adc0d113828d4fa64b3bd7f6ee477cbc1f3335a67af6e9190c9b1347bc4"
PLAN_TITLE = "《兵棋推演与智能决策》课程教学计划（20学时）"
SCHEDULE_TITLE = "《兵棋推演与智能决策》教学进度表（20学时）"
DATA_VERSION = "course-baseline-20h-v4"
PLAN_CONTENT_VERSION = "course-plan-original-word-resolved-20h-v2"
SCHEDULE_CONTENT_VERSION = "course-schedule-derived-from-plan-r16-20h-v2"
PHASE_LABEL = "课程教学计划：用户确认20学时并统一派生关系"
ACTOR = "course-plan-20h-resolution"
RESOLVED_AT = "2026-08-24T12:00:00+08:00"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _replace_exact(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise RuntimeError(f"{label}锚点数量异常：{count}")
    return value.replace(old, new, 1)


def _replace_all(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count < 1:
        raise RuntimeError(f"{label}锚点不存在")
    return value.replace(old, new)


def _replace_in_section(
    value: str,
    start: str,
    end: str,
    transform: Callable[[str], str],
    label: str,
) -> str:
    if value.count(start) != 1 or value.count(end) != 1:
        raise RuntimeError(f"{label}章节边界异常")
    prefix, tail = value.split(start, 1)
    body, suffix = tail.split(end, 1)
    return prefix + start + transform(body) + end + suffix


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


def _document_from_markdown(document_id: str, markdown: str) -> dict[str, Any]:
    return writing_collaboration_service.codec.from_markdown(
        markdown,
        namespace=f"{PROJECT_ID}/{document_id}/authority-import",
    )


def _plan_markdown(current: str) -> str:
    value = current
    value = _replace_exact(
        value,
        'title: "《兵棋推演与智能决策》课程教学计划（16学时稿）"',
        f'title: "{PLAN_TITLE}"',
        "教学计划标题",
    )
    value = _replace_exact(
        value,
        "content_version: course-plan-authoritative-original-word-2025-10-v1",
        f"content_version: {PLAN_CONTENT_VERSION}\ndata_version: {DATA_VERSION}",
        "教学计划内容版本",
    )
    value = _replace_exact(
        value,
        "source_fidelity: exact_original_text",
        "source_fidelity: original_word_structure_with_user_confirmed_20h_resolution",
        "教学计划来源保真状态",
    )
    value = _replace_exact(value, "| 学 时： | 16 |", "| 学 时： | 20 |", "封面学时")
    value = _replace_exact(
        value,
        "二、课程内容与教学要求\n",
        "# 二、课程内容与教学要求\n\n"
        "本课程保留原版Word的五个教学单元，并按L01—L10实施为10次课。"
        "其中理论教学4学时、课程实作14学时、综合考核2学时，每次课2学时。\n",
        "第二部分标题",
    )

    value = _replace_in_section(
        value,
        "## 第三章 兵棋基本操作（第3讲）",
        "## 第四章 兵棋推演实作（第4讲）",
        lambda body: _replace_exact(
            body,
            "学时安排：本模块安排2学时。",
            "学时安排：本单元对应L03—L04，安排4学时。",
            "第三单元学时",
        ),
        "第三单元",
    )
    value = _replace_in_section(
        value,
        "## 第四章 兵棋推演实作（第4讲）",
        "## 第五章 兵棋推演实作（第5讲）",
        lambda body: _replace_exact(
            body,
            "学时安排：本模块安排2学时。",
            "学时安排：本单元对应L05—L09，安排10学时。",
            "第四单元学时",
        ),
        "第四单元",
    )
    value = _replace_in_section(
        value,
        "## 第五章 兵棋推演实作（第5讲）",
        "三、教学设计",
        lambda body: _replace_exact(
            body,
            "学时安排：本模块安排2学时。",
            "学时安排：本单元对应L10，安排2学时。",
            "第五单元学时",
        ),
        "第五单元",
    )
    heading_changes = {
        "## 第一章 兵棋概述（第1讲） ": "## 第一单元 兵棋概述（L01，2学时）",
        "## 第二章 兵棋推演流程及运用（第2讲）": "## 第二单元 兵棋推演流程及运用（L02，2学时）",
        "## 第三章 兵棋基本操作（第3讲）": "## 第三单元 组件、规则查用与单回合操作（L03—L04，4学时）",
        "## 第四章 兵棋推演实作（第4讲）": "## 第四单元 想定、方案与专项综合推演（L05—L09，10学时）",
        "## 第五章 兵棋推演实作（第5讲）": "## 第五单元 综合考核与复盘答辩（L10，2学时）",
    }
    for old, new in heading_changes.items():
        value = _replace_exact(value, old, new, old)

    value = _replace_exact(value, "三、教学设计\n", "# 三、教学设计\n", "第三部分标题")
    value = _replace_exact(value, "四、实施过程\n", "# 四、实施过程\n", "第四部分标题")
    value = _replace_exact(
        value,
        "本课程共10学时，其中，理论教学4学时，实践教学6学时，本课程需要对舰艇作战装备组成和作战使用方法具有一定的专业基础，安排在第六、七学期开设。",
        "本课程共20学时，其中理论教学4学时、课程实作14学时、综合考核2学时。"
        "课程需要学员具备舰艇作战装备组成和作战使用方法的专业基础，安排在第六、七学期开设。",
        "开课学时口径",
    )

    old_schedule = """| 课次 | 内容要点 | 小计 | 理论学时 | 实践学时 | 备注 |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 兵棋概述 | 2 | 2 |  |  |
| 2 | 兵棋推演流程及运用 | 2 | 2 |  |  |
| 3 | 兵棋系统组成 | 2 |  | 2 |  |
| 4 | 推演规则详解与裁决方法 | 2 |  | 2 |  |
| 5 | 防空反导推演 | 2 |  | 2 |  |
| 6 | 对海突击推演 | 2 |  | 2 |  |
| 7 | 综合战术推演与实作考核 | 2 |  | 2 |  |
| 8 | 作战方案提交与答辩 | 2 |  | 2 |  |
| 合计 | 16 | 4 | 12 |  |"""
    new_schedule = """| 课次 | 讲次 | 内容要点 | 小计 | 理论学时 | 实作学时 | 考核学时 |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: |
| 1 | L01 | 兵棋基础与《谋战》体系认识 | 2 | 2 |  |  |
| 2 | L02 | 水面舰艇编队战术、推演流程与裁决方法 | 2 | 2 |  |  |
| 3 | L03 | 《谋战》组件、地图、棋子与规则查用 | 2 |  | 2 |  |
| 4 | L04 | 单回合操作、态势标绘与裁决记录 | 2 |  | 2 |  |
| 5 | L05 | 作战想定理解、关键点识别与任务构建 | 2 |  | 2 |  |
| 6 | L06 | 五人编组、编队部署与行动方案制定 | 2 |  | 2 |  |
| 7 | L07 | 侦察预警、电子战与指挥协同专项推演 | 2 |  | 2 |  |
| 8 | L08 | 制空支援、对海打击与防空反导专项推演 | 2 |  | 2 |  |
| 9 | L09 | 关键点争夺、跨域综合对抗与软件辅助复盘 | 2 |  | 2 |  |
| 10 | L10 | 综合考核：想定分析、对抗推演与复盘答辩 | 2 |  |  | 2 |
| 合计 | 10次课 |  | 20 | 4 | 14 | 2 |"""
    value = _replace_exact(value, old_schedule, new_schedule, "10讲实施表")
    value = _replace_exact(value, "## \n\n## \n\n", "", "空标题清理")

    old_practice_start = "## （三）课程实验（实作）实施方案\n"
    old_assessment_start = "六、考核评价\n"
    if value.count(old_practice_start) != 1 or value.count(old_assessment_start) != 1:
        raise RuntimeError("课程实验或考核章节边界异常")
    prefix, tail = value.split(old_practice_start, 1)
    _old_practice, suffix = tail.split(old_assessment_start, 1)
    practice = """# 五、课程实验（实作）实施方案

| 序号 | 对应讲次 | 实作或考核内容 | 学时 | 主要要求 | 实施方法 | 教学保障条件 |
| :---: | :---: | :--- | :---: | :--- | :---: | :--- |
| 1 | L03—L04 | 组件规则查用、单回合操作与裁决记录 | 4 | 完成组件与版本确认，规范实施行动申报、人工裁决、态势更新和记录核对 | 分组实作 | 《谋战》兵棋、规则与裁决资料、推演场地 |
| 2 | L05—L06 | 想定分析、五人编组与行动方案制定 | 4 | 区分事实、未知、规则推断与指挥员假设，形成部署、责任和行动方案 | 分组实作 | 冻结想定、席位与方案模板、推演场地 |
| 3 | L07—L08 | 侦察电子战、火力防护专项推演 | 4 | 组织航迹、电磁、命令和火力协同，保留裁决与资源状态证据 | 分组专项推演 | 《谋战》兵棋、专项任务包、记录表单 |
| 4 | L09 | 跨域综合对抗与软件辅助复盘 | 2 | 完成综合对抗、关键事件回放、差异分析和第二版方案 | 分组综合推演 | 统一规则数据、手工记录、软件回放条件 |
| 5 | L10 | 综合考核与复盘答辩 | 2 | 独立完成想定研判、履职推演、证据定位、复盘答辩和人工复核 | 综合考核 | 冻结想定、统一量规、证据目录与评分表 |
|  | 合计 |  | 16 | 实作14学时、综合考核2学时 |  |  |
"""
    value = prefix + practice + "\n# 六、考核评价\n" + suffix

    old_assessment = (
        "2.考核方式：形成性考核和终结性考核相结合。形成性考核采取实作的方式，占比40%；"
        "终结性考核采用采取对抗演练和撰写复盘总结报告，占比60%。"
        "形成性考核、终结性考核任一部分低于60分，即为该门课程不及格。"
    )
    new_assessment = (
        "2.考核方式：形成性考核和终结性考核相结合。形成性考核采用L03—L09实作评价，占课程总评40分；"
        "终结性考核采用L10对抗推演、证据复核和复盘答辩，原始成绩按60%计入课程总评。"
        "形成性考核低于24分，或L10终结性考核原始成绩低于60分，即为该门课程不及格。"
    )
    value = _replace_exact(value, old_assessment, new_assessment, "考核方式")
    old_score_table = """| 考核项目 | 实作一 兵棋基本操作 | 实作二 兵棋推演实作 |
| :---: | :---: | :---: |
| 权重 | 50% | 50% |
| 考核 方法 | 实操 | 作战方案 |
| 计分 方法 | 两级制 | 四级制 |
| 佐证 材料 | 成绩单 | 作战方案报告、成绩单 |"""
    new_score_table = """| 考核组成 | 对应讲次 | 课程总评分值 | 主要佐证材料 |
| :---: | :---: | :---: | :--- |
| 基础实作 | L03—L06 | 16分 | 规则索引、操作与裁决记录、想定分析、部署与行动方案 |
| 专项与综合实作 | L07—L09 | 24分 | 专项推演记录、综合证据包、关键决策时间线和第二版方案 |
| 终结性考核 | L10 | 60分 | 综合考核证据包、个人贡献单、复盘答辩和评分记录 |
| 合计 | L03—L10 | 100分 | 形成可追溯的课程评价证据链 |"""
    value = _replace_exact(value, old_score_table, new_score_table, "考核设计表")

    value = _replace_exact(value, "七、保障条件\n", "# 七、保障条件\n", "第七部分标题")
    for old, new in {
        "（二）场地\n": "## （二）场地\n",
        "（三）设施设备\n": "## （三）设施设备\n",
        "（四）信息资源\n": "## （四）信息资源\n",
        "s八、附录\n": "# 八、附录\n",
        "（一）执行时间\n": "## （一）执行时间\n",
        "（二）术语解释\n": "## （二）术语解释\n",
        "（三）其他\n": "## （三）其他\n",
    }.items():
        value = _replace_exact(value, old, new, old.strip())
    return value


def _schedule_markdown(current: str, plan_sha: str) -> str:
    value = current
    replacements = {
        'title: "《水面舰艇作战软件与兵棋推演》教学进度表（20学时）"': f'title: "{SCHEDULE_TITLE}"',
        'content_version: "course-schedule-derived-from-plan-r14-v1"': f'content_version: "{SCHEDULE_CONTENT_VERSION}"',
        "parent_revision: 14": "parent_revision: 16",
        'parent_content_sha256: "f315d92c7a21a5ba89503f3dbb2420fb382ef4eff547f590ef5dc8de7bfb5623"': f'parent_content_sha256: "{plan_sha}"',
        "# 《水面舰艇作战软件与兵棋推演》教学进度表（20学时）": f"# {SCHEDULE_TITLE}",
        "> 本进度表由《水面舰艇作战软件与兵棋推演》课程教学计划修订14派生": "> 本进度表由《兵棋推演与智能决策》课程教学计划修订16派生",
        "| 课程名称 | 水面舰艇作战软件与兵棋推演 |": "| 课程名称 | 兵棋推演与智能决策 |",
        "| 课程计划权威 | doc-e811bedd87f9，修订14 |": "| 课程计划权威 | doc-e811bedd87f9，修订16 |",
    }
    for old, new in replacements.items():
        value = _replace_exact(value, old, new, old)
    return value


def _lesson_markdown(current: str, schedule_sha: str) -> str:
    value = _replace_exact(value=current, old="parent_revision: 16", new="parent_revision: 17", label="教案父修订")
    value = _replace_exact(
        value,
        f'parent_content_sha256: "{SCHEDULE_BASE_SHA256}"',
        f'parent_content_sha256: "{schedule_sha}"',
        "教案父SHA",
    )
    value = _replace_exact(
        value,
        "upstream_course_plan_revision: 14",
        "upstream_course_plan_revision: 16",
        "教案教学计划修订",
    )
    value = _replace_all(value, "教学进度表修订16", "教学进度表修订17", "教案可见进度表修订")
    value = _replace_all(value, "教学计划修订14", "教学计划修订16", "教案可见教学计划修订")
    old_short = f"{SCHEDULE_BASE_SHA256[:8]}…{SCHEDULE_BASE_SHA256[-8:]}"
    if old_short in value:
        value = value.replace(old_short, f"{schedule_sha[:8]}…{schedule_sha[-8:]}")
    return value


def _target(document_id: str, markdown: str) -> dict[str, Any]:
    document = _document_from_markdown(document_id, markdown)
    writing_collaboration_service._validate_round_trip(markdown, document)  # noqa: SLF001
    round_trip = writing_collaboration_service.codec.to_markdown(document)
    return {
        "markdown": markdown,
        "document": document,
        "content_sha256": writing_collaboration_service.codec.document_sha256(document),
        "working_sha256": _text_sha256(markdown),
        "round_trip_sha256": _text_sha256(round_trip),
        "metrics": writing_collaboration_service.codec.metrics(document),
    }


def _assert_plan(value: str) -> None:
    required = [
        PLAN_TITLE,
        "| 学 时： | 20 |",
        "本课程共20学时，其中理论教学4学时、课程实作14学时、综合考核2学时",
        "第一单元 兵棋概述（L01，2学时）",
        "第三单元 组件、规则查用与单回合操作（L03—L04，4学时）",
        "第四单元 想定、方案与专项综合推演（L05—L09，10学时）",
        "第五单元 综合考核与复盘答辩（L10，2学时）",
        "| 合计 | 10次课 |  | 20 | 4 | 14 | 2 |",
        "|  | 合计 |  | 16 | 实作14学时、综合考核2学时 |",
        "形成性考核低于24分",
        "# 八、附录",
    ]
    banned = ["16学时稿", "| 学 时： | 16 |", "本课程共10学时", "| 合计 | 16 | 4 | 12", "s八、附录", "\n## \n"]
    missing = [token for token in required if token not in value]
    hits = [token for token in banned if token in value]
    top = [line for line in value.splitlines() if line.startswith("# ")]
    if missing or hits or len(top) != 8:
        raise RuntimeError(f"20学时教学计划检查失败：missing={missing}, banned={hits}, top={top}")
    if not all(f"| {index} | L{index:02d} |" in value for index in range(1, 11)):
        raise RuntimeError("20学时教学计划未完整覆盖L01—L10")


def _assert_schedule(value: str, plan_sha: str) -> None:
    required = [
        SCHEDULE_TITLE,
        "parent_revision: 16",
        plan_sha,
        "课程教学计划修订16派生",
        "| 课程名称 | 兵棋推演与智能决策 |",
        "| 课程计划权威 | doc-e811bedd87f9，修订16 |",
        "|  | 合计 | 10次课 | 理论4、实作14、考核2 |",
    ]
    banned = ["course-plan-r14", "课程教学计划修订14", "水面舰艇作战软件与兵棋推演》教学进度表"]
    missing = [token for token in required if token not in value]
    hits = [token for token in banned if token in value]
    if missing or hits:
        raise RuntimeError(f"教学进度表检查失败：missing={missing}, banned={hits}")


def _lineage(label: str, source_type: str, parent_id: str, source_sha: str, sequence: int) -> dict[str, Any]:
    return {
        "series_id": "surface-wargame-course-plan" if parent_id == "" else "surface-wargame-course-projections",
        "edition_label": label,
        "sequence": sequence,
        "source_type": source_type,
        "parent_document_id": parent_id,
        "source_checksum": source_sha,
        "generated_at": RESOLVED_AT,
        "source_paths": [str(SOURCE_WORD)] if not parent_id else [],
    }


def _refresh_binding(project: dict[str, Any], document_id: str) -> None:
    record = multi_document_service.get_document(project, document_id)
    binding = copy.deepcopy(record.get("structure_binding") or {})
    if not binding.get("source_document_id"):
        raise RuntimeError(f"{document_id}缺少可刷新的结构绑定")
    binding["source_sha256"] = ""
    multi_document_service.set_structure_binding(project, document_id, binding)


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    if project_id != PROJECT_ID:
        raise RuntimeError("本迁移仅允许作用于冻结课程项目")
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError("课程项目不存在")
    if not SOURCE_WORD.is_file() or _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError("用户确认的原版Word不存在或SHA已变化")

    listed = multi_document_service.list_documents(project, include_archived=False)["documents"]
    plan_docs = [row for row in listed if row.get("product_type") == "course_plan"]
    schedule_docs = [row for row in listed if row.get("product_type") == "teaching_schedule"]
    lesson_docs = [row for row in listed if row.get("product_type") == "lesson_plan"]
    if [row["id"] for row in plan_docs] != [PLAN_ID] or [row["id"] for row in schedule_docs] != [SCHEDULE_ID]:
        raise RuntimeError("活动目录存在重复教学计划或教学进度表，停止自动清理")
    if sorted(row["id"] for row in lesson_docs) != sorted(row[1][0] for row in LESSON_BASES.items()):
        raise RuntimeError("活动目录不是冻结的10讲教案集合")

    plan_before = _state(project, PLAN_ID)
    schedule_before = _state(project, SCHEDULE_ID)
    lesson_before = {name: _state(project, document_id) for name, (document_id, _rev, _sha) in LESSON_BASES.items()}

    plan_source = Path(plan_before["working_path"]).read_text(encoding="utf-8")
    if plan_before["content_sha256"] == PLAN_BASE_SHA256:
        if plan_before["revision"] != PLAN_BASE_REVISION or plan_before["working_sha256"] != PLAN_BASE_WORKING_SHA256:
            raise RuntimeError(f"教学计划r15基线不完整：{plan_before}")
        plan_markdown = _plan_markdown(plan_source)
    else:
        plan_markdown = plan_source
    _assert_plan(plan_markdown)
    plan_target = _target(PLAN_ID, plan_markdown)

    schedule_source = Path(schedule_before["working_path"]).read_text(encoding="utf-8")
    if schedule_before["content_sha256"] == SCHEDULE_BASE_SHA256:
        if schedule_before["revision"] != SCHEDULE_BASE_REVISION or schedule_before["working_sha256"] != SCHEDULE_BASE_WORKING_SHA256:
            raise RuntimeError(f"教学进度表r16基线不完整：{schedule_before}")
        schedule_markdown = _schedule_markdown(schedule_source, plan_target["content_sha256"])
    else:
        schedule_markdown = schedule_source
    _assert_schedule(schedule_markdown, plan_target["content_sha256"])
    schedule_target = _target(SCHEDULE_ID, schedule_markdown)

    lesson_targets: dict[str, dict[str, Any]] = {}
    for name in ["L01", "L02"]:
        before = lesson_before[name]
        document_id, base_revision, base_sha = LESSON_BASES[name]
        source = Path(before["working_path"]).read_text(encoding="utf-8")
        if before["content_sha256"] == base_sha:
            if before["revision"] != base_revision:
                raise RuntimeError(f"{name}修订基线变化：{before}")
            markdown = _lesson_markdown(source, schedule_target["content_sha256"])
        else:
            markdown = source
        if "教学计划修订14" in markdown or "教学进度表修订16" in markdown:
            raise RuntimeError(f"{name}仍含过时可见修订")
        lesson_targets[name] = _target(document_id, markdown)

    base_or_target = {
        "plan": plan_before["content_sha256"] in {PLAN_BASE_SHA256, plan_target["content_sha256"]},
        "schedule": schedule_before["content_sha256"] in {SCHEDULE_BASE_SHA256, schedule_target["content_sha256"]},
        "L01": lesson_before["L01"]["content_sha256"] in {LESSON_BASES["L01"][2], lesson_targets["L01"]["content_sha256"]},
        "L02": lesson_before["L02"]["content_sha256"] in {LESSON_BASES["L02"][2], lesson_targets["L02"]["content_sha256"]},
    }
    for name in ["L03", "L04", "L05", "L06", "L07", "L08", "L09", "L10"]:
        expected_revision, expected_sha = LESSON_BASES[name][1:]
        current = lesson_before[name]
        base_or_target[name] = current["revision"] == expected_revision and current["content_sha256"] == expected_sha
    if not all(base_or_target.values()):
        raise RuntimeError(f"冻结基线已变化：{base_or_target}")

    plan_changed = plan_before["content_sha256"] != plan_target["content_sha256"]
    schedule_changed = schedule_before["content_sha256"] != schedule_target["content_sha256"]
    l01_changed = lesson_before["L01"]["content_sha256"] != lesson_targets["L01"]["content_sha256"]
    l02_changed = lesson_before["L02"]["content_sha256"] != lesson_targets["L02"]["content_sha256"]
    desired_plan_revision = plan_before["revision"] + 1 if plan_changed else plan_before["revision"]
    desired_schedule_revision = schedule_before["revision"] + 1 if schedule_changed else schedule_before["revision"]

    plan_record = multi_document_service.get_document(project, PLAN_ID)
    plan_metadata = copy.deepcopy(plan_record.get("metadata") or {})
    layout = copy.deepcopy(plan_metadata.get("layout_binding") or {})
    if layout:
        layout["status"] = "stale"
        layout["changed_reasons"] = ["用户已确认20学时，既有候选交付未绑定当前20学时正文"]
    source_metrics = copy.deepcopy((plan_metadata.get("content_fidelity") or {}).get("source_metrics") or {})
    plan_metadata.update(
        {
            "last_actor": ACTOR,
            "content_fidelity_current_status": "source_based_user_confirmed_20h_revision_layout_release_stale",
            "content_fidelity": {
                "schema": "openclaw.document-content-fidelity.v1",
                "project_id": PROJECT_ID,
                "document_id": PLAN_ID,
                "document_title": PLAN_TITLE,
                "source_kind": "docx_plus_user_resolution",
                "source_sha256": SOURCE_WORD_SHA256,
                "structured_revision": desired_plan_revision,
                "structured_sha256": plan_target["content_sha256"],
                "status": "passed_with_declared_changes",
                "migration_safe": True,
                "source_metrics": source_metrics,
                "structured_metrics": plan_target["metrics"],
                "differences": {
                    "hours": "用户确认统一为20学时",
                    "implementation": "按现有L01—L10教学进度表展开为10次课",
                    "structure": "修正原Word导入后的一级标题、缺失第五部分和附录标题错误",
                },
                "unresolved_assets": [],
                "empty_formulas": [],
                "warnings": [],
                "audited_at": RESOLVED_AT,
            },
            "course_plan_structure": {
                "schema": "openclaw.course-plan-20h.v2",
                "content_version": PLAN_CONTENT_VERSION,
                "official_course_name": "兵棋推演与智能决策",
                "source_word": {"path": str(SOURCE_WORD), "sha256": SOURCE_WORD_SHA256},
                "top_level_sections": 8,
                "content_units": 5,
                "lesson_count": 10,
                "hours": {"total": 20, "theory": 4, "practice": 14, "assessment": 2},
                "hours_conflict_status": "resolved_by_user_2026-08-24",
            },
            "source_authority": {
                "status": "user_confirmed_original_word_with_20h_resolution",
                "confirmed_at": RESOLVED_AT,
                "path": str(SOURCE_WORD),
                "sha256": SOURCE_WORD_SHA256,
                "baseline_revision": 15,
            },
            "notes": [
                "用户确认原Word为课程教学计划基线，并于2026-08-24明确课程统一采用20学时。",
                "课程教学计划、教学进度表和10讲教案为不同正式成果，不作为重复文档删除。",
            ],
            "layout_binding": layout,
        }
    )
    plan_patch = {
        "title": PLAN_TITLE,
        "data_version": DATA_VERSION,
        "expected_chapters": 8,
        "publication_status": "draft",
        "lineage": _lineage("course-plan-20h-r16", "docx_plus_user_resolution", "", SOURCE_WORD_SHA256, 2),
    }

    schedule_record = multi_document_service.get_document(project, SCHEDULE_ID)
    schedule_metadata = copy.deepcopy(schedule_record.get("metadata") or {})
    schedule_metadata.update(
        {
            "last_actor": ACTOR,
            "parent_authority": {
                "document_id": PLAN_ID,
                "revision": desired_plan_revision,
                "content_sha256": plan_target["content_sha256"],
                "status": "current",
            },
            "notes": ["20学时、10讲实施投影，与用户确认后的课程教学计划修订16对齐。"],
        }
    )
    schedule_patch = {
        "title": SCHEDULE_TITLE,
        "data_version": DATA_VERSION,
        "publication_status": "draft",
        "lineage": _lineage(
            "course-schedule-20h-r17",
            "structured_authority",
            PLAN_ID,
            plan_target["content_sha256"],
            2,
        ),
    }

    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "active_catalog": {
            "course_plan": [row["id"] for row in plan_docs],
            "teaching_schedule": [row["id"] for row in schedule_docs],
            "lesson_plans": sorted(row["id"] for row in lesson_docs),
            "duplicates_to_delete": [],
        },
        "plan_before": plan_before,
        "plan_target": {key: value for key, value in plan_target.items() if key not in {"markdown", "document"}},
        "schedule_before": schedule_before,
        "schedule_target": {key: value for key, value in schedule_target.items() if key not in {"markdown", "document"}},
        "lesson_content_changes": {"L01": l01_changed, "L02": l02_changed, "L03-L10": False},
        "content_changes": {
            "plan": plan_changed,
            "schedule": schedule_changed,
            "L01": l01_changed,
            "L02": l02_changed,
        },
        "catalog_labels": {
            "plan": "course-plan-20h-r16",
            "schedule": "course-schedule-20h-r17",
            "lessons": "course-schedule-20h-r17",
        },
        "source_word_unchanged": _sha256(SOURCE_WORD) == SOURCE_WORD_SHA256,
    }
    catalog_aligned = plan_record.get("title") == PLAN_TITLE and schedule_record.get("title") == SCHEDULE_TITLE
    metadata_aligned = plan_record.get("metadata") == plan_metadata and schedule_record.get("metadata") == schedule_metadata
    if dry_run or (not any([plan_changed, schedule_changed, l01_changed, l02_changed]) and catalog_aligned and metadata_aligned):
        return preview

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if plan_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project, PLAN_ID, plan_markdown, label=PHASE_LABEL, actor=ACTOR
        )
        project = project_manager.get_project(project_id) or project
    multi_document_service.update_document(project, PLAN_ID, plan_patch)
    project = project_manager.get_project(project_id) or project
    multi_document_service.update_document_metadata(project, PLAN_ID, plan_metadata)
    project = project_manager.get_project(project_id) or project

    if schedule_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project, SCHEDULE_ID, schedule_markdown, label=PHASE_LABEL, actor=ACTOR
        )
        project = project_manager.get_project(project_id) or project
    multi_document_service.update_document(project, SCHEDULE_ID, schedule_patch)
    project = project_manager.get_project(project_id) or project
    multi_document_service.update_document_metadata(project, SCHEDULE_ID, schedule_metadata)
    project = project_manager.get_project(project_id) or project
    _refresh_binding(project, SCHEDULE_ID)
    project = project_manager.get_project(project_id) or project

    for name, changed in [("L01", l01_changed), ("L02", l02_changed)]:
        document_id = LESSON_BASES[name][0]
        if changed:
            writing_collaboration_service.replace_authority_from_markdown(
                project, document_id, lesson_targets[name]["markdown"], label=PHASE_LABEL, actor=ACTOR
            )
            project = project_manager.get_project(project_id) or project

    for name, (document_id, _revision, _sha) in LESSON_BASES.items():
        record = multi_document_service.get_document(project, document_id)
        lineage = copy.deepcopy(record.get("lineage") or {})
        lineage.update(
            {
                "series_id": "surface-wargame-course-lessons",
                "edition_label": "course-schedule-20h-r17",
                "sequence": int(name[1:]),
                "source_type": "structured_authority",
                "parent_document_id": SCHEDULE_ID,
                "source_checksum": schedule_target["content_sha256"],
                "generated_at": RESOLVED_AT,
                "source_paths": [schedule_target.get("working_path", schedule_before["working_path"])],
            }
        )
        multi_document_service.update_document(
            project,
            document_id,
            {"data_version": DATA_VERSION, "lineage": lineage, "publication_status": "draft"},
        )
        project = project_manager.get_project(project_id) or project
        _refresh_binding(project, document_id)
        project = project_manager.get_project(project_id) or project

    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "course_plan_authority_status": "user_confirmed_20h_draft",
            "course_plan_hours_conflict": "resolved_20h_by_user_2026-08-24",
            "next_step": "按20学时教学计划依次复核教学进度表和10讲教案，审批前保持草稿。",
        }
    )
    project_manager.update_project(
        project_id,
        {"context": context, "current_phase": "course_plan_20h_authority_resolved"},
    )

    refreshed = project_manager.get_project(project_id) or project
    plan_after = _state(refreshed, PLAN_ID)
    schedule_after = _state(refreshed, SCHEDULE_ID)
    lesson_after = {name: _state(refreshed, document_id) for name, (document_id, _rev, _sha) in LESSON_BASES.items()}
    if plan_after["content_sha256"] != plan_target["content_sha256"] or plan_after["revision"] != desired_plan_revision:
        raise RuntimeError(f"教学计划写入后状态不一致：{plan_after}")
    if schedule_after["content_sha256"] != schedule_target["content_sha256"] or schedule_after["revision"] != desired_schedule_revision:
        raise RuntimeError(f"教学进度表写入后状态不一致：{schedule_after}")
    for name in ["L01", "L02"]:
        target = lesson_targets[name]
        if lesson_after[name]["content_sha256"] != target["content_sha256"]:
            raise RuntimeError(f"{name}可见父修订更新失败：{lesson_after[name]}")
    for name in ["L03", "L04", "L05", "L06", "L07", "L08", "L09", "L10"]:
        if lesson_after[name]["content_sha256"] != lesson_before[name]["content_sha256"]:
            raise RuntimeError(f"{name}正文发生越界变化")

    listed_after = multi_document_service.list_documents(refreshed, include_archived=False)["documents"]
    active_labels = {
        row["id"]: str((row.get("lineage") or {}).get("edition_label") or "")
        for row in listed_after
        if row["id"] in {PLAN_ID, SCHEDULE_ID, *[entry[0] for entry in LESSON_BASES.values()]}
    }
    stale_labels = [label for label in active_labels.values() if label in {"authoritative-original-word-2025-10", "course-plan-r14", "schedule-r16"}]
    if stale_labels:
        raise RuntimeError(f"活动目录仍含过时派生标识：{stale_labels}")
    if _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError("原版Word在迁移期间发生变化")

    return {
        **preview,
        "dry_run": False,
        "snapshot": str(snapshot),
        "plan_after": plan_after,
        "schedule_after": schedule_after,
        "lesson_after_revisions": {name: state["revision"] for name, state in lesson_after.items()},
        "active_labels": active_labels,
        "source_word_unchanged": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
