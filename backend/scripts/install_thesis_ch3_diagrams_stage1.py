"""Create seven editable Chapter 3 thesis diagrams for review.

Stage 1 creates structured diagram documents, binds provenance, versions them,
and exports review artifacts. It does not mutate the thesis body.
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
ACTOR = "thesis-ch3-diagram-stage1"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第三章配图"
SOURCE_ROOT = OUTPUT_ROOT / "04-source"
EXPORT_ROOT = OUTPUT_ROOT / "05-review-exports"
REPORT_ROOT = OUTPUT_ROOT / "06-reports"
BASELINE = OUTPUT_ROOT / "01-baseline/chapter3-structured-baseline.json"
CURRENT_ASSET_ROOT = (
    KNOWLEDGE
    / "06-项目库-Projects/博士论文/_workspace/documents/doc-0cdb6e81aebb/"
    "source/assets/figures/structure/svg"
)
CURRENT_WORKING = (
    KNOWLEDGE
    / "06-项目库-Projects/博士论文/_workspace/documents/doc-0cdb6e81aebb/"
    "working/document.md"
)
CURRENT_FIGURES = {
    "fig3-1": CURRENT_ASSET_ROOT / "ch3-unified-planning-model-v27.svg",
    "fig3-5": CURRENT_ASSET_ROOT / "ch3-c2-system-architecture-v27.svg",
    "fig3-6": CURRENT_ASSET_ROOT / "ch3-information-control-loop-v24.svg",
    "fig3-7": CURRENT_ASSET_ROOT / "ch3-preplanned-dynamic-replanning-v24.svg",
}

PAGE = {"width": 1600, "height": 900, "background": "#ffffff", "grid_size": 8}
BLUE = ("#eaf1f8", "#3d668e")
GREEN = ("#edf5f0", "#4f7f63")
PURPLE = ("#f3f0f8", "#71638e")
AMBER = ("#f7efe7", "#956139")
NEUTRAL = ("#f4f6f9", "#566b82")


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
    font_size: int = 22,
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
        22,
        1320,
        62,
        fill="#ffffff",
        stroke="#ffffff",
        font_size=30,
    )


def _figure_3_1_cells() -> list[dict[str, Any]]:
    return [
        _title("海上无人集群协同任务规划统一总体模型"),
        _node("mission", "任务输入 M_t\n意图 · 对象 · 资源\n环境 · 约束 · 权重", 45, 145, 245, 155, fill=BLUE[0], stroke=BLUE[1]),
        _node("state", "全局评价状态 X_t\n信念 · 兵力 · 位置\n杀伤链 · 风险 · OEI", 345, 145, 290, 155, fill=GREEN[0], stroke=GREEN[1]),
        _node("objective", "统一目标与可行域\nΦ_A^rob · 空间优势场\nΠ_feasible · 授权边界", 690, 145, 300, 155, fill=AMBER[0], stroke=AMBER[1]),
        _node("solution", "统一规划解 Π_t\n任务结构 · 兵力承担\n策略计划 · 目标与执行", 1045, 145, 505, 155, fill=PURPLE[0], stroke=PURPLE[1]),
        _node("task-graph", "任务图 G_T\n前驱 · 支撑\n同步 · 互斥", 45, 430, 220, 145, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("assignment", "承担关系 M_A\n主承担 · 替补\n角色 · 资源预算", 300, 430, 220, 145, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("policy", "任务内策略 SP_t\n感知 · 火力 · 机动\n前置与失败转移", 555, 430, 220, 145, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("target", "目标与路径 P_t\n阶段目标点 · 可达路径\n时序与同步点", 810, 430, 220, 145, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("execution", "执行保障\n规则复核 · 安全控制\n命令与权威裁决", 1065, 430, 220, 145, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("repair", "修复标记 Γ_t\n失败类型 · 影响范围\nL0-L3返回层级", 1320, 430, 230, 145, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("feedback", "执行轨迹 · 裁决事件 · 资源消耗 · 规则介入 · 任务结果\n统一回写同一评价状态，支持方案比较、责任追溯和分级修复", 245, 710, 1110, 120, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _edge("e-mission-state", "mission", "state"),
        _edge("e-state-objective", "state", "objective"),
        _edge("e-objective-solution", "objective", "solution"),
        _edge("e-task-assignment", "task-graph", "assignment"),
        _edge("e-assignment-policy", "assignment", "policy"),
        _edge("e-policy-target", "policy", "target"),
        _edge("e-target-execution", "target", "execution"),
        _edge("e-execution-repair", "execution", "repair"),
        _edge("e-repair-feedback", "repair", "feedback", stroke=PURPLE[1], dashed=True),
        _edge("e-feedback-state", "feedback", "state", stroke=GREEN[1], dashed=True),
    ]


def _figure_3_2_cells() -> list[dict[str, Any]]:
    return [
        _title("作战对象、观测信念与全局评价状态的形成关系"),
        _node("objects", "作战对象\n平台 · 武器 · 传感器\n关键地域 · 杀伤链", 45, 125, 275, 170, fill=BLUE[0], stroke=BLUE[1], font_size=21),
        _node("relations", "体系关系\n指挥 · 承担 · 通信\n前驱 · 支撑 · 共享", 365, 125, 275, 170, fill=PURPLE[0], stroke=PURPLE[1], font_size=21),
        _node("environment", "环境与规则\n海况 · 障碍 · 威胁\n交战规则 · 授权边界", 685, 125, 275, 170, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("intent", "任务语义\n作战意图 · 任务阶段\n风险偏好 · 评价权重", 1005, 125, 275, 170, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("reference", "一致性基准\n统一标识 · 坐标 · 时钟\n规则版本 · 权威帧", 1325, 125, 230, 170, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=20),
        _node("observation", "多源观测与执行证据 O_t\n探测 · 跟踪 · 链路 · 轨迹 · 裁决事件", 95, 390, 420, 120, fill=BLUE[0], stroke=BLUE[1], font_size=21),
        _node("belief", "信念更新 Ψ_b\n敌情分布 b_t · 信念熵 H_b\n置信度与观测质量", 590, 390, 420, 120, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("mapping", "状态映射 Ψ_state\n对象、关系、任务和约束\n按同一基准形成可计算状态", 1085, 390, 420, 120, fill=PURPLE[0], stroke=PURPLE[1], font_size=21),
        _node("evaluation", "全局评价状态 X_t\n红蓝兵力 · 空间位置 · 多杀伤链\n认知不确定性 · 组织复杂度 · 风险", 370, 625, 860, 125, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=22),
        _node("value", "全局态势价值\nΦ_A^rob", 180, 795, 300, 75, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("field", "空间优势场\nF(g,rho;x,t)", 650, 795, 300, 75, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("decision", "规划决策输入\n状态 · 任务 · 资源 · 约束", 1120, 795, 300, 75, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _edge("e-objects-observation", "objects", "observation"),
        _edge("e-relations-belief", "relations", "belief"),
        _edge("e-environment-mapping", "environment", "mapping"),
        _edge("e-intent-mapping", "intent", "mapping"),
        _edge("e-reference-mapping", "reference", "mapping"),
        _edge("e-observation-belief", "observation", "belief"),
        _edge("e-belief-mapping", "belief", "mapping"),
        _edge("e-mapping-evaluation", "mapping", "evaluation"),
        _edge("e-evaluation-value", "evaluation", "value"),
        _edge("e-evaluation-field", "evaluation", "field"),
        _edge("e-evaluation-decision", "evaluation", "decision"),
    ]


def _figure_3_3_cells() -> list[dict[str, Any]]:
    return [
        _title("统一规划解的构成及其章节衔接关系"),
        _node("mission", "任务输入\nM_t", 65, 125, 300, 95, fill=BLUE[0], stroke=BLUE[1], font_size=23),
        _node("state", "评价状态\nX_t", 460, 125, 300, 95, fill=GREEN[0], stroke=GREEN[1], font_size=23),
        _node("constraints", "目标、战术知识与约束\nΦ_A^rob · Π_feasible", 855, 125, 360, 95, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("authority", "权威基准\n标识 · 坐标 · 时钟 · 版本", 1310, 125, 245, 95, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=19),
        _node("solution", "统一规划解 Π_t", 140, 315, 1320, 78, fill=PURPLE[0], stroke=PURPLE[1], font_size=26),
        _node("graph", "任务图\nG_T", 55, 455, 190, 120, fill=BLUE[0], stroke=BLUE[1], font_size=22),
        _node("assign", "承担关系\nM_A", 270, 455, 190, 120, fill=GREEN[0], stroke=GREEN[1], font_size=22),
        _node("policy", "策略计划\nSP_t", 485, 455, 190, 120, fill=PURPLE[0], stroke=PURPLE[1], font_size=22),
        _node("targets", "阶段目标点\nY_t", 700, 455, 190, 120, fill=AMBER[0], stroke=AMBER[1], font_size=22),
        _node("paths", "路径集合\nP_t", 915, 455, 190, 120, fill=BLUE[0], stroke=BLUE[1], font_size=22),
        _node("schedule", "执行时序\nSigma_t", 1130, 455, 190, 120, fill=GREEN[0], stroke=GREEN[1], font_size=22),
        _node("repair", "修复标记\nΓ_t", 1345, 455, 200, 120, fill=PURPLE[0], stroke=PURPLE[1], font_size=22),
        _node("chapter4", "第4章：任务分解与分配\n输入任务条件和评价状态\n形成任务图与兵力承担关系", 80, 700, 420, 125, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("chapter5", "第5章：策略强化与执行\n输入任务图、承担关系和授权边界\n形成策略、目标点与安全路径", 590, 700, 420, 125, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("evidence", "第6章：仿真验证与评价\n使用执行轨迹、裁决和评价记录\n检验原始指标及失败语义", 1100, 700, 420, 125, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _edge("e-mission-solution", "mission", "solution"),
        _edge("e-state-solution", "state", "solution"),
        _edge("e-constraints-solution", "constraints", "solution"),
        _edge("e-authority-solution", "authority", "solution"),
        _edge("e-solution-graph", "solution", "graph"),
        _edge("e-graph-assign", "graph", "assign"),
        _edge("e-assign-policy", "assign", "policy"),
        _edge("e-policy-targets", "policy", "targets"),
        _edge("e-targets-paths", "targets", "paths"),
        _edge("e-paths-schedule", "paths", "schedule"),
        _edge("e-schedule-repair", "schedule", "repair"),
        _edge("e-graph-ch4", "graph", "chapter4"),
        _edge("e-policy-ch5", "policy", "chapter5"),
        _edge("e-repair-evidence", "repair", "evidence"),
    ]


def _figure_3_4_cells() -> list[dict[str, Any]]:
    return [
        _title("分层约束体系、责任边界与可行域门控"),
        _node("a2-title", "A2 战术意图与授权门", 50, 125, 450, 68, fill=AMBER[1], stroke=AMBER[1], font_size=24, label_color="#ffffff"),
        _node("a1-title", "A1 任务规划与方案门", 575, 125, 450, 68, fill=BLUE[1], stroke=BLUE[1], font_size=24, label_color="#ffffff"),
        _node("a0-title", "A0 执行一致性与安全门", 1100, 125, 450, 68, fill=GREEN[1], stroke=GREEN[1], font_size=24, label_color="#ffffff"),
        _node("military", "军事与授权约束\n任务效果 · 风险边界\n交战规则 · 人工确认", 50, 235, 215, 155, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("intent", "意图与任务约束\n阶段 · 时间窗 · 依赖\n关键任务链连续性", 285, 235, 215, 155, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("resource", "资源与能力约束\n平台 · 载荷 · 能源\n兵力覆盖与替补", 575, 235, 215, 155, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("organization", "组织与协同约束\n角色 · 拓扑 · 通信\nOEI与共享冲突", 810, 235, 215, 155, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("environment", "环境与空间约束\n海况 · 威胁 · 障碍\n禁航区与链路衰减", 1100, 235, 215, 155, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("execution", "执行与安全约束\n可达 · 避碰 · 同步\n规则复核与动力学", 1335, 235, 215, 155, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("gate-a2", "A2门控\n确认目的、授权和\n总体风险可接受", 125, 500, 300, 135, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("gate-a1", "A1门控\n验证任务结构、承担关系\n和组织负担可行", 650, 500, 300, 135, fill=BLUE[0], stroke=BLUE[1], font_size=21),
        _node("gate-a0", "A0门控\n验证目标点、路径、时序\n和动作执行安全", 1175, 500, 300, 135, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("joint-gate", "联合硬约束门\n按权威基准汇总三层约束判定", 600, 660, 400, 80, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _node("feasible", "可行规划域 Π_feasible\n进入评价排序、人工审查与执行", 100, 775, 650, 90, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("failure", "拒绝与失败语义\n受影响对象 · 违反约束 · 责任层 · 返回层级", 850, 775, 650, 90, fill=PURPLE[0], stroke=PURPLE[1], font_size=21),
        _edge("e-military-a2", "military", "gate-a2"),
        _edge("e-intent-a2", "intent", "gate-a2"),
        _edge("e-resource-a1", "resource", "gate-a1"),
        _edge("e-org-a1", "organization", "gate-a1"),
        _edge("e-environment-a0", "environment", "gate-a0"),
        _edge("e-execution-a0", "execution", "gate-a0"),
        _edge("e-a2-joint", "gate-a2", "joint-gate"),
        _edge("e-a1-joint", "gate-a1", "joint-gate"),
        _edge("e-a0-joint", "gate-a0", "joint-gate"),
        _edge("e-joint-feasible", "joint-gate", "feasible", "通过"),
        _edge("e-joint-failure", "joint-gate", "failure", "拒绝", stroke=PURPLE[1], dashed=True),
    ]


def _figure_3_5_cells() -> list[dict[str, Any]]:
    cells = [
        _title("指挥控制、任务规划与执行控制的权责边界"),
        _node("h-layer", "责任层", 35, 115, 300, 65, fill=NEUTRAL[1], stroke=NEUTRAL[1], font_size=24, label_color="#ffffff"),
        _node("h-decision", "主要决策", 375, 115, 350, 65, fill=NEUTRAL[1], stroke=NEUTRAL[1], font_size=24, label_color="#ffffff"),
        _node("h-output", "向下输出", 765, 115, 350, 65, fill=NEUTRAL[1], stroke=NEUTRAL[1], font_size=24, label_color="#ffffff"),
        _node("h-boundary", "不得越界", 1155, 115, 410, 65, fill=NEUTRAL[1], stroke=NEUTRAL[1], font_size=24, label_color="#ffffff"),
    ]
    rows = [
        ("A2 战术意图与\n人机协同层", "指挥员确定任务效果\n风险偏好与授权边界", "作战意图 · 任务目标\n规则与总体约束", "模型提供比较与解释\n不替代最终决心和授权", AMBER),
        ("A1 任务规划与\n方案生成层", "形成任务图、兵力承担\n策略组织、目标点与时序", "统一规划解 Π_t\n可比较、可批准、可追溯", "不直接生成姿态、舵量\n不擅自改变目的与授权", BLUE),
        ("A0 策略执行与\n控制层", "规则复核、安全路径\n局部避碰与短时调整", "命令执行 · 轨迹反馈\n裁决事件与失败类型", "局部修复不改任务语义\n越界或不可行必须上返", GREEN),
    ]
    xs = [35, 375, 765, 1155]
    widths = [300, 350, 350, 410]
    for row_index, row in enumerate(rows):
        y = 220 + row_index * 205
        fill, stroke = row[4]
        ids = []
        for col_index, label in enumerate(row[:4]):
            cell_id = f"r{row_index + 1}c{col_index + 1}"
            ids.append(cell_id)
            cells.append(_node(cell_id, label, xs[col_index], y, widths[col_index], 145, fill=fill, stroke=stroke, font_size=20))
        cells.extend([
            _edge(f"e-{ids[0]}-{ids[1]}", ids[0], ids[1]),
            _edge(f"e-{ids[1]}-{ids[2]}", ids[1], ids[2]),
            _edge(f"e-{ids[2]}-{ids[3]}", ids[2], ids[3]),
        ])
    cells.extend([
        _node("flow", "控制向下：目的与约束 → 任务方案 → 平台行动     证据向上：轨迹与裁决 → 方案评价 → 意图修正", 180, 830, 1240, 52, fill="#ffffff", stroke="#ffffff", font_size=19, font_weight=500),
        _edge("e-a2-a1", "r1c1", "r2c1", "职责传递"),
        _edge("e-a1-a0", "r2c1", "r3c1", "执行交接"),
        _edge("e-a0-a1", "r3c4", "r2c4", "失败上返", stroke=PURPLE[1], dashed=True),
        _edge("e-a1-a2", "r2c4", "r1c4", "授权审查", stroke=PURPLE[1], dashed=True),
    ])
    return cells


def _figure_3_6_cells() -> list[dict[str, Any]]:
    return [
        _title("海上无人集群任务规划的信息流、控制流与证据反馈闭环"),
        _node("control-label", "控制流", 35, 135, 155, 65, fill=BLUE[1], stroke=BLUE[1], font_size=23, label_color="#ffffff"),
        _node("commander", "有人指挥\n目的 · 规则 · 授权", 225, 120, 240, 95, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("mission", "任务输入\nM_t", 505, 120, 220, 95, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("plan", "统一规划解\nΠ_t", 765, 120, 220, 95, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("command", "命令与策略包\n规则 · 目标 · 路径", 1025, 120, 240, 95, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("execution", "无人集群执行\n感知 · 火力 · 机动", 1305, 120, 250, 95, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("info-label", "信息流", 35, 375, 155, 65, fill=GREEN[1], stroke=GREEN[1], font_size=23, label_color="#ffffff"),
        _node("world", "作战对象与环境\n真实状态不可完全观测", 225, 355, 250, 105, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=19),
        _node("observation", "多源观测 O_t\n探测 · 通信 · 规则事件", 525, 355, 250, 105, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("belief", "信念状态 b_t\n置信度 · 信念熵 H_b", 825, 355, 250, 105, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("evaluation", "评价状态 X_t\n全局价值 · 优势场 · OEI", 1125, 355, 300, 105, fill=PURPLE[0], stroke=PURPLE[1], font_size=19),
        _node("evidence-label", "证据流", 35, 625, 155, 65, fill=PURPLE[1], stroke=PURPLE[1], font_size=23, label_color="#ffffff"),
        _node("trace", "执行轨迹\n位置 · 资源 · 链路", 1305, 605, 250, 105, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("record", "评价记录\n预期值 · 实际值 · 原始指标", 1005, 605, 250, 105, fill=PURPLE[0], stroke=PURPLE[1], font_size=19),
        _node("failure", "失败语义\n受影响对象 · 原因 · 范围", 705, 605, 250, 105, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _node("repair", "分级修复与校准\nL0-L3 · 规则与阈值更新", 405, 605, 250, 105, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("accountability", "责任追溯\n状态、方案、命令和结果使用同一帧、版本与对象标识", 105, 780, 1390, 85, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=20),
        _edge("e-commander-mission", "commander", "mission"),
        _edge("e-mission-plan", "mission", "plan"),
        _edge("e-plan-command", "plan", "command"),
        _edge("e-command-execution", "command", "execution"),
        _edge("e-world-observation", "world", "observation", stroke=GREEN[1]),
        _edge("e-observation-belief", "observation", "belief", stroke=GREEN[1]),
        _edge("e-belief-evaluation", "belief", "evaluation", stroke=GREEN[1]),
        _edge("e-execution-trace", "execution", "trace", stroke=PURPLE[1], dashed=True),
        _edge("e-trace-record", "trace", "record", stroke=PURPLE[1]),
        _edge("e-record-failure", "record", "failure", stroke=PURPLE[1]),
        _edge("e-failure-repair", "failure", "repair", stroke=PURPLE[1]),
        _edge("e-repair-mission", "repair", "mission", stroke=PURPLE[1], dashed=True),
    ]


def _figure_3_7_cells() -> list[dict[str, Any]]:
    cells = [
        _title("预先规划、执行监控与分级重规划机制"),
        _node("analysis", "任务分析", 35, 125, 220, 95, fill=BLUE[0], stroke=BLUE[1], font_size=21),
        _node("baseline", "态势与资源基线", 295, 125, 220, 95, fill=BLUE[0], stroke=BLUE[1], font_size=21),
        _node("htn", "HTN任务结构", 555, 125, 220, 95, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("marta", "MARTA兵力承担", 815, 125, 220, 95, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("policy", "策略、目标与路径", 1075, 125, 220, 95, fill=PURPLE[0], stroke=PURPLE[1], font_size=21),
        _node("approval", "人工审核与发布", 1335, 125, 220, 95, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("execution", "审核发布后进入方案执行与持续监控\n实际盘面、任务状态、资源、杀伤链和规则事件", 130, 335, 560, 110, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("disturbance", "扰动度量 ΔΞ(t)\n信念 · 资源 · 杀伤链 · 优势场 · 全局价值 · OEI", 785, 335, 560, 110, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("trigger", "触发判定\n进入阈值 · 退出阈值 · 最短持续时间\n离散授权或意图事件单独审查", 555, 520, 490, 125, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=20),
        _node("l0", "L0 执行局部修复\n路径 · 速度 · 避碰\n规则状态刷新", 35, 710, 340, 125, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("l1", "L1 任务内策略修复\n策略切换 · 同步恢复\n目标点重采样", 430, 710, 340, 125, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("l2", "L2 MARTA资源修复\n承担平台 · 角色 · 预算\n替补关系重配", 825, 710, 340, 125, fill=PURPLE[0], stroke=PURPLE[1], font_size=19),
        _node("l3", "L3 HTN结构修复\n任务前置 · 任务链闭合\n意图或任务语义审查", 1220, 710, 340, 125, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _edge("e-analysis-baseline", "analysis", "baseline"),
        _edge("e-baseline-htn", "baseline", "htn"),
        _edge("e-htn-marta", "htn", "marta"),
        _edge("e-marta-policy", "marta", "policy"),
        _edge("e-policy-approval", "policy", "approval"),
        _edge("e-execution-disturbance", "execution", "disturbance"),
        _edge("e-disturbance-trigger", "disturbance", "trigger"),
        _edge("e-trigger-l0", "trigger", "l0"),
        _edge("e-trigger-l1", "trigger", "l1"),
        _edge("e-trigger-l2", "trigger", "l2"),
        _edge("e-trigger-l3", "trigger", "l3"),
    ]
    return cells


def _capture_5130_source() -> Path:
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    base = "http://127.0.0.1:15130"

    def get(path: str) -> dict[str, Any]:
        with urllib.request.urlopen(base + path, timeout=20) as response:
            return json.load(response)

    previous = (
        KNOWLEDGE
        / "output/博士论文-v34第二章配图/01-source/5130-chapter2-diagram-source.json"
    )
    try:
        planning = get("/api/planning/state")
        decision_input = get("/api/planning/situation/decision-input?side=red")
        trace = get("/api/planning/situation/decision-trace?side=red")
        legal = get("/api/planning/situation/legal-actions?side=red&limit=20")
        plan = get("/api/planning/situation/plan?side=red")
        capture_status = "live"
        capture_error = ""
    except Exception as exc:
        if not previous.is_file():
            raise
        prior = json.loads(previous.read_text(encoding="utf-8"))
        planning = {"situation_session_id": (prior.get("authority") or {}).get("planning_session_id"), "assessment": prior.get("planning_state") or {}}
        decision_input = {"authority": (prior.get("authority") or {}).get("decision_authority") or {}, "observation": {"schema": (prior.get("decision_input_contract") or {}).get("observation_schema")}, "action_context": {"schema": (prior.get("decision_input_contract") or {}).get("action_context_schema")}}
        trace = {"plan_lineage": (prior.get("authority") or {}).get("plan_lineage") or {}, **(prior.get("decision_trace") or {})}
        legal = {}
        plan = {}
        capture_status = "fallback-to-prior-audited-snapshot"
        capture_error = f"{type(exc).__name__}: {exc}"

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Chapter 3 model and interface provenance; not an experiment result",
        "capture_status": capture_status,
        "capture_error": capture_error,
        "authority": {
            "planning_session_id": planning.get("situation_session_id"),
            "decision_authority": decision_input.get("authority") or {},
            "plan_lineage": trace.get("plan_lineage") or {},
        },
        "contracts": {
            "observation_schema": (decision_input.get("observation") or {}).get("schema"),
            "action_context_schema": (decision_input.get("action_context") or {}).get("schema"),
            "controlled_entity_count": len((decision_input.get("action_context") or {}).get("controlled_entity_ids") or []),
            "command_budget": (decision_input.get("action_context") or {}).get("command_budget") or {},
            "legal_action_summary": {key: value for key, value in legal.items() if key not in {"actions", "legal_actions"}},
            "plan_keys": sorted(plan.keys()),
        },
        "planning_state": {
            "source": planning.get("source"),
            "map_context": planning.get("map_context") or {},
            "assessment_keys": sorted((planning.get("assessment") or {}).keys()),
        },
        "decision_trace": {
            "mission_intent": trace.get("mission_intent"),
            "task_chain": trace.get("task_chain") or trace.get("task_graph") or {},
            "htn": trace.get("htn") or {},
            "marta": trace.get("marta") or {},
            "advantage_dynamics": trace.get("advantage_dynamics") or {},
        },
        "limitations": [
            "The snapshot supplies object and interface semantics only.",
            "It does not prove algorithm superiority or operational effectiveness.",
            "Plans, observations, commands, and results remain distinct authority objects.",
        ],
    }
    target = SOURCE_ROOT / "5130-chapter3-contract-source.json"
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
    if not existing:
        existing = next(
            (
                row
                for row in listed
                if ((row.get("diagram") or {}).get("diagram_type") == diagram_type)
                and row.get("status") != "archived"
            ),
            None,
        )
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
        "series_id": "thesis-v34-chapter-3-diagrams",
        "source_type": "structured_diagram",
        "target_document_id": TARGET_DOCUMENT_ID,
        "target_section": insertion_section,
        "current_working_path": str(CURRENT_WORKING),
        "current_working_sha256": _sha_file(CURRENT_WORKING),
        "baseline_path": str(BASELINE),
        "baseline_sha256": _sha_file(BASELINE),
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
        {"label": "v34第三章第一阶段审校版", "reason": "chapter-3-stage1"},
        ACTOR,
    )
    return {**current, "changed": changed}


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    required = [BASELINE, CURRENT_WORKING, *CURRENT_FIGURES.values()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("第三章图源缺失：" + "；".join(missing))

    api_snapshot = _capture_5130_source()
    specs = [
        {
            "title": "图3-1 海上无人集群协同任务规划统一总体模型",
            "diagram_type": "unified-planning-model",
            "cells": _figure_3_1_cells(),
            "source_assets": [CURRENT_FIGURES["fig3-1"]],
            "insertion_section": "3.1.3",
            "provenance_note": "Redrawn from the current overall-model figure and the live planning state/decision contracts.",
        },
        {
            "title": "图3-2 作战对象、观测信念与全局评价状态的形成关系",
            "diagram_type": "evaluation-state-formation",
            "cells": _figure_3_2_cells(),
            "source_assets": [],
            "insertion_section": "3.2.2",
            "provenance_note": "New ontology figure separating objects, observations, beliefs, and evaluation state.",
        },
        {
            "title": "图3-3 统一规划解的构成及其章节衔接关系",
            "diagram_type": "plan-solution-contract",
            "cells": _figure_3_3_cells(),
            "source_assets": [],
            "insertion_section": "3.3.4",
            "provenance_note": "New semantic-contract figure grounded in PlanSolution and chapter-level input/output boundaries.",
        },
        {
            "title": "图3-4 分层约束体系、责任边界与可行域门控",
            "diagram_type": "constraint-feasible-domain-gates",
            "cells": _figure_3_4_cells(),
            "source_assets": [],
            "insertion_section": "3.5.3",
            "provenance_note": "New figure showing hard constraints as feasible-domain gates rather than post-hoc filters.",
        },
        {
            "title": "图3-5 指挥控制、任务规划与执行控制的权责边界",
            "diagram_type": "command-planning-execution-authority",
            "cells": _figure_3_5_cells(),
            "source_assets": [CURRENT_FIGURES["fig3-5"]],
            "insertion_section": "3.6",
            "provenance_note": "Redrawn from the current layered architecture with explicit military authority boundaries.",
        },
        {
            "title": "图3-6 海上无人集群任务规划的信息流、控制流与证据反馈闭环",
            "diagram_type": "information-control-evidence-loop",
            "cells": _figure_3_6_cells(),
            "source_assets": [CURRENT_FIGURES["fig3-6"]],
            "insertion_section": "3.6.5",
            "provenance_note": "Redrawn from the current loop figure with an explicit evidence and accountability lane.",
        },
        {
            "title": "图3-7 预先规划、执行监控与分级重规划机制",
            "diagram_type": "preplanned-layered-replanning",
            "cells": _figure_3_7_cells(),
            "source_assets": [CURRENT_FIGURES["fig3-7"]],
            "insertion_section": "3.8",
            "provenance_note": "Redrawn from the current operating mechanism with explicit disturbance and L0-L3 repair semantics.",
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
        label = spec["title"].split(" ", 1)[0]
        svg_review = EXPORT_ROOT / f"{label}-{document_id}.svg"
        json_review = EXPORT_ROOT / f"{label}-{document_id}.json"
        svg_review.write_bytes(svg.read_bytes())
        json_review.write_bytes(json_export.read_bytes())
        current = diagram_service.get(project, document_id)
        report["diagrams"].append(
            {
                "label": label,
                "document_id": document_id,
                "title": spec["title"],
                "revision": (current.get("diagram") or {}).get("revision"),
                "content_sha256": (current.get("diagram") or {}).get("content_sha256"),
                "changed": resource["changed"],
                "svg": {"path": str(svg_review), "sha256": _sha_file(svg_review)},
                "json": {"path": str(json_review), "sha256": _sha_file(json_review)},
            }
        )

    report_path = REPORT_ROOT / "chapter3-stage1-install-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
