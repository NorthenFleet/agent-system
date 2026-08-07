from pathlib import Path
import copy
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import pytest

from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceService,
    W,
    _chapter_number,
    _citation_numbers,
    _postprocess_standard_a4_docx,
    _postprocess_formal_docx,
    _postprocess_wargame_docx,
)
from services.document_outline_service import (
    build_document_directory,
    build_document_structure_snapshot,
    compare_document_structures,
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

### 1.1.1 研究问题

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


def test_workspace_exposes_three_level_directory(workspace):
    result = workspace.workspace(project())
    document = result["directory"][0]
    chapter = next(row for row in document["children"] if row["kind"] == "chapter")
    level_two = chapter["children"][0]
    level_three = level_two["children"][0]

    assert document["node_type"] == "document"
    assert document["level"] == 0
    assert document["title"] == "博士论文"
    assert chapter["level"] == 1
    assert chapter["section_id"] == chapter["id"]
    assert chapter["target_id"].endswith("-heading-1")
    assert chapter["node_type"] == "section"
    assert chapter["source_level"] == 1
    assert level_two["title"] == "1.1 研究背景"
    assert level_two["level"] == 2
    assert level_two["section_id"] == chapter["id"]
    assert level_three["title"] == "1.1.1 研究问题"
    assert level_three["level"] == 3
    assert level_three["source_level"] == 3
    assert level_three["target_id"].startswith(f"{chapter['id']}-heading-")


def test_workspace_keeps_level_four_in_source_but_excludes_it_from_directory(workspace):
    source = workspace.vault / "10-成果库-Outputs" / "毕业论文" / "博士论文" / "博士论文 - 测试.md"
    markdown = source.read_text(encoding="utf-8").replace(
        "本章研究结果表明该方法有效[1]。",
        "#### 1.1.1.1 算法步骤\n\n本章研究结果表明该方法有效[1]。",
    )
    source.write_text(markdown, encoding="utf-8")

    result = workspace.workspace(project())
    document = result["directory"][0]
    chapter = next(row for row in document["children"] if row["kind"] == "chapter")
    level_three = chapter["children"][0]["children"][0]

    assert source.read_text(encoding="utf-8") == markdown
    assert level_three["children"] == []
    assert result["current_structure"]["heading_count"] == 6
    assert result["current_structure"]["source_heading_count"] == 7
    assert all(
        item["level"] <= 3
        for item in result["current_structure"]["chapters"][0]["outline"]
    )


def test_workspace_exposes_current_structure_and_missing_target_status(workspace):
    result = workspace.workspace(project())

    assert result["current_structure"]["version"] == "v1"
    assert result["current_structure"]["chapter_count"] == 1
    assert result["current_structure"]["heading_count"] == 6
    assert result["current_structure"]["chapters"][0]["title"] == "第1章 绪论"
    assert len(result["current_structure"]["chapters"][0]["outline"]) == 2
    assert len(result["current_structure"]["source_sha256"]) == 64
    assert result["structure_sync"]["status"] == "missing"


def test_structure_snapshot_comparison_handles_aligned_and_diverged_without_rewriting():
    service = DocumentWorkspaceService()
    markdown = """# 文档说明

# 第1章 绪论

## 1.1 背景

### 1.1.1 问题

# 第2章 方法

## 2.1 模型
"""
    before = markdown
    sections = service._parse_sections(markdown)
    current = build_document_structure_snapshot(
        sections,
        document_title="普通研究报告",
        version=14,
        source_path="working/document.md",
        source_sha256="abc",
        generated_at="2026-07-29T00:00:00Z",
    )
    target = copy.deepcopy(current)

    aligned = compare_document_structures(current, target)
    target["chapters"][1]["title"] = "第2章 新方法"
    diverged = compare_document_structures(current, target)

    assert markdown == before
    assert current["version"] == "v14"
    assert current["chapter_count"] == 2
    assert current["heading_count"] == 6
    assert aligned["status"] == "aligned"
    assert aligned["source_matches"] is True
    assert aligned["changed_chapters"] == []
    assert diverged["status"] == "diverged"
    assert diverged["changed_chapters"] == [2]


def test_adaptive_directory_handles_mixed_manual_without_rewriting_source():
    service = DocumentWorkspaceService()
    markdown = """# 通用规则手册

# 2026年5月

# 一、想定背景

背景正文。

# 二、作战任务

## （一）红方任务

任务正文。

# 第8章 防空反导裁决模型

## 8.1 适用范围

### 8.1.1 裁决对象

正文。
"""
    before = markdown
    sections = service._parse_sections(markdown)
    document = build_document_directory(sections, "通用规则手册", document_id="manual")

    assert markdown == before
    assert len(document) == 1
    root = document[0]
    assert root["id"] == "document-manual"
    assert root["metadata"]["labels"] == ["2026年5月"]
    assert [row["title"] for row in root["children"]] == [
        "一、想定背景",
        "二、作战任务",
        "第8章 防空反导裁决模型",
    ]
    task = root["children"][1]
    assert task["children"][0]["title"] == "（一）红方任务"
    assert task["children"][0]["level"] == 2
    chapter = root["children"][2]
    assert chapter["children"][0]["level"] == 2
    assert chapter["children"][0]["children"][0]["level"] == 3


def test_adaptive_directory_keeps_duplicate_titles_and_repairs_level_jumps():
    service = DocumentWorkspaceService()
    markdown = """# 第一部分

### 重复标题

#### 重复标题

# 第二部分

## 无编号标题
"""
    sections = service._parse_sections(markdown)
    root = build_document_directory(sections, "普通研究报告")[0]
    first = root["children"][0]
    duplicate_parent = first["children"][0]
    duplicate_child = duplicate_parent["children"][0]

    assert duplicate_parent["title"] == duplicate_child["title"] == "重复标题"
    assert duplicate_parent["id"] != duplicate_child["id"]
    assert duplicate_parent["level"] == 2
    assert duplicate_child["level"] == 3
    assert root["children"][1]["children"][0]["level"] == 2


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


def test_section_update_preserves_next_heading_boundary(tmp_path, monkeypatch):
    service = DocumentWorkspaceService()
    service.vault = tmp_path
    source = tmp_path / "manual.md"
    source.write_text(
        "# 第一章 总则\n\n原正文。\n\n# 第二章 流程\n\n第二章正文。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_find_source_word", lambda project: None)
    manual_project = {
        "id": "manual",
        "name": "规则手册",
        "document_spec": {
            "working_markdown": {"path": str(source)},
            "expected_chapters": 2,
        },
    }
    first = service.workspace(manual_project)
    section = first["sections"][0]

    service.update_section(
        manual_project,
        section["id"],
        "# 第一章 总则\n\n更新后的正文。",
        first["manifest"]["version"],
        "tester",
    )
    updated = service.workspace(manual_project)

    assert [row["title"] for row in updated["sections"]] == ["第一章 总则", "第二章 流程"]
    assert updated["quality"]["blockers"] == 0


def test_citation_groups_expand_ranges_and_ignore_zero():
    assert _citation_numbers("已有研究[1, 3-5]，参数范围为[0, 1]。") == [1, 3, 4, 5]


def test_chapter_number_accepts_arabic_and_chinese_numerals():
    assert _chapter_number("第8章 武器使用与命中规则") == 8
    assert _chapter_number("第十二章 推演记录与争议处理") == 12
    assert _chapter_number("第二十一章 附录") == 21
    assert _chapter_number("总则") is None


def test_standard_a4_docx_postprocess_sets_all_sections_to_a4(tmp_path):
    path = tmp_path / "paper.docx"
    template = Path(__file__).resolve().parents[1] / "assets" / "wargame_a4_reference.docx"
    shutil.copy2(template, path)

    with ZipFile(path) as archive:
        parts = {
            entry.filename: (entry, archive.read(entry.filename))
            for entry in archive.infolist()
        }
    document_entry, payload = parts["word/document.xml"]
    document = ET.fromstring(payload)
    sections = document.findall(f".//{W}sectPr")
    assert sections
    portrait = sections[0].find(f"./{W}pgSz")
    portrait.set(f"{W}w", "12240")
    portrait.set(f"{W}h", "15840")
    if len(sections) == 1:
        landscape_section = ET.fromstring(ET.tostring(sections[0]))
        document.find(f".//{W}body").append(landscape_section)
        sections.append(landscape_section)
    landscape = sections[-1].find(f"./{W}pgSz")
    landscape.set(f"{W}orient", "landscape")
    landscape.set(f"{W}w", "15840")
    landscape.set(f"{W}h", "12240")
    parts["word/document.xml"] = (
        document_entry,
        ET.tostring(document, encoding="utf-8", xml_declaration=True),
    )
    with ZipFile(path, "w") as archive:
        for entry, part_payload in parts.values():
            archive.writestr(entry, part_payload)

    _postprocess_standard_a4_docx(path)

    with ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    sections = document.findall(f".//{W}sectPr")
    portrait = sections[0].find(f"./{W}pgSz")
    landscape = sections[-1].find(f"./{W}pgSz")
    assert (portrait.get(f"{W}w"), portrait.get(f"{W}h")) == ("11906", "16838")
    assert (landscape.get(f"{W}w"), landscape.get(f"{W}h")) == ("16838", "11906")


def test_formal_docx_postprocess_applies_layout_contract_and_cover(tmp_path):
    path = tmp_path / "paper.docx"
    template = Path(__file__).resolve().parents[1] / "assets" / "wargame_a4_reference.docx"
    shutil.copy2(template, path)

    _postprocess_formal_docx(
        path,
        {
            "title": "测试论文题目",
            "author": "测试作者",
            "advisor": "测试导师",
            "advisor_title": "研究员",
            "institution": "测试单位",
            "date": "2026年8月",
        },
    )

    with ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        settings = ET.fromstring(archive.read("word/settings.xml"))
        footer = ET.fromstring(archive.read("word/footer1.xml"))
    section = document.find(f".//{W}sectPr")
    page_size = section.find(f"./{W}pgSz")
    margins = section.find(f"./{W}pgMar")
    assert (page_size.get(f"{W}w"), page_size.get(f"{W}h")) == ("11906", "16838")
    assert (margins.get(f"{W}top"), margins.get(f"{W}bottom")) == ("2098", "1984")
    assert (margins.get(f"{W}left"), margins.get(f"{W}right")) == ("1587", "1474")
    assert section.find(f"./{W}titlePg") is not None
    assert settings.find(f"./{W}updateFields") is not None
    assert "测试论文题目" in "".join(node.text or "" for node in document.findall(f".//{W}t"))
    assert "PAGE" in "".join(node.text or "" for node in footer.findall(f".//{W}instrText"))


def test_wargame_docx_postprocess_sets_print_boundaries(tmp_path):
    path = tmp_path / "manual.docx"
    template = Path(__file__).resolve().parents[1] / "assets" / "wargame_a4_reference.docx"
    shutil.copy2(template, path)

    _postprocess_wargame_docx(path)

    with ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        settings = ET.fromstring(archive.read("word/settings.xml"))
        styles = ET.fromstring(archive.read("word/styles.xml"))
    heading = next(
        paragraph
        for paragraph in document.findall(f".//{W}p")
        if (paragraph.find(f"./{W}pPr/{W}pStyle") is not None)
        and paragraph.find(f"./{W}pPr/{W}pStyle").get(f"{W}val") == "Heading1"
    )
    assert heading.find(f"./{W}pPr/{W}pageBreakBefore") is not None
    assert heading.find(f"./{W}pPr/{W}keepNext") is not None
    paragraph_properties = heading.find(f"./{W}pPr")
    paragraph_property_names = [
        child.tag.rsplit("}", 1)[-1]
        for child in paragraph_properties
    ]
    assert paragraph_property_names.index("keepNext") < paragraph_property_names.index("pageBreakBefore")
    first_row = document.find(f".//{W}tbl/{W}tr")
    assert first_row.find(f"./{W}trPr/{W}tblHeader") is not None
    assert first_row.find(f"./{W}trPr/{W}cantSplit") is not None
    table = document.find(f".//{W}tbl")
    assert table.find(f"./{W}tblPr/{W}tblStyle").get(f"{W}val") == "TableGrid"
    table_width = table.find(f"./{W}tblPr/{W}tblW")
    assert table_width.get(f"{W}type") == "pct"
    assert table_width.get(f"{W}w") == "5000"
    assert table.find(f"./{W}tblPr/{W}tblLayout").get(f"{W}type") == "fixed"
    assert table.find(f"./{W}tblPr/{W}tblBorders/{W}insideV") is not None
    assert all(
        cell.find(f"./{W}tcPr/{W}tcW") is not None
        for cell in first_row.findall(f"./{W}tc")
    )
    for paragraph in table.findall(f".//{W}p"):
        paragraph_style = paragraph.find(f"./{W}pPr/{W}pStyle")
        assert paragraph_style is None or paragraph_style.get(f"{W}val") != "Compact"
        assert paragraph.find(f"./{W}pPr/{W}spacing").get(f"{W}after") == "0"
        assert paragraph.find(f"./{W}pPr/{W}ind").get(f"{W}firstLine") == "0"
    row_property_names = [
        child.tag.rsplit("}", 1)[-1]
        for child in first_row.find(f"./{W}trPr")
    ]
    assert row_property_names.index("cantSplit") < row_property_names.index("tblHeader")
    assert settings.find(f"./{W}updateFields").get(f"{W}val") == "true"
    style_fonts = {
        style.get(f"{W}styleId"): style.find(f".//{W}rFonts").get(f"{W}eastAsia")
        for style in styles.findall(f".//{W}style")
        if style.find(f".//{W}rFonts") is not None
    }
    assert style_fonts["Normal"] == "Songti SC"
    assert style_fonts["Heading1"] == "Heiti SC"
