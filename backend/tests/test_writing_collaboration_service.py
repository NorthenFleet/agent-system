import asyncio
import copy
import hashlib
import json
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.writing_collaboration import (
    WritingAiJob,
    WritingAiMessage,
    WritingAiProposal,
    WritingChangeSet,
    WritingChangeEvent,
    WritingDocumentState,
    WritingDocumentVersion,
    WritingEvidenceRef,
    WritingJarvisRun,
    WritingResearchEvaluation,
    WritingResearchIteration,
)
from services.document_workspace_service import DocumentVersionConflict, DocumentWorkspaceError
from services.structured_document_service import StructuredDocumentCodec
from services.writing_collaboration_service import (
    WritingCollaborationDisabled,
    WritingCollaborationService,
    _now,
)


MARKDOWN = """# 第一章

第一段。

第二段。
"""


class FakeWorkspace:
    def __init__(self):
        self.markdown = MARKDOWN
        self.version = 1
        self.authority = "markdown"
        self.projection_error = ""
        self.fail_projection = False

    def fulltext(self, _project):
        return {"content": self.markdown, "version": self.version}

    def ensure_workspace(self, _project):
        return {"structured_projection_revision": self.version}

    def section(self, _project, section_id):
        if section_id != "section-01-first":
            raise RuntimeError("missing section")
        return {"id": section_id, "title": "第一章", "order_index": 0, "kind": "chapter"}

    def apply_structured_projection(self, _project, markdown, document_revision, _actor, **_kwargs):
        if self.fail_projection:
            raise RuntimeError("projection failed")
        self.markdown = markdown
        self.version = document_revision
        self.authority = "structured_json"
        return {"version": document_revision, "projection_status": "current"}

    def mark_structured_projection_stale(self, _project, _revision, error):
        self.projection_error = error


class FakeDocuments:
    def rich_project(self, project, document_id):
        return {**project, "_document_id": document_id, "_document_title": "测试正文"}


def _service(ai_response=None, *, initialize=True, allow_non_postgres_writes=True):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    workspace = FakeWorkspace()

    async def requester(_agent_id, _prompt):
        return ai_response or '{"summary":"润色","operations":[]}'

    service = WritingCollaborationService(
        session_factory=sessions,
        codec=StructuredDocumentCodec(),
        workspace_service=workspace,
        documents_service=FakeDocuments(),
        ai_requester=requester,
        allow_non_postgres_writes=allow_non_postgres_writes,
    )
    if initialize:
        service.ensure_state({"id": "project-1", "name": "项目"}, "document-1")
    return service, sessions, workspace


def _paragraphs(state):
    return [row for row in state["document"]["content"] if row["type"] == "paragraph"]


def _replace_text(block, text):
    value = copy.deepcopy(block)
    value["content"] = [{"type": "text", "text": text}]
    return value


def test_initialization_assigns_stable_ids_and_switches_only_projection_authority():
    service, sessions, workspace = _service(initialize=False)
    project = {"id": "project-1", "name": "项目"}

    service.ensure_state(project, "document-1")
    state = service.get_state(project, "document-1", "section-01-first")

    assert state["revision"] == 1
    assert workspace.authority == "structured_json"
    assert "第一段。" in workspace.markdown
    ids = [row["attrs"]["blockId"] for row in state["document"]["content"]]
    assert len(ids) == len(set(ids))
    with sessions() as session:
        stored = session.execute(select(WritingDocumentState)).scalar_one()
        assert stored.projection_status == "current"
        assert stored.projection_revision == stored.document_revision == 1


def test_title_derived_section_id_is_remapped_to_stable_heading_id():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}

    state = service.get_state(project, "document-1", "section-01-renamed-heading")

    assert state["section"]["legacy_id"] == "section-01-renamed-heading"
    assert state["section"]["id"].startswith("block-")
    assert state["document"]["content"][0]["attrs"]["blockId"] == state["section"]["id"]


def test_runtime_version_lineage_uses_previous_existing_revision():
    service, sessions, _ = _service()
    with sessions() as session:
        state = session.execute(select(WritingDocumentState)).scalar_one()
        state.document_revision = 8
        service._create_version_row(
            session,
            state,
            label="sparse checkpoint",
            reason="manual",
            actor_type="human",
            actor_id="admin",
        )
        session.commit()
        version = session.execute(select(WritingDocumentVersion).where(
            WritingDocumentVersion.document_revision == 8,
        )).scalar_one()
        assert version.parent_revision == 1


def test_authority_import_advances_past_a_newer_existing_projection():
    service, sessions, workspace = _service()
    project = {"id": "project-1", "name": "项目"}
    workspace.version = 5

    migrated = service.replace_authority_from_markdown(
        project,
        "document-1",
        "# 第一章\n\n来自 Word 的权威正文。\n",
        label="Word 母稿导入",
        actor="migration",
    )

    assert migrated["revision"] == 6
    assert workspace.version == 6
    with sessions() as session:
        state = session.execute(select(WritingDocumentState)).scalar_one()
        assert state.document_revision == 6
        assert state.projection_revision == 6
        event = session.execute(select(WritingChangeEvent)).scalar_one()
        assert event.client_change_id.startswith("authority-import-r6-")


def test_fidelity_import_marks_the_supplied_markdown_projection_current():
    service, sessions, workspace = _service()
    project = {"id": "project-1", "name": "项目"}
    markdown = "# 第一章\n\n$$\n\\Phi_A=1\n$$ （1）\n"
    document = service.codec.from_markdown(markdown, namespace="fidelity-test")

    response = service.replace_authority_from_document(
        project,
        "document-1",
        document,
        markdown,
        label="内容高保真结构迁移",
        actor="test-migration",
    )

    assert response["projection"]["status"] == "current"
    assert workspace.markdown == markdown
    with sessions() as session:
        state = session.execute(select(WritingDocumentState)).scalar_one()
        assert state.schema_version == "tiptap-json-v2"
        assert state.projection_status == "current"
        assert state.projection_revision == state.document_revision == response["revision"]

def test_get_is_side_effect_free_before_explicit_initialization():
    service, sessions, workspace = _service(initialize=False)

    with pytest.raises(DocumentWorkspaceError, match="尚未启用人机双写"):
        service.get_state({"id": "project-1"}, "document-1")

    assert workspace.authority == "markdown"
    with sessions() as session:
        assert session.execute(select(WritingDocumentState)).scalar_one_or_none() is None


def test_sqlite_writes_fail_closed_without_explicit_test_override():
    service, _, _ = _service(
        initialize=False,
        allow_non_postgres_writes=False,
    )

    with pytest.raises(WritingCollaborationDisabled, match="PostgreSQL"):
        service.ensure_state({"id": "project-1"}, "document-1")


def test_different_blocks_merge_even_when_document_revision_is_stale():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first, second = _paragraphs(state)

    service.patch_draft(project, "document-1", {
        "base_document_revision": 1,
        "client_change_id": "human-a",
        "section_id": "section-01-first",
        "changes": [{
            "op": "upsert",
            "block_id": first["attrs"]["blockId"],
            "expected_block_revision": 1,
            "node": _replace_text(first, "人工修改第一段。"),
        }],
    }, "human")
    merged = service.patch_draft(project, "document-1", {
        "base_document_revision": 1,
        "client_change_id": "ai-b",
        "section_id": "section-01-first",
        "changes": [{
            "op": "upsert",
            "block_id": second["attrs"]["blockId"],
            "expected_block_revision": 1,
            "node": _replace_text(second, "AI 修改第二段。"),
        }],
    }, "ai")

    text = service.codec.to_markdown(merged["document"])
    assert "人工修改第一段。" in text
    assert "AI 修改第二段。" in text
    assert merged["revision"] == 3


def test_same_block_stale_change_never_overwrites_current_text():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    block_id = first["attrs"]["blockId"]

    service.patch_draft(project, "document-1", {
        "base_document_revision": 1,
        "client_change_id": "first-writer",
        "changes": [{
            "op": "upsert",
            "block_id": block_id,
            "expected_block_revision": 1,
            "node": _replace_text(first, "当前权威内容。"),
        }],
    }, "human")

    with pytest.raises(DocumentVersionConflict):
        service.patch_draft(project, "document-1", {
            "base_document_revision": 1,
            "client_change_id": "stale-writer",
            "changes": [{
                "op": "upsert",
                "block_id": block_id,
                "expected_block_revision": 1,
                "node": _replace_text(first, "不应覆盖的旧内容。"),
            }],
        }, "human")
    current = service.get_state(project, "document-1", "section-01-first")
    assert "当前权威内容。" in service.codec.to_markdown(current["document"])
    assert "不应覆盖的旧内容。" not in service.codec.to_markdown(current["document"])


def test_stale_upsert_never_resurrects_a_deleted_block():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    block_id = first["attrs"]["blockId"]

    service.patch_draft(project, "document-1", {
        "base_document_revision": state["revision"],
        "client_change_id": "delete-first",
        "changes": [{
            "op": "delete",
            "block_id": block_id,
            "expected_block_revision": first["attrs"]["blockRevision"],
        }],
    }, "human")

    with pytest.raises(DocumentVersionConflict, match="重新修改"):
        service.patch_draft(project, "document-1", {
            "base_document_revision": state["revision"],
            "client_change_id": "stale-resurrection",
            "changes": [{
                "op": "upsert",
                "block_id": block_id,
                "expected_block_revision": first["attrs"]["blockRevision"],
                "node": _replace_text(first, "不应复活。"),
            }],
        }, "human")

    current = service.get_state(project, "document-1", "section-01-first")
    assert block_id not in {row["attrs"]["blockId"] for row in current["document"]["content"]}


def test_move_after_persists_explicit_block_order():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    heading, first, second = state["document"]["content"]

    moved = service.patch_draft(project, "document-1", {
        "base_document_revision": state["revision"],
        "client_change_id": "move-second-before-first",
        "changes": [{
            "op": "move_after",
            "block_id": second["attrs"]["blockId"],
            "expected_block_revision": second["attrs"]["blockRevision"],
            "after_block_id": heading["attrs"]["blockId"],
        }],
    }, "human")

    assert [service.codec.block_markdown(row).strip() for row in moved["document"]["content"]] == [
        "# 第一章", "第二段。", "第一段。"
    ]


def test_invalid_nested_editor_node_is_rejected_without_write():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    invalid = copy.deepcopy(first)
    invalid["content"] = [{"type": "unsupportedInline", "text": "危险内容"}]

    with pytest.raises(DocumentWorkspaceError, match="不符合编辑器契约"):
        service.patch_draft(project, "document-1", {
            "base_document_revision": state["revision"],
            "client_change_id": "invalid-node",
            "changes": [{
                "op": "upsert",
                "block_id": first["attrs"]["blockId"],
                "expected_block_revision": first["attrs"]["blockRevision"],
                "node": invalid,
            }],
        }, "human")
    assert "危险内容" not in service.codec.to_markdown(
        service.get_state(project, "document-1", "section-01-first")["document"]
    )


def test_client_change_id_is_idempotent():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    payload = {
        "base_document_revision": 1,
        "client_change_id": "same-request",
        "changes": [{
            "op": "upsert",
            "block_id": first["attrs"]["blockId"],
            "expected_block_revision": 1,
            "node": _replace_text(first, "只保存一次。"),
        }],
    }

    first_result = service.patch_draft(project, "document-1", payload, "human")
    replay = service.patch_draft(project, "document-1", payload, "human")

    assert first_result["revision"] == replay["revision"] == 2
    assert replay["idempotent_replay"] is True


def test_ai_client_request_id_is_idempotent():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    payload = {
        "client_request_id": "same-ai-request",
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": first["attrs"]["blockId"],
        "instruction": "润色",
    }

    first_job = service.submit_ai_job(project, "document-1", payload, "human")
    replay = service.submit_ai_job(project, "document-1", payload, "human")

    assert replay["id"] == first_job["id"]


def test_ai_job_database_claim_allows_only_one_worker():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    calls = 0

    async def requester(_agent, _prompt):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return '{"summary":"无修改","operations":[]}'

    service.ai_requester = requester
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": first["attrs"]["blockId"],
        "instruction": "检查",
    }, "human")

    async def run_both():
        await asyncio.gather(
            service.process_ai_job(project, "document-1", job["id"], worker_id="worker-a"),
            service.process_ai_job(project, "document-1", job["id"], worker_id="worker-b"),
        )

    asyncio.run(run_both())
    assert calls == 1
    assert service.get_ai_job(project, "document-1", job["id"])["attempt_count"] == 1


def test_ai_job_includes_bounded_prior_conversation_without_expanding_scope():
    project = {"id": "project-1", "name": "项目"}
    service, sessions, _ = _service()
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    captured: list[str] = []

    async def requester(_agent, prompt):
        captured.append(prompt)
        return '{"summary":"无修改","operations":[]}'

    service.ai_requester = requester
    with sessions() as session:
        session.add_all([
            WritingAiMessage(
                id="old-user", project_id="project-1", conversation_id="conversation-1",
                role="user", content="上一轮请保留课程编号。", status="completed",
                client_message_id="old-user-message",
            ),
            WritingAiMessage(
                id="old-assistant", project_id="project-1", conversation_id="conversation-1",
                role="assistant", content="会保留课程编号，仅修改指定段落。", status="completed",
                client_message_id="old-assistant-message",
            ),
        ])
        session.commit()
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": first["attrs"]["blockId"],
        "instruction": "继续润色本段。",
        "conversation_id": "conversation-1",
    }, "human")

    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))

    assert captured
    assert "上一轮请保留课程编号" in captured[0]
    assert "当前指令与下列作用范围优先" in captured[0]
    assert f"BLOCK {first['attrs']['blockId']}" in captured[0]


def test_expired_ai_job_lease_can_be_recovered_by_new_worker():
    service, sessions, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": first["attrs"]["blockId"],
        "instruction": "检查",
    }, "human")
    with sessions() as session:
        row = session.get(WritingAiJob, job["id"])
        row.status = "running"
        row.worker_id = "dead-worker"
        row.lease_expires_at = _now() - timedelta(seconds=1)
        session.commit()

    asyncio.run(service.process_ai_job(
        project, "document-1", job["id"], worker_id="recovery-worker"
    ))

    recovered = service.get_ai_job(project, "document-1", job["id"])
    assert recovered["status"] == "failed"
    assert recovered["error"] == "AI 未返回可执行操作"
    assert recovered["attempt_count"] == 1


def test_ai_auto_applies_unchanged_block_and_conflicts_on_changed_block():
    project = {"id": "project-1", "name": "项目"}
    service, sessions, _ = _service()
    initial = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(initial)[0]
    first_id = first["attrs"]["blockId"]
    original_markdown = service.codec.block_markdown(first)
    formatting_only = original_markdown.strip().rstrip("。！？.!?") + "！"
    response = {
        "summary": "润色完成",
        "operations": [{
            "block_id": first_id,
            "action": "replace",
            "replacement_markdown": formatting_only,
            "summary": "润色段落",
            "rationale": "减少冗余",
        }],
    }
    service.ai_requester = lambda _agent, _prompt: _async_value(response)
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": first_id,
        "instruction": "润色",
    }, "human")
    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))
    completed = service.get_ai_job(project, "document-1", job["id"])
    assert completed["status"] == "applied"
    assert formatting_only in service.codec.to_markdown(
        service.get_state(project, "document-1", "section-01-first")["document"]
    )

    current = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(current)[0]
    block_id = block["attrs"]["blockId"]
    conflict_response = {
        "summary": "再次润色",
        "operations": [{
            "block_id": block_id,
            "action": "replace",
            "replacement_markdown": "AI 的过期建议。",
            "summary": "过期建议",
            "rationale": "测试冲突",
        }],
    }
    service.ai_requester = lambda _agent, _prompt: _async_value(conflict_response)
    stale_job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": block_id,
        "instruction": "润色",
    }, "human")
    service.patch_draft(project, "document-1", {
        "base_document_revision": current["revision"],
        "client_change_id": "human-during-ai",
        "changes": [{
            "op": "upsert",
            "block_id": block_id,
            "expected_block_revision": block["attrs"]["blockRevision"],
            "node": _replace_text(block, "AI 运行期间的人工修改。"),
        }],
    }, "human")
    asyncio.run(service.process_ai_job(project, "document-1", stale_job["id"]))

    conflicted = service.get_ai_job(project, "document-1", stale_job["id"])
    assert conflicted["status"] == "conflicted"
    assert conflicted["proposals"][0]["status"] == "pending"
    assert "AI 运行期间的人工修改。" in service.codec.to_markdown(
        service.get_state(project, "document-1", "section-01-first")["document"]
    )
    with sessions() as session:
        assert session.execute(select(WritingAiProposal)).scalars().all()
        assert session.execute(select(WritingAiJob)).scalars().all()


def test_semantic_rewrite_stays_in_review_even_when_instruction_says_polish():
    project = {"id": "project-1", "name": "项目"}
    service, _, _ = _service()
    initial = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(initial)[0]
    response = {
        "summary": "润色完成",
        "operations": [{
            "block_id": block["attrs"]["blockId"],
            "action": "replace",
            "replacement_markdown": "新增了原文没有的实质性判断。",
            "summary": "改写段落",
            "rationale": "语义发生变化",
        }],
    }
    service.ai_requester = lambda _agent, _prompt: _async_value(response)
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": block["attrs"]["blockId"],
        "instruction": "润色",
    }, "human")

    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))

    completed = service.get_ai_job(project, "document-1", job["id"])
    assert completed["status"] == "review_required"
    assert completed["proposals"][0]["risk_level"] == "medium"
    assert completed["proposals"][0]["approval_required"] is True


def test_ai_cannot_auto_apply_one_block_as_multiple_nodes():
    project = {"id": "project-1", "name": "项目"}
    service, _, workspace = _service(initialize=False)
    workspace.markdown = "# 第一章\n\n甲 乙\n"
    service.ensure_state(project, "document-1")
    initial = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(initial)[0]
    service.ai_requester = lambda _agent, _prompt: _async_value({
        "summary": "调整空白",
        "operations": [{
            "block_id": block["attrs"]["blockId"],
            "action": "replace",
            "replacement_markdown": "甲\n\n乙",
            "summary": "拆分段落",
            "rationale": "测试结构边界",
        }],
    })
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": block["attrs"]["blockId"],
        "instruction": "润色",
    }, "human")

    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))

    completed = service.get_ai_job(project, "document-1", job["id"])
    assert completed["status"] == "review_required"
    assert completed["proposals"][0]["risk_level"] == "high"
    assert completed["proposals"][0]["approval_required"] is True


def test_sign_change_is_not_treated_as_formatting_only():
    project = {"id": "project-1", "name": "项目"}
    service, _, workspace = _service(initialize=False)
    workspace.markdown = "# 第一章\n\n温度为 -5。\n"
    service.ensure_state(project, "document-1")
    initial = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(initial)[0]
    service.ai_requester = lambda _agent, _prompt: _async_value({
        "summary": "润色完成",
        "operations": [{
            "block_id": block["attrs"]["blockId"],
            "action": "replace",
            "replacement_markdown": "温度为 5。",
            "summary": "调整格式",
            "rationale": "测试符号变化",
        }],
    })
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": block["attrs"]["blockId"],
        "instruction": "润色",
    }, "human")

    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))

    completed = service.get_ai_job(project, "document-1", job["id"])
    assert completed["status"] == "review_required"
    assert completed["proposals"][0]["approval_required"] is True


def test_evidence_sensitive_ai_change_requires_approval_without_concurrency_conflict():
    project = {"id": "project-1", "name": "项目"}
    service, sessions, _ = _service()
    initial = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(initial)[0]
    response = {
        "summary": "补充实验结论",
        "operations": [{
            "block_id": block["attrs"]["blockId"],
            "action": "replace",
            "replacement_markdown": "实验结果表明任务成功率提升 20%。",
            "summary": "补充实验结论",
            "rationale": "绑定实验结果",
        }],
    }
    service.ai_requester = lambda _agent, _prompt: _async_value(response)
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": block["attrs"]["blockId"],
        "instruction": "补充实验结论",
    }, "human")

    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))

    completed = service.get_ai_job(project, "document-1", job["id"])
    assert completed["status"] == "review_required"
    assert completed["proposals"][0]["approval_required"] is True
    assert completed["proposals"][0]["requires_rebase"] is False
    assert "实验结果表明" not in service.codec.to_markdown(
        service.get_state(project, "document-1", "section-01-first")["document"]
    )
    with sessions() as session:
        change_set = session.execute(select(WritingChangeSet)).scalar_one()
        assert change_set.status == "review_required"
        assert change_set.evidence_ref_ids == []


def test_approved_research_candidate_applies_exact_text_and_creates_revision(tmp_path):
    project = {"id": "project-1", "name": "项目"}
    service, sessions, workspace = _service()
    state = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(state)[0]
    block_id = block["attrs"]["blockId"]
    operation = {
        "op": "replace_text",
        "block_id": block_id,
        "old_text": "第一段。",
        "new_text": "第一段采用更保守的表述。",
        "reason": "移除未经支持的具体限定",
    }
    candidate_payload = {
        "schema": "writing.literature_candidate.v1",
        "section_id": "section-01-first",
        "operations": [operation],
        "candidate_section_nodes": [block],
    }
    artifact = tmp_path / "candidate.json"
    artifact.write_text(json.dumps(candidate_payload, ensure_ascii=False), encoding="utf-8")

    with sessions() as session:
        run = WritingJarvisRun(
            id="run-research-1",
            project_id="project-1",
            document_id="document-1",
            run_type="literature_review_optimization",
            status="completed",
            idempotency_key="run-research-1",
        )
        change_set = WritingChangeSet(
            id="changeset-research-1",
            project_id="project-1",
            document_id="document-1",
            base_revision=1,
            operations=[operation],
            evidence_ref_ids=[],
            risk_level="high",
            approval_policy="research_candidate",
            status="review_required",
            idempotency_key="changeset-research-1",
            summary="研究候选",
        )
        iteration = WritingResearchIteration(
            id="iteration-research-1",
            project_id="project-1",
            document_id="document-1",
            run_id=run.id,
            iteration_no=1,
            base_revision=1,
            base_section_sha256="a" * 64,
            candidate_sha256="b" * 64,
            candidate_payload=candidate_payload,
            candidate_artifact_path=str(artifact),
            status="review_required",
            change_set_id=change_set.id,
        )
        evaluation = WritingResearchEvaluation(
            id="evaluation-research-1",
            iteration_id=iteration.id,
            evaluator_version="literature-candidate-v1",
            hard_gates={"scope_confined_to_section": True, "body_write_operations": 0},
            dimension_scores={},
            total_score=60,
            baseline_delta=5,
            decision="kept",
            reasons=["test"],
            input_sha256="c" * 64,
        )
        session.add_all([run, change_set, iteration, evaluation])
        session.commit()

    accepted = service.accept_research_change_set(
        project, "document-1", "changeset-research-1", "admin"
    )

    assert accepted["revision"] == 2
    assert "第一段采用更保守的表述。" in workspace.markdown
    with sessions() as session:
        stored_change_set = session.get(WritingChangeSet, "changeset-research-1")
        stored_iteration = session.get(WritingResearchIteration, "iteration-research-1")
        event = session.execute(select(WritingChangeEvent).where(
            WritingChangeEvent.source == "research-candidate-accept"
        )).scalar_one()
        assert stored_change_set.status == "approved"
        assert stored_change_set.result_revision == 2
        assert stored_iteration.status == "kept"
        assert event.document_revision == 2


def test_research_candidate_rejects_missing_mixed_evidence_category(tmp_path):
    project = {"id": "project-1", "name": "项目"}
    service, sessions, _workspace = _service()
    state = service.get_state(project, "document-1", "section-01-first")
    block = _paragraphs(state)[0]
    operation = {
        "op": "replace_text",
        "block_id": block["attrs"]["blockId"],
        "old_text": "第一段。",
        "new_text": "第一段采用联合证据限定。",
        "reason": "联合证据约束",
    }
    evidence_file = tmp_path / "paper.json"
    evidence_file.write_bytes(b"paper")
    evidence_sha = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
    candidate_payload = {
        "schema": "writing.literature_candidate.v1",
        "section_id": "section-01-first",
        "operations": [operation],
        "evidence_ref_ids": ["evidence-paper"],
        "required_evidence_categories": ["experiment", "literature"],
        "selected_evidence_categories": ["literature"],
        "candidate_section_nodes": [block],
    }
    artifact = tmp_path / "mixed-candidate.json"
    artifact.write_text(json.dumps(candidate_payload, ensure_ascii=False), encoding="utf-8")

    with sessions() as session:
        run = WritingJarvisRun(
            id="run-mixed-evidence",
            project_id="project-1",
            document_id="document-1",
            run_type="literature_review_optimization",
            status="completed",
            idempotency_key="run-mixed-evidence",
        )
        evidence = WritingEvidenceRef(
            id="evidence-paper",
            project_id="project-1",
            document_id="document-1",
            source_system="journal",
            source_record_id="paper-1",
            artifact_path=str(evidence_file),
            artifact_sha256=evidence_sha,
            perspective_scope="paper",
            evidence_level="diagnostic",
            evidence_kind="literature",
            source_quality="peer_reviewed",
            support_role="supports",
            directness="direct",
            immutable=True,
        )
        change_set = WritingChangeSet(
            id="changeset-mixed-evidence",
            project_id="project-1",
            document_id="document-1",
            base_revision=1,
            operations=[operation],
            evidence_ref_ids=[evidence.id],
            risk_level="high",
            approval_policy="research_candidate",
            status="review_required",
            idempotency_key="changeset-mixed-evidence",
        )
        iteration = WritingResearchIteration(
            id="iteration-mixed-evidence",
            project_id="project-1",
            document_id="document-1",
            run_id=run.id,
            iteration_no=1,
            base_revision=1,
            base_section_sha256="a" * 64,
            candidate_sha256="b" * 64,
            candidate_payload=candidate_payload,
            candidate_artifact_path=str(artifact),
            status="review_required",
            change_set_id=change_set.id,
        )
        evaluation = WritingResearchEvaluation(
            id="evaluation-mixed-evidence",
            iteration_id=iteration.id,
            evaluator_version="literature-candidate-v1",
            hard_gates={"evidence_policy_satisfied": True, "body_write_operations": 0},
            dimension_scores={},
            total_score=60,
            baseline_delta=5,
            decision="kept",
            reasons=["test"],
            input_sha256="c" * 64,
        )
        session.add_all([run, evidence, change_set, iteration, evaluation])
        session.commit()

    with pytest.raises(DocumentWorkspaceError, match="证据约束已变化"):
        service.accept_research_change_set(
            project, "document-1", "changeset-mixed-evidence", "admin"
        )


def test_invalid_ai_response_fails_without_changing_document():
    service, _, _ = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    before = service.codec.to_markdown(state["document"])

    async def invalid(_agent, _prompt):
        return "这不是 JSON"

    service.ai_requester = invalid
    job = service.submit_ai_job(project, "document-1", {
        "agent_id": "ultra-magnus",
        "scope": "block",
        "block_id": first["attrs"]["blockId"],
        "instruction": "润色",
    }, "human")
    asyncio.run(service.process_ai_job(project, "document-1", job["id"]))

    failed = service.get_ai_job(project, "document-1", job["id"])
    assert failed["status"] == "failed"
    assert "有效 JSON" in failed["error"]
    assert service.codec.to_markdown(
        service.get_state(project, "document-1", "section-01-first")["document"]
    ) == before


def test_projection_failure_keeps_json_authority_stale_and_blocks_export_preparation():
    service, _, workspace = _service()
    project = {"id": "project-1", "name": "项目"}
    state = service.get_state(project, "document-1", "section-01-first")
    first = _paragraphs(state)[0]
    workspace.fail_projection = True

    result = service.patch_draft(project, "document-1", {
        "base_document_revision": state["revision"],
        "client_change_id": "projection-failure",
        "changes": [{
            "op": "upsert",
            "block_id": first["attrs"]["blockId"],
            "expected_block_revision": first["attrs"]["blockRevision"],
            "node": _replace_text(first, "数据库中仍然保留的正文。"),
        }],
    }, "human")

    assert result["projection"]["status"] == "stale"
    assert "数据库中仍然保留的正文。" in service.codec.to_markdown(result["document"])
    with pytest.raises(DocumentWorkspaceError, match="投影重建失败"):
        service.ensure_projection_current(project, "document-1")


async def _async_value(payload):
    import json

    return json.dumps(payload, ensure_ascii=False)
