from pathlib import Path

import pytest

from services.document_comparison_service import DocumentComparisonService
from services.document_workspace_service import document_workspace_service
from services.multi_document_service import MultiDocumentService


@pytest.fixture
def comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(document_workspace_service, "vault", tmp_path)
    monkeypatch.setattr(document_workspace_service, "_find_source_word", lambda project: None)
    source = tmp_path / "thesis.md"
    source.write_text("# 第一章 绪论\n\n共同段落。\n\n旧段落。\n\n# 第二章 方法\n\n保持内容。\n", encoding="utf-8")
    project = {"id": "proj-compare", "name": "版本比对", "enabled_modules": ["writing"], "document_spec": {"working_markdown": {"path": str(source)}, "expected_chapters": 2}}
    documents = MultiDocumentService()
    left = documents.list_documents(project)["documents"][0]
    right_source = tmp_path / "right.md"
    right_source.write_text("# 第一章 绪论\n\n共同段落。\n\n新段落。\n\n# 第三章 实验\n\n新增内容。\n", encoding="utf-8")
    right = documents.create_document(project, "当前稿", "rich_text", source_path=str(right_source))
    return DocumentComparisonService(documents), project, left, right


def test_document_comparison_maps_chapters_and_reports_paragraph_changes(comparison):
    service, project, left, right = comparison
    result = service.compare(project, {"left_document_id": left["id"], "right_document_id": right["id"]})

    assert result["summary"]["unchanged"] >= 1
    assert result["summary"]["modified"] >= 1
    assert result["summary"]["added"] >= 1
    assert any(row["key"] == "chapter:一" and row["matched"] for row in result["sections"])
    assert any(not row["matched"] for row in result["sections"])

    cached = service.compare(project, {"left_document_id": left["id"], "right_document_id": right["id"]})
    assert cached["cached"] is True
