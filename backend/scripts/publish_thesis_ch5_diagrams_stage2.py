"""Publish reviewed Chapter 5 diagrams and academic prose into the thesis."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
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
PARENT_DOCUMENT_ID = "doc-15def56e2401"
EXPECTED_BASE_REVISION = 66
EXPECTED_BASE_SHA256 = "2d7996576bfdbfcca6d9a1dd8edbc9ee000d397bd362b843092cc340a54bed60"
EXPECTED_CHAPTER_SHA256 = "b1ca6faeeb2c05e8d0460938a0542af139b9c54386cce5b9c03d6d766dfbf765"
ACTOR = "thesis-ch5-diagram-stage2"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第五章配图"
STAGE2_ROOT = OUTPUT_ROOT / "07-stage2"
REPORT_PATH = STAGE2_ROOT / "chapter5-stage2-publish-report.json"
CHAPTER_TITLE = "第5章 基于规则武器运用与强化学习机动的无人集群任务内协同规划方法"

FIGURE_NUMBER_MAP = {
    3: 8,
    4: 9,
    5: 10,
    6: 7,
    7: 11,
    8: 12,
    9: 13,
    10: 14,
    11: 15,
    12: 16,
    13: 17,
    14: 18,
    15: 19,
    16: 20,
    17: 21,
}

TERM_REPLACEMENTS = [
    ("PolicyExecutionTrace", "策略执行轨迹记录"),
    ("Target-Move", "阶段目标点"),
    ("Target Move", "阶段目标点"),
    ("5130训练中心", "训练管理系统"),
    ("当前5130", "当前实现"),
    ("5130", "任务规划系统"),
    ("AI Planning", "任务规划系统"),
    ("Wargame", "对抗仿真环境"),
    ("TaskHandoff", "任务交接记录"),
    ("TaskPolicySet", "任务策略集合"),
    ("PolicyDecision", "策略决策记录"),
    ("CommandBundle", "命令记录"),
    ("ExecutionTrace", "执行轨迹记录"),
    ("EvaluationRecord", "评价记录"),
    ("FireAllocationAgent", "规则火力分配单元"),
    ("FireDemand", "火力需求对象"),
    ("full_v2", "完整八维模型"),
    ("simplified_v1", "简化四维模型"),
    ("fire_authorization=false", "释放许可为假"),
    ("Data Lake", "数据湖"),
]

CAPTION_UPDATES = {
    "block-a8c823512ab3f50da4bda36c": "图5-8 G1共享机动策略组件训练与数值稳定性",
    "block-71f5c00c8d6a41c6902e2b90": "图5-9 同一检查点在三类任务输入下的阶段目标点分布",
    "block-ee1f4a9a51ddf869548acc30": "图5-10 共享检查点的阶段目标点与首执行航路点适配",
    "block-843762ed099842d9cb2f1668": "图5-11 三任务共享机动策略的在线优化诊断",
    "block-fdd9c468ae6194f959fe106a": "图5-12 三类任务逐平台阶段目标点与首执行航路点",
    "block-bf38f0ad85d19a788047fe72": "图5-13 三任务共享机动策略十轮在线优化诊断",
    "block-8717bcaee72e88722864646a": "图5-14 三任务固定独立面板先导评价",
    "block-ef6dfb11c3fefd92fd06317b": "图5-16 三种子三阶段共享机动策略课程训练诊断",
    "block-71c3fa54a4fed9ff66d8395e": "图5-17 三任务三方法30种子独立测试奖励与成功率",
    "block-a8b59a318da3cffd63848a5f": "图5-18 共享机动候选相对基线的配对奖励效应与95%置信区间",
    "block-0ea0373615b44f86bb684f28": "图5-19 搜索任务随机种子5003三方法配对航迹",
    "block-9677d49f2eadbc451d4c8466": "图5-20 攻击任务随机种子5003三方法配对航迹",
    "block-9355452c9c1aaa0c2f9bbdee": "图5-21 通用机动任务随机种子5003三方法配对航迹",
}

PARAGRAPH_OVERRIDES = {
    "block-4d0a3e71249d2e3715c146f3": (
        "不同任务以不同方式组合两条策略链。搜索任务以规则感知支撑和学习机动为主；攻击任务依次或并行"
        "调用目标确认、协同占位、火力分配、释放许可和攻击后脱离；转场、会合和撤离任务以学习机动为主，"
        "并保持必要的威胁监视。搜索、攻击和机动是任务或任务阶段语义，规则武器运用与强化学习机动是被"
        "这些任务复用的决策机制。第四章任务交接包向本章任务策略集合的受约束映射及本层必须保持的上位"
        "不变量如图5-1所示。"
    ),
    "block-77d26f6ef0bfadaea7426dfd": (
        "火力规则策略负责目标合法性复核、武器—目标适配、射程与射界检查、协同攻击窗口校核，并在既有"
        "指挥授权持续有效的前提下形成武器选择、等待或释放许可。该策略不产生新的指挥授权，也不得扩大"
        "授权适用的目标、行动、区域和时段。其输出写为"
    ),
    "block-e0378ac36ea0a7150727d770": (
        "火力规则策略的前置条件至少包括：授权记录存在且未撤销，目标身份和敌我属性满足交战规则，目标"
        "信念质量达到阈值，武器可用，平台位于有效作用区，友军与禁射区约束满足，协同攻击时序已经形成。"
        "任一条件不满足时，只允许输出等待、拒绝许可或重新占位请求，不能产生武器释放指令。"
    ),
    "block-077e50f89218ea64f626c385": (
        "火力规则策略采用确定性规则，是因为武器运用属于安全关键过程，必须具有明确、可审计和可复现的"
        "判据；但规则许可不能替代有权主体的指挥授权。指挥授权、规则释放许可与执行前复核构成相互独立的"
        "三重门控，如图5-2所示。即使机动策略已经生成攻击占位点，也只有在授权持续有效、规则条件全部成立"
        "且权威执行器再次复核通过后，方可实施武器释放；授权过期、撤销或目标与任务阶段变化时必须立即"
        "闭锁并重新校核。"
    ),
    "block-b49bb0b2a295f5f6b0efdf7d": (
        "动作所有权必须随任务策略集合和模型检查点共同版本化。规则可以生成动作掩码、修改共享上下文或"
        "拒绝非法动作，但不能在未声明所有权的情况下替代机动网络生成另一目标点；机动网络也不能越过"
        "指挥授权和火力规则直接产生武器释放命令。感知、火力与机动策略共享任务上下文，但不共享动作权限，"
        "其职责分工与输出通道如图5-3所示。"
    ),
    "block-85b7e1a074996c8c918480f5": (
        "单个决策周期按照“上下文更新—规则预检查—策略选择—机动推理—安全投影—命令合成—反馈记录”"
        "的顺序运行。攻击任务还必须显式处理目标丢失、授权撤销、协同窗口错失、毁伤评估和攻击后脱离等"
        "事件分支，其策略调用图与侦察—打击—评估—脱离时序如图5-4所示。"
    ),
    "block-7a3f7495e76b58c5e9a4c06f": (
        "层级执行距离描述全局阶段目标被局部执行器离散为首个航路点时的层级步长；目标较远而单次可执行"
        "步长较短时，该值可以很大，因而不能单独解释为策略误差或约束违反。方向一致性表示首执行航路点"
        "总体朝向阶段目标，目标进展量表示保持周期内平台与阶段目标的距离实际缩短。只有将三者与路径"
        "可达率、命令执行率、长时域到达率和安全屏障介入次数联合报告，才能区分策略选点、路径方向和分层"
        "步长差异。阶段目标点、全局路径、首执行航路点和控制量的分层关系如图5-5所示；当前记录只支持"
        "首个执行航路点，不据此宣称已保存完整规划路径。"
    ),
    "block-89d2310f11797a16664876b8": (
        "当失败码表明当前层仍有局部可行修复，且策略窗口累计优势未持续为负时，优先保持任务与承担关系"
        "不变。感知短时失效、武器窗口未开启、局部路径阻塞和单次目标点不可行均不得直接触发资源重分配"
        "或任务重分解。只有本层重试次数、等待时间或窗口优势损失超过实验阈值才逐级升级。各级可修改对象"
        "和必须保持的不变量如表5-7及图5-6所示。"
    ),
    "block-0b5808359e32714cff16b715": (
        "字段模式必须版本化，所有产物共享批次标识、运行标识、想定标识、方法标识和随机种子。摘要只能"
        "由原始日志计算，不能由界面状态或人工表格反向填充。任务内对象链、证据等级及其允许形成的主张"
        "边界如图5-7所示。"
    ),
    "block-8d692a6e4a5c8ca9f3fdc32d": (
        "图5-15依据已发布的三任务共享目标地图网络资产重绘。输入侧包括局部空间态势、可见实体序列、"
        "战术函数条件、时序历史和合法目标掩码；中间层分别执行空间编码、实体关系编码、条件编码与循环"
        "记忆，并在共享特征层形成逐平台分散决策；输出侧由64×64目标单元热力图、格内连续偏移和仅用于"
        "集中训练的价值头组成。部署阶段学习策略只形成阶段目标点，传感器、武器、平台分配和底层控制均"
        "不属于学习动作。该图证明5.6节网络结构已经落实为可版本化方法资产，不承担训练收敛或战术优越性"
        "证明；相关结论仍以不可变训练日志和独立评价记录为依据。"
    ),
}

HEADING_OVERRIDES = {
    "block-8234c499f57351b72fd75533": (3, "5.5.3 目标热力图与连续偏移"),
    "block-50c630da1d62951b2fff8c00": (3, "5.8.3 任务规划系统—对抗仿真环境接口"),
}

TABLE_REPLACEMENTS = {
    "block-cb3fa32e3f2934d9caf2f90e": [("武器授权", "武器释放许可")],
}

DATA_CAPTIONS = [CAPTION_UPDATES[key] for key in CAPTION_UPDATES]

FIGURES = [
    {
        "label": "图5-1",
        "caption": "第四章任务交接包向第五章任务策略集合的受约束映射",
        "document_id": "doc-4824bc951387",
        "revision": 1,
        "anchor_block_id": "block-4d0a3e71249d2e3715c146f3",
        "legacy_src": "ch5-task-policy-contract-v30.svg",
        "legacy_caption": "图5-1 任务交接—规则武器与学习机动双策略调度—命令执行总体结构",
    },
    {
        "label": "图5-2",
        "caption": "指挥授权、规则许可与武器释放的三重门控及撤销链",
        "document_id": "doc-234271a20a30",
        "revision": 2,
        "anchor_block_id": "block-077e50f89218ea64f626c385",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图5-3",
        "caption": "感知、火力与机动异构策略协同及动作所有权",
        "document_id": "doc-c48fcf07e342",
        "revision": 1,
        "anchor_block_id": "block-b49bb0b2a295f5f6b0efdf7d",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图5-4",
        "caption": "攻击任务的策略调用图与侦察—打击—评估—脱离时序",
        "document_id": "doc-37fadd114b5e",
        "revision": 1,
        "anchor_block_id": "block-380a552ae0903b5b3862f8e9",
        "legacy_src": "ch5-policy-sequence-v30.svg",
        "legacy_caption": "图5-2 任务内规则武器与学习机动调用时序",
    },
    {
        "label": "图5-5",
        "caption": "阶段目标点、路径、首执行航路点与控制量的分层转换",
        "document_id": "doc-bc4623c80f3a",
        "revision": 1,
        "anchor_block_id": "block-7a3f7495e76b58c5e9a4c06f",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图5-6",
        "caption": "任务内失败语义与L0—L3最小充分回退机制",
        "document_id": "doc-15709f444ead",
        "revision": 3,
        "anchor_block_id": "block-3577e53ca9b18c4a1e70adc4",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图5-7",
        "caption": "任务内规划执行证据链与证据等级—主张边界",
        "document_id": "doc-4f59cf50af20",
        "revision": 1,
        "anchor_block_id": "block-0b5808359e32714cff16b715",
        "legacy_src": "ch5-06-evidence-chain-v23.svg",
        "legacy_caption": "图5-6 任务内双策略规划的可追溯G2证据链",
    },
    {
        "label": "图5-15",
        "caption": "任务条件化共享机动网络结构与动作所有权",
        "document_id": "doc-ad24c36c8cad",
        "revision": 2,
        "anchor_block_id": "block-b5371eb9c0a5b24c4282fb15",
        "legacy_src": "ch5-shared-targetmap-network-evidence-v23.svg",
        "legacy_caption": "图5-11 三任务共享目标地图网络结构及实现证据插图",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(node: dict[str, Any]) -> str:
    return str(node.get("text") or "") + "".join(
        _text(child)
        for child in node.get("content") or []
        if isinstance(child, dict)
    )


def _search_text(block: dict[str, Any]) -> str:
    attrs = block.get("attrs") or {}
    return "\n".join(
        value
        for value in (
            _text(block),
            str(attrs.get("markdown") or ""),
            str(attrs.get("src") or ""),
            str(attrs.get("alt") or ""),
            str(attrs.get("title") or ""),
        )
        if value
    )


def _block_map(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str((block.get("attrs") or {}).get("blockId") or ""): block
        for block in (state.get("document") or {}).get("content") or []
        if (block.get("attrs") or {}).get("blockId")
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _heading(level: int, text: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _raw_caption(text: str) -> dict[str, Any]:
    return {"type": "rawMarkdown", "attrs": {"markdown": f"<center>{text}</center>"}}


def _chapter_bounds(state: dict[str, Any]) -> tuple[str, int, int]:
    blocks = (state.get("document") or {}).get("content") or []
    start = next(
        index
        for index, block in enumerate(blocks)
        if block.get("type") == "heading"
        and int((block.get("attrs") or {}).get("level") or 0) == 1
        and _text(block).strip() == CHAPTER_TITLE
    )
    end = next(
        index
        for index in range(start + 1, len(blocks))
        if blocks[index].get("type") == "heading"
        and int((blocks[index].get("attrs") or {}).get("level") or 0) == 1
    )
    return str((blocks[start].get("attrs") or {}).get("blockId") or ""), start, end


def _chapter_sha256(state: dict[str, Any]) -> str:
    _, start, end = _chapter_bounds(state)
    blocks = (state.get("document") or {}).get("content") or []
    payload = json.dumps(blocks[start:end], ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _current_figure_blocks(state: dict[str, Any], label: str) -> list[dict[str, Any]]:
    return [
        block
        for block in (state.get("document") or {}).get("content") or []
        if str((block.get("attrs") or {}).get("artifactLabel") or "") == label
        and str((block.get("attrs") or {}).get("artifactKind") or "")
        in {"figure", "figure-caption"}
    ]


def _legacy_block_ids(
    state: dict[str, Any], *, src_suffix: str, caption_text: str
) -> list[str]:
    if not src_suffix:
        return []
    blocks = (state.get("document") or {}).get("content") or []
    image_index = next(
        (
            index
            for index, block in enumerate(blocks)
            if block.get("type") == "image"
            and str((block.get("attrs") or {}).get("src") or "").endswith(src_suffix)
        ),
        None,
    )
    if image_index is None:
        return []
    ids = [str((blocks[image_index].get("attrs") or {}).get("blockId") or "")]
    if image_index + 1 < len(blocks):
        candidate = blocks[image_index + 1]
        if caption_text and caption_text in _search_text(candidate):
            ids.append(str((candidate.get("attrs") or {}).get("blockId") or ""))
    return [value for value in ids if value]


def _diagram_resource(project: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    resource = diagram_service.get(project, str(spec["document_id"]))
    diagram = resource.get("diagram") or {}
    document = resource.get("document") or {}
    expected_title = f"{spec['label']} {spec['caption']}"
    if document.get("status") != "active" or str(document.get("title") or "") != expected_title:
        raise DocumentWorkspaceError(f"绘图身份不匹配：{spec['document_id']}")
    if int(diagram.get("revision") or 0) != int(spec["revision"]):
        raise DocumentWorkspaceError(
            f"{spec['label']}修订不匹配：当前{diagram.get('revision')}，预期{spec['revision']}"
        )
    return resource


def _strip_top_identity(node: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(node)
    attrs = dict(result.get("attrs") or {})
    attrs.pop("blockId", None)
    attrs.pop("blockRevision", None)
    if attrs:
        result["attrs"] = attrs
    else:
        result.pop("attrs", None)
    return result


def _transform_string(value: str) -> str:
    def renumber(match: re.Match[str]) -> str:
        old = int(match.group(1))
        return f"图5-{FIGURE_NUMBER_MAP.get(old, old)}"

    value = re.sub(r"图5-(\d+)", renumber, value)
    for old, new in TERM_REPLACEMENTS:
        value = value.replace(old, new)
    return value


def _transform_node(block: dict[str, Any], block_id: str) -> dict[str, Any]:
    node = _strip_top_identity(block)

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "text" and isinstance(item, str):
                result[key] = _transform_string(item)
            elif key == "markdown" and isinstance(item, str):
                result[key] = _transform_string(item)
            else:
                result[key] = visit(item)
        return result

    node = visit(node)
    if block_id in TABLE_REPLACEMENTS:
        table_replacements = TABLE_REPLACEMENTS[block_id]

        def replace_table(value: Any) -> Any:
            if isinstance(value, list):
                return [replace_table(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_table(item) for key, item in value.items()}
            if isinstance(value, str):
                for old, new in table_replacements:
                    value = value.replace(old, new)
            return value

        node = replace_table(node)
    if block_id in CAPTION_UPDATES:
        node = _raw_caption(CAPTION_UPDATES[block_id])
    if block_id in PARAGRAPH_OVERRIDES:
        node = _paragraph(PARAGRAPH_OVERRIDES[block_id])
    if block_id in HEADING_OVERRIDES:
        level, text = HEADING_OVERRIDES[block_id]
        node = _heading(level, text)
    return node


def _preflight(project: dict[str, Any]) -> dict[str, Any]:
    record = multi_document_service.get_document(project, TARGET_DOCUMENT_ID)
    if not record.get("is_primary") or record.get("edit_policy") != "editable":
        raise DocumentWorkspaceError("目标必须是当前可编辑主文档")
    if str((record.get("lineage") or {}).get("parent_document_id") or "") != PARENT_DOCUMENT_ID:
        raise DocumentWorkspaceError("目标文档继承关系已变化，停止发布")
    parent = multi_document_service.get_document(project, PARENT_DOCUMENT_ID)
    if parent.get("edit_policy") != "read_only":
        raise DocumentWorkspaceError("父文档不再是只读历史版本，停止发布")

    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)
    full_sha = writing_collaboration_service.codec.document_sha256(state["document"])
    chapter_sha = _chapter_sha256(state)
    if int(state.get("document_revision") or 0) != EXPECTED_BASE_REVISION:
        raise DocumentWorkspaceError(
            f"正文修订已变化：当前{state.get('document_revision')}，预期{EXPECTED_BASE_REVISION}"
        )
    if full_sha != EXPECTED_BASE_SHA256 or chapter_sha != EXPECTED_CHAPTER_SHA256:
        raise DocumentWorkspaceError("正文或第五章内容哈希已变化，停止发布")
    if str((state.get("projection") or {}).get("status") or "") != "current":
        raise DocumentWorkspaceError("Markdown投影不是current，停止发布")

    chapter_id, start, end = _chapter_bounds(state)
    blocks = _block_map(state)
    required = {
        *(str(spec["anchor_block_id"]) for spec in FIGURES),
        *CAPTION_UPDATES.keys(),
        *PARAGRAPH_OVERRIDES.keys(),
        *HEADING_OVERRIDES.keys(),
        *TABLE_REPLACEMENTS.keys(),
    }
    missing = sorted(required - set(blocks))
    if missing:
        raise DocumentWorkspaceError("第五章稳定块缺失：" + "、".join(missing))
    diagrams = [_diagram_resource(project, spec) for spec in FIGURES]
    return {
        "record": record,
        "parent": parent,
        "state": state,
        "chapter_id": chapter_id,
        "chapter_start": start,
        "chapter_end": end,
        "content_sha256": full_sha,
        "chapter_sha256": chapter_sha,
        "diagrams": diagrams,
        "legacy_replacements": {
            str(spec["label"]): _legacy_block_ids(
                state,
                src_suffix=str(spec["legacy_src"]),
                caption_text=str(spec["legacy_caption"]),
            )
            for spec in FIGURES
        },
    }


def _backup(project: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    state = preflight["state"]
    document_root = multi_document_service._document_root(project, TARGET_DOCUMENT_ID)  # noqa: SLF001
    backup_name = f"chapter5-stage2-before-r{EXPECTED_BASE_REVISION:06d}"
    roots = [
        document_root / "backups" / backup_name,
        STAGE2_ROOT / "backups" / backup_name,
    ]
    manifest = {
        "created_at": _now(),
        "project_id": PROJECT_ID,
        "target_document_id": TARGET_DOCUMENT_ID,
        "parent_document_id": PARENT_DOCUMENT_ID,
        "document_revision": state["document_revision"],
        "content_sha256": preflight["content_sha256"],
        "chapter_sha256": preflight["chapter_sha256"],
        "projection": state.get("projection") or {},
        "diagram_revisions": {
            str(spec["document_id"]): int(spec["revision"]) for spec in FIGURES
        },
    }
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        for name, value in {
            "structured-state.json": state,
            "document-record.json": preflight["record"],
            "parent-document-record.json": preflight["parent"],
            "backup-manifest.json": manifest,
        }.items():
            path = root / name
            if not path.exists():
                path.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
        for relative in ("source/document.md", "working/document.md", "manifest.json"):
            source = document_root / relative
            target = root / relative.replace("/", "-")
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
        index = multi_document_service._index_path(project)  # noqa: SLF001
        if index.is_file() and not (root / "documents.json").exists():
            shutil.copy2(index, root / "documents.json")
    return {
        "document_backup": str(roots[0]),
        "stage_backup": str(roots[1]),
        "manifest": manifest,
    }


def _update_textual_blocks(
    project: dict[str, Any], chapter_id: str
) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID, chapter_id)
    operations: list[dict[str, Any]] = []
    changed_ids: list[str] = []
    textual_types = {
        "paragraph",
        "heading",
        "table",
        "codeBlock",
        "orderedList",
        "bulletList",
        "rawMarkdown",
    }
    for block in (state.get("document") or {}).get("content") or []:
        if block.get("type") not in textual_types:
            continue
        attrs = block.get("attrs") or {}
        block_id = str(attrs.get("blockId") or "")
        transformed = _transform_node(block, block_id)
        if transformed == _strip_top_identity(block):
            continue
        operations.append(
            {
                "op": "replace",
                "block_id": block_id,
                "expected_block_revision": int(attrs.get("blockRevision") or 1),
                "node": transformed,
            }
        )
        changed_ids.append(block_id)
    if not operations:
        return {"skipped": True, "changed_block_ids": []}
    result = writing_collaboration_service.patch_draft(
        project,
        TARGET_DOCUMENT_ID,
        {
            "section_id": chapter_id,
            "expected_revision": state["document_revision"],
            "client_change_id": "thesis-v34-ch5-prose-captions-renumber-v1",
            "operations": operations,
        },
        ACTOR,
    )
    return {
        "skipped": False,
        "changed_block_ids": changed_ids,
        "changed_block_count": len(changed_ids),
        "document_revision": result.get("document_revision"),
        "projection": result.get("projection"),
    }


def _publish_figure(
    project: dict[str, Any], chapter_id: str, spec: dict[str, Any]
) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID, chapter_id)
    current = _current_figure_blocks(state, str(spec["label"]))
    revision_marker = f"{spec['document_id']}-r{spec['revision']}-"
    current_image = next((block for block in current if block.get("type") == "image"), None)
    if current_image and revision_marker in str((current_image.get("attrs") or {}).get("src") or ""):
        return {"label": spec["label"], "skipped": True, "reason": "already published"}

    block_ids = set(_block_map(state))
    replacements = _legacy_block_ids(
        state,
        src_suffix=str(spec["legacy_src"]),
        caption_text=str(spec["legacy_caption"]),
    )
    replacements.extend(
        str((block.get("attrs") or {}).get("blockId") or "") for block in current
    )
    replacements = [value for value in dict.fromkeys(replacements) if value in block_ids]
    result = diagram_service.publish_to_document(
        project,
        str(spec["document_id"]),
        {
            "target_document_id": TARGET_DOCUMENT_ID,
            "target_section_id": chapter_id,
            "expected_document_revision": state["document_revision"],
            "expected_diagram_revision": int(spec["revision"]),
            "anchor_block_id": str(spec["anchor_block_id"]),
            "replace_block_ids": replacements,
            "figure_label": str(spec["label"]),
            "caption": str(spec["caption"]),
            "width": "145mm",
            "export_format": "svg",
            "client_change_id": (
                f"thesis-v34-ch5-{str(spec['label']).replace('图', 'figure-')}-"
                f"r{spec['revision']}-stage2"
            ),
        },
        ACTOR,
    )
    return {
        "label": spec["label"],
        "skipped": False,
        "diagram_revision": result.get("diagram_revision"),
        "document_revision": result.get("document_revision"),
        "inserted_block_ids": result.get("inserted_block_ids") or [],
        "asset": result.get("asset") or {},
        "reference": result.get("reference") or {},
        "replaced_block_ids": replacements,
    }


def _verification(project: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID, chapter_id)
    blocks = (state.get("document") or {}).get("content") or []
    searchable = "\n".join(_search_text(block) for block in blocks)
    labels: dict[str, Any] = {}
    for spec in FIGURES:
        figure_blocks = _current_figure_blocks(state, str(spec["label"]))
        image = next((block for block in figure_blocks if block.get("type") == "image"), None)
        caption = next(
            (
                block
                for block in figure_blocks
                if str((block.get("attrs") or {}).get("artifactKind") or "")
                == "figure-caption"
            ),
            None,
        )
        references = [
            row
            for row in diagram_service.list_references(project, str(spec["document_id"]))
            if row.get("target_document_id") == TARGET_DOCUMENT_ID
            and row.get("target_section_id") == chapter_id
            and int(row.get("diagram_revision") or 0) == int(spec["revision"])
        ]
        labels[str(spec["label"])] = {
            "image_block_id": (image.get("attrs") or {}).get("blockId") if image else "",
            "image_src": (image.get("attrs") or {}).get("src") if image else "",
            "caption_block_id": (caption.get("attrs") or {}).get("blockId") if caption else "",
            "caption_text": _text(caption).strip() if caption else "",
            "current_reference_count": sum(
                1 for row in references if row.get("status") == "current"
            ),
            "reference_formats": [row.get("export_format") for row in references],
        }
    raw_captions = [
        str((block.get("attrs") or {}).get("markdown") or "")
        for block in blocks
        if block.get("type") == "rawMarkdown"
        and "图5-" in str((block.get("attrs") or {}).get("markdown") or "")
    ]
    all_caption_numbers = sorted(
        int(value)
        for value in re.findall(r"图5-(\d+)", "\n".join(raw_captions + [
            _text(block)
            for block in blocks
            if str((block.get("attrs") or {}).get("artifactKind") or "") == "figure-caption"
        ]))
    )
    return {
        "document_revision": state.get("document_revision"),
        "content_sha256": writing_collaboration_service.codec.document_sha256(
            writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)["document"]
        ),
        "projection": state.get("projection") or {},
        "labels": labels,
        "caption_numbers": all_caption_numbers,
        "data_caption_checks": {
            caption: f"<center>{caption}</center>" in raw_captions for caption in DATA_CAPTIONS
        },
        "old_assets_still_referenced": {
            str(spec["legacy_src"]): str(spec["legacy_src"]) in searchable
            for spec in FIGURES
            if spec["legacy_src"]
        },
        "forbidden_development_terms": {
            term: term in searchable
            for term in (
                "3021",
                "5130",
                "localhost",
                "AI Planning",
                "Wargame",
                "Target Move",
                "Target-Move",
                "FireAllocationAgent",
            )
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    preflight = _preflight(project)
    base_report = {
        "stage": 2,
        "mode": "preflight" if args.preflight else "apply",
        "checked_at": _now(),
        "project_id": PROJECT_ID,
        "target_document_id": TARGET_DOCUMENT_ID,
        "parent_document_id": PARENT_DOCUMENT_ID,
        "document_revision": preflight["state"]["document_revision"],
        "content_sha256": preflight["content_sha256"],
        "chapter_sha256": preflight["chapter_sha256"],
        "chapter_id": preflight["chapter_id"],
        "legacy_replacements": preflight["legacy_replacements"],
        "diagram_revisions": {
            str(spec["label"]): {
                "document_id": spec["document_id"],
                "revision": spec["revision"],
            }
            for spec in FIGURES
        },
    }
    if args.preflight:
        print(json.dumps(base_report, ensure_ascii=False, indent=2))
        return

    STAGE2_ROOT.mkdir(parents=True, exist_ok=True)
    report = {**base_report, "started_at": _now()}
    try:
        report["backup"] = _backup(project, preflight)
        report["textual_update"] = _update_textual_blocks(project, preflight["chapter_id"])
        report["publications"] = [
            _publish_figure(project, preflight["chapter_id"], spec)
            for spec in FIGURES
        ]
        report["verification"] = _verification(project, preflight["chapter_id"])
        checks = report["verification"]
        if any(checks["old_assets_still_referenced"].values()):
            raise DocumentWorkspaceError("旧结构图仍被第五章引用")
        if any(checks["forbidden_development_terms"].values()):
            raise DocumentWorkspaceError("第五章仍出现开发环境标识")
        if checks["caption_numbers"] != list(range(1, 22)):
            raise DocumentWorkspaceError(
                f"第五章图号不连续：{checks['caption_numbers']}"
            )
        if not all(checks["data_caption_checks"].values()):
            raise DocumentWorkspaceError("数据图题注更新验证失败")
        for spec in FIGURES:
            label = str(spec["label"])
            current = checks["labels"][label]
            if not current["image_block_id"] or current["caption_text"] != f"{label} {spec['caption']}":
                raise DocumentWorkspaceError(f"{label}正文发布验证失败")
            if current["current_reference_count"] != 1:
                raise DocumentWorkspaceError(f"{label}当前结构化引用数量不是1")
        report["status"] = "completed"
        report["completed_at"] = _now()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["failed_at"] = _now()
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        raise

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
