import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.writing_collaboration import (
    WritingAiJob,
    WritingAiProposal,
    WritingChangeSet,
    WritingDocumentState,
)
from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceError,
)
from services.word_addin_bridge_service import WordAddinBridgeService


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture()
def bridge():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            WritingDocumentState.__table__,
            WritingAiJob.__table__,
            WritingAiProposal.__table__,
            WritingChangeSet.__table__,
        ],
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    original = "原始普通段落。"
    replacement = "经人工确认的普通段落。"
    with sessions() as session:
        session.add(
            WritingDocumentState(
                project_id="project-1",
                document_id="document-1",
                document_revision=7,
                schema_version=2,
                content_json={
                    "type": "doc",
                    "content": [{
                        "type": "paragraph",
                        "attrs": {"blockId": "block-1", "blockRevision": 3},
                        "content": [{"type": "text", "text": original}],
                    }],
                },
                content_sha256="1" * 64,
                approved_revision=6,
                published_revision=5,
                projection_revision=7,
                projection_status="current",
            )
        )
        job = WritingAiJob(
            id="job-1",
            project_id="project-1",
            document_id="document-1",
            client_request_id="request-1",
            agent_id="ultra-magnus",
            instruction="优化当前段落",
            scope="selection",
            base_document_revision=7,
            target_blocks=[],
            selection={"text": original, "text_sha256": _sha(original), "block_id": "block-1"},
            risk_policy={"allow_auto_draft": False},
            status="review_required",
        )
        proposal = WritingAiProposal(
            id="proposal-1",
            job_id=job.id,
            project_id="project-1",
            document_id="document-1",
            block_id="block-1",
            operation_type="replace",
            base_block_revision=3,
            base_block_sha256="2" * 64,
            replacement_markdown=replacement,
            replacement_json=[
                {
                    "type": "paragraph",
                    "attrs": {"blockId": "block-1", "blockRevision": 4},
                    "content": [{"type": "text", "text": replacement}],
                }
            ],
            risk_level="medium",
            approval_required=True,
            concurrency_status="unchanged",
            status="pending",
        )
        session.add_all(
            [
                job,
                proposal,
                WritingChangeSet(
                    id="changeset-1",
                    project_id="project-1",
                    document_id="document-1",
                    base_revision=7,
                    proposal_id=proposal.id,
                    operations=[{"op": "replace", "block_id": "block-1"}],
                    risk_level="medium",
                    status="review_required",
                    idempotency_key="proposal:proposal-1",
                ),
            ]
        )
        session.commit()
    return WordAddinBridgeService(sessions, token_secret="test-secret"), sessions, original, replacement


def test_context_keeps_structured_document_authoritative(bridge):
    service, _sessions, _original, _replacement = bridge

    result = service.context("project-1", "document-1")

    assert result["mode"] == "candidate_only"
    assert result["revision"] == 7
    assert result["structured_authority_unchanged"] is True
    assert result["allowed_operations"] == ["replace_plain_paragraph"]


def test_resolve_paragraph_requires_an_exact_unique_stable_block(bridge):
    service, sessions, original, _replacement = bridge

    result = service.resolve_paragraph(
        "project-1", "document-1", text=original, text_sha256=_sha(original)
    )
    assert result == {
        "block_id": "block-1",
        "block_revision": 3,
        "revision": 7,
        "content_sha256": "1" * 64,
        "match_count": 1,
        "match_mode": "exact_unique_plain_paragraph",
    }

    with sessions() as session:
        state = session.query(WritingDocumentState).filter_by(
            project_id="project-1", document_id="document-1"
        ).one()
        state.content_json = {
            "type": "doc",
            "content": [state.content_json["content"][0], state.content_json["content"][0]],
        }
        session.commit()
    with pytest.raises(DocumentWorkspaceError, match="不唯一"):
        service.resolve_paragraph(
            "project-1", "document-1", text=original, text_sha256=_sha(original)
        )


def test_validate_and_record_word_candidate_without_advancing_revision(bridge):
    service, sessions, original, replacement = bridge
    validated = service.validate_apply(
        "project-1",
        "document-1",
        "changeset-1",
        base_revision=7,
        current_paragraph_sha256=_sha(original),
        office_session_id="office-session-1",
        document_session_fingerprint=_sha("word-document-1"),
    )

    assert validated["replacement_text"] == replacement
    assert validated["replacement_sha256"] == _sha(replacement)
    receipt = service.record_receipt(
        "project-1",
        "document-1",
        "changeset-1",
        apply_token=validated["apply_token"],
        before_sha256=_sha(original),
        after_sha256=_sha(replacement),
        office_session_id="office-session-1",
        document_session_fingerprint=_sha("word-document-1"),
        actor="admin",
    )
    replay = service.record_receipt(
        "project-1",
        "document-1",
        "changeset-1",
        apply_token=validated["apply_token"],
        before_sha256=_sha(original),
        after_sha256=_sha(replacement),
        office_session_id="office-session-1",
        document_session_fingerprint=_sha("word-document-1"),
        actor="admin",
    )

    assert receipt["status"] == "word_candidate_applied"
    assert len(receipt["status"]) <= 24
    assert receipt["current_revision"] == 7
    assert receipt["structured_authority_unchanged"] is True
    assert replay["idempotent_replay"] is True
    with sessions() as session:
        state = session.query(WritingDocumentState).filter_by(
            project_id="project-1", document_id="document-1"
        ).one()
        change_set = session.get(WritingChangeSet, "changeset-1")
        assert state.document_revision == 7
        assert change_set.result_revision == 0
        assert change_set.operations[-1]["op"] == "word_application_receipt"


def test_validate_rejects_stale_document_or_word_paragraph(bridge):
    service, sessions, original, _replacement = bridge
    with pytest.raises(DocumentVersionConflict, match="Word 段落"):
        service.validate_apply(
            "project-1",
            "document-1",
            "changeset-1",
            base_revision=7,
            current_paragraph_sha256=_sha(original + "人工修改"),
            office_session_id="office-session-1",
            document_session_fingerprint=_sha("word-document-1"),
        )

    with sessions() as session:
        state = session.query(WritingDocumentState).filter_by(
            project_id="project-1", document_id="document-1"
        ).one()
        state.document_revision = 8
        session.commit()
    with pytest.raises(DocumentVersionConflict, match="正文修订"):
        service.validate_apply(
            "project-1",
            "document-1",
            "changeset-1",
            base_revision=7,
            current_paragraph_sha256=_sha(original),
            office_session_id="office-session-1",
            document_session_fingerprint=_sha("word-document-1"),
        )


def test_validate_rejects_formatted_or_structured_replacement(bridge):
    service, sessions, original, _replacement = bridge
    with sessions() as session:
        proposal = session.get(WritingAiProposal, "proposal-1")
        proposal.replacement_json = [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "带格式文本", "marks": [{"type": "bold"}]}
                ],
            }
        ]
        session.commit()

    with pytest.raises(DocumentWorkspaceError, match="带格式"):
        service.validate_apply(
            "project-1",
            "document-1",
            "changeset-1",
            base_revision=7,
            current_paragraph_sha256=_sha(original),
            office_session_id="office-session-1",
            document_session_fingerprint=_sha("word-document-1"),
        )
