"""Immutable, separately authorized shadow snapshots. No memory schema changes."""
from sqlalchemy import MetaData, Table, Column, String, Integer, JSON, DateTime, ForeignKey, Index
from models import knowledge_schema_v1 as t
metadata = MetaData()
snapshots = Table('kb_context_snapshots', metadata,
    Column('id', String(80), primary_key=True),
    Column('space_id', String(80), ForeignKey(t.spaces.c.id), nullable=False),
    Column('owner_user_id', String(160), nullable=False),
    Column('project_id', String(160), nullable=False),
    Column('access_epoch', Integer, nullable=False),
    Column('payload', JSON, nullable=False),
    Column('content_hash', String(64), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False))
Index('ix_kb_context_scope', snapshots.c.owner_user_id, snapshots.c.space_id, snapshots.c.created_at)
