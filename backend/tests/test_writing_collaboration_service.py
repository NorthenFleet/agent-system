import asyncio
import copy
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.writing_collaboration import (
    WritingAiJob,
    WritingAiProposal,
    WritingChangeSet,
    WritingDocumentState,
    WritingDocumentVersion,
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
