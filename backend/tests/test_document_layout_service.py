import hashlib
import json
import shutil
from pathlib import Path

import pytest

from services.document_layout_service import DocumentLayoutService
from services.document_workspace_service import document_workspace_service


@pytest.fixture
def layout_context(tmp_path, monkeypatch):
    monkeypatch.setattr(document_workspace_service, "vault", tmp_path)
    monkeypatch.setattr(document_workspace_service, "_find_source_word", lambda project: None)
    source = tmp_path / "10-成果库-Outputs" / "report" / "body.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 第一章 测试\n\n## 1.1 内容\n\n正文。\n", encoding="utf-8")
    project = {
        "id": "proj-layout",
        "name": "普通研究报告",
        "document_spec": {"working_markdown": {"path": str(source)}},
        "_course_document_record": {
            "id": "doc-layout",
            "kind": "rich_text",
            "publication_status": "draft",
            "metadata": {},
        },
    }
    document_workspace_service.ensure_workspace(project)
    root = document_workspace_service._workspace_root(project) / "layout" / "profiles" / "formal-v1"  # noqa: SLF001
    root.mkdir(parents=True)
    template = root / "reference.docx"
    source_template = Path(__file__).resolve().parents[1] / "assets" / "wargame_a4_reference.docx"
    shutil.copy2(source_template, template)
    template_sha = hashlib.sha256(template.read_bytes()).hexdigest()
    profile = {
        "id": "formal-v1",
        "name": "正式报告模板",
        "version": "v1",
        "applies_to": {"kind": "rich_text", "document_types": ["研究报告"]},
        "authority_source": {"path": str(source_template), "sha256": template_sha},
        "template_path": str(template),
        "template_sha256": template_sha,
        "status": "published",
        "page": {"size": "A4"},
        "styles": {},
        "rules": {},
    }
    (root / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return project, source, template


def test_layout_binding_is_generic_and_becomes_stale_after_content_change(layout_context):
    project, source, _template = layout_context
    service = DocumentLayoutService()
    binding = service.binding_patch(
        project,
        profile_id="formal-v1",
        cover={"title": "研究报告", "author": "作者"},
        layout_revision="R1",
    )
    project["_course_document_record"]["metadata"] = {"layout_binding": binding}

    state = service.state(project)
    assert state["binding"]["status"] == "aligned"
    assert state["profile"]["name"] == "正式报告模板"
    assert state["frontmatter"]["abstract_zh"] == "pending"

    working = Path(document_workspace_service.ensure_workspace(project)["working_markdown"])
    working.write_text(working.read_text(encoding="utf-8") + "\n变更。\n", encoding="utf-8")
    state = service.state(project)
    assert state["binding"]["status"] == "stale"
    assert "正文哈希变化" in state["binding"]["changed_reasons"]


def test_current_word_reference_becomes_an_immutable_shared_template(layout_context, monkeypatch):
    project, _source, template = layout_context
    project["_course_document_record"]["product_type"] = "lesson_plan"
    service = DocumentLayoutService()
    monkeypatch.setattr(
        service,
        "_render_template_preview",
        lambda root, path: {"pdf_path": str(root / "preview.pdf"), "page_count": 3, "showcase_pages": [{"page": 1, "label": "封面/首页", "kind": "cover"}]},
    )

    profile = service.register_reference_template(
        project,
        data=template.read_bytes(),
        filename="第1讲-当前教案.docx",
    )
    binding = service.binding_patch(project, profile_id=profile["id"])
    project["_course_document_record"]["metadata"] = {"layout_binding": binding}
    state = service.state(project)

    assert profile["rules"]["template_mode"] == "reference_docx"
    assert profile["authority_source"]["role"] == "current_word_reference"
    assert Path(profile["template_path"]).is_file()
    assert state["binding"]["postprocess"] == "preserve_reference"
    assert state["profile"]["id"].startswith("lesson-plan-word-")
    assert state["template_catalog"]["same_type_count"] == 1
