from pathlib import Path

import pytest

from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceService,
    _citation_numbers,
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    service = DocumentWorkspaceService()
    service.vault = tmp_path
    source = tmp_path / "10-成果库-Outputs" / "毕业论文" / "博士论文"
    source.mkdir(parents=True)
    (source / "博士论文 - 测试.md").write_text(
        """# 测试博士论文

## 摘要

本文提出一个测试模型[1]。

# 第1章 绪论

## 1.1 研究背景

本章研究结果表明该方法有效[1]。

![测试图](assets/test.png)

# 参考文献

[1] Test Author. Test Paper[J]. 2025.
""",
        encoding="utf-8",
    )
    (source / "assets").mkdir()
    (source / "assets" / "test.png").write_bytes(b"png")
    monkeypatch.setattr(service, "_find_source_word", lambda project: None)
    return service


def project():
    return {
        "id": "thesis",
        "name": "博士论文",
        "enabled_modules": ["writing"],
        "document_spec": {"references": [{"title": "内部概念说明", "source_type": "knowledge_base"}]},
    }


def test_workspace_parses_sections_references_and_assets(workspace):
    result = workspace.workspace(project())
    assert result["stats"]["chapter_count"] == 1
    assert result["reference_summary"]["formal"] == 1
    assert result["reference_summary"]["knowledge"] == 1
    assert result["quality"]["missing_assets"] == 0


def test_references_include_section_locations_and_coverage(workspace):
    result = workspace.references(project())
    reference = result["formal"][0]
    assert reference["usage_count"] == 2
    assert reference["section_count"] == 2
    assert {row["kind"] for row in reference["locations"]} == {"frontmatter", "chapter"}
    assert result["summary"]["sections_with_citations"] == 2
    assert sum(row["citation_occurrences"] for row in result["section_coverage"]) == 2


def test_section_update_is_versioned(workspace):
    current = workspace.workspace(project())
    section_id = next(row["id"] for row in current["sections"] if row["kind"] == "chapter")
    section = workspace.section(project(), section_id)
    updated = workspace.update_section(project(), section_id, section["content"] + "\n新增内容。", 1, "tester")
    assert updated["version"] == 2
    assert "新增内容" in updated["content"]
    assert any(row["name"].startswith("v0001-before") for row in workspace.versions(project()))
    with pytest.raises(DocumentVersionConflict):
        workspace.update_section(project(), section_id, updated["content"], 1, "tester")


def test_citation_groups_expand_ranges_and_ignore_zero():
    assert _citation_numbers("已有研究[1, 3-5]，参数范围为[0, 1]。") == [1, 3, 4, 5]
