"""Create editable Chapter 5 thesis diagrams for review.

Stage 1 creates structured diagram documents, records method provenance, and
exports SVG/JSON review artifacts. It does not mutate the thesis body.
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
ACTOR = "thesis-ch5-diagram-stage1"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第五章配图"
SOURCE_ROOT = OUTPUT_ROOT / "04-source"
EXPORT_ROOT = OUTPUT_ROOT / "05-review-exports"
REPORT_ROOT = OUTPUT_ROOT / "06-reports"
BASELINE = OUTPUT_ROOT / "01-baseline/chapter5-structured-baseline.json"
CURRENT_ROOT = (
    KNOWLEDGE
    / "06-项目库-Projects/博士论文/_workspace/documents/doc-0cdb6e81aebb"
)
CURRENT_WORKING = CURRENT_ROOT / "working/document.md"
ASSET_ROOT = CURRENT_ROOT / "source/assets/figures"
CURRENT_FIGURES = {
    "contract": ASSET_ROOT / "structure/svg/ch5-task-policy-contract-v30.svg",
    "sequence": ASSET_ROOT / "structure/svg/ch5-policy-sequence-v30.svg",
    "evidence": ASSET_ROOT / "data/ch5-06-evidence-chain-v23.svg",
    "network": ASSET_ROOT / "ui-evidence/svg/ch5-shared-targetmap-network-evidence-v23.svg",
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
        "shape": "rect",
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


def _figure_5_1_cells() -> list[dict[str, Any]]:
    return [
        _title("第四章任务交接包向第五章任务策略集合的受约束映射"),
        _node("handoff", "经批准的任务交接包\n任务目标 · 依赖关系 · 承担平台 · 角色\n任务级区域 · 资源预算 · 约束与评价依据", 140, 120, 1320, 100, fill=AMBER[0], stroke=AMBER[1], font_size=22),
        _node("gate1", "交接有效性门\n任务可行 · 承担者有效 · 区域非空\n前置条件、坐标、时钟与版本可解析", 90, 300, 430, 135, fill=RED[0], stroke=RED[1], font_size=20),
        _node("mapping", "任务内映射\n识别任务阶段和平台角色\n选择可用策略单元与调用关系\n初始化共享上下文和失败回退规则", 585, 300, 430, 135, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("gate2", "不变量校核门\n不改变任务目的、任务依赖、承担关系\n不扩大任务区域、资源预算或行动权限", 1080, 300, 430, 135, fill=RED[0], stroke=RED[1], font_size=20),
        _node("sensor", "感知规则策略集合\n搜索 · 识别 · 跟踪 · 效果评估", 45, 550, 350, 105, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("fire", "火力规则策略集合\n合法性复核 · 武器匹配 · 释放许可", 425, 550, 350, 105, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _node("maneuver", "协同机动策略集合\n阶段目标点 · 编队意图 · 任务参数", 805, 550, 350, 105, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("graph", "策略调用与回退结构\n前置 · 同步 · 互斥 · 终止 · 失败语义", 1185, 550, 370, 105, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("result", "任务策略集合\n只细化任务内部“何时调用什么能力、下一阶段去哪里”\n不能重新生成任务图、重新分配兵力或创设行动授权", 180, 750, 1240, 95, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _edge("e-handoff-gate1", "handoff", "gate1"),
        _edge("e-handoff-mapping", "handoff", "mapping"),
        _edge("e-handoff-gate2", "handoff", "gate2"),
        _edge("e-gate1-mapping", "gate1", "mapping"),
        _edge("e-gate2-mapping", "gate2", "mapping"),
        _edge("e-mapping-sensor", "mapping", "sensor"),
        _edge("e-mapping-fire", "mapping", "fire"),
        _edge("e-mapping-maneuver", "mapping", "maneuver"),
        _edge("e-mapping-graph", "mapping", "graph"),
        _edge("e-sensor-result", "sensor", "result"),
        _edge("e-fire-result", "fire", "result"),
        _edge("e-maneuver-result", "maneuver", "result"),
        _edge("e-graph-result", "graph", "result"),
    ]


def _figure_5_2_cells() -> list[dict[str, Any]]:
    return [
        _title("指挥授权、规则许可与武器释放的三重门控及撤销链"),
        _node("authority", "有权指挥主体签发授权\n签发主体 · 适用目标与行动 · 时空范围\n交战规则版本 · 有效期 · 撤销状态 · 审计标识", 120, 115, 1360, 110, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("gate-a", "第一门：授权有效性\n存在且未撤销 · 对象、行动、区域、时段均在范围内", 180, 285, 1240, 85, fill=RED[0], stroke=RED[1], font_size=21),
        _node("knowledge", "目标确认与态势证据\n敌我属性 · 航迹质量 · 目标信念 · 受保护对象", 45, 455, 430, 110, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("weapon", "武器与协同条件\n武器就绪 · 射程射界 · 弹药与通道 · 协同时窗", 585, 455, 430, 110, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("safety", "安全与交战规则\n禁射区 · 友军间隔 · 风险边界 · 任务阶段", 1125, 455, 430, 110, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("gate-r", "第二门：规则释放许可\n规则只消费既有授权并复核当前技术与战术条件；不得自行创设指挥权", 180, 635, 1240, 90, fill=AMBER[0], stroke=AMBER[1], font_size=21),
        _node("executor", "第三门：权威执行前复核\n再次校核授权、目标、窗口和安全状态\n通过后方可实施武器释放", 100, 760, 940, 105, fill=GREEN[0], stroke=GREEN[1], font_size=19),
        _node("deny", "等待 / 拒绝 / 中止\n授权过期或撤销、目标变化、条件失效\n立即闭锁并重新校核", 1110, 760, 400, 105, fill=RED[0], stroke=RED[1], font_size=17),
        _edge("e-authority-gatea", "authority", "gate-a"),
        _edge("e-gatea-knowledge", "gate-a", "knowledge"),
        _edge("e-gatea-weapon", "gate-a", "weapon"),
        _edge("e-gatea-safety", "gate-a", "safety"),
        _edge("e-knowledge-gater", "knowledge", "gate-r"),
        _edge("e-weapon-gater", "weapon", "gate-r"),
        _edge("e-safety-gater", "safety", "gate-r"),
        _edge("e-gater-executor", "gate-r", "executor"),
        _edge("e-gatea-deny", "gate-a", "deny", stroke=RED[1], dashed=True),
        _edge("e-gater-deny", "gate-r", "deny", stroke=RED[1], dashed=True),
        _edge("e-executor-deny", "executor", "deny", stroke=RED[1], dashed=True),
    ]


def _figure_5_3_cells() -> list[dict[str, Any]]:
    return [
        _title("感知、火力与机动异构策略协同及动作所有权"),
        _node("context", "共享任务上下文\n任务阶段 · 平台角色 · 目标信念 · 资源状态 · 约束 · 执行反馈", 160, 110, 1280, 90, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=22),
        _node("sensor", "感知规则策略\n拥有：传感器模式、扫描扇区、航迹维护\n输出：目标信念与信息质量", 45, 300, 440, 140, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("fire", "火力规则策略\n拥有：武器候选与释放许可通道\n前提：既有指挥授权持续有效", 580, 300, 440, 140, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("maneuver", "协同机动策略\n拥有：各平台阶段目标点通道\n不拥有：传感器、武器和底层控制", 1115, 300, 440, 140, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("arbiter", "策略调度与冲突消解\n依据前置、同步、互斥、终止和优先级形成兼容激活集合", 240, 555, 1120, 90, fill=PURPLE[0], stroke=PURPLE[1], font_size=22),
        _node("sensor-out", "传感器指令", 65, 750, 280, 75, fill=BLUE[0], stroke=BLUE[1], font_size=21),
        _node("fire-out", "武器释放许可\n不是指挥授权", 425, 750, 300, 75, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _node("target-out", "阶段目标点", 805, 750, 280, 75, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("control-out", "路径与控制量\n由经典规划和控制生成", 1165, 750, 370, 75, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=18),
        _edge("e-context-sensor", "context", "sensor"),
        _edge("e-context-fire", "context", "fire"),
        _edge("e-context-maneuver", "context", "maneuver"),
        _edge("e-sensor-arbiter", "sensor", "arbiter"),
        _edge("e-fire-arbiter", "fire", "arbiter"),
        _edge("e-maneuver-arbiter", "maneuver", "arbiter"),
        _edge("e-arbiter-sensorout", "arbiter", "sensor-out"),
        _edge("e-arbiter-fireout", "arbiter", "fire-out"),
        _edge("e-arbiter-targetout", "arbiter", "target-out"),
        _edge("e-target-control", "target-out", "control-out"),
    ]


def _figure_5_4_cells() -> list[dict[str, Any]]:
    return [
        _title("攻击任务的策略调用图与侦察—打击—评估—脱离时序"),
        _node("observe", "任务上下文更新\n目标信念、授权状态、平台与资源", 55, 120, 300, 95, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=19),
        _node("confirm", "目标确认与持续跟踪\n感知规则", 430, 120, 300, 95, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("position", "接敌与攻击阵位机动\n学习机动", 805, 120, 300, 95, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("permission", "授权复核与释放许可\n火力规则", 1180, 120, 340, 95, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _node("sync", "协同窗口同步门\n目标确认 ∧ 阵位可用 ∧ 授权有效 ∧ 武器与安全条件满足", 220, 325, 1160, 85, fill=RED[0], stroke=RED[1], font_size=21),
        _node("release", "权威执行器复核并实施释放", 80, 535, 340, 95, fill=AMBER[0], stroke=AMBER[1], font_size=20),
        _node("assess", "毁伤与任务效果评估\n以权威裁决更新信念", 510, 535, 340, 95, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("egress", "攻击后脱离或保持监视\n学习机动与感知规则", 940, 535, 340, 95, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("stop", "中止 / 等待 / 重新占位", 1370, 535, 190, 95, fill=RED[0], stroke=RED[1], font_size=17),
        _node("feedback", "事件驱动反馈\n目标丢失返回确认；窗口错失返回占位；授权撤销立即闭锁；效果不足且条件仍满足时形成再攻击需求", 175, 755, 1250, 95, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=20),
        _edge("e-observe-confirm", "observe", "confirm"),
        _edge("e-confirm-position", "confirm", "position"),
        _edge("e-position-permission", "position", "permission"),
        _edge("e-confirm-sync", "confirm", "sync"),
        _edge("e-position-sync", "position", "sync"),
        _edge("e-permission-sync", "permission", "sync"),
        _edge("e-sync-release", "sync", "release", "满足"),
        _edge("e-release-assess", "release", "assess"),
        _edge("e-assess-egress", "assess", "egress", "完成"),
        _edge("e-sync-stop", "sync", "stop", "不满足", stroke=RED[1]),
        _edge("e-assess-feedback", "assess", "feedback"),
        _edge("e-egress-feedback", "egress", "feedback"),
        _edge("e-stop-feedback", "stop", "feedback"),
        _edge("e-feedback-confirm", "feedback", "confirm", "重新确认", dashed=True),
        _edge("e-feedback-position", "feedback", "position", "重新占位", dashed=True),
    ]


def _figure_5_5_cells() -> list[dict[str, Any]]:
    return [
        _title("阶段目标点、路径、首执行航路点与控制量的分层转换"),
        _node("actor", "协同机动策略\n回答“下一阶段去哪里”\n输出各平台阶段目标点", 55, 120, 360, 115, fill=GREEN[0], stroke=GREEN[1], font_size=21),
        _node("mask", "动作掩码与连续可行域投影\n地图 · 禁区 · 航程 · 间隔 · 时窗", 500, 120, 600, 115, fill=RED[0], stroke=RED[1], font_size=20),
        _node("goal", "经投影的阶段目标点\n保留投影前后位置与距离", 1185, 120, 360, 115, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("global", "全局路径规划\n回答“沿什么路径”\n形成可达路径或明确失败", 55, 350, 430, 115, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("conflict", "多平台时空冲突消解\n优先级 · 预约 · 安全间隔 · 协同窗口", 585, 350, 430, 115, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("waypoint", "首个可执行航路点\n只是完整路径的当前执行接口\n不等同于已到达阶段目标", 1115, 350, 430, 115, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _node("local", "局部避碰与控制器\n回答“如何安全运动”\n生成速度、姿态与控制量", 240, 595, 520, 115, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=20),
        _node("execution", "平台运动与权威状态更新\n实际位置 · 轨迹 · 资源 · 安全介入 · 到达状态", 840, 595, 520, 115, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("metrics", "分层解释指标\n目标点—首航路点距离只描述层级步长；须与方向一致性、目标进展、路径可达率、长时域到达率和安全介入联合解释", 175, 790, 1250, 80, fill=AMBER[0], stroke=AMBER[1], font_size=19),
        _edge("e-actor-mask", "actor", "mask"),
        _edge("e-mask-goal", "mask", "goal"),
        _edge("e-goal-global", "goal", "global"),
        _edge("e-global-conflict", "global", "conflict"),
        _edge("e-conflict-waypoint", "conflict", "waypoint"),
        _edge("e-waypoint-local", "waypoint", "local"),
        _edge("e-local-execution", "local", "execution"),
        _edge("e-execution-metrics", "execution", "metrics"),
    ]


def _figure_5_6_cells() -> list[dict[str, Any]]:
    return [
        _title("任务内失败语义与L0—L3最小充分回退机制"),
        _node("failure", "显式失败语义\n感知失效 · 授权或武器等待 · 目标点不可行 · 路径阻塞\n能力覆盖失效 · 任务链断裂", 170, 110, 1260, 95, fill=RED[0], stroke=RED[1], font_size=21),
        _node("classify", "按受影响对象选择最低充分修复层\n先判断本层是否仍有局部可行修复，再检查重试预算、迟滞窗口与上位不变量", 170, 270, 1260, 85, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _node("l0", "L0 策略/执行局部修复\n等待、重试、局部路径、速度与避碰\n保持：目标点语义、承担关系、任务图", 25, 465, 350, 135, fill=BLUE[0], stroke=BLUE[1], font_size=18),
        _node("l1", "L1 任务内策略与目标修复\n策略替代、战术参数、目标点、局部顺序\n保持：当前任务、平台角色、任务图", 425, 465, 350, 135, fill=GREEN[0], stroke=GREEN[1], font_size=18),
        _node("l2", "L2 兵力与资源修复\n返回资源分配层调整平台、角色、区域或预算\n保持：可行任务图与任务目的", 825, 465, 350, 135, fill=PURPLE[0], stroke=PURPLE[1], font_size=18),
        _node("l3", "L3 任务结构修复\n返回任务分解层重构任务链\n保持：经确认的指挥意图与授权边界", 1225, 465, 350, 135, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _node("verify", "修复后复核\n策略图 · 规则状态 · 坐标 · 掩码 · 路径 · 任务一致性 · 优势恢复\n本层失败时按照L0→L1→L2→L3逐级升级，禁止越级覆盖", 210, 710, 920, 100, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=18),
        _node("infeasible", "仍不可行\n输出规划不可行及证据\n交由意图层或人工处置", 1190, 710, 330, 90, fill=RED[0], stroke=RED[1], font_size=18),
        _edge("e-failure-classify", "failure", "classify"),
        _edge("e-classify-l0", "classify", "l0"),
        _edge("e-classify-l1", "classify", "l1"),
        _edge("e-classify-l2", "classify", "l2"),
        _edge("e-classify-l3", "classify", "l3"),
        _edge("e-l0-verify", "l0", "verify"),
        _edge("e-l1-verify", "l1", "verify"),
        _edge("e-l2-verify", "l2", "verify"),
        _edge("e-l3-verify", "l3", "verify"),
        _edge("e-verify-infeasible", "verify", "infeasible", stroke=RED[1]),
    ]


def _figure_5_7_cells() -> list[dict[str, Any]]:
    return [
        _title("任务内规划执行证据链与证据等级—主张边界"),
        _node("handoff", "任务交接记录\n3份", 25, 165, 190, 85, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _node("policy", "任务策略集合\n3份", 255, 165, 190, 85, fill=PURPLE[0], stroke=PURPLE[1], font_size=18),
        _node("decision", "策略决策记录\n12条", 485, 165, 190, 85, fill=GREEN[0], stroke=GREEN[1], font_size=18),
        _node("command", "命令记录\n12条", 715, 165, 190, 85, fill=BLUE[0], stroke=BLUE[1], font_size=18),
        _node("execute", "权威执行与裁决", 945, 165, 190, 85, fill=RED[0], stroke=RED[1], font_size=18),
        _node("trace", "执行轨迹记录\n12条", 1175, 165, 190, 85, fill=BLUE[0], stroke=BLUE[1], font_size=18),
        _node("evaluate", "汇总评价记录\n3份", 1405, 165, 170, 85, fill=GREEN[0], stroke=GREEN[1], font_size=17),
        _node("identity", "同一运行标识与对象链校验\n任务、策略集合、决策、命令、轨迹和评价逐级绑定；记录可见信息边界、动作所有权、合法性、失败码与校验摘要", 130, 350, 1340, 95, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=20),
        _node("g0", "G0\n公式、合同与实验协议冻结\n只支持“问题已定义”", 25, 555, 280, 125, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=18),
        _node("g1", "G1\n组件、形状、掩码与梯度验证\n只支持“组件可训练”", 340, 555, 280, 125, fill=BLUE[0], stroke=BLUE[1], font_size=18),
        _node("g2", "G2\n任务内对象链与权威执行闭合\n只支持“系统链路闭合”", 655, 555, 280, 125, fill=GREEN[0], stroke=GREEN[1], font_size=18),
        _node("g3", "G3\n真实三任务轨迹进入共享更新\n只支持“在线训练链成立”", 970, 555, 280, 125, fill=PURPLE[0], stroke=PURPLE[1], font_size=18),
        _node("alevel", "A级\n独立场景、配对基线、多种子统计\n才允许任务内效能比较", 1285, 555, 280, 125, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _node("boundary", "主张边界\n第五章从冻结交接包开始，不能验证上游任务分解与兵力分配正确性；任务内A级结果也不能外推为完整指挥控制系统优势", 180, 780, 1240, 85, fill=RED[0], stroke=RED[1], font_size=20),
        _edge("e-handoff-policy", "handoff", "policy"),
        _edge("e-policy-decision", "policy", "decision"),
        _edge("e-decision-command", "decision", "command"),
        _edge("e-command-execute", "command", "execute"),
        _edge("e-execute-trace", "execute", "trace"),
        _edge("e-trace-evaluate", "trace", "evaluate"),
        _edge("e-policy-identity", "policy", "identity"),
        _edge("e-evaluate-identity", "evaluate", "identity"),
        _edge("e-identity-g0", "identity", "g0"),
        _edge("e-identity-g1", "identity", "g1"),
        _edge("e-identity-g2", "identity", "g2"),
        _edge("e-identity-g3", "identity", "g3"),
        _edge("e-identity-a", "identity", "alevel"),
        _edge("e-a-boundary", "alevel", "boundary"),
    ]


def _figure_5_15_cells() -> list[dict[str, Any]]:
    return [
        _title("任务条件化共享机动网络结构与动作所有权"),
        _node("spatial", "局部空间态势\n8通道任务坐标栅格", 35, 115, 270, 95, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("entities", "可见实体序列\n平台、目标与置信信息", 350, 115, 270, 95, fill=BLUE[0], stroke=BLUE[1], font_size=19),
        _node("tactical", "战术函数条件\n任务、阶段、角色与规则状态", 665, 115, 270, 95, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _node("temporal", "时序历史\n部分可观测状态", 980, 115, 270, 95, fill=PURPLE[0], stroke=PURPLE[1], font_size=19),
        _node("mask", "合法目标掩码\n由规则与环境生成", 1295, 115, 270, 95, fill=RED[0], stroke=RED[1], font_size=18),
        _node("conv", "空间编码器\n保留目标位置分辨率", 105, 300, 310, 100, fill=BLUE[0], stroke=BLUE[1], font_size=20),
        _node("transformer", "实体关系编码器\n掩码保持集合语义", 490, 300, 310, 100, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("condition", "标量与条件编码器\n区分允许做什么与为何移动", 875, 300, 310, 100, fill=AMBER[0], stroke=AMBER[1], font_size=18),
        _node("lstm", "循环记忆单元\n融合历史与当前任务语境", 1260, 300, 310, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=20),
        _node("shared", "共享特征与逐平台分散决策\n不同平台共享参数，依据各自局部观测、角色和历史形成差异化输出", 185, 505, 1230, 90, fill=NEUTRAL[0], stroke=NEUTRAL[1], font_size=21),
        _node("heatmap", "64×64目标单元热力图\n多峰区域选择", 75, 700, 360, 100, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("offset", "格内连续偏移\n降低栅格量化误差", 500, 700, 360, 100, fill=GREEN[0], stroke=GREEN[1], font_size=20),
        _node("value", "集中价值头\n仅在训练阶段评价联合状态", 925, 700, 300, 100, fill=PURPLE[0], stroke=PURPLE[1], font_size=18),
        _node("boundary", "部署输出边界\n学习策略只形成阶段目标点\n传感器、武器、平台分配\n和底层控制均非学习动作", 1280, 685, 285, 130, fill=RED[0], stroke=RED[1], font_size=15),
        _edge("e-spatial-conv", "spatial", "conv"),
        _edge("e-entities-transformer", "entities", "transformer"),
        _edge("e-tactical-condition", "tactical", "condition"),
        _edge("e-temporal-lstm", "temporal", "lstm"),
        _edge("e-mask-shared", "mask", "shared", stroke=RED[1]),
        _edge("e-conv-shared", "conv", "shared"),
        _edge("e-transformer-shared", "transformer", "shared"),
        _edge("e-condition-shared", "condition", "shared"),
        _edge("e-lstm-shared", "lstm", "shared"),
        _edge("e-shared-heatmap", "shared", "heatmap"),
        _edge("e-shared-offset", "shared", "offset"),
        _edge("e-shared-value", "shared", "value"),
        _edge("e-heatmap-offset", "heatmap", "offset"),
        _edge("e-offset-boundary", "offset", "boundary"),
    ]


def _capture_method_source() -> Path:
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    base = "http://127.0.0.1:15130"

    def get(path: str) -> dict[str, Any]:
        with urllib.request.urlopen(base + path, timeout=20) as response:
            return json.load(response)

    network_library = get("/api/network-library")
    target = next(
        row
        for row in network_library.get("items") or []
        if row.get("id") == "wargame-multitask-targetmap-policy-v1"
    )
    plans = get("/api/training/plans")
    related_plans = [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "status": row.get("status"),
            "revision": row.get("current_revision") or row.get("revision"),
            "config_hash": row.get("config_hash"),
        }
        for row in plans.get("plans") or []
        if "wargame-multitask-targetmap-policy-v1"
        in json.dumps(row.get("definition") or {}, ensure_ascii=False)
    ]
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Chapter 5 method and network provenance; not an experiment result",
        "network": {
            key: target.get(key)
            for key in (
                "id",
                "name",
                "description",
                "version",
                "status",
                "input_signature",
                "output_signature",
                "node_count",
                "edge_count",
                "updated_at",
            )
        },
        "related_training_plans": related_plans,
        "limitations": [
            "The source records method and interface semantics only.",
            "A published network asset does not prove convergence or tactical superiority.",
            "Rule permission consumes existing command authority and cannot create it.",
            "The learned policy owns maneuver target points only.",
        ],
    }
    output = SOURCE_ROOT / "chapter5-method-source.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


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
    method_source: Path,
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
        "series_id": "thesis-v34-chapter-5-diagrams",
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
        "method_source_path": str(method_source),
        "method_source_sha256": _sha_file(method_source),
        "provenance_note": provenance_note,
        "publication_status": "stage1-review",
    }
    multi_document_service.update_document(project, diagram_id, {"lineage": lineage})
    current = diagram_service.get(project, diagram_id)
    diagram_service.create_version(
        project,
        diagram_id,
        {"label": "v34第五章第一阶段审校版", "reason": "chapter-5-stage1"},
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
        raise SystemExit("第五章图源缺失：" + "；".join(missing))

    method_source = _capture_method_source()
    specs = [
        {
            "title": "图5-1 第四章任务交接包向第五章任务策略集合的受约束映射",
            "diagram_type": "ch5-handoff-policy-constrained-mapping",
            "cells": _figure_5_1_cells(),
            "source_assets": [CURRENT_FIGURES["contract"]],
            "insertion_section": "5.1.3",
            "provenance_note": "Redrawn from the historical task-policy contract with explicit upstream invariants and command-authority limits.",
        },
        {
            "title": "图5-2 指挥授权、规则许可与武器释放的三重门控及撤销链",
            "diagram_type": "ch5-command-authority-release-gates",
            "cells": _figure_5_2_cells(),
            "source_assets": [],
            "insertion_section": "5.2.3",
            "provenance_note": "New military command-and-control figure separating normative authorization, rule permission, and execution.",
        },
        {
            "title": "图5-3 感知、火力与机动异构策略协同及动作所有权",
            "diagram_type": "ch5-heterogeneous-policy-action-ownership",
            "cells": _figure_5_3_cells(),
            "source_assets": [CURRENT_FIGURES["contract"]],
            "insertion_section": "5.2.5",
            "provenance_note": "New action-ownership figure showing shared context without shared control authority.",
        },
        {
            "title": "图5-4 攻击任务的策略调用图与侦察—打击—评估—脱离时序",
            "diagram_type": "ch5-attack-policy-event-sequence",
            "cells": _figure_5_4_cells(),
            "source_assets": [CURRENT_FIGURES["sequence"]],
            "insertion_section": "5.4.4",
            "provenance_note": "Redrawn from the historical policy sequence to add command authorization, event-driven waiting, assessment, abort, and return branches.",
        },
        {
            "title": "图5-5 阶段目标点、路径、首执行航路点与控制量的分层转换",
            "diagram_type": "ch5-target-path-waypoint-control-hierarchy",
            "cells": _figure_5_5_cells(),
            "source_assets": [],
            "insertion_section": "5.7.2",
            "provenance_note": "New layered execution figure separating target selection, path planning, first-waypoint execution, and control.",
        },
        {
            "title": "图5-6 任务内失败语义与L0—L3最小充分回退机制",
            "diagram_type": "ch5-failure-semantics-l0-l3-repair",
            "cells": _figure_5_6_cells(),
            "source_assets": [],
            "insertion_section": "5.7.5",
            "provenance_note": "New repair hierarchy preserving the minimum sufficient unchanged objects at each level.",
        },
        {
            "title": "图5-7 任务内规划执行证据链与证据等级—主张边界",
            "diagram_type": "ch5-evidence-chain-claim-boundary",
            "cells": _figure_5_7_cells(),
            "source_assets": [CURRENT_FIGURES["evidence"]],
            "insertion_section": "5.8.3",
            "provenance_note": "Redrawn from the historical evidence chain to include task policy sets, authoritative adjudication, object identity, and claim gates.",
        },
        {
            "title": "图5-15 任务条件化共享机动网络结构与动作所有权",
            "diagram_type": "ch5-task-conditioned-maneuver-network",
            "cells": _figure_5_15_cells(),
            "source_assets": [CURRENT_FIGURES["network"]],
            "insertion_section": "5.8.6",
            "provenance_note": "Redrawn from the published target-map network asset without the development-interface screenshot and with explicit action ownership.",
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
        "method_source": {"path": str(method_source), "sha256": _sha_file(method_source)},
        "diagrams": [],
    }
    for spec in specs:
        resource = _ensure_diagram(project, method_source=method_source, **spec)
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

    report_path = REPORT_ROOT / "chapter5-stage1-install-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
