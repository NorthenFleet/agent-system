import sys
import types
import uuid
import pytest
import sqlalchemy as sa
from services.knowledge import runtime
from services.knowledge.service import KnowledgeError
from scripts.apply_knowledge_schema import apply


def test_dedicated_database_does_not_redirect_legacy_store(monkeypatch):
    monkeypatch.setenv('DATABASE_URL','sqlite:////private/tmp/legacy.db')
    monkeypatch.setenv('SECOND_BRAIN_DATABASE_URL','postgresql+psycopg2:///knowledge')
    assert runtime.database_url()=='postgresql+psycopg2:///knowledge'
    monkeypatch.delenv('SECOND_BRAIN_DATABASE_URL')
    with pytest.raises(KnowledgeError): runtime.database_url()
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg2:///fallback')
    assert runtime.database_url()=='postgresql+psycopg2:///fallback'
    monkeypatch.setenv('SECOND_BRAIN_DATABASE_URL','not-a-url')
    with pytest.raises(KnowledgeError): runtime.database_url()


def test_configured_pilot_owner_is_limited_to_selected_project(svc,monkeypatch):
    runtime.get_service.cache_clear()
    monkeypatch.setattr(runtime,'knowledge_engine',lambda:svc.engine)
    monkeypatch.setenv('SECOND_BRAIN_SOURCE_ROOT',str(svc.root))
    monkeypatch.setenv('SECOND_BRAIN_PILOT_OWNER_ID','1')
    monkeypatch.setenv('SECOND_BRAIN_PILOT_PROJECT_ID','selected')
    monkeypatch.setitem(sys.modules,'project_manager',types.SimpleNamespace(project_manager=types.SimpleNamespace(
        get_project=lambda pid:{'id':pid} if pid in {'selected','other'} else None)))
    try:
        actual=runtime.get_service()
        assert actual.project_check('1','selected')
        assert not actual.project_check('other','selected')
        assert not actual.project_check('1','other')
        assert not actual.project_check('1','missing')
    finally: runtime.get_service.cache_clear()


def test_scoped_provisioning_is_atomic_idempotent_and_preserves_existing_store(svc):
    schema='second_brain_'+uuid.uuid4().hex
    with svc.engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE legacy_marker(id integer primary key)')
        conn.exec_driver_sql('INSERT INTO legacy_marker VALUES (1)')
    try:
        first=apply(svc.engine,schema)
        assert len(first['applied'])==4 and first['legacy_alembic_version_unchanged']
        assert apply(svc.engine,schema)['applied']==[]
        with svc.engine.begin() as conn:
            assert conn.exec_driver_sql('SELECT id FROM legacy_marker').scalar_one()==1
            assert conn.execute(sa.text(f'SELECT count(*) FROM "{schema}".kb_schema_migrations')).scalar_one()==4
            conn.execute(sa.text(f'ALTER TABLE "{schema}".kb_spaces ADD COLUMN unexpected text'))
        with pytest.raises(KnowledgeError,match='漂移'):apply(svc.engine,schema)
    finally:
        with svc.engine.begin() as conn:conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_provisioner_rejects_public_or_foreign_tables(svc):
    with pytest.raises(KnowledgeError):apply(svc.engine,'public')
    schema='second_brain_'+uuid.uuid4().hex
    with svc.engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(sa.text(f'CREATE TABLE "{schema}".foreign_data(id integer)'))
    try:
        with pytest.raises(KnowledgeError,match='非知识'):apply(svc.engine,schema)
        with svc.engine.connect() as conn:
            assert sa.inspect(conn).get_table_names(schema=schema)==['foreign_data']
    finally:
        with svc.engine.begin() as conn:conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
