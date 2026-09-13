"""Publish the five reviewed Chapter 2 diagrams into the current thesis.

The script is deliberately guarded by the current primary-document lineage,
document revision, content hash, stable block ids, and fixed diagram revisions.
It creates a rollback snapshot before the first body mutation.
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
EXPECTED_BASE_REVISION = 21
EXPECTED_BASE_SHA256 = "d06029b5d58745070239c7d8b1f97410e1f6fce1cdb687dfb5ff9f50ae46574d"
ACTOR = "thesis-ch2-diagram-stage2"

KNOWLEDGE = Path("/Users/apple/工作桌面/knowledge")
OUTPUT_ROOT = KNOWLEDGE / "output/博士论文-v34第二章配图"
STAGE2_ROOT = OUTPUT_ROOT / "05-stage2"
REPORT_PATH = STAGE2_ROOT / "chapter2-stage2-publish-report.json"

CHAPTER_TITLE = "第2章 无人集群任务规划的理论基础"
PARAGRAPH_UPDATES = {
    "block-5b887a7df6f5918144a883f0": (
        "三种方式不是固定不变的体系选择，而应随任务阶段、网络状态和组织复杂度动态切换。"
        "预先规划阶段可以采用较强的集中计算形成全局基准方案；执行阶段以分层控制为主；"
        "链路中断或局部威胁突变时，部分群组进入分布式自治；通信恢复后再进行状态汇聚和方案校正。"
        "三种协同方式的适用条件、主要风险及动态切换中的人工授权边界如图2-3所示。"
    ),
    "block-d17a32f9c52d22a50eddc378": (
        "全局态势价值、空间优势场和分层投影关系如图2-4所示。"
        "红蓝兵力、环境与多杀伤链首先形成规则型态势评价，神经价值网络学习规则模型未覆盖的长期残差；"
        "所得全局价值进一步形成面向不同兵力群和任务角色的空间优势场，"
        "并分别约束HTN、MARTA和任务内强化学习机动。"
    ),
    "block-e824c794f4bceda97f8bc9fb": (
        "第3章据此建立统一状态、派生态势评价状态、规划解和约束体系；"
        "第4章展开HTN任务结构、MARTA兵力配置及多杀伤链组织方法；"
        "第5章研究战术函数条件化共享机动策略、集中价值评价和安全执行；"
        "第6章在统一仿真环境和证据合同下检验规则评价、价值估计、优势场与原始任务指标之间的关系。"
        "三类任务规划模型的功能耦合、统一规划对象链及章节映射如图2-5所示。"
    ),
}

FIGURES = [
    {
        "label": "图2-1",
        "caption": "指挥控制闭环中的任务规划定位及多流关系",
        "document_id": "doc-dcd1c8b24825",
        "revision": 1,
        "anchor_block_id": "block-dacacb092dd9d6653fbdd30d",
        "legacy_src": "ch2-c2-mission-planning-loop-v23.svg",
        "legacy_caption": "图2-1 指挥控制闭环中的任务规划定位及多流关系",
    },
    {
        "label": "图2-2",
        "caption": "指挥决心向规划变量和任务图的映射关系",
        "document_id": "doc-a3c0266ac5aa",
        "revision": 2,
        "anchor_block_id": "block-bdadfd006ad0f906ff11f1ab",
        "legacy_src": "ch2-intent-to-task-graph-v23.svg",
        "legacy_caption": "图2-2 指挥决心向规划变量和任务图的映射关系",
    },
    {
        "label": "图2-3",
        "caption": "集中式、分层式与分布式协同控制及授权边界",
        "document_id": "doc-e5d1bd0ab4e6",
        "revision": 1,
        "anchor_block_id": "block-5b887a7df6f5918144a883f0",
        "legacy_src": "",
        "legacy_caption": "",
    },
    {
        "label": "图2-4",
        "caption": "战术知识约束的全局态势价值、优势场与分层投影",
        "document_id": "doc-33b23d121e10",
        "revision": 2,
        "anchor_block_id": "block-d17a32f9c52d22a50eddc378",
        "legacy_src": "ch2-global-situation-advantage-field-v25.svg",
        "legacy_caption": "图2-3 战术知识约束的全局态势价值、优势场与分层投影",
    },
    {
        "label": "图2-5",
        "caption": "三类任务规划模型的耦合关系及章节映射",
        "document_id": "doc-4e06a50b09e7",
        "revision": 2,
        "anchor_block_id": "block-e824c794f4bceda97f8bc9fb",
        "legacy_src": "",
        "legacy_caption": "",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


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


def _chapter_id(state: dict[str, Any]) -> str:
    for block in (state.get("document") or {}).get("content") or []:
        attrs = block.get("attrs") or {}
        if (
            block.get("type") == "heading"
            and int(attrs.get("level") or 0) == 1
            and _text(block).strip() == CHAPTER_TITLE
        ):
            return str(attrs.get("blockId") or "")
    raise DocumentWorkspaceError("当前结构化正文缺少第二章稳定标题块")


def _current_figure_blocks(state: dict[str, Any], label: str) -> list[dict[str, Any]]:
    return [
        block
        for block in (state.get("document") or {}).get("content") or []
        if str((block.get("attrs") or {}).get("artifactLabel") or "") == label
        and str((block.get("attrs") or {}).get("artifactKind") or "")
        in {"figure", "figure-caption"}
    ]


def _legacy_block_ids(
    state: dict[str, Any],
    *,
    src_suffix: str,
    caption_text: str,
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
    if str(document.get("title") or "") != expected_title:
        raise DocumentWorkspaceError(f"绘图标题不匹配：{spec['document_id']}")
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
        raise DocumentWorkspaceError("第三版父文档不再是只读历史版本，停止发布")

    state = writing_collaboration_service.get_state(project, TARGET_DOCUMENT_ID)
    sha256 = writing_collaboration_service.codec.document_sha256(state["document"])
    if int(state.get("document_revision") or 0) != EXPECTED_BASE_REVISION:
        raise DocumentWorkspaceError(
            f"正文修订已变化：当前{state.get('document_revision')}，预期{EXPECTED_BASE_REVISION}"
        )
    if sha256 != EXPECTED_BASE_SHA256:
        raise DocumentWorkspaceError("正文内容哈希已变化，停止发布")
    if str((state.get("projection") or {}).get("status") or "") != "current":
        raise DocumentWorkspaceError("Markdown投影不是current，停止发布")

    chapter_id = _chapter_id(state)
    blocks = _block_map(state)
    missing_anchors = [
        str(spec["anchor_block_id"])
        for spec in FIGURES
        if str(spec["anchor_block_id"]) not in blocks
    ]
    missing_paragraphs = [block_id for block_id in PARAGRAPH_UPDATES if block_id not in blocks]
    if missing_anchors or missing_paragraphs:
        raise DocumentWorkspaceError(
            "第二章稳定块缺失：" + "、".join([*missing_anchors, *missing_paragraphs])
        )

    diagrams = [_diagram_resource(project, spec) for spec in FIGURES]
    return {
        "record": record,
        "parent": parent,
        "state": state,
        "chapter_id": chapter_id,
        "content_sha256": sha256,
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
    document_root = multi_document_service._document_root(  # noqa: SLF001
        project, TARGET_DOCUMENT_ID
    )
    backup_name = f"chapter2-stage2-before-r{EXPECTED_BASE_REVISION:06d}"
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
        "projection": state.get("projection") or {},
        "diagram_revisions": {
            str(spec["document_id"]): int(spec["revision"]) for spec in FIGURES
        },
    }
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        snapshots = {
            "structured-state.json": state,
            "document-record.json": preflight["record"],
            "parent-document-record.json": preflight["parent"],
            "backup-manifest.json": manifest,
        }
        for name, value in snapshots.items():
            path = root / name
            if not path.exists():
                path.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
        for relative in (
            "source/document.md",
            "working/document.md",
            "manifest.json",
        ):
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
    project: dict[str, Any],
    chapter_id: str,
    block_id: str,
    text: str,
) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(
        project, TARGET_DOCUMENT_ID, chapter_id
    )
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
            "client_change_id": f"thesis-v34-ch2-paragraph-{block_id}-v1",
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
    project: dict[str, Any],
    chapter_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(
        project, TARGET_DOCUMENT_ID, chapter_id
    )
    current = _current_figure_blocks(state, str(spec["label"]))
    revision_marker = f"{spec['document_id']}-r{spec['revision']}-"
    current_image = next((block for block in current if block.get("type") == "image"), None)
    if current_image and revision_marker in str((current_image.get("attrs") or {}).get("src") or ""):
        return {
            "label": spec["label"],
            "skipped": True,
            "reason": f"revision {spec['revision']} already published",
        }

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
                f"thesis-v34-ch2-{str(spec['label']).replace('图', 'figure-')}-"
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
    state = writing_collaboration_service.get_state(
        project, TARGET_DOCUMENT_ID, chapter_id
    )
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
            for row in diagram_service.list_references(
                project, str(spec["document_id"])
            )
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
            "all_reference_statuses": [row.get("status") for row in references],
        }

    old_assets = {
        str(spec["legacy_src"]): str(spec["legacy_src"]) in searchable
        for spec in FIGURES
        if spec["legacy_src"]
    }
    paragraph_checks = {
        block_id: (
            _text(_block_map(state).get(block_id) or {}).strip() == expected
        )
        for block_id, expected in PARAGRAPH_UPDATES.items()
    }
    return {
        "document_revision": state.get("document_revision"),
        "content_sha256": writing_collaboration_service.codec.document_sha256(
            writing_collaboration_service.get_state(
                project, TARGET_DOCUMENT_ID
            )["document"]
        ),
        "projection": state.get("projection") or {},
        "labels": labels,
        "old_assets_still_referenced": old_assets,
        "paragraph_checks": paragraph_checks,
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
    preflight_report = {
        "stage": 2,
        "mode": "preflight" if args.preflight else "apply",
        "checked_at": _now(),
        "project_id": PROJECT_ID,
        "target_document_id": TARGET_DOCUMENT_ID,
        "parent_document_id": PARENT_DOCUMENT_ID,
        "document_revision": preflight["state"]["document_revision"],
        "content_sha256": preflight["content_sha256"],
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
        print(json.dumps(preflight_report, ensure_ascii=False, indent=2))
        return

    STAGE2_ROOT.mkdir(parents=True, exist_ok=True)
    report = {**preflight_report, "started_at": _now()}
    try:
        report["backup"] = _backup(project, preflight)
        report["paragraph_updates"] = [
            _replace_paragraph(
                project,
                preflight["chapter_id"],
                block_id,
                text,
            )
            for block_id, text in PARAGRAPH_UPDATES.items()
        ]
        report["publications"] = [
            _publish_figure(project, preflight["chapter_id"], spec)
            for spec in FIGURES
        ]
        report["verification"] = _verification(
            project, preflight["chapter_id"]
        )
        report["status"] = "completed"
        report["completed_at"] = _now()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["failed_at"] = _now()
        try:
            current = writing_collaboration_service.get_state(
                project, TARGET_DOCUMENT_ID
            )
            report["failure_state"] = {
                "document_revision": current.get("document_revision"),
                "projection": current.get("projection") or {},
            }
        except Exception as state_exc:  # pragma: no cover - diagnostic path
            report["failure_state_error"] = str(state_exc)
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
