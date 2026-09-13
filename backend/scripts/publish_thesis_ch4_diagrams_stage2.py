"""Publish seven reviewed Chapter 4 diagrams into the current thesis.

Publication is guarded by the editable-primary lineage, the full-document and
Chapter 4 hashes, stable anchor blocks, and fixed structured-diagram revisions.
A rollback snapshot is written before the first body mutation.
"""

from __future__ import annotations

import argparse
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
PARENT_DOCUMENT_ID = "doc-15def56e2401"
EXPECTED_BASE_REVISION = 45
EXPECTED_BASE_SHA256 = "d7b80daef5dcd86d1f509cb3df2d1c8abf48669d11c7dd6182f430b86b0b9d23"
EXPECTED_CHAPTER_SHA256 = "5a3b5b08cee38698cfc76063fdf7f802bf68b7b34fe021a678e4a018d89654e5"
ACTOR = "thesis-ch4-diagram-stage2"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第四章配图"
STAGE2_ROOT = OUTPUT_ROOT / "07-stage2"
REPORT_PATH = STAGE2_ROOT / "chapter4-stage2-publish-report.json"

CHAPTER_TITLE = "第4章 任务分解与任务分配方法"

PARAGRAPH_UPDATES = {
    "block-b3e698e07ab0d4151d61e928": (
        "图4-1给出了指挥意图、全局评价状态和战术知识向任务需求的语义映射。经确认的任务目的、"
        "期望效果、优先级与风险边界同敌我兵力、关键地域、多任务链关系及不确定性共同进入语义解释；"
        "任务模板、能力条件与协同规则用于形成标准任务节点、关系边和兵力资源需求。每个输出对象均"
        "保留意图来源、评价状态版本、约束依据与解释链，模型只执行映射和校核，不新增任务目的或"
        "行动授权。"
    ),
    "block-848fe3aaf187689380df6e1f": (
        "为直观展示多任务链耦合关系，图4-2将两条目标处置链、态势塑造链和共享支撑任务置于同一"
        "任务网络。目标处置链按照发现定位、持续确认、合法性与授权复核、任务作用和效果评估形成"
        "功能闭合；态势塑造链通过关键地域侦察、机动部署、区域控制和条件更新创造后续行动条件。"
        "通信中继、数据融合、导航授时、补给保障与预备兵力作为可被多条链共享的独立任务节点，"
        "避免把空间塑造和体系支撑压缩为单一目标链的附属步骤。"
    ),
    "block-ea3a352696829041aed2b295": (
        "单目标任务分解从末端任务效果出发，结合目标属性、评价状态与资源边界，逆向确定持续确认、"
        "搜索发现及必要支撑环节。该过程用于说明局部目标链的因果构造，不代表多目标条件下各任务链"
        "相互独立；链间共享、冲突和态势塑造关系将在后续候选任务图合成与比较阶段统一处理。"
    ),
    "block-b9b291388e5a6ae23a7bb95c": (
        "逆向展开首先校核末端效果所要求的任务类型、作用对象、时间窗与能力需求，再逐级补充前置任务"
        "和通信保障等支撑条件。每一步均继承上位授权、风险和区域边界，并将成立条件写入任务节点与"
        "关系边；若必要条件不能满足，则输出结构不可行原因，而不是以默认节点补齐任务链。"
    ),
    "block-c917f7ba6c923d581fdddb15": (
        "因此，单目标分解的核心不是枚举任务名称，而是构造可解释、可校核且能够与其他任务链合并的"
        "局部偏序结构。该结构为多目标耦合、共享支撑识别和HTN候选方法比较提供基本单元，但最终任务图"
        "仍需在共同评价状态和全局反事实基线上进行选择。"
    ),
    "block-3b3b22771d4e244f82dc5826": (
        "候选方法既可以形成直接目标处置链，也可以先生成关键位置争夺、共享中继、攻击阵位或预备兵力"
        "等态势塑造任务；既可以为每个目标建立独立支撑，也可以构造支撑多条任务链的共享节点。HTN"
        "依据方法前置条件生成可解释的候选任务结构，硬约束校核剔除语义、授权、时序、资源或风险不满足"
        "的候选，剩余结构再在同一反事实基线上比较全局贡献，形成选定任务图并保留备选与淘汰原因，"
        "如图4-3所示。"
    ),
    "block-ac2d4fbdd679de613324fa24": (
        "各因子分别表示平台存活、类型适配、粗粒度可达、时间窗、资源、风险、任务级区域和行动权限"
        "约束是否满足。其中，行动权限因子只核验既有授权记录是否存在、是否覆盖相应任务类型、对象、"
        "区域和时段，不由算法自行授予或扩大权限。任一因子为0时，强制"
    ),
    "block-0f70c917c72c6d81d48505fe": (
        "门控后形成候选平台集合。若候选集合为空、聚合能力不能覆盖任务需求，或候选兵力无法在任务"
        "时间窗内形成所要求的部署关系，则生成不可行状态并停止评分。硬约束门控先于启发式排序和全局"
        "价值比较；高匹配分不能补偿不可达、越权或风险超限，技术可行性也不等同于指挥主体已经批准行动。"
    ),
    "block-01a078dbad97c390bbcd36b4": (
        "上述约束共同保证资源配置在能力、数量、时间、空间、共享链路、体系韧性和资源消耗方面可执行，"
        "并保持任务图的依赖语义[49][64][70][72-73]。约束从经确认的任务目的、交战规则、授权范围和"
        "总体风险边界向任务节点、HTN候选结构及MARTA资源配置逐层继承；下层可以增加更严格的结构或"
        "资源条件，但不得删除、放宽或越权解释上位硬约束，其分层校核关系如图4-4所示。"
    ),
    "block-0e5952885d1765de9c3d9334": (
        "MARTA由任务图与结构贡献、全局评价状态、可用兵力资源和约束授权范围共同驱动，依次执行硬约束"
        "门控、候选兵力组合构造、局部启发式筛选、全局反事实评价、约束优化与一致性校核，并输出承担"
        "矩阵、平台角色、任务级部署区域、资源预算和替补集合，如图4-5所示。"
    ),
    "block-a459e16028df9ac557aabeaf": (
        "图4-5强调局部启发式与最终方案评价的职责分离。能力、距离、忙闲和类型适配等局部评分只用于"
        "压缩候选空间；最终选择依据是候选配置相对于共同基线造成的兵力价值、位置环境价值、多任务链"
        "关系和体系韧性变化。关键任务无可行候选或候选组合不能形成规定部署时，模型显式输出受影响"
        "任务、违反约束及建议返回层级，进入4.7节的反馈修正过程。"
    ),
    "block-89df0fa0e9644e5dfa7e5b7f": (
        "耦合迭代不是无条件追求可分配，而是在保持任务语义、上位授权和全局盘面价值的前提下消除"
        "任务结构与兵力配置之间的不一致。能力缺口、时序冲突、资源碰撞和区域不可行优先在MARTA层"
        "实施平台替换、时间调整、预算重分或任务级区域修正；只有任务链断裂、意图覆盖不足或关键态势"
        "目标失效时，才返回HTN重构并在必要时上报指挥层。每轮均保存失败类型、修正范围和评价记录，"
        "不得伪造承担关系或以局部收益抵消硬约束，其最小充分修正机制如图4-6所示。"
    ),
    "block-22e1fbfee4dc07e508a6f1dd": (
        "任务图闭合、关键任务能力覆盖、关键地域与多任务链部署条件、角色冲突、预备兵力和资源预算等"
        "校核只形成技术候选方案。交接第5章之前，指挥主体还必须依据经确认的任务目的、交战规则和授权"
        "边界，审查意图一致性、目标合法性、风险接受范围与责任归属，并对方案作出批准、限定修改或拒绝"
        "决定。只有批准并形成授权记录的方案方可进入第5章；修改方案返回相应HTN或MARTA层复审，拒绝"
        "方案不得进入执行链。技术可行性与全局价值评价不自动构成行动授权，人工审查与交接门如图4-7"
        "所示。第五章只能在批准的任务语义和连续可行域内组织策略与阶段目标点，不得自行改变承担关系、"
        "任务级区域或任务链结构。"
    ),
}

FIGURES = [
    {
        "label": "图4-1",
        "caption": "指挥意图、全局态势与任务需求的语义映射",
        "document_id": "doc-eada07b171bb",
        "revision": 1,
        "anchor_block_id": "block-b3e698e07ab0d4151d61e928",
        "legacy_src": "ch4-mission-input-structure-v23.svg",
        "legacy_caption": "图4-1 任务输入属性结构图",
    },
    {
        "label": "图4-2",
        "caption": "目标处置链、态势塑造链与共享支撑任务网络",
        "document_id": "doc-6ed5e6d27e61",
        "revision": 1,
        "anchor_block_id": "block-848fe3aaf187689380df6e1f",
        "legacy_src": "ch4-kill-chain-task-mapping-v27.svg",
        "legacy_caption": "图4-2 杀伤链阶段与任务类型映射关系图",
    },
    {
        "label": "图4-3",
        "caption": "HTN候选任务结构的生成、剪枝与全局选择",
        "document_id": "doc-11616fa4df0c",
        "revision": 1,
        "anchor_block_id": "block-3b3b22771d4e244f82dc5826",
        "legacy_src": "ch4-reverse-task-decomposition-v23.svg",
        "legacy_caption": "图4-3 基于杀伤链的逆向任务分解计算流程",
    },
    {
        "label": "图4-4",
        "caption": "任务约束的继承、分层校核与不可越权关系",
        "document_id": "doc-3608a8ce12c9",
        "revision": 1,
        "anchor_block_id": "block-01a078dbad97c390bbcd36b4",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图4-5",
        "caption": "全局态势价值约束下的MARTA兵力与资源分配结构",
        "document_id": "doc-7f6f6f18e9a1",
        "revision": 2,
        "anchor_block_id": "block-0e5952885d1765de9c3d9334",
        "legacy_src": "ch4-marta-allocation-model-v27.svg",
        "legacy_caption": "图4-4 全局态势价值约束下的MARTA兵力与资源分配结构",
    },
    {
        "label": "图4-6",
        "caption": "分解—分配失败反馈与最小充分修正机制",
        "document_id": "doc-bc894c778dca",
        "revision": 2,
        "anchor_block_id": "block-89df0fa0e9644e5dfa7e5b7f",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图4-7",
        "caption": "候选任务—兵力方案的人工审查、授权与交接门",
        "document_id": "doc-b7e6d48bb6e9",
        "revision": 2,
        "anchor_block_id": "block-22e1fbfee4dc07e508a6f1dd",
        "legacy_src": "",
        "legacy_caption": "",
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
    chapter_id = str((blocks[start].get("attrs") or {}).get("blockId") or "")
    return chapter_id, start, end


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
        raise DocumentWorkspaceError("正文或第四章内容哈希已变化，停止发布")
    if str((state.get("projection") or {}).get("status") or "") != "current":
        raise DocumentWorkspaceError("Markdown投影不是current，停止发布")

    chapter_id, _, _ = _chapter_bounds(state)
    blocks = _block_map(state)
    required = {
        *(str(spec["anchor_block_id"]) for spec in FIGURES),
        *PARAGRAPH_UPDATES.keys(),
    }
    missing = sorted(required - set(blocks))
    if missing:
        raise DocumentWorkspaceError("第四章稳定块缺失：" + "、".join(missing))
    diagrams = [_diagram_resource(project, spec) for spec in FIGURES]
    return {
        "record": record,
        "parent": parent,
        "state": state,
        "chapter_id": chapter_id,
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
    backup_name = f"chapter4-stage2-before-r{EXPECTED_BASE_REVISION:06d}"
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


def _replace_paragraph(
    project: dict[str, Any], chapter_id: str, block_id: str, text: str
) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID, chapter_id)
    block = _block_map(state).get(block_id)
    if not block:
        raise DocumentWorkspaceError(f"承接段落不存在：{block_id}")
    if _text(block).strip() == text:
        return {"block_id": block_id, "skipped": True}
    result = writing_collaboration_service.patch_draft(
        project,
        TARGET_DOCUMENT_ID,
        {
            "section_id": chapter_id,
            "expected_revision": state["document_revision"],
            "client_change_id": f"thesis-v34-ch4-paragraph-{block_id}-v1",
            "operations": [
                {
                    "op": "replace",
                    "block_id": block_id,
                    "expected_block_revision": int(
                        (block.get("attrs") or {}).get("blockRevision") or 1
                    ),
                    "node": _paragraph(text),
                }
            ],
        },
        ACTOR,
    )
    return {
        "block_id": block_id,
        "skipped": False,
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
                f"thesis-v34-ch4-{str(spec['label']).replace('图', 'figure-')}-"
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
    return {
        "document_revision": state.get("document_revision"),
        "content_sha256": writing_collaboration_service.codec.document_sha256(
            writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)["document"]
        ),
        "projection": state.get("projection") or {},
        "labels": labels,
        "old_assets_still_referenced": {
            str(spec["legacy_src"]): str(spec["legacy_src"]) in searchable
            for spec in FIGURES
            if spec["legacy_src"]
        },
        "paragraph_checks": {
            block_id: _text(_block_map(state).get(block_id) or {}).strip() == expected
            for block_id, expected in PARAGRAPH_UPDATES.items()
        },
        "forbidden_development_terms": {
            term: term in searchable
            for term in ("3021", "5130", "localhost", "document_id", "revision-")
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
        report["paragraph_updates"] = [
            _replace_paragraph(project, preflight["chapter_id"], block_id, text)
            for block_id, text in PARAGRAPH_UPDATES.items()
        ]
        report["publications"] = [
            _publish_figure(project, preflight["chapter_id"], spec)
            for spec in FIGURES
        ]
        report["verification"] = _verification(project, preflight["chapter_id"])
        checks = report["verification"]
        if not all(checks["paragraph_checks"].values()):
            raise DocumentWorkspaceError("段落更新验证失败")
        if any(checks["old_assets_still_referenced"].values()):
            raise DocumentWorkspaceError("旧图仍被第四章引用")
        if any(checks["forbidden_development_terms"].values()):
            raise DocumentWorkspaceError("第四章出现开发环境标识")
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
