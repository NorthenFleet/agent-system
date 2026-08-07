import pytest

from services.structured_document_service import StructuredDocumentCodec


SAMPLE = """---
title: 测试文档
---

# 第一章 绪论

这是 **加粗**、*强调* 与 [链接](https://example.com) 的正文[1]。

## 1.1 方法

- 要点一
- 要点二

| 指标 | 数值 |
| --- | ---: |
| 正确率 | 95% |

> 这是需要核验的结论。

![架构图](assets/diagram.png)

```python
print("ok")
```

[^note]: 脚注原文必须保留。
"""


def test_markdown_round_trip_preserves_academic_structure():
    codec = StructuredDocumentCodec()

    document = codec.from_markdown(SAMPLE, namespace="project/document")
    markdown = codec.to_markdown(document)
    reparsed = codec.from_markdown(markdown, namespace="roundtrip")

    before = codec.metrics(document)
    after = codec.metrics(reparsed)
    assert before["heading_count"] == after["heading_count"] == 2
    assert before["table_count"] == after["table_count"] == 1
    assert before["image_count"] == after["image_count"] == 1
    assert before["citation_count"] == after["citation_count"] == 1
    assert before["plain_text_sha256"] == after["plain_text_sha256"]
    assert "[^note]: 脚注原文必须保留。" in markdown


def test_markdown_import_assigns_stable_unique_block_ids():
    codec = StructuredDocumentCodec()

    first = codec.from_markdown(SAMPLE, namespace="project/document")
    second = codec.from_markdown(SAMPLE, namespace="project/document")
    first_ids = [row["attrs"]["blockId"] for row in first["content"]]
    second_ids = [row["attrs"]["blockId"] for row in second["content"]]

    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))
    assert all(row["attrs"]["blockRevision"] == 1 for row in first["content"])


def test_block_hash_ignores_revision_but_detects_content_change():
    codec = StructuredDocumentCodec()
    document = codec.from_markdown("# 标题\n\n正文。\n", namespace="doc")
    block = document["content"][1]
    original = codec.block_sha256(block)

    block["attrs"]["blockRevision"] = 9
    assert codec.block_sha256(block) == original

    block["content"][0]["text"] = "修改后的正文。"
    assert codec.block_sha256(block) != original


def test_unknown_markdown_is_kept_as_raw_block():
    codec = StructuredDocumentCodec()
    document = codec.from_markdown("::: custom\n保留扩展语法\n:::\n", namespace="raw")

    assert document["content"][0]["type"] == "rawMarkdown"
    assert codec.to_markdown(document).strip() == "::: custom\n保留扩展语法\n:::"


def test_display_math_is_kept_as_raw_block():
    codec = StructuredDocumentCodec()
    markdown = """$$
\\Phi_A^{rob}(t)=
\\mathbb{E}[\\widehat\\Phi_A(t)]
-\\kappa\\sigma[\\widehat\\Phi_A(t)]
$$     （3.10）
"""

    document = codec.from_markdown(markdown, namespace="math")
    projected = codec.to_markdown(document)
    reparsed = codec.from_markdown(projected, namespace="math-roundtrip")

    assert document["content"][0]["type"] == "rawMarkdown"
    assert projected == markdown
    assert codec.metrics(document)["plain_text_sha256"] == codec.metrics(reparsed)["plain_text_sha256"]


def test_hard_break_markdown_spaces_do_not_become_plain_text():
    codec = StructuredDocumentCodec()
    markdown = "**输入：**  \n总体任务。"

    document = codec.from_markdown(markdown, namespace="hard-break")
    projected = codec.to_markdown(document)
    reparsed = codec.from_markdown(projected, namespace="hard-break-roundtrip")

    before = codec._plain_text(document)
    after = codec._plain_text(reparsed)
    assert before == "输入：总体任务。"
    assert after == before


def test_table_alignment_uses_tiptap_tablekit_align_attribute():
    codec = StructuredDocumentCodec()
    document = codec.from_markdown(
        "| 左 | 中 | 右 |\n| :--- | :---: | ---: |\n| A | B | C |\n",
        namespace="table-align",
    )

    cells = document["content"][0]["content"][0]["content"]
    assert [cell["attrs"]["align"] for cell in cells] == ["left", "center", "right"]
    assert "| --- | :---: | ---: |" in codec.to_markdown(document)


def test_recursive_schema_rejects_unknown_nested_nodes():
    codec = StructuredDocumentCodec()
    document = codec.from_markdown("正文。\n", namespace="invalid")
    document["content"][0]["content"] = [{"type": "unknownInline", "text": "x"}]

    with pytest.raises(ValueError, match="只能包含行内节点"):
        codec.validate_document(document)
