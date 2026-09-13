#!/usr/bin/env python3
"""Audit and remap the two course presentations without mutating PPTX binaries."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.course_production_service import COURSE_PROJECT_ID  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402


PHASE_LABEL = "课程开学准备第二阶段A：课件审计与联动"
CONTENT_VERSION = "surface-course-presentation-phase2a-v1"
DECKS = {
    "doc-67294b2100be": {
        "label": "54页《谋战》手工兵棋讲解",
        "expected_sha256": "79f9b517578e71881f15f124e344f5cc6794c9d03f720f25ffa03debb5494bc9",
        "slide_count": 54,
        "source_document_id": "doc-e6071aa369ed",
        "allowed_units": ["L03", "L04", "L05", "L06", "L07", "L08", "L09"],
        "narrative_sections": [
            {"id": "foundation", "title": "兵棋作用、概念与课程定位", "start_slide": 1, "end_slide": 14},
            {"id": "components", "title": "《谋战》组成、规则与裁决流程", "start_slide": 15, "end_slide": 29},
            {"id": "roles", "title": "推演组织与五人编组", "start_slide": 30, "end_slide": 34},
            {"id": "workflow", "title": "想定、部署、推演与复盘", "start_slide": 35, "end_slide": 42},
            {"id": "software_ai", "title": "兵棋、作战软件与智能决策", "start_slide": 43, "end_slide": 54},
        ],
        "appendix": {35, 45, 46, 47, 51, 52},
        "critical": {
            17: ("rewrite_required", "页面存在“手工兵器”错字，正式授课前改为“手工兵棋”。"),
            28: ("rewrite_required", "交战级时间步仍写为30秒，与当前课程基线10秒冲突；修订前禁止作为正式规则讲授。"),
            35: ("retain_with_boundary", "本页为历史想定结构示例，不是0522权威想定；只讲想定字段，不得引用其中平台和兵力数据裁决。"),
            42: ("rewrite_required", "“复利效用”“最终要”等文字错误需修正为“复盘效用”“最重要”。"),
        },
    },
    "doc-5b225b46318f": {
        "label": "88页兵棋推演与智能决策培训课件",
        "expected_sha256": "b708023dbb29ce19c0b2e9f683512253e9e9669fb01e652c932474bc7e2a1d09",
        "slide_count": 88,
        "source_document_id": "doc-e811bedd87f9",
        "allowed_units": [f"L{number:02d}" for number in range(1, 11)],
        "narrative_sections": [
            {"id": "overview", "title": "兵棋概述与构成", "start_slide": 1, "end_slide": 25},
            {"id": "decision", "title": "决策、任务规划与兵棋作用", "start_slide": 26, "end_slide": 47},
            {"id": "practice", "title": "兵棋运用与课程实作方法", "start_slide": 48, "end_slide": 68},
            {"id": "intelligence", "title": "兵棋、作战软件与智能决策", "start_slide": 69, "end_slide": 86},
            {"id": "assessment", "title": "总结、答疑与仿真验证", "start_slide": 87, "end_slide": 88},
        ],
        "appendix": {
            *range(5, 15),
            *range(43, 47),
            49,
            50,
            52,
            *range(61, 69),
            *range(73, 79),
            *range(82, 87),
        },
        "critical": {
            5: ("rewrite_required", "“历史渊远流长”“兵器界”等文字错误需修订。"),
            20: ("rewrite_required", "页面存在“对症结果”“兵器规则”等错字，需统一为兵棋裁决表述。"),
            23: ("rewrite_required", "随机事件说明含多处错字，需重写为可教学的概率裁决说明。"),
            32: ("retain_with_boundary", "“蓝鹰”任务为通用示例，不是0522想定；只用于任务规划字段教学。"),
            45: ("rewrite_required", "页面含“合湾、合军、平合”等错字，且历史资料来源待补充。"),
            52: ("rewrite_required", "伯克、F-35C、弗吉尼亚参数属于历史/未核验示例，禁止用于0522裁决；应改为规则查用反例或换成当前权威数据。"),
            61: ("rewrite_required", "页面将“兵棋推演”误写为“兵器推演”，需修正并压缩文字。"),
            65: ("retain_with_boundary", "海湾战争桌游案例属于方法案例，需补充来源并避免把故事性叙述当作严格因果证据。"),
            67: ("rewrite_required", "兵力数字和“5800量”等表述需来源核验与文字修正；建议仅放附录。"),
        },
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slide_texts(path: Path) -> list[str]:
    namespace = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    import xml.etree.ElementTree as ET

    texts: list[str] = []
    with ZipFile(path) as archive:
        for slide_number in range(1, 1000):
            name = f"ppt/slides/slide{slide_number}.xml"
            try:
                payload = archive.read(name)
            except KeyError:
                break
            root = ET.fromstring(payload)
            values = [node.text.strip() for node in root.iter(f"{namespace}t") if node.text and node.text.strip()]
            texts.append(" ".join(values))
    return texts


def _compact_title(text: str, slide: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return f"第{slide}页"
    for repeated in (
        "兵棋在现代军事中的作用意义",
        "水面舰艇编队战术手工兵棋",
        "海军大连舰艇学院",
    ):
        cleaned = cleaned.replace(repeated, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ｜|：:")
    title = re.split(r"[。；;]", cleaned)[0].strip()
    return (title[:30] or f"第{slide}页").strip()


def _units_54(slide: int) -> list[str]:
    if slide in {5, 6}:
        return ["L03", "L08"]
    if 1 <= slide <= 27:
        return ["L03"]
    if slide in {28, 29, 38}:
        return ["L04"]
    if 30 <= slide <= 34:
        return ["L06"]
    if slide == 35:
        return ["L05"]
    if slide in {36, 37}:
        return ["L06"]
    if slide == 39:
        return ["L07"]
    if 40 <= slide <= 54:
        return ["L09"]
    raise ValueError(f"54页课件未映射页面：{slide}")


def _units_88(slide: int) -> list[str]:
    if 1 <= slide <= 25:
        return ["L01"]
    if 26 <= slide <= 47:
        return ["L02"]
    if slide in {48, 49, 50, 51, 52}:
        return ["L03"]
    if slide == 53:
        return ["L05"]
    if slide == 54:
        return ["L06"]
    if slide == 55:
        return ["L05", "L09"]
    if slide == 56:
        return ["L08", "L09"]
    if slide == 57:
        return ["L03", "L04", "L05", "L06", "L07", "L08", "L09"]
    if 58 <= slide <= 60:
        return ["L05", "L09"]
    if 61 <= slide <= 68:
        return ["L09"]
    if 69 <= slide <= 86:
        return ["L09"]
    if slide in {87, 88}:
        return ["L10"]
    raise ValueError(f"88页课件未映射页面：{slide}")


def _claim(units: list[str]) -> str:
    labels = {
        "L01": "建立兵棋概念、构成和课程价值的共同认识",
        "L02": "理解水面舰艇编队战术、任务规划、指挥控制与裁决链",
        "L03": "掌握《谋战》地图、棋子、规则手册和裁决表的配套查用",
        "L04": "按10秒交战级事件完成合法操作、裁决和状态记录",
        "L05": "从权威想定提取任务、兵力、边界、情报条件和胜负判据",
        "L06": "形成五人编组、席位协同、部署和行动方案",
        "L07": "组织侦察预警、电子战和可追溯的信息共享",
        "L08": "组织制空支援、对海打击与分层防空反导",
        "L09": "围绕关键点完成跨域综合对抗、软件复核和证据化复盘",
        "L10": "按统一量规完成综合考核、证据定位和复盘答辩",
    }
    return "；".join(labels[unit] for unit in units)


def _notes(
    deck_label: str,
    slide: int,
    units: list[str],
    claim: str,
    status: str,
    issue: str,
) -> str:
    boundary = issue or "本页只用于课程方法与机制说明；具体规则、参数和裁决以R1.2/D1.2及登记数据为准。"
    return "\n".join(
        [
            f"【课程定位】{'、'.join(units)}",
            f"【本页主张】{claim}。",
            f"【审查状态】{status}",
            f"【讲解要点】结合{deck_label}第{slide}页讲清动作、规则、结果和证据之间的关系。",
            f"【规则边界】{boundary}",
            "【资料来源】",
            f"- {deck_label}源第{slide}页",
            "- 《谋战》R1.2/D1.2三册规则",
            "- 课程知识库优选底稿与参数核验矩阵",
        ]
    )


def _build_manifest(project: dict[str, Any], document_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    manifest = multi_document_service.presentation_manifest(project, document_id)
    document = manifest.pop("document", None)
    manifest.pop("structure_binding", None)
    path = multi_document_service._content_path(project, document or {"id": document_id, "kind": "presentation"})  # noqa: SLF001
    if not path.is_file():
        path = multi_document_service.source_file(project, document_id)
    current_sha256 = _sha256(path)
    if current_sha256 != spec["expected_sha256"]:
        raise RuntimeError(f"{document_id} PPTX哈希已变化，停止迁移：{current_sha256}")
    texts = _slide_texts(path)
    if len(texts) != spec["slide_count"]:
        raise RuntimeError(f"{document_id}页数异常：{len(texts)}")

    slides = []
    for slide, text in enumerate(texts, start=1):
        units = _units_54(slide) if spec["slide_count"] == 54 else _units_88(slide)
        status, issue = spec["critical"].get(slide, ("retain", ""))
        claim = _claim(units)
        slides.append(
            {
                "slide": slide,
                "source_slide": slide,
                "title": _compact_title(text, slide),
                "thesis_sections": units,
                "claim": claim,
                "evidence_level": "D",
                "evidence_ids": ["doc-6cec684156d3", "doc-8c97c44611e2"],
                "notes": _notes(spec["label"], slide, units, claim, status, issue),
                "appendix": slide in spec["appendix"],
                "review_status": status,
                "review_issue": issue,
                "evidence": {
                    "level": "D",
                    "ids": ["doc-6cec684156d3", "doc-8c97c44611e2"],
                    "boundary": issue or "具体规则、参数和裁决以R1.2/D1.2及登记数据为准。",
                },
            }
        )

    appendix_count = sum(1 for row in slides if row["appendix"])
    review_counts: dict[str, int] = {}
    for row in slides:
        review_counts[row["review_status"]] = review_counts.get(row["review_status"], 0) + 1

    manifest.update(
        {
            "schema": "openclaw.course-presentation-mapping",
            "contract_version": "course-baseline-20h-v4-presentation-audit",
            "content_version": CONTENT_VERSION,
            "narrative_sections": spec["narrative_sections"],
            "slides": slides,
        }
    )
    authority = manifest.setdefault("authority", {})
    output = authority.setdefault("presentation_output", {})
    output.update(
        {
            "sha256": current_sha256,
            "slide_count": len(slides),
            "main_slide_count": len(slides) - appendix_count,
            "appendix_slide_count": appendix_count,
            "notes_count": 0,
            "status": "audited_pending_binary_revision",
            "publication_status": "draft",
        }
    )
    authority["course"] = {
        "project_id": COURSE_PROJECT_ID,
        "data_version": "course-baseline-20h-v4",
        "rules_version": "R1.2/D1.2",
        "hours": 20,
        "sessions": 10,
        "structure": "2次理论＋7次实作＋1次考核",
        "role": "canonical-course-baseline",
    }
    authority["review"] = {
        "reviewed_slide_count": len(slides),
        "review_counts": review_counts,
        "binary_revision_required": any(row["review_status"] == "rewrite_required" for row in slides),
        "embedded_speaker_notes_available": False,
        "reviewed_at": "2026-08-14",
    }
    return manifest


def _audit_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "---",
        'title: "课程课件逐页审计与10讲映射（第二阶段A）"',
        'status: "internal"',
        f'content_version: "{CONTENT_VERSION}"',
        'data_version: "course-baseline-20h-v4"',
        'rules_version: "R1.2/D1.2"',
        "---",
        "",
        "# 课程课件逐页审计与10讲映射（第二阶段A）",
        "",
        "> 本文件是内部生产记录，不计入16份正式成果。两套PPTX二进制保持原样；本阶段只固化逐页用途、讲次映射、证据边界、附录划分和待重写状态。",
        "",
        "## 一、审计结论",
        "",
        "- 课程基线：20学时、10次课，L01—L02理论、L03—L09实作、L10考核。",
        "- 规则基线：《谋战》R1.2/D1.2；历史案例、口述参数和旧课件数值不得进入正式裁决。",
        "- 两套课件共142页，已完成文本与视觉逐页检查；原PPTX未修改、未批准、未发布。",
        "- 54页课件定位为L03—L09实作支撑课件；88页课件定位为L01—L10课程导入、方法与案例库。",
        "",
        "## 二、课件状态",
        "",
        "| 课件 | 页数 | 主讲页 | 附录页 | 待重写 | 带边界保留 | 二进制状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        counts = result["review_counts"]
        lines.append(
            f"| {result['label']} | {result['slide_count']} | {result['main_slide_count']} | "
            f"{result['appendix_slide_count']} | {counts.get('rewrite_required', 0)} | "
            f"{counts.get('retain_with_boundary', 0)} | 原文件未改 |"
        )
    lines.extend(
        [
            "",
            "## 三、P0修订项",
            "",
            "1. 54页课件第28页：交战级时间步由旧口径30秒改为当前10秒，并注明其他时间层级只在对应规则启用时使用。",
            "2. 54页课件第35页、88页课件第32页：统一标为“历史/通用想定结构示例”，不得作为0522想定事实。",
            "3. 88页课件第52页：移出主讲序列，改造为“历史参数为什么不能直接用于裁决”的规则查用反例；正式裁决只读R1.2/D1.2及登记数据。",
            "4. 修正“手工兵器、兵器规则、随机送、复利效用、最终要、合湾、平合”等明显错字。",
            "",
            "## 四、下一步",
            "",
            "安全PPT编辑通道恢复后，按manifest中的`review_status`逐页回写：先完成P0规则与参数边界，再压缩高密度文字页，最后补充嵌入式讲者备注并全页渲染验收。",
        ]
    )
    return "\n".join(lines) + "\n"


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")

    documents = {row["id"]: row for row in multi_document_service.list_documents(project)["documents"]}
    previews = []
    manifests: dict[str, dict[str, Any]] = {}
    for document_id, spec in DECKS.items():
        if document_id not in documents:
            raise RuntimeError(f"课件文档不存在：{document_id}")
        manifest = _build_manifest(project, document_id, spec)
        manifests[document_id] = manifest
        counts = manifest["authority"]["review"]["review_counts"]
        output = manifest["authority"]["presentation_output"]
        previews.append(
            {
                "document_id": document_id,
                "label": spec["label"],
                "slide_count": output["slide_count"],
                "main_slide_count": output["main_slide_count"],
                "appendix_slide_count": output["appendix_slide_count"],
                "review_counts": counts,
                "pptx_sha256": output["sha256"],
                "source_document_id": spec["source_document_id"],
            }
        )

    if dry_run:
        return {"phase": PHASE_LABEL, "dry_run": True, "presentations": previews}

    snapshot = p0._snapshot(project)  # noqa: SLF001
    for document_id, spec in DECKS.items():
        binding = {
            "mode": "mapped",
            "source_document_id": spec["source_document_id"],
            "source_version": "course-baseline-20h-v4",
            "source_sha256": "",
            "status": "aligned",
            "mapped_items": spec["slide_count"],
            "unmapped_items": [],
            "changed_sections": [],
        }
        multi_document_service.set_structure_binding(
            project,
            document_id,
            binding,
            manifest=manifests[document_id],
        )

    workspace_root = multi_document_service._project_root(project)  # noqa: SLF001
    audit_path = workspace_root / "imported_sources" / "course_presentation_phase2a_audit.md"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(_audit_markdown(previews), encoding="utf-8")

    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "presentation_audit_summary": "两套课件共142页已完成逐页审计与10讲映射；54页课件6页转附录、88页课件36页转附录；PPTX原文件未改。",
            "presentation_editing_blocker": "当前运行环境未暴露演示文稿专用依赖加载入口，且无已连接PowerPoint会话；禁止绕过为直接XML改写。",
            "next_step": "恢复安全PPT编辑通道后，先修正交战级10秒、历史想定边界和旧参数页，再完成逐页版式与讲者备注回写。",
        }
    )
    project_manager.update_project(
        project_id,
        {
            "context": context,
            "current_phase": "course_presentation_phase2a",
        },
    )

    refreshed = project_manager.get_project(project_id) or project
    verification = []
    for document_id, spec in DECKS.items():
        record = multi_document_service.get_document(refreshed, document_id)
        manifest = multi_document_service.presentation_manifest(refreshed, document_id)
        slides = manifest["slides"]
        output = manifest["authority"]["presentation_output"]
        allowed = set(spec["allowed_units"])
        verification.append(
            {
                "document_id": document_id,
                "slide_count": len(slides),
                "all_slides_mapped": all(row.get("thesis_sections") for row in slides),
                "units_within_scope": all(set(row["thesis_sections"]).issubset(allowed) for row in slides),
                "all_manifest_notes_present": all(str(row.get("notes") or "").strip() for row in slides),
                "embedded_speaker_notes_count": output["notes_count"],
                "pptx_sha256_unchanged": output["sha256"] == spec["expected_sha256"],
                "structure_binding_status": record["structure_binding"]["status"],
                "publication_status": record["publication_status"],
            }
        )
    return {
        "phase": PHASE_LABEL,
        "dry_run": False,
        "snapshot": str(snapshot),
        "audit_path": str(audit_path),
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
