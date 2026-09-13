"""Remove two orphaned legacy captions after Chapter 5 renumbering."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_manager import project_manager
from services.document_workspace_service import DocumentWorkspaceError
from services.writing_collaboration_service import writing_collaboration_service

import publish_thesis_ch5_diagrams_stage2 as publication


EXPECTED_REVISION = 75
EXPECTED_SHA256 = "ddb9a46a1f064def6b17b9a127f519ee7ec578ce13c503e11dfaf5eb05b6b8e2"
EXPECTED_CHAPTER_SHA256 = "e33053712364090c3f2606611e46249567eabc61ceac67efca83e0c8e041b27e"
ORPHANS = {
    "block-8b554b3436bd246e128fb435": (
        2,
        "<center>图5-7 任务内双策略规划的可追溯G2证据链</center>",
    ),
    "block-01e78a4d4b234e6ff1865652": (
        2,
        "<center>图5-15 三任务共享目标地图网络结构及实现证据插图</center>",
    ),
}
REPORT = publication.STAGE2_ROOT / "chapter5-orphan-caption-repair-report.json"


def main() -> None:
    project = project_manager.get_project(publication.PROJECT_ID)
    if not project:
        raise SystemExit("博士论文项目不存在")
    state = writing_collaboration_service.get_state(
        project, publication.TARGET_DOCUMENT_ID
    )
    full_sha = writing_collaboration_service.codec.document_sha256(state["document"])
    chapter_sha = publication._chapter_sha256(state)
    if int(state.get("document_revision") or 0) != EXPECTED_REVISION:
        raise DocumentWorkspaceError("正文修订已变化，停止孤立题注修复")
    if full_sha != EXPECTED_SHA256 or chapter_sha != EXPECTED_CHAPTER_SHA256:
        raise DocumentWorkspaceError("正文或第五章哈希已变化，停止孤立题注修复")
    chapter_id, _, _ = publication._chapter_bounds(state)
    blocks = publication._block_map(state)
    operations = []
    for block_id, (expected_revision, markdown) in ORPHANS.items():
        block = blocks.get(block_id)
        if not block:
            raise DocumentWorkspaceError(f"孤立题注不存在：{block_id}")
        if str((block.get("attrs") or {}).get("markdown") or "") != markdown:
            raise DocumentWorkspaceError(f"孤立题注内容已变化：{block_id}")
        operations.append(
            {
                "op": "delete",
                "block_id": block_id,
                "expected_block_revision": expected_revision,
            }
        )
    result = writing_collaboration_service.patch_draft(
        project,
        publication.TARGET_DOCUMENT_ID,
        {
            "section_id": chapter_id,
            "expected_revision": state["document_revision"],
            "client_change_id": "thesis-v34-ch5-remove-orphan-captions-v1",
            "operations": operations,
        },
        publication.ACTOR,
    )
    verification = publication._verification(project, chapter_id)
    if verification["caption_numbers"] != list(range(1, 22)):
        raise DocumentWorkspaceError(
            f"第五章图号仍不连续：{verification['caption_numbers']}"
        )
    if any(verification["old_assets_still_referenced"].values()):
        raise DocumentWorkspaceError("旧结构图仍被第五章引用")
    if any(verification["forbidden_development_terms"].values()):
        raise DocumentWorkspaceError("第五章仍出现开发环境标识")
    if not all(verification["data_caption_checks"].values()):
        raise DocumentWorkspaceError("数据图题注验证失败")
    for spec in publication.FIGURES:
        current = verification["labels"][spec["label"]]
        if current["caption_text"] != f"{spec['label']} {spec['caption']}":
            raise DocumentWorkspaceError(f"{spec['label']}结构化题注不匹配")
        if current["current_reference_count"] != 1:
            raise DocumentWorkspaceError(f"{spec['label']}当前结构化引用数量不是1")
    payload = {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "deleted_block_ids": list(ORPHANS),
        "patch_result": result,
        "verification": verification,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
