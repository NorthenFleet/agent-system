"""Persistent state for structured human-AI document editing."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WritingDocumentState(Base):
    __tablename__ = "writing_document_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    schema_version = Column(String(32), nullable=False, default="tiptap-json-v1")
    document_revision = Column(Integer, nullable=False, default=1)
    content_json = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    source_markdown_sha256 = Column(String(64), nullable=False, default="")
    projection_revision = Column(Integer, nullable=False, default=0)
    projection_status = Column(String(24), nullable=False, default="stale")
    projection_error = Column(Text, nullable=False, default="")
    approved_revision = Column(Integer, nullable=False, default=0)
    published_revision = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("project_id", "document_id", name="uq_writing_document_state"),
        Index("ix_writing_document_state_projection", "projection_status", "updated_at"),
    )


class WritingDocumentVersion(Base):
    __tablename__ = "writing_document_versions"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    document_revision = Column(Integer, nullable=False)
    label = Column(String(160), nullable=False, default="")
    reason = Column(String(40), nullable=False, default="checkpoint")
    content_json = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    markdown_snapshot = Column(Text, nullable=False, default="")
    actor_type = Column(String(16), nullable=False, default="human")
    actor_id = Column(String(64), nullable=False, default="")
    parent_revision = Column(Integer, nullable=False, default=0)
    lifecycle_status = Column(String(20), nullable=False, default="working", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_id",
            "document_revision",
            name="uq_writing_document_version_revision",
        ),
    )


class WritingChangeEvent(Base):
    __tablename__ = "writing_change_events"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    document_revision = Column(Integer, nullable=False, index=True)
    client_change_id = Column(String(96), nullable=False, default="")
    actor_type = Column(String(16), nullable=False)
    actor_id = Column(String(64), nullable=False, default="")
    source = Column(String(32), nullable=False)
    operations = Column(JSON, nullable=False, default=list)
    before_sha256 = Column(String(64), nullable=False)
    after_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_id",
            "client_change_id",
            name="uq_writing_change_client_id",
        ),
    )


class WritingAiJob(Base):
    __tablename__ = "writing_ai_jobs"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    client_request_id = Column(String(96), nullable=False)
    section_id = Column(String(128), nullable=False, default="")
    agent_id = Column(String(64), nullable=False)
    instruction = Column(Text, nullable=False)
    scope = Column(String(16), nullable=False)
    base_document_revision = Column(Integer, nullable=False)
    target_blocks = Column(JSON, nullable=False, default=list)
    selection = Column(JSON, nullable=False, default=dict)
    evidence_ref_ids = Column(JSON, nullable=False, default=list)
    risk_policy = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="queued", index=True)
    summary = Column(Text, nullable=False, default="")
    raw_response = Column(Text, nullable=False, default="")
    error = Column(Text, nullable=False, default="")
    requested_by = Column(String(64), nullable=False, default="")
    worker_id = Column(String(128), nullable=False, default="")
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    conversation_id = Column(String(64), nullable=False, default="", index=True)
    request_message_id = Column(String(64), nullable=False, default="")
    response_message_id = Column(String(64), nullable=False, default="")

    proposals = relationship(
        "WritingAiProposal",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="WritingAiProposal.created_at.asc()",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_id",
            "client_request_id",
            name="uq_writing_ai_job_client_request",
        ),
    )


class WritingWorkspacePreference(Base):
    __tablename__ = "writing_workspace_preferences"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    owner_user_id = Column(String(64), nullable=False, index=True)
    schema_version = Column(Integer, nullable=False, default=1)
    revision = Column(Integer, nullable=False, default=1)
    preference_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "owner_user_id",
            name="uq_writing_workspace_preference_owner",
        ),
    )


class WritingAiConversation(Base):
    __tablename__ = "writing_ai_conversations"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    owner_user_id = Column(String(64), nullable=False, index=True)
    agent_id = Column(String(64), nullable=False, default="ultra-magnus")
    title = Column(String(200), nullable=False, default="协作会话")
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    messages = relationship(
        "WritingAiMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="WritingAiMessage.created_at.asc()",
    )


class WritingAiMessage(Base):
    __tablename__ = "writing_ai_messages"

    id = Column(String(64), primary_key=True)
    conversation_id = Column(
        String(64),
        ForeignKey("writing_ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False, default="")
    target_context = Column(JSON, nullable=False, default=dict)
    job_kind = Column(String(24), nullable=False, default="")
    job_id = Column(String(64), nullable=False, default="", index=True)
    proposal_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="completed", index=True)
    error = Column(Text, nullable=False, default="")
    client_message_id = Column(String(96), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    conversation = relationship("WritingAiConversation", back_populates="messages")

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="uq_writing_ai_message_client_id",
        ),
    )


class PresentationAiJob(Base):
    __tablename__ = "presentation_ai_jobs"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    slide = Column(Integer, nullable=False)
    client_request_id = Column(String(96), nullable=False)
    agent_id = Column(String(64), nullable=False, default="presentation-editor")
    instruction = Column(Text, nullable=False)
    draft = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="queued", index=True)
    proposal = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=False, default="")
    requested_by = Column(String(64), nullable=False, default="")
    conversation_id = Column(String(64), nullable=False, default="", index=True)
    request_message_id = Column(String(64), nullable=False, default="")
    response_message_id = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_id",
            "client_request_id",
            name="uq_presentation_ai_job_client_request",
        ),
    )

class WritingAiProposal(Base):
    __tablename__ = "writing_ai_proposals"

    id = Column(String(64), primary_key=True)
    job_id = Column(
        String(64),
        ForeignKey("writing_ai_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    block_id = Column(String(96), nullable=False, index=True)
    operation_type = Column(String(24), nullable=False, default="replace")
    base_block_revision = Column(Integer, nullable=False)
    base_block_sha256 = Column(String(64), nullable=False)
    replacement_markdown = Column(Text, nullable=False, default="")
    replacement_json = Column(JSON, nullable=False, default=list)
    diff = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    rationale = Column(Text, nullable=False, default="")
    risk_level = Column(String(16), nullable=False, default="low", index=True)
    approval_required = Column(Boolean, nullable=False, default=False)
    evidence_ref_ids = Column(JSON, nullable=False, default=list)
    concurrency_status = Column(String(16), nullable=False, default="unchanged")
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String(64), nullable=False, default="")

    job = relationship("WritingAiJob", back_populates="proposals")


class WritingClaim(Base):
    __tablename__ = "writing_claims"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    document_revision = Column(Integer, nullable=False, index=True)
    section_id = Column(String(128), nullable=False, default="", index=True)
    block_id = Column(String(96), nullable=False, default="", index=True)
    claim_text = Column(Text, nullable=False)
    claim_type = Column(String(32), nullable=False, default="argument")
    minimum_evidence_level = Column(String(16), nullable=False, default="diagnostic")
    evidence_status = Column(String(24), nullable=False, default="missing", index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_by = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class WritingEvidenceRef(Base):
    __tablename__ = "writing_evidence_refs"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    source_system = Column(String(48), nullable=False)
    source_record_id = Column(String(160), nullable=False, default="")
    artifact_path = Column(Text, nullable=False, default="")
    artifact_sha256 = Column(String(64), nullable=False)
    perspective_scope = Column(String(64), nullable=False, default="project")
    evidence_level = Column(String(16), nullable=False, default="diagnostic", index=True)
    allowed_claim_scope = Column(Text, nullable=False, default="")
    provenance = Column(JSON, nullable=False, default=dict)
    immutable = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_id",
            "source_system",
            "source_record_id",
            "artifact_sha256",
            name="uq_writing_evidence_identity",
        ),
    )


class WritingEvidenceBinding(Base):
    __tablename__ = "writing_evidence_bindings"

    id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("writing_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_ref_id = Column(String(64), ForeignKey("writing_evidence_refs.id", ondelete="RESTRICT"), nullable=False, index=True)
    support_scope = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="active")
    created_by = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_ref_id", name="uq_writing_claim_evidence"),
    )


class WritingEvidenceGap(Base):
    __tablename__ = "writing_evidence_gaps"

    id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("writing_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    required_level = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    research_matrix = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="open", index=True)
    dispatched_run_id = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class WritingChangeSet(Base):
    __tablename__ = "writing_change_sets"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    base_revision = Column(Integer, nullable=False)
    result_revision = Column(Integer, nullable=False, default=0)
    proposal_id = Column(String(64), ForeignKey("writing_ai_proposals.id", ondelete="SET NULL"), nullable=True, unique=True)
    operations = Column(JSON, nullable=False, default=list)
    evidence_ref_ids = Column(JSON, nullable=False, default=list)
    risk_level = Column(String(16), nullable=False, default="low", index=True)
    approval_policy = Column(String(32), nullable=False, default="risk_driven")
    status = Column(String(24), nullable=False, default="review_required", index=True)
    idempotency_key = Column(String(96), nullable=False)
    summary = Column(Text, nullable=False, default="")
    decided_by = Column(String(64), nullable=False, default="")
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("project_id", "document_id", "idempotency_key", name="uq_writing_changeset_idempotency"),
    )


class WritingWordImport(Base):
    __tablename__ = "writing_word_imports"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    base_revision = Column(Integer, nullable=False)
    filename = Column(String(255), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    mapping_status = Column(String(24), nullable=False, default="manual_review", index=True)
    change_set_id = Column(String(64), ForeignKey("writing_change_sets.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class WritingWordRelease(Base):
    __tablename__ = "writing_word_releases"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    document_revision = Column(Integer, nullable=False, index=True)
    template_sha256 = Column(String(64), nullable=False)
    docx_path = Column(Text, nullable=False, default="")
    docx_sha256 = Column(String(64), nullable=False, default="")
    pdf_path = Column(Text, nullable=False, default="")
    pdf_sha256 = Column(String(64), nullable=False, default="")
    field_refresh_status = Column(String(24), nullable=False, default="pending")
    page_check = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="candidate", index=True)
    idempotency_key = Column(String(96), nullable=False)
    approved_by = Column(String(64), nullable=False, default="")
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("project_id", "document_id", "idempotency_key", name="uq_writing_release_idempotency"),
    )


class WritingJarvisRun(Base):
    __tablename__ = "writing_jarvis_runs"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    run_type = Column(String(48), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    idempotency_key = Column(String(96), nullable=False)
    input_payload = Column(JSON, nullable=False, default=dict)
    result_payload = Column(JSON, nullable=False, default=dict)
    approval_reason = Column(Text, nullable=False, default="")
    requested_by = Column(String(64), nullable=False, default="")
    lease_owner = Column(String(128), nullable=False, default="")
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    recovery_cursor = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "document_id", "idempotency_key", name="uq_writing_jarvis_run_idempotency"),
    )


class WritingJarvisStep(Base):
    __tablename__ = "writing_jarvis_steps"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("writing_jarvis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_key = Column(String(80), nullable=False)
    status = Column(String(24), nullable=False, default="pending", index=True)
    depends_on = Column(JSON, nullable=False, default=list)
    attempt_count = Column(Integer, nullable=False, default=0)
    input_payload = Column(JSON, nullable=False, default=dict)
    result_payload = Column(JSON, nullable=False, default=dict)
    compensation = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("run_id", "step_key", name="uq_writing_jarvis_step"),
    )
