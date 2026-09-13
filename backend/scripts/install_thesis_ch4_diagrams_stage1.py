"""Create seven editable Chapter 4 thesis diagrams for review.

Stage 1 creates structured diagram documents, binds auditable provenance,
versions them, and exports SVG/JSON review artifacts. It does not mutate the
thesis body.
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
ACTOR = "thesis-ch4-diagram-stage1"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第四章配图"
SOURCE_ROOT = OUTPUT_ROOT / "04-source"
EXPORT_ROOT = OUTPUT_ROOT / "05-review-exports"
REPORT_ROOT = OUTPUT_ROOT / "06-reports"
BASELINE = OUTPUT_ROOT / "01-baseline/chapter4-structured-baseline.json"
CURRENT_ROOT = (
    KNOWLEDGE
    / "06-项目库-Projects/博士论文/_workspace/documents/doc-0cdb6e81aebb"
)
CURRENT_WORKING = CURRENT_ROOT / "working/document.md"
CURRENT_ASSET_ROOT = CURRENT_ROOT / "source/assets/figures/structure/svg"
CURRENT_FIGURES = {
    "fig4-1": CURRENT_ASSET_ROOT / "ch4-mission-input-structure-v23.svg",
    "fig4-2": CURRENT_ASSET_ROOT / "ch4-kill-chain-task-mapping-v27.svg",
    "fig4-3": CURRENT_ASSET_ROOT / "ch4-reverse-task-decomposition-v23.svg",
    "fig4-4": CURRENT_ASSET_ROOT / "ch4-marta-allocation-model-v27.svg",
}

PAGE = {"width": 1600, "height": 900, "background": "#ffffff", "grid_size": 8}
BLUE = ("#eaf1f8", "#3d668e")
GREEN = ("#edf5f0", "#4f7f63")
PURPLE = ("#f3f0f8", "#71638e")
AMBER = ("#f7efe7", "#956139")
RED = ("#faeeee", "#a95757")
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
    dashed: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "fill": fill,
        "stroke": stroke,
        "strokeWidth": 2,
        "rx": 8,
        "ry": 8,
    }
    if dashed:
        body["strokeDasharray"] = "8 6"
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
            "body": body,
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
        font_size=31,
        font_weight=700,
    )


def _figure_4_1_cells() -> list[dict[str, Any]]:
    cells = [
        _title("指挥意图、全局态势与任务需求的语义映射"),
        _node("intent", "经确认的指挥意图\n任务目的 · 期望效果\n优先级 · 风险边界", 55, 130, 430, 130, fill=AMBER[0], stroke=AMBER[1]),
        _node("state", "全局评价状态\n敌我兵力 · 关键地域\n多链关系 · 不确定性", 585, 130, 430, 130, fill=BLUE[0], stroke=BLUE[1]),
        _node("knowledge", "战术知识与规则\n任务模板 · 能力条件\n时空约束 · 协同关系", 1115, 130, 430, 130, fill=GREEN[0], stroke=GREEN[1]),
        _node("mapping", "语义解释与一致性校核\n对象对齐 → 效果解析 → 条件继承 → 任务图映射", 165, 330, 1270, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=25),
        _node("task", "标准任务节点\n对象 · 效果 · 类型\n时间窗 · 优先级", 55, 520, 430, 135, fill=BLUE[0], stroke=BLUE[1]),
        _node("relation", "任务关系边\n前置 · 并行 · 同步\n共享 · 互斥 · 替补", 585, 520, 430, 135, fill=PURPLE[0], stroke=PURPLE[1]),
        _node("requirement", "兵力与资源需求\n能力覆盖 · 任务级区域\n预算 · 风险 · 授权范围", 1115, 520, 430, 135, fill=GREEN[0], stroke=GREEN[1]),
        _node("trace", "可追溯任务需求基线\n每个任务节点均保留意图来源、评价状态版本、约束依据与解释链；模型不得新增任务目的或行动授权", 165, 750, 1270, 105, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _edge("e-intent-map", "intent", "mapping"),
        _edge("e-state-map", "state", "mapping"),
        _edge("e-knowledge-map", "knowledge", "mapping"),
        _edge("e-map-task", "mapping", "task"),
        _edge("e-map-relation", "mapping", "relation"),
        _edge("e-map-requirement", "mapping", "requirement"),
        _edge("e-task-trace", "task", "trace"),
        _edge("e-relation-trace", "relation", "trace"),
        _edge("e-requirement-trace", "requirement", "trace"),
    ]
    return cells


def _figure_4_2_cells() -> list[dict[str, Any]]:
    cells = [
        _title("目标处置链、态势塑造链与共享支撑任务网络"),
        _node("col-object", "任务目的", 35, 110, 185, 55, fill=NEUTRAL[1], stroke=NEUTRAL[1], font_size=21, label_color="#ffffff"),
        _node("col-find", "发现定位", 270, 110, 210, 55, fill=BLUE[1], stroke=BLUE[1], font_size=21, label_color="#ffffff"),
        _node("col-track", "持续确认", 535, 110, 210, 55, fill=BLUE[1], stroke=BLUE[1], font_size=21, label_color="#ffffff"),
        _node("col-gate", "合法性与授权门", 800, 110, 210, 55, fill=AMBER[1], stroke=AMBER[1], font_size=20, label_color="#ffffff"),
        _node("col-act", "作用与控制", 1065, 110, 210, 55, fill=PURPLE[1], stroke=PURPLE[1], font_size=21, label_color="#ffffff"),
        _node("col-assess", "效果评估", 1330, 110, 210, 55, fill=GREEN[1], stroke=GREEN[1], font_size=21, label_color="#ffffff"),
        _node("obj-a", "目标处置链 A\n形成预定任务效果", 35, 210, 185, 100, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=19),
        _node("find-a", "区域搜索\n目标发现", 270, 210, 210, 100, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("track-a", "识别跟踪\n状态确认", 535, 210, 210, 100, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("gate-a", "目标合法性\n行动授权范围", 800, 210, 210, 100, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("act-a", "任务作用\n火力或非火力", 1065, 210, 210, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("assess-a", "效果评估\n链路闭合", 1330, 210, 210, 100, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("obj-b", "目标处置链 B\n形成预定任务效果", 35, 365, 185, 100, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=19),
        _node("find-b", "区域搜索\n目标发现", 270, 365, 210, 100, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("track-b", "识别跟踪\n状态确认", 535, 365, 210, 100, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("gate-b", "目标合法性\n行动授权范围", 800, 365, 210, 100, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("act-b", "任务作用\n火力或非火力", 1065, 365, 210, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("assess-b", "效果评估\n链路闭合", 1330, 365, 210, 100, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("obj-s", "态势塑造链\n创造后续行动条件", 35, 520, 185, 100, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=19),
        _node("find-s", "关键地域侦察\n威胁辨识", 270, 520, 210, 100, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("track-s", "机动部署\n持续态势保持", 535, 520, 210, 100, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("gate-s", "意图一致性\n风险边界复核", 800, 520, 210, 100, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _node("act-s", "区域控制\n遮断或掩护", 1065, 520, 210, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=19),
        _node("assess-s", "塑造效果评估\n条件更新", 1330, 520, 210, 100, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("support", "共享支撑任务池\n通信中继 · 数据融合 · 导航授时 · 补给保障 · 预备兵力", 260, 720, 1080, 105, fill=GREEN[0], stroke=GREEN[1], font_size=22),
    ]
    for row in ("a", "b", "s"):
        for left, right in (("obj", "find"), ("find", "track"), ("track", "gate"), ("gate", "act"), ("act", "assess")):
            cells.append(_edge(f"e-{left}-{right}-{row}", f"{left}-{row}", f"{right}-{row}"))
    for target in ("track-a", "act-a", "track-b", "act-b", "track-s", "act-s"):
        cells.append(_edge(f"e-support-{target}", "support", target, stroke=GREEN[1], dashed=True))
    return cells


def _figure_4_3_cells() -> list[dict[str, Any]]:
    return [
        _title("HTN候选任务结构的生成、剪枝与全局选择"),
        _node("intent", "指挥意图与任务效果\n优先级 · 风险 · 时间窗", 55, 120, 420, 110, fill=AMBER[0], stroke=AMBER[1]),
        _node("state", "全局评价状态\n多链关系 · 关键地域 · 资源", 590, 120, 420, 110, fill=BLUE[0], stroke=BLUE[1]),
        _node("methods", "HTN方法库与任务模板\n前置条件 · 分解算子 · 失败语义", 1125, 120, 420, 110, fill=GREEN[0], stroke=GREEN[1]),
        _node("expand", "受约束的层次展开\n选择方法 → 绑定对象 → 继承约束 → 形成候选任务图", 165, 285, 1270, 92, fill=PURPLE[0], stroke=PURPLE[1], font_size=24),
        _node("candidate-a", "候选结构 A\n目标链优先\n共享支撑集中", 70, 455, 390, 120, fill=BLUE[0], stroke=BLUE[1]),
        _node("candidate-b", "候选结构 B\n塑造链先行\n关键地域优先", 605, 455, 390, 120, fill=GREEN[0], stroke=GREEN[1]),
        _node("candidate-c", "候选结构 C\n多链并行\n预备兵力增强", 1140, 455, 390, 120, fill=PURPLE[0], stroke=PURPLE[1]),
        _node("prune", "硬约束剪枝\n前置条件 · 授权范围 · 时序 · 资源 · 风险 · 冲突", 165, 640, 1270, 88, fill=RED[0], stroke=RED[1], font_size=23),
        _node("compare", "共同基线下的全局价值比较\n评价任务结构对兵力价值、位置环境价值、多链耦合与体系韧性的整体贡献", 265, 785, 870, 82, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("selected", "选定任务图\n并保留备选与淘汰原因", 1200, 785, 320, 82, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _edge("e-intent-expand", "intent", "expand"),
        _edge("e-state-expand", "state", "expand"),
        _edge("e-methods-expand", "methods", "expand"),
        _edge("e-expand-a", "expand", "candidate-a"),
        _edge("e-expand-b", "expand", "candidate-b"),
        _edge("e-expand-c", "expand", "candidate-c"),
        _edge("e-a-prune", "candidate-a", "prune"),
        _edge("e-b-prune", "candidate-b", "prune"),
        _edge("e-c-prune", "candidate-c", "prune"),
        _edge("e-prune-compare", "prune", "compare"),
        _edge("e-compare-selected", "compare", "selected"),
    ]


def _figure_4_4_cells() -> list[dict[str, Any]]:
    return [
        _title("任务约束的继承、分层校核与不可越权关系"),
        _node("source", "上位约束基线\n经确认的任务目的 · 交战规则 · 授权范围 · 总体风险边界", 110, 115, 1060, 95, fill=AMBER[0], stroke=AMBER[1], font_size=22),
        _node("source-gate", "A2确认\n模型不可生成或放宽", 1240, 115, 270, 95, fill=RED[0], stroke=RED[1], font_size=19),
        _node("task", "任务节点与关系边\n对象、效果、时间窗、优先级、前置、同步、互斥和共享关系", 110, 260, 1060, 95, fill=BLUE[0], stroke=BLUE[1], font_size=22),
        _node("task-gate", "语义校核\n不得改变任务目的", 1240, 260, 270, 95, fill=RED[0], stroke=RED[1], font_size=19),
        _node("htn", "HTN候选任务结构\n继承全部上位硬约束，并增加结构完整性、链路连续性和方法前置条件", 110, 405, 1060, 95, fill=PURPLE[0], stroke=PURPLE[1], font_size=22),
        _node("htn-gate", "结构校核\n只可收紧可行域", 1240, 405, 270, 95, fill=RED[0], stroke=RED[1], font_size=19),
        _node("marta", "MARTA兵力与资源配置\n增加能力覆盖、数量、时间、任务级区域、共享链路、预备兵力与预算约束", 110, 550, 1060, 95, fill=GREEN[0], stroke=GREEN[1], font_size=22),
        _node("marta-gate", "资源校核\n不可用收益抵消硬约束", 1240, 550, 270, 95, fill=RED[0], stroke=RED[1], font_size=18),
        _node("handoff", "经审查的任务—兵力方案\n任务图、承担关系、角色、任务级区域、资源预算、替补关系与约束证据", 110, 695, 1060, 105, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _node("principle", "继承原则\n下层可细化、可收紧\n不得删除、放宽或越权解释", 1240, 695, 270, 105, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _edge("e-source-task", "source", "task"),
        _edge("e-task-htn", "task", "htn"),
        _edge("e-htn-marta", "htn", "marta"),
        _edge("e-marta-handoff", "marta", "handoff"),
        _edge("e-source-gate", "source", "source-gate", stroke=RED[1]),
        _edge("e-task-gate", "task", "task-gate", stroke=RED[1]),
        _edge("e-htn-gate", "htn", "htn-gate", stroke=RED[1]),
        _edge("e-marta-gate", "marta", "marta-gate", stroke=RED[1]),
        _edge("e-handoff-principle", "handoff", "principle", stroke=AMBER[1]),
    ]


def _figure_4_5_cells() -> list[dict[str, Any]]:
    return [
        _title("全局态势价值约束下的MARTA兵力与资源分配结构"),
        _node("task-graph", "任务图与结构贡献\n任务链 · 关键任务 · 共享关系", 35, 115, 350, 105, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("state", "全局评价状态\n兵力价值 · 位置环境价值\n多链关系 · 体系韧性", 425, 115, 350, 105, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("forces", "可用兵力与资源\n能力 · 状态 · 位置\n载荷 · 能源 · 预备", 815, 115, 350, 105, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("constraints", "约束与授权范围\n时空 · 风险 · 区域\n预算 · 行动权限", 1205, 115, 350, 105, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("gate", "第一步：硬约束门控\n剔除不可达、越权、风险超限或资源不足的任务—平台组合", 150, 285, 1300, 88, fill=RED[0], stroke=RED[1], font_size=22),
        _node("candidate", "第二步：候选兵力组合构造\n按任务关键度、候选稀缺度和多链共享关系形成可行组合", 150, 430, 620, 95, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("heuristic", "局部启发式\n仅用于筛选与排序\n不作为最终效能值", 810, 430, 280, 95, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=18),
        _node("global", "第三步：全局反事实评价\n相对共同基线比较\n全局态势价值变化", 1130, 430, 320, 95, fill=BLUE[0], stroke=BLUE[1], font_size=17),
        _node("optimize", "第四步：约束优化与一致性校核\n检查能力覆盖、并发冲突、任务级部署、共享支撑、预算和预备兵力", 150, 590, 900, 95, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("failure", "不可行输出\n失败类型 · 受影响任务\n违反约束 · 返回候选构造或HTN", 1120, 590, 330, 95, fill=RED[0], stroke=RED[1], font_size=17),
        _node("result", "资源配置解\n承担矩阵 · 平台角色 · 任务级部署区域 · 资源预算 · 替补集合", 220, 760, 1160, 95, fill=GREEN[0], stroke=GREEN[1], font_size=22),
        _edge("e-task-gate", "task-graph", "gate"),
        _edge("e-state-gate", "state", "gate"),
        _edge("e-forces-gate", "forces", "gate"),
        _edge("e-constraints-gate", "constraints", "gate"),
        _edge("e-gate-candidate", "gate", "candidate"),
        _edge("e-candidate-heuristic", "candidate", "heuristic"),
        _edge("e-heuristic-global", "heuristic", "global"),
        _edge("e-global-optimize", "global", "optimize"),
        _edge("e-optimize-result", "optimize", "result"),
        _edge("e-optimize-failure", "optimize", "failure", stroke=RED[1]),
    ]


def _figure_4_6_cells() -> list[dict[str, Any]]:
    return [
        _title("分解—分配失败反馈与最小充分修正机制"),
        _node("htn", "HTN候选任务图\n结构完整且继承硬约束", 45, 135, 320, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("marta", "MARTA可行性门控\n候选构造与全局比较", 455, 135, 320, 100, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("check", "一致性校核\n链路 · 时序 · 资源 · 区域", 865, 135, 320, 100, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("success", "可行任务—兵力方案\n进入人工审查与授权门", 1275, 135, 280, 100, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("classify", "失败语义分类\n明确受影响任务、违反约束、责任层级和可修正范围", 180, 315, 1240, 80, fill=RED[0], stroke=RED[1], font_size=22),
        _node("capability", "能力缺口\n替换平台\n增加共享支撑", 30, 480, 270, 120, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("time", "时序冲突\n调整开始时刻\n重排非关键任务", 340, 480, 270, 120, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("resource", "资源碰撞\n重分预算\n启用预备兵力", 650, 480, 270, 120, fill=PURPLE[0], stroke=PURPLE[1], font_size=19),
        _node("region", "区域不可行\n调整任务级区域\n更换候选组合", 960, 480, 270, 120, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _node("structure", "链路断裂或意图不一致\n返回HTN重构\n必要时上报指挥层", 1270, 480, 300, 120, fill=RED[0], stroke=RED[1], font_size=18),
        _node("repair", "最小充分修正原则\n优先在不改变任务目的和上位授权的最低层消除失败；仅当局部修正不能恢复可行性时，才提升返回层级", 180, 690, 1240, 105, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _node("guard", "禁止伪造承担关系、隐去失败或用局部收益抵消硬约束", 420, 825, 760, 48, fill=RED[0], stroke=RED[1], font_size=18),
        _edge("e-htn-marta", "htn", "marta"),
        _edge("e-marta-check", "marta", "check"),
        _edge("e-check-success", "check", "success"),
        _edge("e-check-classify", "check", "classify", stroke=RED[1]),
        _edge("e-classify-capability", "classify", "capability", stroke=RED[1]),
        _edge("e-classify-time", "classify", "time", stroke=RED[1]),
        _edge("e-classify-resource", "classify", "resource", stroke=RED[1]),
        _edge("e-classify-region", "classify", "region", stroke=RED[1]),
        _edge("e-classify-structure", "classify", "structure", stroke=RED[1]),
        _edge("e-capability-repair", "capability", "repair"),
        _edge("e-time-repair", "time", "repair"),
        _edge("e-resource-repair", "resource", "repair"),
        _edge("e-region-repair", "region", "repair"),
        _edge("e-structure-repair", "structure", "repair"),
    ]


def _figure_4_7_cells() -> list[dict[str, Any]]:
    return [
        _title("候选任务—兵力方案的人工审查、授权与交接门"),
        _node("baseline", "经确认的上位基线\n任务目的 · 期望效果 · 交战规则 · 授权范围 · 风险边界", 180, 115, 1240, 90, fill=AMBER[0], stroke=AMBER[1], font_size=22),
        _node("candidate", "技术候选方案\n任务图 · 承担关系 · 角色\n任务级区域 · 资源预算 · 替补关系", 55, 285, 430, 125, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("machine", "机器可验证检查\n结构完整性 · 资源可行性\n时空一致性 · 约束证据", 585, 285, 430, 125, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("human", "指挥主体人工审查\n意图一致性 · 目标合法性\n风险接受 · 授权范围 · 责任归属", 1115, 285, 430, 125, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("principle", "技术可行性与全局价值评价只说明“方案能否实施、相对是否有利”\n不自动构成行动授权，也不替代指挥员决心", 230, 505, 1140, 95, fill=RED[0], stroke=RED[1], font_size=22),
        _node("approve", "批准\n形成授权记录\n进入第五章策略生成", 110, 690, 390, 115, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("revise", "修改后复审\n限定修正对象与边界\n返回HTN或MARTA", 605, 690, 390, 115, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("reject", "拒绝或终止\n保留原因与证据\n不得进入执行链", 1100, 690, 390, 115, fill=RED[0], stroke=RED[1], font_size=21),
        _edge("e-baseline-candidate", "baseline", "candidate"),
        _edge("e-baseline-human", "baseline", "human"),
        _edge("e-candidate-machine", "candidate", "machine"),
        _edge("e-machine-human", "machine", "human"),
        _edge("e-human-principle", "human", "principle"),
        _edge("e-principle-approve", "principle", "approve", "批准"),
        _edge("e-principle-revise", "principle", "revise", "修改"),
        _edge("e-principle-reject", "principle", "reject", "拒绝"),
        _edge("e-revise-candidate", "revise", "candidate", "限定返回", stroke=AMBER[1], dashed=True),
    ]


def _capture_5130_source() -> Path:
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    base = "http://127.0.0.1:15130"

    def get(path: str) -> dict[str, Any]:
        with urllib.request.urlopen(base + path, timeout=20) as response:
            return json.load(response)

    previous = (
        KNOWLEDGE
        / "output/博士论文-v34第三章配图/04-source/5130-chapter3-contract-source.json"
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
        planning = {
            "situation_session_id": (prior.get("authority") or {}).get("planning_session_id"),
            "assessment": prior.get("planning_state") or {},
        }
        decision_input = {
            "authority": (prior.get("authority") or {}).get("decision_authority") or {},
            "observation": {"schema": (prior.get("contracts") or {}).get("observation_schema")},
            "action_context": {
                "schema": (prior.get("contracts") or {}).get("action_context_schema"),
                "command_budget": (prior.get("contracts") or {}).get("command_budget") or {},
            },
        }
        trace = {
            "plan_lineage": (prior.get("authority") or {}).get("plan_lineage") or {},
            **(prior.get("decision_trace") or {}),
        }
        legal = {}
        plan = {}
        capture_status = "fallback-to-prior-audited-snapshot"
        capture_error = f"{type(exc).__name__}: {exc}"

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Chapter 4 HTN/MARTA contract provenance; not an experiment result",
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
            "command_budget": (decision_input.get("action_context") or {}).get("command_budget") or {},
            "legal_action_summary": {
                key: value
                for key, value in legal.items()
                if key not in {"actions", "legal_actions"}
            },
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
            "The snapshot supplies model and interface semantics only.",
            "It does not prove algorithm superiority or operational effectiveness.",
            "Technical feasibility and value evaluation do not grant military authority.",
            "Plans, observations, commands, authorizations, and results remain distinct authority objects.",
        ],
    }
    target = SOURCE_ROOT / "5130-chapter4-contract-source.json"
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
        "series_id": "thesis-v34-chapter-4-diagrams",
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
        {"label": "v34第四章第一阶段审校版", "reason": "chapter-4-stage1"},
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
        raise SystemExit("第四章图源缺失：" + "；".join(missing))

    api_snapshot = _capture_5130_source()
    specs = [
        {
            "title": "图4-1 指挥意图、全局态势与任务需求的语义映射",
            "diagram_type": "ch4-intent-state-task-semantics",
            "cells": _figure_4_1_cells(),
            "source_assets": [CURRENT_FIGURES["fig4-1"]],
            "insertion_section": "4.2.5",
            "provenance_note": "Redrawn from the current task-input structure with explicit intent, evaluation-state, and traceability semantics.",
        },
        {
            "title": "图4-2 目标处置链、态势塑造链与共享支撑任务网络",
            "diagram_type": "ch4-multiple-task-chain-network",
            "cells": _figure_4_2_cells(),
            "source_assets": [CURRENT_FIGURES["fig4-2"]],
            "insertion_section": "4.3.3",
            "provenance_note": "Redrawn from the current task-chain mapping to distinguish multiple target chains, shaping tasks, common support, and authorization prerequisites.",
        },
        {
            "title": "图4-3 HTN候选任务结构的生成、剪枝与全局选择",
            "diagram_type": "ch4-htn-candidate-selection",
            "cells": _figure_4_3_cells(),
            "source_assets": [CURRENT_FIGURES["fig4-3"]],
            "insertion_section": "4.4.3",
            "provenance_note": "Reframed from the historical reverse-decomposition figure as a complete candidate generation, hard-pruning, and global-selection process.",
        },
        {
            "title": "图4-4 任务约束的继承、分层校核与不可越权关系",
            "diagram_type": "ch4-constraint-inheritance-gates",
            "cells": _figure_4_4_cells(),
            "source_assets": [],
            "insertion_section": "4.5.5",
            "provenance_note": "New authority-boundary figure showing downward constraint inheritance and the prohibition on lower-level relaxation.",
        },
        {
            "title": "图4-5 全局态势价值约束下的MARTA兵力与资源分配结构",
            "diagram_type": "ch4-marta-global-value-allocation",
            "cells": _figure_4_5_cells(),
            "source_assets": [CURRENT_FIGURES["fig4-4"]],
            "insertion_section": "4.5.6",
            "provenance_note": "Redrawn from the current MARTA figure to separate hard gating, candidate construction, heuristic screening, global counterfactual evaluation, and infeasibility feedback.",
        },
        {
            "title": "图4-6 分解—分配失败反馈与最小充分修正机制",
            "diagram_type": "ch4-decomposition-allocation-repair",
            "cells": _figure_4_6_cells(),
            "source_assets": [],
            "insertion_section": "4.7.3",
            "provenance_note": "New failure-semantics figure separating local MARTA repair from structural HTN return and command-level escalation.",
        },
        {
            "title": "图4-7 候选任务—兵力方案的人工审查、授权与交接门",
            "diagram_type": "ch4-human-authorization-handoff",
            "cells": _figure_4_7_cells(),
            "source_assets": [],
            "insertion_section": "4.7.4",
            "provenance_note": "New command-and-control figure separating technical feasibility and value evaluation from human authorization and Chapter 5 handoff.",
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

    report_path = REPORT_ROOT / "chapter4-stage1-install-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
