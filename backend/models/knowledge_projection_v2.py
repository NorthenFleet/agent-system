"""Additive SB2 projection state; v1 schema stays frozen."""
from sqlalchemy import MetaData, Table, Column, String, Integer, DateTime, JSON, ForeignKey
from models import knowledge_schema_v1 as t
metadata = MetaData()
# Column references retain foreign keys across the separate metadata collections.
receipts = Table('kb_projection_receipts', metadata,
    Column('id', String(80), ForeignKey(t.outbox.c.id, name='fk_kb_projection_event'), primary_key=True),
    Column('space_id', String(80), ForeignKey(t.spaces.c.id, name='fk_kb_projection_space'), nullable=False, index=True),
    Column('fence', Integer, nullable=False),
    Column('lease_until', DateTime(timezone=True)),
    Column('next_attempt_at', DateTime(timezone=True)),
    Column('error_code', String(80), nullable=False),
    Column('result', JSON, nullable=False))
