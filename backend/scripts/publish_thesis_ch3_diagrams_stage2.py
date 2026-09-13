"""Publish seven reviewed Chapter 3 diagrams into the current thesis.

Publication is guarded by the editable-primary lineage, the full-document and
Chapter 3 hashes, stable anchor blocks, and fixed structured-diagram revisions.
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
EXPECTED_BASE_REVISION = 30
EXPECTED_BASE_SHA256 = "ee9c027c6d9b3d73352092d53fbc9750992babbec60b36910cec6450f97f6096"
EXPECTED_CHAPTER_SHA256 = "790eea8636d2927b8e34f8875b182b73dc3c412de49398040e2e3acba66323bf"
ACTOR = "thesis-ch3-diagram-stage2"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第三章配图"
STAGE2_ROOT = OUTPUT_ROOT / "07-stage2"
REPORT_PATH = STAGE2_ROOT / "chapter3-stage2-publish-report.json"

CHAPTER_TITLE = "第3章 海上无人集群协同任务规划总体模型"

PARAGRAPH_UPDATES = {
    "block-98ed57a137c997704e958f7a": (
        "图3-1给出了海上无人集群协同任务规划的统一总体模型。任务输入与执行证据在统一标识、"
        "坐标、时钟和规则版本下形成全局评价状态，统一目标函数与分层硬约束共同限定规划可行域；"
        "在此基础上，模型生成由任务图、兵力承担关系、任务内策略、阶段目标点、路径时序和修复标记"
        "构成的统一规划解。执行轨迹、裁决事件和资源消耗回写同一评价状态，使方案比较、责任追溯"
        "与分级修复建立在一致的作战态势基准上。"
    ),
    "block-6116f8919036414e948ea847": (
        "执行层持续回传实际位置、资源消耗、链路状态、裁决事件和局部风险，形成新的多源观测 O_t；"
        "观测经信念更新与状态映射，形成面向红蓝兵力、空间位置、多杀伤链、认知不确定性和组织复杂度"
        "的全局评价状态 X_t。作战对象、体系关系、环境规则、任务语义与一致性基准共同参与这一形成"
        "过程，如图3-2所示。由此建立“观测—信念—评价状态—全局价值与优势场—规划—执行—再观测”"
        "的闭环，避免兵力机动仅围绕单一目标或单条杀伤链进行局部优化。"
    ),
    "block-f0b3cabf062cc56784ef6d16": (
        "路径集合 P_t 与执行时序 Σ_t 共同构成带时间信息的平台参考轨迹；修复标记 Γ_t 则记录策略重试、"
        "目标点重采样、任务内策略调整、资源重配或任务结构重构等返回层级。每个目标点同时关联评价状态、"
        "空间边际价值、约束投影结果和替代候选，使在线决策、执行结果与后续验证使用同一评价依据。"
        "统一规划解的构成及其向第4章任务分解与分配、第5章策略强化与执行、第6章仿真验证与评价的衔接"
        "关系如图3-3所示。"
    ),
    "block-4c5d5b04d4507d6ae85c3d7f": (
        "总体约束按职责分为三层。A2层约束任务效果、风险边界、交战规则、人工确认、任务阶段和关键任务链"
        "连续性，保证战术意图与授权合法；A1层约束平台能力、资源预算、兵力覆盖、组织拓扑、策略前置、"
        "资源互斥与协同负担，保证任务结构和兵力承担可行；A0层约束环境威胁、禁航区域、通信保持、可达性、"
        "避碰、同步、规则复核与动力学，保证行动执行安全。三层硬约束在同一权威基准下联合门控：通过者"
        "进入可行规划域 Π_feasible，未通过者必须返回受影响对象、违反约束、责任层和修复层级，而不能"
        "以局部收益抵消硬约束，如图3-4所示。"
    ),
    "block-327415a9f6954a4b6f5028da": (
        "总体模型按照权责边界划分为A2战术意图与人机协同层、A1任务规划与方案生成层和A0策略执行与"
        "控制层。A2确定任务效果、风险偏好与授权边界，模型只提供候选比较和解释，不替代指挥员最终决心；"
        "A1形成可比较、可批准、可追溯的统一规划解，不直接生成平台姿态或控制量；A0完成规则复核、安全"
        "路径和局部调整，且不得擅自改变任务语义。A2—A0回答“由谁决定什么”，L0—L3回答扰动后“需要"
        "返回多高层修复”，两套分层相互正交。控制向下传递、证据向上回流的权责边界如图3-5所示。"
    ),
    "block-f9474114be35884d83e761a3": (
        "该闭环表明，信息更新、指挥控制与评价证据在任务执行过程中持续耦合。执行反馈不仅服务于局部控制，"
        "还通过兵力位置、多杀伤链状态、信念熵、全局态势价值、空间优势场和组织熵指数影响上层规划。"
        "任务输入与统一规划解形成控制流，多源观测、信念状态和评价状态形成信息流，执行轨迹、评价记录、"
        "失败语义和分级修复形成证据流；三类流均使用同一权威帧、规则版本和对象标识，以支持评价校准、"
        "方案比较和责任追溯，如图3-6所示。"
    ),
    "block-0f45e900ad842daa39bb6250": (
        "海上无人集群任务规划由任务执行前的预先规划和执行过程中的临机规划共同构成。预先规划依据任务意图、"
        "敌我态势、环境条件和资源边界形成初始方案与评价基线，经人工审核与授权后进入执行；执行监控持续"
        "比较实际盘面与规划盘面，并以信念、资源、多杀伤链、优势场、全局价值和组织熵指数的变化度量扰动。"
        "当扰动满足进入阈值、退出阈值和最短持续时间条件时，体系分别实施L0执行局部修复、L1任务内策略修复、"
        "L2资源重配或L3任务结构重构；涉及授权或意图变化的离散事件单独提交审查。预先规划、执行监控与分级"
        "重规划机制如图3-7所示。"
    ),
}

FIGURES = [
    {
        "label": "图3-1",
        "caption": "海上无人集群协同任务规划统一总体模型",
        "document_id": "doc-e0d8e261bc3f",
        "revision": 2,
        "anchor_block_id": "block-98ed57a137c997704e958f7a",
        "legacy_src": "ch3-unified-planning-model-v27.svg",
        "legacy_caption": "图3-1 海上无人集群任务规划统一总体模型",
    },
    {
        "label": "图3-2",
        "caption": "作战对象、观测信念与全局评价状态的形成关系",
        "document_id": "doc-2ae9d147887a",
        "revision": 2,
        "anchor_block_id": "block-6116f8919036414e948ea847",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图3-3",
        "caption": "统一规划解的构成及其章节衔接关系",
        "document_id": "doc-cf2e3fcea68a",
        "revision": 1,
        "anchor_block_id": "block-f0b3cabf062cc56784ef6d16",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图3-4",
        "caption": "分层约束体系、责任边界与可行域门控",
        "document_id": "doc-aaa7d48041b9",
        "revision": 3,
        "anchor_block_id": "block-4c5d5b04d4507d6ae85c3d7f",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图3-5",
        "caption": "指挥控制、任务规划与执行控制的权责边界",
        "document_id": "doc-bf44aa036266",
        "revision": 2,
        "anchor_block_id": "block-327415a9f6954a4b6f5028da",
        "legacy_src": "ch3-c2-system-architecture-v27.svg",
        "legacy_caption": "图3-2 海上无人集群作战体系结构与多流耦合关系图",
    },
    {
        "label": "图3-6",
        "caption": "海上无人集群任务规划的信息流、控制流与证据反馈闭环",
        "document_id": "doc-1c3f035db473",
        "revision": 2,
        "anchor_block_id": "block-f9474114be35884d83e761a3",
        "legacy_src": "ch3-information-control-loop-v24.svg",
        "legacy_caption": "图3-3 海上无人集群任务规划信息—控制—评价闭环",
    },
    {
        "label": "图3-7",
        "caption": "预先规划、执行监控与分级重规划机制",
        "document_id": "doc-9a7cfb86a66d",
        "revision": 3,
        "anchor_block_id": "block-0f45e900ad842daa39bb6250",
        "legacy_src": "ch3-preplanned-dynamic-replanning-v24.svg",
        "legacy_caption": "图3-4 海上无人集群任务规划运行机制图",
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
        raise DocumentWorkspaceError("正文或第三章内容哈希已变化，停止发布")
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
        raise DocumentWorkspaceError("第三章稳定块缺失：" + "、".join(missing))
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
    backup_name = f"chapter3-stage2-before-r{EXPECTED_BASE_REVISION:06d}"
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
            "client_change_id": f"thesis-v34-ch3-paragraph-{block_id}-v1",
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
                f"thesis-v34-ch3-{str(spec['label']).replace('图', 'figure-')}-"
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
            raise DocumentWorkspaceError("旧图仍被第三章引用")
        if any(checks["forbidden_development_terms"].values()):
            raise DocumentWorkspaceError("第三章出现开发环境标识")
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
