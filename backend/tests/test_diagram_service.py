import copy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from agent_messenger import OpenClawEmptyResponseError
from services.diagram_service import DiagramService
from services.document_workspace_service import (
    DocumentVersionConflict,
    document_workspace_service,
)
from services.multi_document_service import MultiDocumentService


PROJECT = {
    "id": "project-diagram",
    "name": "图表测试项目",
    "enabled_modules": ["writing"],
    "document_spec": {"expected_chapters": 1},
}


@pytest.fixture
def diagram_service(tmp_path, monkeypatch):
    monkeypatch.setattr(document_workspace_service, "vault", tmp_path)
    monkeypatch.setattr(document_workspace_service, "_find_source_word", lambda project: None)
    source = tmp_path / "body.md"
    source.write_text("# 第一章 测试\n\n正文。\n", encoding="utf-8")
    PROJECT["document_spec"]["working_markdown"] = {"path": str(source)}

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    async def fake_ai(_agent_id, _prompt):
        return """{
          "summary": "统一节点样式",
          "rationale": "提高论文插图一致性",
          "risk_level": "low",
          "operations": [
            {"action": "apply_style", "cell_id": "problem", "attrs": {"body": {"fill": "#eef6ff"}}}
          ]
        }"""

    return DiagramService(
        session_factory=sessions,
        documents_service=MultiDocumentService(),
        ai_requester=fake_ai,
    )


def test_diagram_create_save_version_and_svg_export(diagram_service):
    created = diagram_service.create(
        PROJECT,
        {"title": "论文技术路线", "template_id": "thesis-roadmap"},
        "tester",
    )
    document_id = created["document"]["id"]
    assert created["diagram"]["revision"] == 1
    assert len(created["diagram"]["cells"]) == 10

    edited = copy.deepcopy(created["diagram"])
    edited["cells"][0]["label"] = "核心科学问题"
    saved = diagram_service.update_draft(
        PROJECT,
        document_id,
        {"expected_revision": 1, **edited},
        "tester",
    )
    assert saved["revision"] == 2
    assert saved["cells"][0]["cell_revision"] == 2
    diagram_service.create_version(
        PROJECT, document_id, {"label": "人工检查点"}, "tester"
    )
    assert len(diagram_service.list_versions(PROJECT, document_id)) == 2

    with pytest.raises(DocumentVersionConflict):
        diagram_service.update_draft(
            PROJECT,
            document_id,
            {"expected_revision": 1, **edited},
            "tester",
        )

    exported = diagram_service.export(PROJECT, document_id, "svg", "tester")
    assert exported.read_text(encoding="utf-8").startswith("<svg")


def test_svg_export_renders_multiline_labels(diagram_service):
    created = diagram_service.create(
        PROJECT,
        {
            "title": "多行图表",
            "cells": [{
                "id": "node-1",
                "type": "node",
                "x": 10,
                "y": 10,
                "width": 240,
                "height": 100,
                "label": "第一行\n第二行",
            }],
        },
        "tester",
    )
    exported = diagram_service.export(PROJECT, created["document"]["id"], "svg", "tester")
    svg = exported.read_text(encoding="utf-8")
    assert "<tspan" in svg
    assert "第一行" in svg
    assert "第二行" in svg


@pytest.mark.asyncio
async def test_diagram_ai_proposal_merges_by_cell_revision(diagram_service):
    target = diagram_service.documents_service.create_document(PROJECT, "论文正文", "rich_text")
    created = diagram_service.create(
        PROJECT,
        {"title": "系统架构", "template_id": "thesis-roadmap"},
        "tester",
    )
    document_id = created["document"]["id"]
    diagram_service.create_reference(
        PROJECT,
        document_id,
        {"target_kind": "rich_text", "target_document_id": target["id"]},
        "tester",
    )
    job = await diagram_service.submit_ai_job(
        PROJECT,
        document_id,
        {
            "client_request_id": "diagram-job-1",
            "instruction": "统一科学问题节点样式",
            "target_cell_ids": ["problem"],
        },
        "tester",
    )
    accepted = diagram_service.accept_proposal(
        PROJECT, document_id, job["proposal"]["id"], "tester"
    )
    assert accepted["proposal"]["status"] == "applied"
    problem = next(cell for cell in accepted["diagram"]["cells"] if cell["id"] == "problem")
    assert problem["attrs"]["body"]["fill"] == "#eef6ff"
    assert diagram_service.list_references(PROJECT, document_id)[0]["status"] == "update_available"


@pytest.mark.asyncio
async def test_diagram_ai_retries_once_after_empty_openclaw_response(diagram_service):
    attempts = []

    async def flaky_ai(_agent_id, prompt):
        attempts.append(prompt)
        if len(attempts) == 1:
            raise OpenClawEmptyResponseError("智能体本次未生成可审阅内容，请重试。")
        return """{
          "summary": "生成结构化节点",
          "rationale": "空响应后重试成功",
          "risk_level": "low",
          "operations": [
            {"action": "add_cell", "cell": {"id": "node-1", "type": "node", "shape": "rect", "x": 10, "y": 20, "width": 200, "height": 80, "label": "任务规划"}}
          ]
        }"""

    diagram_service.ai_requester = flaky_ai
    created = diagram_service.create(PROJECT, {"title": "空响应重试图"}, "tester")
    job = await diagram_service.submit_ai_job(
        PROJECT,
        created["document"]["id"],
        {
            "client_request_id": "diagram-empty-retry-1",
            "instruction": "生成任务规划节点",
        },
        "tester",
    )

    assert job["status"] == "succeeded"
    assert len(attempts) == 2
    assert "禁止返回 NO_REPLY" in attempts[1]
    assert job["proposal"]["operations"][0]["cell"]["type"] == "node"


def test_diagram_reference_is_marked_stale_after_new_revision(diagram_service):
    target = diagram_service.documents_service.create_document(PROJECT, "论文正文", "rich_text")
    created = diagram_service.create(PROJECT, {"title": "论文插图"}, "tester")
    document_id = created["document"]["id"]
    reference = diagram_service.create_reference(
        PROJECT,
        document_id,
        {
            "target_kind": "rich_text",
            "target_document_id": target["id"],
            "target_section_id": "section-1",
            "caption": "图 1 技术路线",
        },
        "tester",
    )
    assert reference["status"] == "current"

    diagram_service.update_draft(
        PROJECT,
        document_id,
        {"expected_revision": 1, **created["diagram"]},
        "tester",
    )
    references = diagram_service.list_references(PROJECT, document_id)
    assert references[0]["status"] == "update_available"


def test_diagram_reference_can_bind_an_existing_version(diagram_service):
    target = diagram_service.documents_service.create_document(PROJECT, "论文正文", "rich_text")
    created = diagram_service.create(PROJECT, {"title": "论文插图"}, "tester")
    document_id = created["document"]["id"]
    diagram_service.update_draft(
        PROJECT,
        document_id,
        {"expected_revision": 1, **created["diagram"]},
        "tester",
    )

    reference = diagram_service.create_reference(
        PROJECT,
        document_id,
        {
            "diagram_version": 1,
            "target_kind": "rich_text",
            "target_document_id": target["id"],
        },
        "tester",
    )

    assert reference["diagram_revision"] == 1
    assert reference["status"] == "update_available"


def test_publish_to_document_inserts_fixed_svg_and_caption(diagram_service):
    target = diagram_service.documents_service.create_document(PROJECT, "论文正文", "rich_text")
    created = diagram_service.create(
        PROJECT,
        {"title": "总体研究框架", "template_id": "thesis-roadmap"},
        "tester",
    )

    class CollaborationStub:
        def __init__(self):
            self.payload = None

        def get_state(self, _project, _document_id, _section_id=""):
            return {
                "document_revision": 4,
                "document": {
                    "type": "doc",
                    "content": [{
                        "type": "paragraph",
                        "attrs": {"blockId": "anchor", "blockRevision": 2},
                        "content": [{"type": "text", "text": "总体研究思路。"}],
                    }],
                },
            }

        def patch_draft(self, _project, _document_id, payload, _actor):
            self.payload = payload
            return {"document_revision": 5, "projection": {"status": "current"}}

    stub = CollaborationStub()
    diagram_service.collaboration_service = stub
    result = diagram_service.publish_to_document(
        PROJECT,
        created["document"]["id"],
        {
            "target_document_id": target["id"],
            "expected_document_revision": 4,
            "expected_diagram_revision": 1,
            "anchor_block_id": "anchor",
            "figure_label": "图1-1",
            "caption": "总体研究框架",
            "client_change_id": "publish-figure-1",
        },
        "tester",
    )

    assert result["document_revision"] == 5
    assert result["reference"]["status"] == "current"
    operations = stub.payload["operations"]
    image = next(row["node"] for row in operations if row["node"]["type"] == "image")
    caption = next(row["node"] for row in operations if row["node"]["type"] == "paragraph")
    assert image["attrs"]["src"].startswith("assets/")
    assert image["attrs"]["artifactLabel"] == "图1-1"
    assert caption["content"][0]["text"] == "图1-1 总体研究框架"
