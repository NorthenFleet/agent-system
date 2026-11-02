"""Frozen SB1 schema. Separate metadata prevents legacy startup create_all writes.

Future schema changes belong in new migrations; do not mutate this snapshot.
"""
from sqlalchemy import (MetaData, Table, Column, String, Integer, Text, JSON,
                        ForeignKey, UniqueConstraint, CheckConstraint, DateTime, Index)

metadata = MetaData()


def key(name="id", target=None):
    return Column(name, String(80), *([ForeignKey(target)] if target else []),
                  primary_key=name == "id", nullable=False)


def string(name, size=240, **kw):
    return Column(name, String(size), nullable=False, **kw)


def stamp():
    return Column("created_at", DateTime(timezone=True), nullable=False)


spaces = Table("kb_spaces", metadata, key(), string("owner_user_id", 160),
    string("name"), string("project_id", 160), string("policy_revision", 80),
    string("status", 32), Column("access_epoch", Integer, nullable=False),
    Column("sequence", Integer, nullable=False), stamp())
sources = Table("kb_sources", metadata, key(), key("space_id", "kb_spaces.id"),
    string("title"), string("kind", 32), string("status", 32), stamp())
versions = Table("kb_source_versions", metadata, key(), key("source_id", "kb_sources.id"),
    key("space_id", "kb_spaces.id"), string("content_sha256", 64),
    string("blob_ref", 180), string("mime", 100), Column("size_bytes", Integer, nullable=False),
    string("parse_status", 32), string("parser_version", 80), stamp(),
    UniqueConstraint("space_id", "content_sha256"))
spans = Table("kb_source_spans", metadata, key(),
    key("source_version_id", "kb_source_versions.id"), Column("locator", JSON, nullable=False),
    Column("text", Text, nullable=False), string("text_sha256", 64))
pages = Table("kb_pages", metadata, key(), key("space_id", "kb_spaces.id"),
    string("type", 32), string("title"), Column("revision", Integer, nullable=False),
    string("status", 32), stamp(),
    CheckConstraint("type IN ('source','concept','entity','synthesis')"))
revisions = Table("kb_page_revisions", metadata, key(), key("page_id", "kb_pages.id"),
    Column("revision_no", Integer, nullable=False), Column("body_json", JSON, nullable=False),
    string("content_hash", 64), key("change_set_id", "kb_change_sets.id"), stamp(),
    UniqueConstraint("page_id", "revision_no"))
claims = Table("kb_claims", metadata, key(), key("page_revision_id", "kb_page_revisions.id"),
    string("block_id", 80), Column("text", Text, nullable=False), string("epistemic_status", 32))
evidence = Table("kb_claim_evidence", metadata,
    Column("claim_id", String(80), ForeignKey("kb_claims.id"), primary_key=True),
    Column("source_span_id", String(80), ForeignKey("kb_source_spans.id"), primary_key=True),
    string("stance", 32))
links = Table("kb_links", metadata, key(), key("from_revision_id", "kb_page_revisions.id"),
    key("to_revision_id", "kb_page_revisions.id"), string("relation", 32),
    Column("rationale", Text, nullable=False))
changes = Table("kb_change_sets", metadata, key(), key("space_id", "kb_spaces.id"),
    string("status", 32), Column("payload", JSON, nullable=False), string("payload_hash", 64),
    string("review_actor", 160), Column("review_reason", Text, nullable=False), stamp())
jobs = Table("kb_ingest_jobs", metadata, key(), key("space_id", "kb_spaces.id"),
    key("source_version_id", "kb_source_versions.id"), string("stage", 32),
    Column("options", JSON, nullable=False), string("change_set_id", 80),
    string("work_run_id", 80), string("error_code", 80),
    Column("attempt", Integer, nullable=False), Column("fence", Integer, nullable=False),
    Column("lease_until", DateTime(timezone=True)), stamp())
releases = Table("kb_releases", metadata, key(), key("space_id", "kb_spaces.id"),
    Column("sequence", Integer, nullable=False), key("change_set_id", "kb_change_sets.id"),
    Column("manifest", JSON, nullable=False), stamp(),
    UniqueConstraint("change_set_id"), UniqueConstraint("space_id", "sequence"))
outbox = Table("kb_outbox", metadata, key(), key("space_id", "kb_spaces.id"),
    string("event_type", 80), Column("payload", JSON, nullable=False), string("status", 32),
    Column("attempts", Integer, nullable=False), stamp())
audit = Table("kb_audit_events", metadata, key(), key("space_id", "kb_spaces.id"),
    string("actor", 160), string("action", 80), string("object_ref", 240),
    Column("details", JSON, nullable=False), stamp())
requests = Table("kb_requests", metadata, key(), key("space_id", "kb_spaces.id"),
    string("actor", 160), string("operation", 80), string("request_key", 160),
    string("payload_hash", 64), Column("response", JSON, nullable=False), stamp(),
    UniqueConstraint("space_id", "actor", "operation", "request_key"))

Index("ix_kb_spaces_owner", spaces.c.owner_user_id, spaces.c.status)
Index("ix_kb_sources_space", sources.c.space_id, sources.c.status)
Index("ix_kb_spans_version", spans.c.source_version_id)
Index("ix_kb_pages_space", pages.c.space_id, pages.c.status, pages.c.type)
Index("ix_kb_changes_space", changes.c.space_id, changes.c.status)
Index("ix_kb_jobs_queue", jobs.c.stage, jobs.c.lease_until, jobs.c.created_at)
Index("ix_kb_jobs_source", jobs.c.space_id, jobs.c.source_version_id)
Index("ix_kb_evidence_source", evidence.c.source_span_id)
Index("ix_kb_outbox_space", outbox.c.space_id, outbox.c.status)
