"""Create and publish the two v34 chapter-one diagrams idempotently."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager
from services.diagram_service import diagram_service
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service
from services.writing_collaboration_service import writing_collaboration_service


PROJECT_ID = "proj-10fbeefae5"
TARGET_DOCUMENT_ID = "doc-0cdb6e81aebb"
SOURCE_DOCUMENT_ID = "doc-b555e198855d"
SOURCE_WORD = Path(
    "/Users/apple/工作桌面/knowledge/10-成果库-Outputs/毕业论文/博士论文/"
    "排版权威源/博士论文-第二版正式排版母稿-20260324.docx"
)
SOURCE_FIGURES = [
    Path(
        "/Users/apple/工作桌面/knowledge/06-项目库-Projects/博士论文/_workspace/"
        "documents/doc-b555e198855d/source/assets/1ec0f1ef6a01-image1.jpeg"
    ),
    Path(
        "/Users/apple/工作桌面/knowledge/06-项目库-Projects/博士论文/_workspace/"
        "documents/doc-b555e198855d/source/assets/bf4ec22fa518-image2.jpeg"
    ),
]

RESEARCH_PARAGRAPH_ID = "block-3a88c126bb780948f4cecd65"
ROADMAP_PARAGRAPH_ID = "block-572fda6c25a265c64244751c"
OLD_FIGURE_BLOCK_IDS = [
    "block-a6439c4583947555469dc59e",
    "block-c3e2614ca8d0b997919c57d3",
]

RESEARCH_PARAGRAPH = (
    "全文形成“指挥控制需求—理论机制—统一模型—分层方法—闭环证据”的研究链。"
    "指挥控制活动与海上无人集群运用矛盾界定任务级规划需要保持的意图、权限、任务链和风险边界；"
    "统一状态—价值机制为不同层级方案提供共同评价尺度；统一输入、规划解和双向接口连接任务结构、"
    "力量组织、任务内协同和执行恢复；统一想定、统一裁决、统一随机种子和可追踪记录共同构成理论与方法的验证闭环。"
    "总体研究框架如图1-1所示。"
)
ROADMAP_PARAGRAPH = (
    "技术路线以三个科学问题为牵引：Q1形成全局态势评价、空间优势场、统一目标与重规划判据；"
    "Q2形成MissionInput、EvaluationState、PlanSolution以及任务结构—资源配置—策略组织—执行可行性的双向映射；"
    "Q3形成任务内策略组织、受限自主协同、经典执行保障和分级恢复机制。"
    "三条研究线在规划—执行—评价闭环中汇合，具体技术路线如图1-2所示。"
)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _node(
    cell_id: str,
    label: str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    fill: str = "#f8fafc",
    stroke: str = "#4f6f91",
    font_size: int = 20,
    shape: str = "rect",
) -> dict[str, Any]:
    return {
        "id": cell_id,
        "cell_revision": 1,
        "type": "node",
        "shape": shape,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "label": label,
        "attrs": {
            "body": {
                "fill": fill,
                "stroke": stroke,
                "strokeWidth": 2,
                "rx": 8,
                "ry": 8,
            },
            "label": {
                "fill": "#162334",
                "fontSize": font_size,
                "fontWeight": 600,
                "textWrap": {"width": width - 28, "height": height - 18, "ellipsis": False},
            },
        },
    }


def _edge(cell_id: str, source: str, target: str, label: str = "") -> dict[str, Any]:
    return {
        "id": cell_id,
        "cell_revision": 1,
        "type": "edge",
        "shape": "edge",
        "source": source,
        "target": target,
        "label": label,
        "attrs": {
            "line": {
                "stroke": "#4f79a6",
                "strokeWidth": 2.2,
                "targetMarker": {"name": "block", "width": 11, "height": 8},
            }
        },
    }


def _feedback_edge(cell_id: str, source: str, target: str, label: str = "") -> dict[str, Any]:
    edge = _edge(cell_id, source, target, label)
    edge["attrs"]["line"]["stroke"] = "#6b7f93"
    edge["attrs"]["line"]["strokeDasharray"] = "8 6"
    return edge


def _figure_one_cells() -> list[dict[str, Any]]:
    cells = [
        _node("title", "海上无人集群智能协同任务规划总体研究框架", 100, 28, 1040, 68, fill="#ffffff", stroke="#ffffff", font_size=32),
        _node("problem", "问题提出\n跨域异构集群协同 · 指挥意图保持 · 动态规划与可验证执行", 80, 125, 920, 110, fill="#f3f7fb", font_size=24),
        _node("theory", "战术理论基础\n指挥控制与任务规划 · POMDP与BDI · 优势动力学 · 信息熵与组织熵", 80, 275, 920, 110, fill="#eef5fb", font_size=23),
        _node("architecture", "体系架构\n有人/无人协同 · 分层规划与动态评价 · 预先规划—临机规划—闭环重规划", 80, 425, 920, 115, fill="#edf7f4", stroke="#438071", font_size=23),
        _node("model", "统一规划产品与双向接口\n任务结构｜承担关系｜角色与资源｜规则、目标点与路径｜重规划标记", 120, 585, 840, 90, fill="#f6f3fb", stroke="#6a5a91", font_size=22),
        _node("method-model", "统一态势与规划模型\n全局评价 · 目标函数\n分层接口 · 重规划判据", 55, 735, 220, 175, fill="#e9f3fb", stroke="#3e78a8", font_size=21),
        _node("method-task", "任务分解与分配\nHTN任务图 · MARTA分配\n约束门控 · 可行性回退", 300, 735, 220, 175, fill="#fff5d9", stroke="#b88b2d", font_size=21),
        _node("method-weapon", "规则武器运用策略\n威胁排序 · 武器匹配\n火力分配 · 授权控制", 545, 735, 220, 175, fill="#fbeaea", stroke="#b85b5b", font_size=21),
        _node("method-maneuver", "协同机动策略\n共享目标 · 编队与速度\n经典规划与执行反馈", 790, 735, 220, 175, fill="#eaf7ef", stroke="#4a8a62", font_size=21),
        _node("validation", "仿真验证与战术效能评估\n统一想定、裁决规则与随机种子 · 基线、消融与扰动实验\n完整记录成功、失败、超时和统计证据", 100, 980, 900, 135, fill="#f3f7fb", font_size=21),
        _node("feedback", "验证反馈\n模型修正\n约束校准\n方法迭代", 1040, 275, 140, 635, fill="#ffffff", stroke="#6b7f93", font_size=19),
        _edge("e-problem-theory", "problem", "theory"),
        _edge("e-theory-architecture", "theory", "architecture"),
        _edge("e-architecture-model", "architecture", "model"),
        _edge("e-model-model", "model", "method-model"),
        _edge("e-model-task", "model", "method-task"),
        _edge("e-model-weapon", "model", "method-weapon"),
        _edge("e-model-maneuver", "model", "method-maneuver"),
        _edge("e-method-model-validation", "method-model", "validation"),
        _edge("e-method-task-validation", "method-task", "validation"),
        _edge("e-method-weapon-validation", "method-weapon", "validation"),
        _edge("e-method-maneuver-validation", "method-maneuver", "validation"),
        _feedback_edge("e-validation-feedback", "validation", "feedback"),
        _feedback_edge("e-feedback-theory", "feedback", "theory"),
    ]
    return cells


def _figure_two_cells() -> list[dict[str, Any]]:
    return [
        _node("title", "海上无人集群智能协同任务规划技术路线", 100, 28, 1040, 68, fill="#ffffff", stroke="#ffffff", font_size=32),
        _node("theory", "理论基础\nPOMDP不确定性建模｜BDI意图与组织建模｜优势动力学｜信息熵与组织熵", 80, 125, 920, 115, fill="#eef5fb", font_size=23),
        _node("evaluation", "Q1 统一状态与动态评价\n全局态势价值 · 空间优势场\n统一目标与重规划判据", 100, 310, 420, 130, fill="#edf7f4", stroke="#438071", font_size=22),
        _node("framework", "分层规划与协同决策\n任务结构—力量组织—任务内协同\n执行监控与分级恢复", 580, 310, 420, 130, fill="#edf7f4", stroke="#438071", font_size=22),
        _node("object-chain", "统一规划对象与双向接口\n任务输入｜评价状态｜规划解｜任务交接｜策略集合｜执行与评价记录", 130, 500, 820, 90, fill="#f6f3fb", stroke="#6a5a91", font_size=22),
        _node("q1", "研究链 Q1\n全局态势评价\n空间优势场\n动态重规划", 75, 665, 280, 175, fill="#e9f3fb", stroke="#3e78a8", font_size=22),
        _node("q2", "研究链 Q2\nHTN任务分解\nMARTA任务分配\n约束校核与回退", 400, 665, 280, 175, fill="#fff5d9", stroke="#b88b2d", font_size=22),
        _node("q3", "研究链 Q3\n规则约束的策略组织\n协同机动与执行保障\n分级恢复", 725, 665, 280, 175, fill="#fbeaea", stroke="#b85b5b", font_size=22),
        _node("command", "策略合成与执行\n策略决策 → 命令生成 → 权威环境裁决 → 执行轨迹", 140, 900, 840, 95, fill="#eaf7ef", stroke="#4a8a62", font_size=22),
        _node("validation", "仿真验证与证据闭环\n冻结想定、裁决规则和随机种子 · 设置基线、消融、扰动与规模扩展实验\n从完整运行记录形成可复核的战术效能结论", 120, 1045, 880, 115, fill="#f3f7fb", font_size=21),
        _node("feedback", "反馈修正\n理论校准\n方法迭代", 1040, 310, 140, 530, fill="#ffffff", stroke="#6b7f93", font_size=19),
        _edge("e-theory-evaluation", "theory", "evaluation"),
        _edge("e-theory-framework", "theory", "framework"),
        _edge("e-evaluation-chain", "evaluation", "object-chain"),
        _edge("e-framework-chain", "framework", "object-chain"),
        _edge("e-chain-q1", "object-chain", "q1"),
        _edge("e-chain-q2", "object-chain", "q2"),
        _edge("e-chain-q3", "object-chain", "q3"),
        _edge("e-q1-command", "q1", "command"),
        _edge("e-q2-command", "q2", "command"),
        _edge("e-q3-command", "q3", "command"),
        _edge("e-command-validation", "command", "validation"),
        _feedback_edge("e-validation-feedback", "validation", "feedback"),
        _feedback_edge("e-feedback-theory", "feedback", "theory"),
    ]


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _find_block(state: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    return next(
        (
            block
            for block in (state.get("document") or {}).get("content") or []
            if str((block.get("attrs") or {}).get("blockId") or "") == block_id
        ),
        None,
    )


def _replace_paragraph(project: dict[str, Any], block_id: str, text: str, client_id: str) -> None:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)
    block = _find_block(state, block_id)
    if not block:
        raise DocumentWorkspaceError(f"第一章过渡段不存在：{block_id}")
    current_text = "".join(str(row.get("text") or "") for row in block.get("content") or [])
    if current_text == text:
        return
    writing_collaboration_service.patch_draft(
        project,
        TARGET_DOCUMENT_ID,
        {
            "expected_revision": state["document_revision"],
            "client_change_id": client_id,
            "operations": [{
                "op": "replace",
                "block_id": block_id,
                "expected_block_revision": int((block.get("attrs") or {}).get("blockRevision") or 1),
                "node": _paragraph(text),
            }],
        },
        "thesis-diagram-migration",
    )


def _ensure_diagram(
    project: dict[str, Any],
    title: str,
    diagram_type: str,
    cells: list[dict[str, Any]],
    source_figure: Path,
) -> dict[str, Any]:
    listed = diagram_service.list(project).get("diagrams") or []
    existing = next((row for row in listed if row.get("title") == title), None)
    page_settings = {"width": 1240, "height": 1180, "background": "#ffffff", "grid_size": 8}
    if not existing:
        resource = diagram_service.create(
            project,
            {
                "title": title,
                "diagram_type": diagram_type,
                "theme_id": "academic-thesis",
                "page_settings": page_settings,
                "cells": cells,
            },
            "thesis-diagram-migration",
        )
        diagram_id = resource["document"]["id"]
    else:
        diagram_id = str(existing["id"])
        current = diagram_service.get(project, diagram_id)["diagram"]
        desired = {
            "title": title,
            "diagram_type": diagram_type,
            "theme_id": "academic-thesis",
            "page_settings": page_settings,
            "cells": cells,
        }
        comparable = {key: current.get(key) for key in desired}
        comparable["cells"] = [
            {key: value for key, value in cell.items() if key != "cell_revision"}
            for cell in comparable.get("cells") or []
        ]
        desired_comparable = copy.deepcopy(desired)
        desired_comparable["cells"] = [
            {key: value for key, value in cell.items() if key != "cell_revision"}
            for cell in desired_comparable["cells"]
        ]
        if comparable != desired_comparable:
            diagram_service.update_draft(
                project,
                diagram_id,
                {"expected_revision": current["revision"], **desired},
                "thesis-diagram-migration",
            )
    multi_document_service.update_document(
        project,
        diagram_id,
        {
            "lineage": {
                "series_id": "thesis-v34-chapter-1-diagrams",
                "source_type": "structured_diagram",
                "source_document_id": SOURCE_DOCUMENT_ID,
                "source_figure_path": str(source_figure),
                "source_figure_sha256": _sha_file(source_figure),
                "source_word_path": str(SOURCE_WORD),
                "source_word_sha256": _sha_file(SOURCE_WORD),
                "target_document_id": TARGET_DOCUMENT_ID,
            }
        },
    )
    diagram_service.create_version(
        project,
        diagram_id,
        {"label": "v34第一章审校版", "reason": "chapter-1-redraw"},
        "thesis-diagram-migration",
    )
    return diagram_service.get(project, diagram_id)


def _figure_blocks(state: dict[str, Any], label: str) -> list[dict[str, Any]]:
    return [
        block
        for block in (state.get("document") or {}).get("content") or []
        if str((block.get("attrs") or {}).get("artifactLabel") or "") == label
        and str((block.get("attrs") or {}).get("artifactKind") or "")
        in {"figure", "figure-caption"}
    ]


def _publish(
    project: dict[str, Any],
    diagram: dict[str, Any],
    *,
    label: str,
    caption: str,
    anchor_id: str,
    replace_ids: list[str],
    client_id: str,
) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)
    current_blocks = _figure_blocks(state, label)
    diagram_revision = int(diagram["diagram"]["revision"])
    revision_marker = f"{diagram['document']['id']}-r{diagram_revision}-"
    current_image = next((block for block in current_blocks if block.get("type") == "image"), None)
    if current_image and revision_marker in str((current_image.get("attrs") or {}).get("src") or ""):
        return {"skipped": True, "reason": f"{label} revision {diagram_revision} already published"}
    existing_ids = {
        str((block.get("attrs") or {}).get("blockId") or "")
        for block in (state.get("document") or {}).get("content") or []
    }
    current_block_ids = [
        str((block.get("attrs") or {}).get("blockId") or "")
        for block in current_blocks
    ]
    return diagram_service.publish_to_document(
        project,
        diagram["document"]["id"],
        {
            "target_document_id": TARGET_DOCUMENT_ID,
            "expected_document_revision": state["document_revision"],
            "expected_diagram_revision": diagram["diagram"]["revision"],
            "anchor_block_id": anchor_id,
            "replace_block_ids": [
                value
                for value in [*replace_ids, *current_block_ids]
                if value in existing_ids
            ],
            "figure_label": label,
            "caption": caption,
            "width": "145mm",
            "export_format": "svg",
            "client_change_id": f"{client_id}-r{diagram_revision}",
        },
        "thesis-diagram-migration",
    )


def _backup(project: dict[str, Any]) -> Path:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)
    root = multi_document_service._project_root(project)  # noqa: SLF001
    target = root / "versions" / f"before-ch1-diagrams-r{state['document_revision']:06d}"
    target.mkdir(parents=True, exist_ok=True)
    state_path = target / "structured-document.json"
    if not state_path.exists():
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    documents = root / "documents.json"
    if documents.is_file() and not (target / "documents.json").exists():
        shutil.copy2(documents, target / "documents.json")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "target_document_id": TARGET_DOCUMENT_ID,
        "document_revision": state["document_revision"],
        "source_word": {"path": str(SOURCE_WORD), "sha256": _sha_file(SOURCE_WORD)},
        "source_figures": [
            {"path": str(path), "sha256": _sha_file(path)} for path in SOURCE_FIGURES
        ],
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    multi_document_service.assert_writable(project, TARGET_DOCUMENT_ID)
    if not SOURCE_WORD.is_file() or not all(path.is_file() for path in SOURCE_FIGURES):
        raise SystemExit("第二版Word或参考图缺失，已阻止重绘")

    backup = _backup(project)
    figure_one = _ensure_diagram(
        project,
        "图1-1 海上无人集群智能协同任务规划总体研究框架",
        "thesis-overall-framework",
        _figure_one_cells(),
        SOURCE_FIGURES[0],
    )
    figure_two = _ensure_diagram(
        project,
        "图1-2 海上无人集群智能协同任务规划技术路线",
        "thesis-technology-roadmap",
        _figure_two_cells(),
        SOURCE_FIGURES[1],
    )

    _replace_paragraph(project, RESEARCH_PARAGRAPH_ID, RESEARCH_PARAGRAPH, "thesis-v34-ch1-research-transition-v1")
    publish_one = _publish(
        project,
        figure_one,
        label="图1-1",
        caption="海上无人集群智能协同任务规划总体研究框架",
        anchor_id=RESEARCH_PARAGRAPH_ID,
        replace_ids=[],
        client_id="thesis-v34-ch1-figure-1",
    )
    _replace_paragraph(project, ROADMAP_PARAGRAPH_ID, ROADMAP_PARAGRAPH, "thesis-v34-ch1-roadmap-transition-v1")
    publish_two = _publish(
        project,
        figure_two,
        label="图1-2",
        caption="海上无人集群智能协同任务规划技术路线",
        anchor_id=ROADMAP_PARAGRAPH_ID,
        replace_ids=OLD_FIGURE_BLOCK_IDS,
        client_id="thesis-v34-ch1-figure-2",
    )
    final_state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)
    print(json.dumps({
        "backup": str(backup),
        "figure_one_id": figure_one["document"]["id"],
        "figure_two_id": figure_two["document"]["id"],
        "publish_one": {
            "skipped": bool(publish_one.get("skipped")),
            "document_revision": publish_one.get("document_revision"),
            "diagram_revision": publish_one.get("diagram_revision"),
            "reason": publish_one.get("reason"),
        },
        "publish_two": {
            "skipped": bool(publish_two.get("skipped")),
            "document_revision": publish_two.get("document_revision"),
            "diagram_revision": publish_two.get("diagram_revision"),
            "reason": publish_two.get("reason"),
        },
        "document_revision": final_state["document_revision"],
        "projection": final_state["projection"],
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
