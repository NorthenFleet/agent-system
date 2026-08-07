import hashlib
from pathlib import Path

import pytest

from scripts.sync_writing_document_structure import _planned_workspace


def _workspace(version: int = 16, source_sha256: str = "") -> dict:
    return {
        "manifest": {"version": version},
        "stats": {},
        "sections": [],
        "current_structure": {
            "version": f"v{version}",
            "source_sha256": source_sha256,
            "chapters": [],
        },
    }


def test_planned_workspace_builds_v18_structure_without_writing_source(
    tmp_path: Path,
) -> None:
    markdown_path = tmp_path / "thesis-v18.md"
    markdown = (
        "# 文档说明\n\n说明。\n\n"
        "# 第1章 绪论\n\n## 1.1 背景\n\n### 1.1.1 问题\n\n正文。\n\n"
        "# 第2章 方法\n\n## 2.1 模型\n\n正文。\n"
    )
    markdown_path.write_text(markdown, encoding="utf-8")

    planned, content = _planned_workspace(
        {"id": "project", "name": "普通研究报告"},
        {"id": "document", "title": "研究报告正文"},
        _workspace(),
        markdown_path,
        18,
    )

    assert content == markdown
    assert planned["manifest"]["version"] == 18
    assert planned["current_structure"]["version"] == "v18"
    assert planned["current_structure"]["chapter_count"] == 2
    assert planned["current_structure"]["heading_count"] == 6
    assert markdown_path.read_text(encoding="utf-8") == markdown


def test_planned_workspace_is_idempotent_for_same_version_and_hash(
    tmp_path: Path,
) -> None:
    markdown_path = tmp_path / "thesis-v18.md"
    markdown = "# 第1章 绪论\n\n正文。\n"
    markdown_path.write_text(markdown, encoding="utf-8")
    source_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    current = _workspace(18, source_sha256)

    planned, content = _planned_workspace(
        {"id": "project", "name": "普通研究报告"},
        {"id": "document", "title": "研究报告正文"},
        current,
        markdown_path,
        18,
    )

    assert planned is current
    assert content is None


def test_planned_workspace_rejects_version_rollback(tmp_path: Path) -> None:
    markdown_path = tmp_path / "thesis-v17.md"
    markdown_path.write_text("# 第1章 绪论\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="必须高于当前版本"):
        _planned_workspace(
            {"id": "project", "name": "普通研究报告"},
            {"id": "document", "title": "研究报告正文"},
            _workspace(18, "different"),
            markdown_path,
            17,
        )
