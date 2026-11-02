"""SB4 local cross-domain proposals and periodic maintenance receipts."""
from sqlalchemy import MetaData, Table, Column, String, JSON, DateTime, ForeignKey, UniqueConstraint
from models import knowledge_schema_v1 as t

metadata = MetaData()


def scoped(name, *columns):
    return Table(name, metadata,
        Column('id', String(80), primary_key=True),
        Column('space_id', String(80), ForeignKey(t.spaces.c.id), nullable=False),
        *columns, Column('created_at', DateTime(timezone=True), nullable=False))


imports = scoped('kb_external_imports',
    Column('source_version_id', String(80), ForeignKey(t.versions.c.id), nullable=False),
    Column('reference_key', String(64), nullable=False),
    Column('reference', JSON, nullable=False),
    UniqueConstraint('space_id', 'reference_key'))
proposals = scoped('kb_memory_proposals',
    Column('owner_user_id', String(160), nullable=False),
    Column('payload', JSON, nullable=False),
    Column('content_hash', String(64), nullable=False),
    Column('status', String(32), nullable=False),
    Column('invalid_reason', String(80), nullable=False))
runs = scoped('kb_maintenance_runs',
    Column('period_key', String(80), nullable=False),
    Column('report', JSON, nullable=False),
    Column('content_hash', String(64), nullable=False),
    Column('work_run_id', String(80), nullable=False),
    UniqueConstraint('space_id', 'period_key'))
