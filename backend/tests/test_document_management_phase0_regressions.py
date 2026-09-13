from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from services.diagram_service import DiagramService
from services.document_workspace_service import document_workspace_service
from services.multi_document_service import MultiDocumentService


@pytest.fixture
def document_services(tmp_path, monkeypatch):
    monkeypatch.setattr(document_workspace_service, "vault", tmp_path)
    monkeypatch.setattr(document_workspace_service, "_find_source_word", lambda project: None)
    source = tmp_path / "body.md"
    source.write_text("# 第一章 测试\n\n正文。\n", encoding="utf-8")
    project = {
        "id": "project-document-phase0",
        "name": "文档管理阶段0测试",
        "enabled_modules": ["writing"],
        "document_spec": {
            "expected_chapters": 1,
            "working_markdown": {"path": str(source)},
        },
    }

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    documents = MultiDocumentService()
    diagrams = DiagramService(session_factory=sessions, documents_service=documents)
    return project, source, documents, diagrams


@pytest.mark.xfail(
    strict=True,
    reason="phase 1 must hydrate document summaries from authoritative diagram state",
)
def test_document_list_uses_authoritative_diagram_revision_and_counts(document_services):
    project, _source, documents, diagrams = document_services
    created = diagrams.create(
        project,
        {
            "title": "任务规划技术路线",
            "cells": [
                {"id": "n1", "type": "node", "label": "任务输入"},
                {"id": "n2", "type": "node", "label": "规划输出"},
                {"id": "e1", "type": "edge", "source": "n1", "target": "n2"},
            ],
        },
        "phase0",
    )

    listed = next(
        row
        for row in documents.list_documents(project)["documents"]
        if row["id"] == created["document"]["id"]
    )

    assert listed["revision"] == created["diagram"]["revision"]
    assert listed["stats"]["node_count"] == 2
    assert listed["stats"]["edge_count"] == 1


@pytest.mark.xfail(
    strict=True,
    reason="phase 1 must not mark a canonical document stale against itself",
)
def test_canonical_self_binding_remains_aligned_after_own_content_changes(document_services):
    project, _source, documents, _diagrams = document_services
    primary = documents.list_documents(project)["documents"][0]
    workspace = documents.rich_workspace(project, primary["id"])
    documents.update_document_metadata(
        project,
        primary["id"],
        {
            "structure_binding": {
                "mode": "canonical",
                "source_document_id": primary["id"],
                "source_version": f"v{primary['revision']}",
                "source_sha256": primary["source_checksum"],
                "status": "aligned",
                "mapped_items": 1,
                "unmapped_items": [],
                "changed_sections": [],
            }
        },
    )

    Path(workspace["working_markdown"]).write_text(
        "# 第一章 测试\n\n正文已更新。\n",
        encoding="utf-8",
    )
    refreshed = documents.get_document(project, primary["id"])

    assert refreshed["structure_binding"]["status"] == "aligned"
