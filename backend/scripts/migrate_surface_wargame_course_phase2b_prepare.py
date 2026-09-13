#!/usr/bin/env python3
"""Prepare the exact Phase 2B presentation authoring package without editing PPTX binaries."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from scripts import migrate_surface_wargame_course_phase2a as phase2a  # noqa: E402
from services.course_production_service import COURSE_PROJECT_ID  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PHASE_LABEL = "课程开学准备第二阶段B准备：课件P0精确修订包"
CONTENT_VERSION = "surface-course-presentation-phase2b-prep-v1"
INTERNAL_DOCUMENT_ID = "doc-8c97c44611e2"
SECTION_MARKER = "## 六、课程课件第二阶段B精确修订包"
BLOCKER = "required_presentation_runtime_unavailable"


REVISIONS: dict[str, dict[int, dict[str, Any]]] = {
    "doc-67294b2100be": {
        1: {
            "mode": "replace_page_copy",
            "title": "《谋战·水面舰艇编队战术手工兵棋》",
            "body": "水面舰艇作战软件与兵棋推演课程｜实作课件",
            "target_status": "retain",
            "purpose": "统一课程名称和课件定位。",
        },
        17: {
            "mode": "text_replacements",
            "replacements": [["谋战水面舰艇编队手工兵器", "《谋战·水面舰艇编队战术手工兵棋》"]],
            "target_status": "retain",
            "purpose": "修正课程名称和“手工兵器”错字。",
        },
        28: {
            "mode": "replace_page_copy",
            "title": "推演流程——控制兵棋的时间演进",
            "body": (
                "流程结构\n"
                "1. 回合控制：时间步推进、阶段划分\n"
                "2. 行动申报：态势通报、方案制定、方案提交\n"
                "3. 裁决执行：行动执行、裁决判定、结果记录\n"
                "4. 态势更新：状态更新、态势生成、信息分发\n\n"
                "当前课程口径\n"
                "交战级：1个交战步＝10秒\n"
                "其他时间层级只在相应规则明确启用时使用。"
            ),
            "target_status": "retain",
            "purpose": "将旧30秒口径统一为当前10秒权威口径。",
        },
        35: {
            "mode": "add_boundary_banner",
            "banner": "历史想定结构示例｜非0522权威想定，仅用于字段教学",
            "target_status": "retain_with_boundary",
            "purpose": "保留想定字段教学价值，阻断历史平台和兵力数据进入正式裁决。",
        },
        42: {
            "mode": "text_replacements",
            "replacements": [["复利效用", "复盘效用"], ["最终要", "最重要"]],
            "target_status": "retain",
            "purpose": "修正影响理解的错字。",
        },
        54: {
            "mode": "text_replacements",
            "replacements": [["2026年3月", "本学期授课使用"]],
            "target_status": "retain",
            "purpose": "移除未确认的固定日期，避免与实际排课冲突。",
        },
    },
    "doc-5b225b46318f": {
        1: {
            "mode": "replace_page_copy",
            "title": "水面舰艇作战软件与兵棋推演",
            "body": "课程导入与方法基础｜20学时·10次课",
            "target_status": "retain",
            "purpose": "将通识培训课件纳入3021课程正式叙事。",
        },
        5: {
            "mode": "replace_page_copy",
            "title": "古代兵棋：起源与发展",
            "body": (
                "兵棋历史源远流长。古代指挥者常用器物或标记代表地形和兵力，通过摆设态势、演练部署与比较方案来推断可能的交战结果。\n\n"
                "《墨子·公输》中“解带为城、以牒为械”的记载，可用于说明早期以象征物模拟攻防过程的思想。"
            ),
            "target_status": "retain",
            "purpose": "修正“历史渊远流长”“兵器界”等错误并压缩表述。",
        },
        20: {
            "mode": "replace_page_copy",
            "title": "兵棋规则：推演规则与裁决规则",
            "body": (
                "兵棋规则规定棋子如何行动，以及行动结果如何裁决，是对战争经验、演习数据和实验数据的抽象表达。\n\n"
                "推演规则：规定推演方、地图与时间尺度、推演流程、棋子及图表的使用方法。\n"
                "裁决规则：规定机动、探测、交战与毁伤等行动结果的判定方法。"
            ),
            "target_status": "retain",
            "purpose": "将“对症结果、兵器规则”等错误统一为规范兵棋表述。",
        },
        23: {
            "mode": "replace_page_copy",
            "title": "随机事件：用概率表达作战不确定性",
            "body": (
                "作战结果具有不确定性。兵棋以概率模型和随机数生成器模拟偶然事件。\n\n"
                "手工兵棋通常通过掷骰子取得随机数；计算机兵棋通过受控随机函数生成随机数。\n\n"
                "随机结果必须与规则条件、修正因素和裁决表共同使用，不能脱离规则单独解释。"
            ),
            "target_status": "retain",
            "purpose": "重写随机事件说明，消除多处错字和概念混乱。",
        },
        32: {
            "mode": "add_boundary_banner",
            "banner": "通用任务规划字段示例｜非0522权威想定",
            "target_status": "retain_with_boundary",
            "purpose": "只讲任务规划字段，不把“蓝鹰”案例视为课程权威想定。",
        },
        45: {
            "mode": "replace_page_copy",
            "title": "兵棋的应用领域",
            "body": (
                "历史上，联合战区级模拟等系统曾被用于战区级推演。兵棋也可用于政治、外交、经济和社会管理等领域的决策实验。\n\n"
                "具体型号、采购与运用事实需依据可核验来源确认；本页仅用于说明兵棋应用范围。"
            ),
            "target_status": "retain_with_boundary",
            "purpose": "删除无法可靠还原的错字句，保留应用领域教学用途并补足来源边界。",
        },
        52: {
            "mode": "replace_page_copy",
            "title": "历史参数为什么不能直接用于裁决",
            "body": (
                "页面原有伯克、F-35C、弗吉尼亚参数来自历史或未核验材料。\n\n"
                "本课程正式推演只使用《谋战》R1.2/D1.2及登记的R1.1/D1.1裁决与算子数据。\n\n"
                "查用步骤：确认版本 → 确认对象 → 确认适用条件 → 登记条目 → 交叉复核。\n\n"
                "禁止：将旧课件、口述数值或其他想定数据直接拼接到0522裁决。"
            ),
            "target_status": "retain_with_boundary",
            "purpose": "把高风险旧参数表改造成规则查用反例。",
        },
        61: {
            "mode": "replace_page_copy",
            "title": "定量与定性思维",
            "body": (
                "兵棋推演把定量分析与定性判断结合起来。设计阶段需要收集和治理数据，推演阶段需要依据规则计算和分析，复盘阶段需要统计结果并解释原因。\n\n"
                "概率统计、运筹方法和博弈分析可支撑判断，但最终结论必须回到任务、规则、行动和证据链。"
            ),
            "target_status": "retain",
            "purpose": "修正“兵器推演”并压缩过度表述。",
        },
        65: {
            "mode": "add_boundary_banner",
            "banner": "历史方法案例｜需依据来源核验，不作为严格因果证据",
            "target_status": "retain_with_boundary",
            "purpose": "保留问题导向案例，同时限制故事性叙述的证据效力。",
        },
        67: {
            "mode": "replace_page_copy",
            "title": "海湾战争兵力数据示例（附录）",
            "body": (
                "本页原有兵力与装备数字来自历史汇编材料，存在文字错误和来源缺口。\n\n"
                "教学用途：练习数据来源登记、单位统一、交叉核验和不确定性标注。\n\n"
                "使用边界：完成来源核验前，不引用具体数字形成事实结论，不用于《谋战》0522想定裁决。"
            ),
            "target_status": "retain_with_boundary",
            "purpose": "将未核验兵力表改为数据治理练习并保持附录属性。",
        },
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _speaker_notes(deck_label: str, slide: int, item: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"【讲解目标】{item['purpose']}",
            "【教学动作】先让学员识别原页面问题，再展示修订后的规则口径或资料边界。",
            "【规则边界】正式裁决以《谋战》R1.2/D1.2及登记的R1.1/D1.1裁决与算子数据为准。",
            "【检查问题】本页内容属于概念、方法、历史案例，还是可进入正式裁决的权威规则？",
            "[Sources]",
            f"- {deck_label}源第{slide}页",
            "- 《谋战》R1.2/D1.2三册规则",
            "- 《谋战》口述材料参数核验矩阵",
            "- 课程知识库优选底稿与融合说明",
        ]
    )


def _copy_summary(item: dict[str, Any]) -> str:
    if item["mode"] == "replace_page_copy":
        return f"标题：{item['title']}；正文：{item['body'].replace(chr(10), ' / ')}"
    if item["mode"] == "add_boundary_banner":
        return f"新增边界条：{item['banner']}"
    return "；".join(f"{old}→{new}" for old, new in item["replacements"])


def _authoring_section() -> str:
    lines = [
        SECTION_MARKER,
        "",
        "> 本节锁定两套课件首批P0页面的精确替换文案、讲者备注和验收条件。当前PPTX二进制尚未改写；只有通过演示文稿专用运行依赖或已连接PowerPoint会话编辑、全页渲染验收并由3021版本化回写后，页面状态才能转为“已完成”。",
        "",
        "### 6.1 生产状态与边界",
        "",
        "- 修订范围：54页课件6页、88页课件10页，共16页。",
        "- 优先级：先修规则口径和高风险旧参数，再修错字与历史资料边界，最后统一标题页和日期。",
        "- 当前状态：精确文案已锁定，等待安全PPT编辑通道；不得直接改写PPT内部XML。",
        "- 完成条件：原二进制进入版本库、新PPTX通过结构校验、所有目标词替换、16页逐页全尺寸复核、142页全量渲染无新增溢出。",
        "",
        "### 6.2 54页《谋战》实作课件修订表",
        "",
        "| 页码 | 编辑方式 | 精确修订内容 | 完成后状态 |",
        "| ---: | --- | --- | --- |",
    ]
    for slide, item in REVISIONS["doc-67294b2100be"].items():
        lines.append(f"| {slide} | `{item['mode']}` | {_copy_summary(item)} | `{item['target_status']}` |")
    lines.extend(
        [
            "",
            "### 6.3 88页课程导入与方法课件修订表",
            "",
            "| 页码 | 编辑方式 | 精确修订内容 | 完成后状态 |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for slide, item in REVISIONS["doc-5b225b46318f"].items():
        lines.append(f"| {slide} | `{item['mode']}` | {_copy_summary(item)} | `{item['target_status']}` |")
    lines.extend(
        [
            "",
            "### 6.4 讲者备注统一模板",
            "",
            "每个目标页嵌入五段式备注：讲解目标、教学动作、规则边界、检查问题和`[Sources]`来源块。逐页具体文本已写入对应PPT联动清单的`authoring_plan.speaker_notes`字段。",
            "",
            "### 6.5 页面级验收词",
            "",
            "- 54页课件必须出现：`交战级：1个交战步＝10秒`、`历史想定结构示例`、`复盘效用`；不得再出现：`手工兵器`、`交战级：1回合=30秒`、`复利效用`、`最终要`。",
            "- 88页课件必须出现：`随机事件：用概率表达作战不确定性`、`历史参数为什么不能直接用于裁决`、`通用任务规划字段示例`；不得再出现：`历史渊远流长`、`兵器界`、`对症结果`、`兵器规则`、`随机送`、`兵器推演`、`5800量`。",
            "- 两套课件不得把历史案例、口述数值或其他想定数据标记为0522权威裁决依据。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _current_internal_markdown(project: dict[str, Any]) -> str:
    context = multi_document_service.rich_project_context(project, INTERNAL_DOCUMENT_ID)
    manifest = document_workspace_service.ensure_workspace(context)
    working = Path(str(manifest.get("working_markdown") or ""))
    if not working.is_file():
        raise RuntimeError(f"内部底稿工作稿不存在：{working}")
    return working.read_text(encoding="utf-8")


def _updated_internal_markdown(current: str) -> str:
    base = current.split(SECTION_MARKER, 1)[0].rstrip()
    base = base.replace('content_version: "course-knowledge-selection-v1"', 'content_version: "course-knowledge-selection-v2"')
    return base + "\n\n" + _authoring_section()


def _replace_internal_markdown(project: dict[str, Any], markdown: str) -> None:
    context = multi_document_service.rich_project_context(project, INTERNAL_DOCUMENT_ID)
    manifest = document_workspace_service.ensure_workspace(context)
    if manifest.get("content_authority") == "structured_json":
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            INTERNAL_DOCUMENT_ID,
            markdown,
            label="课程课件第二阶段B精确修订包",
            actor="course-phase2b-preparation",
        )
        return
    multi_document_service.replace_rich_text_markdown(
        project,
        INTERNAL_DOCUMENT_ID,
        markdown,
        actor="course-phase2b-preparation",
    )


def _prepare_manifest(project: dict[str, Any], document_id: str) -> dict[str, Any]:
    manifest = multi_document_service.presentation_manifest(project, document_id)
    document = manifest.pop("document", None)
    binding = manifest.pop("structure_binding", None)
    original_manifest = copy.deepcopy(manifest)
    spec = phase2a.DECKS[document_id]
    path = multi_document_service._content_path(project, document or {"id": document_id, "kind": "presentation"})  # noqa: SLF001
    actual_sha = _sha256(path)
    if actual_sha != spec["expected_sha256"]:
        raise RuntimeError(f"{document_id} PPTX哈希已变化，停止准备：{actual_sha}")
    slide_map = {int(row["slide"]): row for row in manifest.get("slides") or []}
    if len(slide_map) != spec["slide_count"]:
        raise RuntimeError(f"{document_id}逐页联动清单不完整：{len(slide_map)}")
    deck_revisions = REVISIONS[document_id]
    for slide, item in deck_revisions.items():
        row = slide_map[slide]
        row["authoring_plan"] = {
            **copy.deepcopy(item),
            "speaker_notes": _speaker_notes(spec["label"], slide, item),
            "binary_applied": False,
            "visual_qa": "pending",
        }
    manifest["content_version"] = CONTENT_VERSION
    manifest["authoring_package"] = {
        "phase": PHASE_LABEL,
        "status": "ready_blocked_by_runtime",
        "blocked_by": BLOCKER,
        "target_slide_count": len(deck_revisions),
        "exact_visible_copy_locked": True,
        "speaker_notes_locked": True,
        "source_binary_sha256": actual_sha,
        "binary_mutated": False,
        "required_acceptance": [
            "versioned_binary_replacement",
            "target_string_scan",
            "target_slide_full_size_review",
            "all_slide_render_review",
            "manifest_hash_refresh",
        ],
    }
    output = manifest.setdefault("authority", {}).setdefault("presentation_output", {})
    output["status"] = "audited_pending_binary_revision"
    output["sha256"] = actual_sha
    review = manifest["authority"].setdefault("review", {})
    review["binary_revision_required"] = True
    review["authoring_package_ready"] = True
    review["authoring_package_target_slide_count"] = len(deck_revisions)
    return {
        "manifest": manifest,
        "binding": binding,
        "sha256": actual_sha,
        "changed": manifest != original_manifest,
    }


def _audit_markdown(previews: list[dict[str, Any]]) -> str:
    lines = [
        "---",
        'title: "课程课件P0精确修订生产包（第二阶段B准备）"',
        'status: "internal"',
        f'content_version: "{CONTENT_VERSION}"',
        'data_version: "course-baseline-20h-v4"',
        'rules_version: "R1.2/D1.2"',
        "---",
        "",
        "# 课程课件P0精确修订生产包（第二阶段B准备）",
        "",
        "> 本文件是内部生产记录，不计入16份正式成果。精确修订文案已锁定，但PPTX二进制未修改、未批准、未发布。",
        "",
        "## 一、范围",
        "",
    ]
    for row in previews:
        lines.append(f"- {row['label']}：{row['target_slide_count']}页，源SHA-256 `{row['sha256']}`。")
    lines.extend(["", "## 二、精确修订清单", "", _authoring_section(), "## 三、当前阻断", "", f"- `{BLOCKER}`：当前没有已连接PowerPoint会话，且未提供演示文稿专用运行依赖加载入口。", "- 禁止以直接XML改写、非专用脚本或会破坏母版/版式的方式绕过。", ""])
    return "\n".join(lines)


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")
    documents = multi_document_service.list_documents(project)["documents"]
    before_count = len(documents)
    internal = next((row for row in documents if row["id"] == INTERNAL_DOCUMENT_ID), None)
    if internal is None:
        raise RuntimeError("课程知识库优选底稿不存在")
    current_internal_markdown = _current_internal_markdown(project)

    prepared: dict[str, dict[str, Any]] = {}
    previews: list[dict[str, Any]] = []
    for document_id in REVISIONS:
        item = _prepare_manifest(project, document_id)
        prepared[document_id] = item
        previews.append(
            {
                "document_id": document_id,
                "label": phase2a.DECKS[document_id]["label"],
                "target_slide_count": len(REVISIONS[document_id]),
                "sha256": item["sha256"],
            }
        )

    revised_markdown = _updated_internal_markdown(current_internal_markdown)
    markdown_changed = revised_markdown != current_internal_markdown
    if dry_run:
        return {
            "phase": PHASE_LABEL,
            "dry_run": True,
            "document_count": before_count,
            "internal_document_update": markdown_changed,
            "presentation_manifest_updates": sum(1 for item in prepared.values() if item["changed"]),
            "binary_mutations": 0,
            "presentations": previews,
        }

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if markdown_changed:
        _replace_internal_markdown(project, revised_markdown)
    for document_id, prepared_item in prepared.items():
        if not prepared_item["changed"]:
            continue
        binding = prepared_item["binding"] or multi_document_service.structure_binding(project, document_id)
        multi_document_service.set_structure_binding(
            project,
            document_id,
            binding,
            manifest=prepared_item["manifest"],
        )

    workspace_root = multi_document_service._project_root(project)  # noqa: SLF001
    audit_path = workspace_root / "imported_sources" / "course_presentation_phase2b_authoring_package.md"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(_audit_markdown(previews), encoding="utf-8")

    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "presentation_phase2b_summary": "两套课件共16个P0页面的精确替换文案、讲者备注、验收词和回写顺序已锁定；PPTX原文件保持不变。",
            "presentation_editing_blocker": "当前运行环境未暴露演示文稿专用依赖加载入口，且无已连接PowerPoint会话；禁止绕过为直接XML改写。",
            "next_step": "连接合规PPT编辑通道后，按authoring_plan完成16页二进制修订、142页全量渲染和3021版本化回写。",
        }
    )
    project_manager.update_project(
        project_id,
        {"context": context, "current_phase": "course_presentation_phase2b_prepared"},
    )

    refreshed = project_manager.get_project(project_id) or project
    after_documents = multi_document_service.list_documents(refreshed)["documents"]
    verification = []
    for document_id, spec in phase2a.DECKS.items():
        manifest = multi_document_service.presentation_manifest(refreshed, document_id)
        path = multi_document_service._content_path(refreshed, manifest["document"])  # noqa: SLF001
        target_rows = [row for row in manifest["slides"] if row.get("authoring_plan")]
        verification.append(
            {
                "document_id": document_id,
                "pptx_sha256_unchanged": _sha256(path) == spec["expected_sha256"],
                "target_slide_count": len(target_rows),
                "all_visible_copy_locked": all(row["authoring_plan"].get("mode") for row in target_rows),
                "all_speaker_notes_locked": all(row["authoring_plan"].get("speaker_notes") for row in target_rows),
                "binary_applied": any(row["authoring_plan"].get("binary_applied") for row in target_rows),
                "authoring_status": manifest.get("authoring_package", {}).get("status"),
            }
        )
    return {
        "phase": PHASE_LABEL,
        "dry_run": False,
        "snapshot": str(snapshot),
        "audit_path": str(audit_path),
        "document_count_before": before_count,
        "document_count_after": len(after_documents),
        "internal_document_updated": markdown_changed,
        "binary_mutations": 0,
        "presentations": previews,
        "verification": verification,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=COURSE_PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
