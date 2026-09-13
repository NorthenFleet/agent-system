"""Create the five editable Chapter 2 thesis diagrams in 3021.

Stage 1 deliberately creates/version-controls diagram documents and exports
review artifacts. It does not publish them into the thesis body.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager
from services.diagram_service import diagram_service
from services.multi_document_service import multi_document_service


PROJECT_ID = "proj-10fbeefae5"
TARGET_DOCUMENT_ID = "doc-0cdb6e81aebb"
SOURCE_DOCUMENT_ID = "doc-b555e198855d"
ACTOR = "thesis-ch2-diagram-stage1"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第二章配图"
SOURCE_ROOT = OUTPUT_ROOT / "01-source"
EXPORT_ROOT = OUTPUT_ROOT / "02-review-exports"
REPORT_ROOT = OUTPUT_ROOT / "03-reports"

SOURCE_WORD = (
    KNOWLEDGE
    / "10-成果库-Outputs/毕业论文/博士论文/排版权威源/博士论文-第二版正式排版母稿-20260324.docx"
)
SOURCE_MARKDOWN = (
    KNOWLEDGE
    / "10-成果库-Outputs/毕业论文/博士论文/论文章节/版本/第三版/博士论文-第三版-七章工作稿.md"
)
CURRENT_ASSET_ROOT = (
    KNOWLEDGE
    / "06-项目库-Projects/博士论文/_workspace/documents/doc-0cdb6e81aebb/source/assets/figures/structure/svg"
)
SECOND_EDITION_FIGURE = (
    KNOWLEDGE
    / "06-项目库-Projects/博士论文/_workspace/documents/doc-b555e198855d/source/assets/f4627aeb5442-image3.png"
)
CURRENT_FIGURES = {
    "fig2-1": CURRENT_ASSET_ROOT / "ch2-c2-mission-planning-loop-v23.svg",
    "fig2-2": CURRENT_ASSET_ROOT / "ch2-intent-to-task-graph-v23.svg",
    "fig2-4": CURRENT_ASSET_ROOT / "ch2-global-situation-advantage-field-v25.svg",
}

PAGE = {"width": 1600, "height": 900, "background": "#ffffff", "grid_size": 8}


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
    stroke: str = "#496b8e",
    font_size: int = 24,
    font_weight: int = 600,
    label_color: str = "#172334",
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
                "fill": label_color,
                "fontSize": font_size,
                "fontWeight": font_weight,
                "textWrap": {
                    "width": max(width - 24, 40),
                    "height": max(height - 16, 30),
                    "ellipsis": False,
                },
            },
        },
    }


def _edge(
    cell_id: str,
    source: str,
    target: str,
    label: str = "",
    *,
    stroke: str = "#4f79a6",
    dashed: bool = False,
) -> dict[str, Any]:
    line: dict[str, Any] = {
        "stroke": stroke,
        "strokeWidth": 2.2,
        "targetMarker": {"name": "block", "width": 11, "height": 8},
    }
    if dashed:
        line["strokeDasharray"] = "8 6"
    return {
        "id": cell_id,
        "cell_revision": 1,
        "type": "edge",
        "shape": "edge",
        "source": source,
        "target": target,
        "label": label,
        "attrs": {"line": line},
    }


def _title(label: str) -> dict[str, Any]:
    return _node(
        "title",
        label,
        140,
        24,
        1320,
        64,
        fill="#ffffff",
        stroke="#ffffff",
        font_size=31,
    )


def _figure_2_1_cells() -> list[dict[str, Any]]:
    cells = [
        _title("指挥控制闭环中的任务规划定位及多流关系"),
        _node("mission", "任务受领", 40, 150, 210, 105, fill="#eaf1f8"),
        _node("situation", "态势认知", 300, 150, 210, 105, fill="#edf5f0", stroke="#4f8066"),
        _node("decision", "决心形成", 560, 150, 210, 105, fill="#eaf1f8"),
        _node("planning", "任务规划", 820, 150, 210, 105, fill="#edf5f0", stroke="#4f8066"),
        _node("control", "行动控制", 1080, 150, 210, 105, fill="#eaf1f8"),
        _node("evaluation", "效果评价", 1340, 150, 210, 105, fill="#edf5f0", stroke="#4f8066"),
        _node(
            "planning-core",
            "任务规划核心职能\n意图解析 · 任务分解 · 资源组织 · 时空协调 · 风险校核",
            430,
            365,
            740,
            140,
            fill="#f4f0f8",
            stroke="#756493",
            font_size=23,
        ),
        _node(
            "state-object",
            "统一状态对象\n观测 · 信念 · 任务结构 · 承担关系 · 方案 · 轨迹 · 评价记录",
            310,
            650,
            980,
            125,
            fill="#f6f8fb",
            stroke="#566b82",
            font_size=23,
        ),
        _node(
            "human-boundary",
            "人工授权边界\n目的与风险 · 规则变更\n重大越界上行确认",
            1320,
            405,
            235,
            165,
            fill="#f7efe7",
            stroke="#91603a",
            font_size=21,
        ),
        _node(
            "legend",
            "控制流：任务与命令     信息反馈：态势与效果     数据流：同一对象语义与版本",
            270,
            815,
            1060,
            48,
            fill="#ffffff",
            stroke="#ffffff",
            font_size=18,
            font_weight=400,
        ),
        _edge("e-mission-situation", "mission", "situation"),
        _edge("e-situation-decision", "situation", "decision"),
        _edge("e-decision-planning", "decision", "planning"),
        _edge("e-planning-control", "planning", "control"),
        _edge("e-control-evaluation", "control", "evaluation"),
        _edge("e-planning-core", "planning", "planning-core"),
        _edge("e-core-control", "planning-core", "control", "可执行方案"),
        _edge("e-eval-state", "evaluation", "state-object", "信息反馈", stroke="#4f8066", dashed=True),
        _edge("e-state-situation", "state-object", "situation", "状态更新", stroke="#4f8066", dashed=True),
        _edge("e-state-core", "state-object", "planning-core", "统一数据流", stroke="#756493", dashed=True),
        _edge("e-boundary-core", "human-boundary", "planning-core", "授权约束", stroke="#91603a", dashed=True),
    ]
    return cells


def _figure_2_2_cells() -> list[dict[str, Any]]:
    cells = [
        _title("指挥决心向规划变量和任务图的映射关系"),
        _node("h1", "人的决心", 30, 120, 330, 75, fill="#3d668e", stroke="#3d668e", font_size=28, label_color="#ffffff"),
        _node("h2", "机器表达", 420, 120, 330, 75, fill="#4f7f63", stroke="#4f7f63", font_size=28, label_color="#ffffff"),
        _node("h3", "规划对象", 810, 120, 330, 75, fill="#71638e", stroke="#71638e", font_size=28, label_color="#ffffff"),
        _node("h4", "责任归属", 1200, 120, 330, 75, fill="#956139", stroke="#956139", font_size=28, label_color="#ffffff"),
    ]
    rows = [
        ("目的与预期效果", "目标状态 · 成功判据", "任务目标 · 评价函数", "人负责目的与风险"),
        ("行动重点与顺序", "任务价值 · 优先级", "时间窗 · 调度权重", "机器负责结构生成"),
        ("时机与协同关系", "前驱 · 同步 · 互斥", "任务图关系集合", "机器负责组合优化"),
        ("兵力运用要求", "能力 · 角色 · 链路", "承担矩阵 · 编成", "人保留授权边界"),
        ("风险与临机原则", "阈值 · 规则 · 触发器", "可行域 · 恢复标记", "越界条件上行确认"),
    ]
    fills = [
        ("#eaf1f8", "#edf5f0", "#f3f0f8", "#f7efe7"),
    ] * 5
    strokes = [("#3d668e", "#4f7f63", "#71638e", "#956139")] * 5
    xs = [30, 420, 810, 1200]
    for row_index, row in enumerate(rows):
        y = 235 + row_index * 118
        ids = []
        for col_index, label in enumerate(row):
            cell_id = f"r{row_index + 1}c{col_index + 1}"
            ids.append(cell_id)
            cells.append(
                _node(
                    cell_id,
                    label,
                    xs[col_index],
                    y,
                    330,
                    88,
                    fill=fills[row_index][col_index],
                    stroke=strokes[row_index][col_index],
                    font_size=21,
                    font_weight=500,
                )
            )
        cells.extend(
            [
                _edge(f"e-{ids[0]}-{ids[1]}", ids[0], ids[1]),
                _edge(f"e-{ids[1]}-{ids[2]}", ids[1], ids[2]),
                _edge(f"e-{ids[2]}-{ids[3]}", ids[2], ids[3]),
            ]
        )
    return cells


def _figure_2_3_cells() -> list[dict[str, Any]]:
    return [
        _title("集中式、分层式与分布式协同控制及授权边界"),
        _node(
            "conditions",
            "协同方式选择条件\n集群规模 · 任务耦合 · 通信质量 · 控制跨度 · 对抗节奏",
            270,
            115,
            1060,
            105,
            fill="#f4f6f9",
            stroke="#566b82",
            font_size=23,
        ),
        _node(
            "centralized",
            "集中式协同\n中心统一感知与求解\n全局一致性较强\n适用：规模较小、链路稳定\n风险：计算拥塞与单点瓶颈",
            60,
            310,
            430,
            300,
            fill="#eaf1f8",
            stroke="#3d668e",
            font_size=22,
        ),
        _node(
            "hierarchical",
            "分层式协同\n意图—任务—群组—平台分层\n任务与角色成为主要控制对象\n适用：中大规模异构集群\n优势：兼顾全局约束与局部自治",
            585,
            310,
            430,
            300,
            fill="#edf5f0",
            stroke="#4f7f63",
            font_size=22,
        ),
        _node(
            "distributed",
            "分布式协同\n依据局部观测与邻域规则行动\n平台自治程度较高\n适用：链路受限、局部变化快速\n风险：局部策略偏离总体目的",
            1110,
            310,
            430,
            300,
            fill="#f3f0f8",
            stroke="#71638e",
            font_size=22,
        ),
        _node(
            "boundary",
            "动态切换与人工授权边界\n预先规划偏集中计算 → 执行阶段以分层控制为主 → 链路受限时局部分布式自治 → 通信恢复后汇聚校正\n作战目的、交战规则和重大风险始终由人保持控制",
            180,
            700,
            1240,
            130,
            fill="#f7efe7",
            stroke="#956139",
            font_size=21,
        ),
        _edge("e-cond-centralized", "conditions", "centralized"),
        _edge("e-cond-hierarchical", "conditions", "hierarchical"),
        _edge("e-cond-distributed", "conditions", "distributed"),
        _edge("e-centralized-boundary", "centralized", "boundary", "条件变化", dashed=True),
        _edge("e-hierarchical-boundary", "hierarchical", "boundary", "主控方式", stroke="#4f7f63"),
        _edge("e-distributed-boundary", "distributed", "boundary", "状态汇聚", dashed=True),
    ]


def _figure_2_4_cells() -> list[dict[str, Any]]:
    return [
        _title("战术知识约束的全局态势价值、优势场与分层投影"),
        _node(
            "input",
            "全局态势输入\n红蓝兵力与类型\n空间位置与关键地域\n海况、电磁与威胁环境\n多杀伤链网络与任务阶段",
            35,
            135,
            330,
            320,
            fill="#eaf1f8",
            stroke="#3d668e",
            font_size=21,
        ),
        _node(
            "rule",
            "战术规则评价器\n兵力价值 V_F\n位置价值 V_P\n杀伤链价值 V_K",
            430,
            135,
            365,
            155,
            fill="#edf5f0",
            stroke="#4f7f63",
            font_size=22,
        ),
        _node(
            "residual",
            "神经价值残差\n长期协同、能力克制\n敌方响应与非线性效应",
            430,
            330,
            365,
            155,
            fill="#f3f0f8",
            stroke="#71638e",
            font_size=22,
        ),
        _node(
            "robust",
            "风险修正的全局态势价值\nΦ_A^rob\n信念熵 H_b 修正\nOEI、资源与损失风险修正",
            860,
            180,
            360,
            240,
            fill="#f4f6f9",
            stroke="#3d668e",
            font_size=22,
        ),
        _node(
            "field",
            "空间优势场\nF(g, ρ; x, t)\n候选位置的全局边际贡献\n关键地域 · 覆盖 · 通信 · 风险",
            1280,
            180,
            285,
            240,
            fill="#f7efe7",
            stroke="#956139",
            font_size=21,
        ),
        _node(
            "projection",
            "按决策变量逐层投影，共享同一全局评价，不在各层另设相互冲突的目标函数",
            190,
            500,
            1220,
            55,
            fill="#ffffff",
            stroke="#ffffff",
            font_size=20,
            font_weight=500,
        ),
        _node("htn", "HTN任务分解\n目标 → 任务结构\n关键地域与杀伤链环节", 45, 610, 340, 150, fill="#eaf1f8", stroke="#3d668e", font_size=21),
        _node("marta", "MARTA资源分配\n任务 → 兵力与角色\n多链共享、冲突与组织负担", 435, 610, 340, 150, fill="#edf5f0", stroke="#4f7f63", font_size=21),
        _node("policy", "任务内协同策略\n战术函数 → 阶段目标点\n共享策略与反事实贡献", 825, 610, 340, 150, fill="#f3f0f8", stroke="#71638e", font_size=21),
        _node("control", "经典规划与控制\n目标点 → 路径与控制量\n可达、安全、避碰与动力学", 1215, 610, 340, 150, fill="#f7efe7", stroke="#956139", font_size=21),
        _node(
            "feedback",
            "执行反馈与多尺度评价：兵力位置 · 杀伤链闭合 · 任务原始指标 · H_b · OEI → L0 / L1 / L2 / L3",
            210,
            815,
            1180,
            58,
            fill="#f4f6f9",
            stroke="#566b82",
            font_size=19,
        ),
        _edge("e-input-rule", "input", "rule"),
        _edge("e-input-residual", "input", "residual"),
        _edge("e-rule-robust", "rule", "robust"),
        _edge("e-residual-robust", "residual", "robust"),
        _edge("e-robust-field", "robust", "field"),
        _edge("e-htn-marta", "htn", "marta", "任务结构"),
        _edge("e-marta-policy", "marta", "policy", "承担关系"),
        _edge("e-policy-control", "policy", "control", "阶段目标"),
    ]


def _figure_2_5_cells() -> list[dict[str, Any]]:
    return [
        _title("三类任务规划模型的耦合关系及章节映射"),
        _node(
            "pomdp",
            "不确定认知模型\nPOMDP · 信念状态 · 信念熵\n输出：b_t、H_b、认知收益\n回答：依据什么状态规划",
            50,
            125,
            440,
            215,
            fill="#eaf1f8",
            stroke="#3d668e",
            font_size=21,
        ),
        _node(
            "organization",
            "大规模协同模型\nHTN任务图 · MARTA组合优化\n输出：G_T、承担关系、任务交接\n回答：做什么、由谁完成",
            580,
            125,
            440,
            215,
            fill="#edf5f0",
            stroke="#4f7f63",
            font_size=21,
        ),
        _node(
            "dynamic",
            "动态对抗模型\n全局态势价值 · 空间优势场\n学习机动 · 分层重规划\n回答：向哪里、何时修正",
            1110,
            125,
            440,
            215,
            fill="#f3f0f8",
            stroke="#71638e",
            font_size=21,
        ),
        _node(
            "belief-output",
            "认知状态投影\nb_t · H_b · 敌方兵力信念",
            110,
            385,
            320,
            80,
            fill="#eaf1f8",
            stroke="#3d668e",
            font_size=19,
        ),
        _node(
            "task-output",
            "任务组织投影\nG_T · 承担矩阵 · 任务交接",
            640,
            385,
            320,
            80,
            fill="#edf5f0",
            stroke="#4f7f63",
            font_size=19,
        ),
        _node(
            "value-output",
            "动态价值投影\n全局态势价值 · 优势场 · L0—L3",
            1170,
            385,
            320,
            80,
            fill="#f3f0f8",
            stroke="#71638e",
            font_size=19,
        ),
        _node(
            "object-chain",
            "统一规划对象链\nMissionInput → EvaluationState → PlanSolution → TaskHandoff\nTaskPolicySet → PolicyDecision → CommandBundle → ExecutionTrace → EvaluationRecord",
            100,
            515,
            1400,
            105,
            fill="#f4f6f9",
            stroke="#566b82",
            font_size=18,
        ),
        _node("chapter3", "第3章 统一总体模型\n状态、目标、约束与接口", 40, 680, 340, 120, fill="#eaf1f8", stroke="#3d668e", font_size=21),
        _node("chapter4", "第4章 任务分解与分配\nHTN结构与MARTA承担", 430, 680, 340, 120, fill="#edf5f0", stroke="#4f7f63", font_size=21),
        _node("chapter5", "第5章 任务内协同方法\n策略组织、机动与安全执行", 820, 680, 340, 120, fill="#f3f0f8", stroke="#71638e", font_size=21),
        _node("chapter6", "第6章 仿真验证与评估\n原始指标、扰动与证据分级", 1210, 680, 340, 120, fill="#f7efe7", stroke="#956139", font_size=21),
        _node(
            "feedback",
            "执行与评价记录反向更新信念、任务结构、兵力承担和全局态势价值；失败按L0—L3返回对应规划层级修正",
            225,
            835,
            1150,
            50,
            fill="#ffffff",
            stroke="#ffffff",
            font_size=18,
            font_weight=400,
        ),
        _edge("e-pomdp-output", "pomdp", "belief-output"),
        _edge("e-org-output", "organization", "task-output"),
        _edge("e-dynamic-output", "dynamic", "value-output"),
        _edge("e-ch3-ch4", "chapter3", "chapter4"),
        _edge("e-ch4-ch5", "chapter4", "chapter5"),
        _edge("e-ch5-ch6", "chapter5", "chapter6"),
    ]


def _capture_5130_source() -> Path:
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    base = "http://127.0.0.1:15130"

    def get(path: str) -> dict[str, Any]:
        with urllib.request.urlopen(base + path, timeout=15) as response:
            return json.load(response)

    planning = get("/api/planning/state")
    decision_input = get("/api/planning/situation/decision-input?side=red")
    trace = get("/api/planning/situation/decision-trace?side=red")
    assessment = planning.get("assessment") or {}
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Chapter 2 diagram provenance; not an experiment result",
        "authority": {
            "planning_session_id": planning.get("situation_session_id"),
            "decision_authority": decision_input.get("authority") or {},
            "plan_lineage": trace.get("plan_lineage") or {},
        },
        "planning_state": {
            "source": planning.get("source"),
            "map_context": planning.get("map_context") or {},
            "raw_metrics": assessment.get("raw_metrics") or {},
            "normalized_metrics": assessment.get("normalized_metrics") or {},
            "belief_state": assessment.get("belief_state") or {},
            "intent_assessment": assessment.get("intent_assessment") or {},
            "paper_metrics": assessment.get("paper_metrics") or {},
            "replan_recommendation": assessment.get("replan_recommendation") or {},
        },
        "decision_input_contract": {
            "observation_schema": (decision_input.get("observation") or {}).get("schema"),
            "action_context_schema": (decision_input.get("action_context") or {}).get("schema"),
            "controlled_entity_count": len(
                (decision_input.get("action_context") or {}).get("controlled_entity_ids") or []
            ),
            "command_budget_model": (
                (decision_input.get("action_context") or {}).get("command_budget") or {}
            ).get("model"),
            "ruleset_revision": (
                (decision_input.get("action_context") or {}).get("authority") or {}
            ).get("ruleset_revision"),
        },
        "decision_trace": {
            "mission_intent": trace.get("mission_intent"),
            "task_graph": {
                "template_id": (trace.get("task_chain") or {}).get("template_id"),
                "nodes": (trace.get("task_chain") or {}).get("nodes") or [],
                "edges": (trace.get("task_chain") or {}).get("edges") or [],
                "cross_chain_dependencies": (
                    (trace.get("task_chain") or {}).get("cross_chain_dependencies") or []
                ),
            },
            "htn": trace.get("htn") or {},
            "marta": trace.get("marta") or {},
            "advantage_dynamics": trace.get("advantage_dynamics") or {},
        },
        "limitations": [
            "Snapshot may be at the initial simulation frame.",
            "Fields establish data availability and provenance only.",
            "No interface value is treated as a thesis experiment conclusion.",
        ],
    }
    target = SOURCE_ROOT / "5130-chapter2-diagram-source.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _comparable(diagram: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(diagram)
    result["cells"] = [
        {key: value for key, value in cell.items() if key != "cell_revision"}
        for cell in result.get("cells") or []
    ]
    return result


def _ensure_diagram(
    project: dict[str, Any],
    *,
    title: str,
    diagram_type: str,
    cells: list[dict[str, Any]],
    source_assets: list[Path],
    api_snapshot: Path,
    insertion_section: str,
    provenance_note: str,
) -> dict[str, Any]:
    listed = diagram_service.list(project).get("diagrams") or []
    existing = next((row for row in listed if row.get("title") == title), None)
    desired = {
        "title": title,
        "diagram_type": diagram_type,
        "theme_id": "academic-thesis",
        "page_settings": PAGE,
        "cells": cells,
    }
    changed = False
    if not existing:
        resource = diagram_service.create(project, desired, ACTOR)
        diagram_id = str(resource["document"]["id"])
        changed = True
    else:
        diagram_id = str(existing["id"])
        current = diagram_service.get(project, diagram_id)["diagram"]
        current_view = {key: current.get(key) for key in desired}
        if _comparable(current_view) != _comparable(desired):
            diagram_service.update_draft(
                project,
                diagram_id,
                {"expected_revision": current["revision"], **desired},
                ACTOR,
            )
            changed = True

    lineage = {
        "series_id": "thesis-v34-chapter-2-diagrams",
        "source_type": "structured_diagram",
        "source_document_id": SOURCE_DOCUMENT_ID,
        "target_document_id": TARGET_DOCUMENT_ID,
        "target_section": insertion_section,
        "source_markdown_path": str(SOURCE_MARKDOWN),
        "source_markdown_sha256": _sha_file(SOURCE_MARKDOWN),
        "source_word_path": str(SOURCE_WORD),
        "source_word_sha256": _sha_file(SOURCE_WORD),
        "source_assets": [
            {"path": str(path), "sha256": _sha_file(path)} for path in source_assets
        ],
        "api_snapshot_path": str(api_snapshot),
        "api_snapshot_sha256": _sha_file(api_snapshot),
        "provenance_note": provenance_note,
        "publication_status": "stage1-review",
    }
    multi_document_service.update_document(project, diagram_id, {"lineage": lineage})
    current = diagram_service.get(project, diagram_id)
    diagram_service.create_version(
        project,
        diagram_id,
        {"label": "v34第二章第一阶段审校版", "reason": "chapter-2-stage1"},
        ACTOR,
    )
    return {**current, "changed": changed}


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    required = [SOURCE_WORD, SOURCE_MARKDOWN, SECOND_EDITION_FIGURE, *CURRENT_FIGURES.values()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("第二章图源缺失：" + "；".join(missing))

    api_snapshot = _capture_5130_source()
    specs = [
        {
            "title": "图2-1 指挥控制闭环中的任务规划定位及多流关系",
            "diagram_type": "c2-mission-planning-loop",
            "cells": _figure_2_1_cells(),
            "source_assets": [CURRENT_FIGURES["fig2-1"], SECOND_EDITION_FIGURE],
            "insertion_section": "2.2.1",
            "provenance_note": "Redrawn from the current v34 structure and the second-edition OODA/advantage-loop concept.",
        },
        {
            "title": "图2-2 指挥决心向规划变量和任务图的映射关系",
            "diagram_type": "intent-to-task-graph",
            "cells": _figure_2_2_cells(),
            "source_assets": [CURRENT_FIGURES["fig2-2"]],
            "insertion_section": "2.2.2",
            "provenance_note": "Editable reconstruction of the current v34 intent-to-task mapping figure.",
        },
        {
            "title": "图2-3 集中式、分层式与分布式协同控制及授权边界",
            "diagram_type": "coordination-control-paradigms",
            "cells": _figure_2_3_cells(),
            "source_assets": [],
            "insertion_section": "2.3.3",
            "provenance_note": "New conceptual figure grounded in Chapter 2 control-mode analysis and the live action-authority contract.",
        },
        {
            "title": "图2-4 战术知识约束的全局态势价值、优势场与分层投影",
            "diagram_type": "global-situation-advantage-field",
            "cells": _figure_2_4_cells(),
            "source_assets": [CURRENT_FIGURES["fig2-4"], SECOND_EDITION_FIGURE],
            "insertion_section": "2.4.6",
            "provenance_note": "Editable reconstruction and renumbering of the current v34 Figure 2-3; second-edition advantage dynamics retained only as conceptual lineage.",
        },
        {
            "title": "图2-5 三类任务规划模型的耦合关系及章节映射",
            "diagram_type": "planning-model-coupling",
            "cells": _figure_2_5_cells(),
            "source_assets": [],
            "insertion_section": "2.5.4",
            "provenance_note": "New synthesis figure grounded in the v34 section mapping and the live planning state/decision-trace contracts.",
        },
    ]

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "stage": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "target_document_id": TARGET_DOCUMENT_ID,
        "target_document_mutated": False,
        "api_snapshot": {"path": str(api_snapshot), "sha256": _sha_file(api_snapshot)},
        "diagrams": [],
    }
    for spec in specs:
        resource = _ensure_diagram(project, api_snapshot=api_snapshot, **spec)
        document_id = str(resource["document"]["id"])
        svg = diagram_service.export(project, document_id, "svg", ACTOR)
        json_export = diagram_service.export(project, document_id, "json", ACTOR)
        svg_review = EXPORT_ROOT / f"{spec['title'].split(' ', 1)[0]}-{document_id}.svg"
        json_review = EXPORT_ROOT / f"{spec['title'].split(' ', 1)[0]}-{document_id}.json"
        svg_review.write_bytes(svg.read_bytes())
        json_review.write_bytes(json_export.read_bytes())
        current = diagram_service.get(project, document_id)
        report["diagrams"].append(
            {
                "document_id": document_id,
                "title": spec["title"],
                "diagram_revision": current["diagram"]["revision"],
                "content_sha256": current["diagram"]["content_sha256"],
                "cell_count": len(current["diagram"]["cells"]),
                "changed": resource["changed"],
                "target_section": spec["insertion_section"],
                "svg_export": str(svg_review),
                "json_export": str(json_review),
            }
        )

    report_path = REPORT_ROOT / "chapter2-stage1-install-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
