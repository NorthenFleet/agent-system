import copy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.writing_collaboration import (
    PresentationAiJob,
    WritingAiJob,
    WritingAiMessage,
)
from services.document_workspace_service import DocumentWorkspaceError
from services.writing_workbench_service import (
    WritingWorkbenchConflict,
    WritingWorkbenchService,
    _public_error,
)


PROJECT = {"id": "project-1", "name": "测试项目", "enabled_modules": ["writing"]}


class FakeDocuments:
    def assert_writable(self, project, document_id):
        return {"id": document_id, "edit_policy": "editable"}

    def presentation_slide_proposal(
        self,
        project,
        document_id,
        slide,
        draft,
        instruction,
        agent_id,
    ):
        assert project["id"] == PROJECT["id"]
        return {
            "id": f"proposal-{document_id}-{slide}",
            "status": "succeeded",
            "slide": slide,
            "agent_id": agent_id,
            "summary": "已生成结构化PPT建议",
            "patch": {**copy.deepcopy(draft), "instruction": instruction},
        }


class FakeCollaboration:
    def __init__(self, sessions):
        self.sessions = sessions
        self.submissions = []
        self.cancelled = []

    def submit_ai_job(self, project, document_id, payload, actor):
        self.submissions.append(copy.deepcopy(payload))
        row = WritingAiJob(
            id="writing-job-1",
            project_id=project["id"],
            document_id=document_id,
            client_request_id=payload["client_request_id"],
            section_id=payload.get("section_id", ""),
            agent_id=payload["agent_id"],
            instruction=payload["instruction"],
            scope=payload["scope"],
            base_document_revision=3,
            target_blocks=[],
            selection=payload.get("selection") or {},
            evidence_ref_ids=[],
            risk_policy=payload.get("risk_policy") or {},
            status="queued",
            requested_by=actor,
            conversation_id=payload.get("conversation_id", ""),
            request_message_id=payload.get("request_message_id", ""),
            response_message_id=payload.get("response_message_id", ""),
        )
        with self.sessions() as session:
            session.add(row)
            session.commit()
        return {"id": row.id, "status": row.status}

    def cancel_ai_job(self, project, document_id, job_id):
        self.cancelled.append((project["id"], document_id, job_id))
        return {"id": job_id, "status": "cancelled"}


@pytest.fixture
def workbench():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    collaboration = FakeCollaboration(sessions)
    service = WritingWorkbenchService(
        session_factory=sessions,
        collaboration_service=collaboration,
        documents_service=FakeDocuments(),
    )
    return service, sessions, collaboration


def _preference(expected_revision=0):
    return {
        "expected_revision": expected_revision,
        "schema_version": 1,
        "preset": "comparison",
        "split_percent": 50,
        "maximized_pane": None,
        "panes": {
            "left": {"module": "document", "resource_id": "document-1"},
            "right": {"module": "presentation", "resource_id": "slides-1"},
        },
    }


def test_preference_uses_optimistic_revision_and_survives_service_restart(workbench):
    service, sessions, collaboration = workbench

    assert service.get_preference(PROJECT["id"], "user-1")["revision"] == 0
    saved = service.update_preference(PROJECT["id"], "user-1", _preference())
    assert saved["revision"] == 1
    assert saved["panes"]["right"]["module"] == "presentation"

    with pytest.raises(WritingWorkbenchConflict, match="当前修订 1"):
        service.update_preference(PROJECT["id"], "user-1", _preference())

    restarted = WritingWorkbenchService(
        session_factory=sessions,
        collaboration_service=collaboration,
        documents_service=FakeDocuments(),
    )
    restored = restarted.get_preference(PROJECT["id"], "user-1")
    assert restored["revision"] == 1
    assert restored["preset"] == "document_presentation"
    assert restored["schema_version"] == 3


def test_presentation_conversation_is_idempotent_and_persistent(workbench):
    service, sessions, collaboration = workbench
    conversation = service.create_conversation(
        PROJECT["id"], "user-1", {"title": "PPT协作", "agent_id": "presentation-editor"}
    )
    payload = {
        "client_message_id": "message-1",
        "agent_id": "presentation-editor",
        "content": "压缩这一页并保留证据边界",
        "target": {
            "kind": "presentation",
            "document_id": "slides-1",
            "slide": 4,
            "draft": {"title": "原始标题"},
        },
    }

    submitted = service.submit_message(
        PROJECT, "user-1", conversation["id"], payload
    )
    assert submitted["job"]["status"] == "succeeded"
    assert submitted["job"]["proposal"]["slide"] == 4

    replay = service.submit_message(PROJECT, "user-1", conversation["id"], payload)
    assert replay["idempotent_replay"] is True

    restarted = WritingWorkbenchService(
        session_factory=sessions,
        collaboration_service=collaboration,
        documents_service=FakeDocuments(),
    )
    messages = restarted.list_messages(PROJECT["id"], "user-1", conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["status"] == "succeeded"
    assert messages[1]["proposal_ids"] == ["proposal-slides-1-4"]
    restored_job = restarted.get_presentation_job(
        PROJECT["id"], "slides-1", submitted["job"]["id"]
    )
    assert restored_job["proposal"]["patch"]["title"] == "原始标题"
    with sessions() as session:
        assert session.query(PresentationAiJob).count() == 1
        assert session.query(WritingAiMessage).count() == 2


def test_document_message_binds_job_to_immutable_target_snapshot(workbench):
    service, sessions, collaboration = workbench
    conversation = service.create_conversation(
        PROJECT["id"], "user-1", {"title": "正文协作"}
    )
    target = {
        "kind": "document",
        "document_id": "document-1",
        "scope": "block",
        "section_id": "section-1",
        "block_id": "block-1",
        "block_revision": 7,
        "selection": {"text": "待润色内容"},
        "revision": 12,
    }
    submitted = service.submit_message(
        PROJECT,
        "user-1",
        conversation["id"],
        {
            "client_message_id": "document-message-1",
            "content": "学术润色",
            "agent_id": "ultra-magnus",
            "target": target,
        },
    )

    target["block_revision"] = 99
    assert collaboration.submissions[0]["block_revision"] == 7
    with sessions() as session:
        job = session.execute(select(WritingAiJob)).scalar_one()
        response = session.get(WritingAiMessage, submitted["response_message_id"])
        assert job.conversation_id == conversation["id"]
        assert job.response_message_id == response.id
        assert response.job_kind == "document"
        assert response.job_id == job.id
        assert response.target_context["block_revision"] == 7


def test_conversation_access_is_scoped_to_owner(workbench):
    service, _, _ = workbench
    conversation = service.create_conversation(PROJECT["id"], "user-1", {})

    with pytest.raises(DocumentWorkspaceError, match="会话不存在"):
        service.list_messages(PROJECT["id"], "user-2", conversation["id"])


def test_public_error_hides_openclaw_runtime_metadata():
    raw = (
        'OpenClaw 未返回可显示文本：{"runId":"sensitive",'
        '"result":{"meta":{"sessionFile":"/Users/private/session.jsonl"}}}'
    )

    message = _public_error(RuntimeError(raw))

    assert message == "智能体本次未生成可审阅内容，请重试。"
    assert "runId" not in message
    assert "sessionFile" not in message
