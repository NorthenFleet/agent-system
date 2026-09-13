#!/usr/bin/env python3
"""Create the auditable v34 doctoral-thesis candidate from the frozen v33 state.

The candidate is editable but deliberately excluded from the formal delivery
package.  It never mutates the v33 authority, historical Word baseline, or
frozen Word/PDF/PPT deliverables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project_manager import project_manager  # noqa: E402
from services.document_workspace_service import DocumentWorkspaceError  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402

PROJECT_ID = "proj-10fbeefae5"
V33_ID = "doc-15def56e2401"
SERIES_ID = "doctoral-thesis"
EDITION_LABEL = "第三版·v34候选工作稿"
TITLE = "博士论文·第三版 v34（七章候选工作稿）"
SOURCE = Path(
    "/Users/apple/工作桌面/knowledge/10-成果库-Outputs/毕业论文/博士论文/"
    "论文章节/版本/第三版/博士论文-第三版-七章工作稿.md"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _marker(name: str) -> str:
    return f"<!-- v34:{name} -->"


def _chapter_opening(number: int) -> str:
    next_label = "参考文献与可复核边界" if number == 7 else f"第{number + 1}章"
    focus = {
        1: "研究问题、对象边界与可检验的科学问题",
        2: "统一建模所需的理论概念、约束语义与方法依据",
        3: "从任务意图到可评价规划解的统一状态、变量与接口",
        4: "从规划解到可执行任务结构和资源承担关系的前端求解",
        5: "从任务交接到技能调度、机动决策与受约束执行的后端求解",
        6: "对统一方法链进行可复算、可区分证据等级的验证",
        7: "在已有证据范围内归纳结论、创新与适用边界",
    }[number]
    return (
        f"{_marker(f'chapter-{number}-opening')}\n\n"
        f"承接上章已经界定的概念、约束与问题边界，本章聚焦于{focus}。"
        "本章只对能够由定义、实现、数据合同或实验记录支持的对象作出陈述，"
        "不以局部联通或训练现象替代系统级效能结论。\n\n"
        "为便于跨章复核，以下论述按照“输入条件—决策对象—约束与失败语义—输出记录”展开；"
        f"本章形成的结构化产出将作为{next_label}的直接输入或证据依据。\n"
    )


def _chapter_closing(number: int) -> str:
    next_label = "参考文献、附录与后续研究" if number == 7 else f"第{number + 1}章"
    return (
        f"{_marker(f'chapter-{number}-closing')}\n\n"
        "综上，本章将其输入、关键决策、约束校核、失败语义和可追溯输出限定在同一对象链中。"
        f"这些输出不被视为终局结论，而以版本化记录交接给{next_label}；"
        "后续章节若发现条件不满足，应沿记录的失败原因回到相应层级修正，而非以默认值掩盖不可行状态。\n"
    )


CONTRACTS = {
    "## 3.9 本章小结": """<!-- v34:chapter-3-interface-contract -->

## 3.8.5 统一接口契约与向第4章的交接

第3章只拥有统一表示与总体评价的决策权：以 `MissionInput` 固化任务意图、态势、规则与资源约束；以 `EvaluationState` 记录由该输入派生的信念、优势、风险和评价版本；以 `PlanSolution` 保存候选任务结构、承担关系、阶段目标和评价依据。其硬约束包括语义完整性、版本一致性、规则边界和资源可表达性；缺失输入、坐标语义不一致、评价版本失配或约束无法投影时，必须输出可定位的 `PlanningFailure`，不得生成可执行的伪方案。

| 交接对象 | 第3章输出 | 第4章读取与决策 | 失败后的回退条件 |
| --- | --- | --- | --- |
| 任务前端输入 | `MissionInput`、`EvaluationState` | HTN任务图与MARTA候选生成 | 输入不完整或坐标/规则版本不一致时回到任务输入校核 |
| 规划候选 | `PlanSolution`、目标函数与约束包 | 可行任务结构、承担关系、替补与预算 | 无可行候选时回传失败类型、受影响任务和违反约束 |
| 证据记录 | 评价版本、候选评分与假设 | 形成可审计 `TaskHandoff` | 记录缺失时禁止交给任务内执行层 |

第4章只能在该接口内细化任务图和资源承担，不重新定义总体评价口径；其输出应以 `TaskHandoff` 返回任务依赖、承担矩阵、时间窗、区域、资源预算与前端失败报告，供第5章继续实例化。

""",
    "## 4.9 本章小结": """<!-- v34:chapter-4-interface-contract -->

## 4.8.5 分解—分配接口与向第5章的交接

第4章拥有任务结构和任务级资源组织的决策权：HTN负责将 `PlanSolution` 展开为带依赖、目标、时间窗和能力需求的任务图；MARTA负责在硬可行性门控后给出承担矩阵、角色、任务级区域、资源预算和替补关系。约束至少覆盖能力、数量、时效、资源、任务依赖、并发冲突和风险边界。其失败语义必须区分“任务结构不可达”“资源不足”“时间窗冲突”“空间/通信粗校核失败”和“评价版本失配”，并携带受影响任务与可回退的上层位置。

| 交接对象 | 第4章输出 | 第5章读取与决策 | 回退条件 |
| --- | --- | --- | --- |
| 前端方案 | `TaskHandoff`：任务图、承担关系、约束包、前端评价记录 | 任务技能包、技能调用、机动阶段目标和执行策略 | 任务内能力、路径或规则不可满足时先回传受影响任务 |
| 资源组织 | 平台占用、角色、区域、预算、替补关系 | 共享机动与规则调度的责任范围 | 需要改变承担关系或任务依赖时回到MARTA/HTN |
| 可审计失败 | `FrontPlanningFailure` 与评价版本 | 分级重规划和第6章失败分类 | 无失败记录不得把不可执行结果标记为完成 |

第5章不得越过本章重新分配平台或修改任务依赖；其执行反馈可触发局部技能修复，只有超出任务内边界时才携带证据回退到MARTA或HTN。

""",
    "## 5.13 本章小结": """<!-- v34:chapter-5-interface-contract -->

## 5.12.5 执行反馈接口与向第6章的可观测交接

第5章拥有任务内技能编排和受约束执行的决策权：从 `TaskHandoff` 生成 `TaskPolicySet`，再由规则门控、共享机动策略和执行保障形成 `PolicyDecision` 与 `CommandBundle`。核心决策变量包括技能调用顺序、阶段目标点、共享策略动作、规则许可、路径与时序；硬约束包括动作所有权、交战规则、运动学、通信保持、风险阈值和上游资源占用。规则拒绝、路径不可达、通信降级、观测失配、策略超时和命令执行失败都必须保留分类代码，不得被重试次数或奖励值掩盖。

| 可观测对象 | 第5章输出 | 第6章统计用途 | 失败后的交接 |
| --- | --- | --- | --- |
| 执行决策 | `PolicyDecision`、`CommandBundle`、规则介入记录 | 规则合规、动作有效率、命令闭合率 | 局部失败由L0-L1修复，超界则上行回退 |
| 运行轨迹 | `ExecutionTrace`、坐标/单位版本、随机种子与耗时 | 任务完成、恢复时间、资源消耗与可重复性 | 轨迹不完整或坐标合同失败时判为无效运行 |
| 评估记录 | `EvaluationRecord`、失败分类、指标原值 | E1-E4 与M0-M8的原始统计输入 | 只可由原始运行重算，不能以训练曲线替代 |

第6章据此区分协议、烟测、任务内验证和系统级统计验证；只有在预注册场景、种子、基线和失败记录齐全时，才讨论效能差异及其置信区间。

""",
}


def _insert_before(markdown: str, heading: str, block: str) -> str:
    if block.splitlines()[0] in markdown:
        return markdown
    position = markdown.find(heading)
    if position < 0:
        raise DocumentWorkspaceError(f"v33 缺少预期标题：{heading}")
    return markdown[:position] + block + "\n" + markdown[position:]


def rebuild(markdown: str) -> str:
    result = markdown
    chapter_positions = []
    for number in range(1, 8):
        heading = f"# 第{number}章"
        index = result.find(heading)
        if index < 0:
            raise DocumentWorkspaceError(f"v33 缺少第{number}章")
        chapter_positions.append((number, index))
    # Apply contracts before inserting chapter endings so the target headings remain stable.
    for heading, block in CONTRACTS.items():
        result = _insert_before(result, heading, block)
    for number in range(1, 8):
        heading = f"# 第{number}章"
        start = result.find(heading)
        if _marker(f"chapter-{number}-opening") not in result:
            end = result.find("\n", start) + 1
            result = result[:end] + "\n" + _chapter_opening(number) + result[end:]
    # Locate each boundary after the openings/contracts have been added.
    for number in reversed(range(1, 8)):
        if _marker(f"chapter-{number}-closing") in result:
            continue
        start = result.find(f"# 第{number}章")
        next_start = result.find("\n# 第", start + 1)
        references = result.find("\n# 参考文献", start + 1)
        candidates = [value for value in (next_start, references) if value >= 0]
        end = min(candidates) if candidates else len(result)
        result = result[:end].rstrip() + "\n\n" + _chapter_closing(number) + "\n" + result[end:]
    return result


def candidate(rows: list[dict]) -> dict | None:
    return next(
        (
            row
            for row in rows
            if str(row.get("data_version") or "") == "thesis-v34-candidate"
            or (
                (row.get("lineage") or {}).get("series_id") == SERIES_ID
                and str((row.get("lineage") or {}).get("edition_label") or "") == EDITION_LABEL
            )
        ),
        None,
    )


def create(apply: bool) -> dict:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise DocumentWorkspaceError("博士论文项目不存在")
    documents = multi_document_service.list_documents(project, include_archived=True).get("documents") or []
    v33 = next((row for row in documents if row.get("id") == V33_ID), None)
    if not v33:
        raise DocumentWorkspaceError("v33 正文不存在")
    if not SOURCE.is_file():
        raise DocumentWorkspaceError(f"v33 源文件不存在：{SOURCE}")
    state = writing_collaboration_service.get_state(project, V33_ID)
    markdown = writing_collaboration_service.codec.to_markdown(state["document"])
    prepared = rebuild(markdown)
    source_checksum = _sha(markdown)
    report = {
        "project_id": PROJECT_ID,
        "parent_document_id": V33_ID,
        "parent_revision": int(state.get("document_revision") or 0),
        "parent_sha256": source_checksum,
        "candidate_title": TITLE,
        "chapter_count": sum(1 for line in prepared.splitlines() if line.startswith("# 第") and "章" in line),
        "transition_markers": prepared.count("<!-- v34:chapter-"),
        "interface_contracts": prepared.count("<!-- v34:chapter-") >= 3,
        "delivery_role": "candidate",
        "apply": apply,
    }
    existing = candidate(documents)
    if existing:
        lineage = dict(existing.get("lineage") or {})
        lineage.update({
            "series_id": SERIES_ID,
            "edition_label": EDITION_LABEL,
            "sequence": 4,
            "source_type": "structured_authority",
            "parent_document_id": V33_ID,
            "source_checksum": source_checksum,
            "source_paths": [str(SOURCE)],
        })
        existing = multi_document_service.update_document(project, existing["id"], {
            "title": TITLE,
            "status": "active",
            "sort_order": 3,
            "is_output_product": True,
            "output_format": "docx",
            "required_for_release": False,
            "expected_chapters": 7,
            "edit_policy": "editable",
            "delivery_role": "candidate",
            "publication_status": "draft",
            "data_version": "thesis-v34-candidate",
            "lineage": lineage,
        })
        report["document_id"] = existing["id"]
        report["candidate_revision"] = int(existing.get("revision") or 0)
        report["status"] = "existing"
        return report
    if not apply:
        report["status"] = "planned"
        return report

    created = multi_document_service.create_document(
        project,
        TITLE,
        "rich_text",
        outline=[f"第{number}章" for number in range(1, 8)],
        is_primary=False,
        is_output_product=True,
        output_format="docx",
        publication_status="draft",
        edit_policy="editable",
        delivery_role="candidate",
        data_version="thesis-v34-candidate",
        lineage={
            "series_id": SERIES_ID,
            "edition_label": EDITION_LABEL,
            "sequence": 4,
            "source_type": "structured_authority",
            "parent_document_id": V33_ID,
            "source_checksum": source_checksum,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_paths": [str(SOURCE)],
        },
    )
    multi_document_service.replace_rich_text_markdown(
        project,
        created["id"],
        prepared,
        "v34-candidate-bootstrap",
    )
    state = writing_collaboration_service.ensure_state(project, created["id"])
    report.update({
        "document_id": created["id"],
        "status": "created",
        "candidate_revision": int(getattr(state, "document_revision", 0) or 0),
        "candidate_sha256": str(getattr(state, "content_sha256", "") or ""),
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="create the candidate")
    args = parser.parse_args()
    print(json.dumps(create(args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
