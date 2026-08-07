"""Persistent state for structured human-AI document editing."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
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
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String(64), nullable=False, default="")

    job = relationship("WritingAiJob", back_populates="proposals")
