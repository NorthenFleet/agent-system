import json
import sqlite3
import sys
import types
from contextlib import contextmanager
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from models.knowledge_operations_v4 import imports, proposals, runs
from services.knowledge.bridges import KnowledgeBridges, registered_reference
from services.knowledge.operations import KnowledgeOperations, run_scheduled_once
from services.knowledge.service import KnowledgeError, digest, now
from .test_domain import space, prepare, publish, count, TEXT


def request(change):
    page = change['payload']['pages'][0]
    return {'page_id': page['page_id'], 'revision': 1, 'block_id': page['blocks'][0]['block_id'],
            'memory_key': 'research-evidence', 'proposed_content': '保留核验依据', 'reason': '项目复盘'}


def ref(**kw):
    return {'kind': 'artifact', 'container_id': 'mission', 'object_id': 'artifact', 'version': 2,
            'expected_hash': digest(TEXT), 'selected': True, **kw}


def test_reference_import_atomic_dedup_and_never_autoextract(svc):
    sid = space(svc)
    bridge = KnowledgeBridges(svc, lambda a, p, r: ('report.md', TEXT, {'lifecycle': 'draft'}))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda n: bridge.import_reference('owner', sid, ref(), str(n)), range(3)))
    assert len({r['id'] for r in results}) == 1
    assert count(svc, imports) == count(svc, t.versions) == 1
    assert count(svc, t.jobs) == 0
    assert not results[0]['auto_extract'] and not results[0]['independent_evidence']
    assert results[0]['reference']['lifecycle'] == 'draft'
    svc.retract_source('owner', results[0]['version_id'], 'withdraw')
    with pytest.raises(KnowledgeError, match='撤回'):
        bridge.import_reference('owner', sid, ref(), '0')


def test_import_revalidates_upstream_on_retry_and_rolls_back_binding_failure(svc):
    sid = space(svc)
    bridge = KnowledgeBridges(svc, lambda a, p, r: ('report.md', TEXT, {}))
    bridge.import_reference('owner', sid, ref(), 'first')
    bridge.resolver = lambda a, p, r: ('report.md', b'changed', {})
    with pytest.raises(KnowledgeError, match='变化'):
        bridge.import_reference('owner', sid, ref(), 'first')
    with pytest.raises(KnowledgeError, match='变化'):
        bridge.import_reference('owner', sid, ref(expected_hash=digest(b'changed')), 'different-hash')
    assert count(svc, imports) == 1
    other = space(svc, key='empty')
    bridge.resolver = lambda a, p, r: ('report.md', TEXT, {'bad': object()})
    with pytest.raises(sa.exc.StatementError):
        bridge.import_reference('owner', other, ref(), 'bad')
    assert count(svc, t.versions) == 1
    with pytest.raises(KnowledgeError):
        bridge.import_reference('other', sid, ref(), 'wrong')


def test_actual_registered_artifact_reader_checks_owner_project_version_hash_and_selection(svc, tmp_path, monkeypatch):
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE orchestration_missions(id TEXT, owner_user_id TEXT, project_id TEXT);
        CREATE TABLE mission_artifacts(id TEXT, mission_id TEXT, plan_version INTEGER, uri TEXT, content_hash TEXT, work_run_id TEXT);
        INSERT INTO orchestration_missions VALUES ('mission','owner','project-a');''')
    report = tmp_path / 'report.md'; report.write_bytes(TEXT)
    db.execute('INSERT INTO mission_artifacts VALUES (?,?,?,?,?,?)', ('artifact','mission',2,str(report),digest(TEXT),'wr1'))
    @contextmanager
    def connect():
        yield db
    monkeypatch.setitem(sys.modules, 'services.command_center_service', types.SimpleNamespace(command_center_service=types.SimpleNamespace(connect=connect)))
    monkeypatch.setenv('COMMAND_CENTER_ARTIFACT_ROOTS', str(tmp_path))
    try:
        assert registered_reference('owner', 'project-a', ref())[1] == TEXT
        for actor, project, params in [('other','project-a',ref()), ('owner','other',ref()),
                ('owner','project-a',ref(version=1)), ('owner','project-a',ref(selected=False)),
                ('owner','project-a',ref(expected_hash='0'*64))]:
            with pytest.raises(KnowledgeError):
                registered_reference(actor, project, params)
        report.write_bytes(b'changed')
        with pytest.raises(KnowledgeError, match='核验'):
            registered_reference('owner', 'project-a', ref())
    finally:
        db.close()


def test_document_reads_fixed_authority_not_stale_projection(svc, monkeypatch):
    from services.structured_document_service import structured_document_codec as codec
    engine = sa.create_engine('sqlite://')
    versions = sa.Table('writing_document_versions', sa.MetaData(),
        sa.Column('id', sa.String), sa.Column('project_id', sa.String), sa.Column('document_id', sa.String),
        sa.Column('document_revision', sa.Integer), sa.Column('content_json', sa.JSON),
        sa.Column('content_sha256', sa.String), sa.Column('markdown_snapshot', sa.String),
        sa.Column('lifecycle_status', sa.String))
    versions.metadata.create_all(engine)
    document = {'type': 'doc', 'content': [{'type':'paragraph','content':[{'type':'text','text':'固定依据'}]}]}
    checksum = codec.document_sha256(document)
    with engine.begin() as conn:
        conn.execute(versions.insert().values(id='v1',project_id='project-a',document_id='doc',document_revision=3,
            content_json=document,content_sha256=checksum,markdown_snapshot='过期内容',lifecycle_status='working'))
    monkeypatch.setitem(sys.modules, 'database', types.SimpleNamespace(engine=engine))
    params = ref(kind='document',container_id='doc',object_id='v1',version=3,expected_hash=checksum)
    try:
        _, data, meta = registered_reference('owner', 'project-a', params)
        assert '固定依据' in data.decode() and '过期内容' not in data.decode()
        assert meta['lifecycle'] == 'working'
        with pytest.raises(KnowledgeError):
            registered_reference('owner', 'wrong-project', params)
        with engine.begin() as conn:
            conn.execute(versions.update().values(content_sha256='0'*64))
        with pytest.raises(KnowledgeError, match='核验'):
            registered_reference('owner', 'project-a', params)
    finally:
        engine.dispose()


def test_memory_proposal_idempotent_scope_and_immediate_withdrawal(svc):
    sid, source, change = prepare(svc); publish(svc, change)
    bridge = KnowledgeBridges(svc); body = request(change)
    first = bridge.propose_memory('owner', sid, body, 'proposal')
    assert first['mode'] == 'export_only' and not first['approved']
    assert first['evidence_refs'] and first['entry']['source_hashes']
    assert bridge.propose_memory('owner', sid, body, 'proposal') == first
    assert count(svc, proposals) == 1
    with pytest.raises(KnowledgeError):
        bridge.propose_memory('owner', sid, {**body, 'proposed_content':'different'}, 'proposal')
    with pytest.raises(KnowledgeError):
        bridge.propose_memory('owner', sid, {**body, 'requested_scope':'agent'}, 'agent')
    with pytest.raises(KnowledgeError):
        bridge.read_proposal('other', first['id'])
    svc.retract_source('owner', source['version_id'], 'withdraw')
    with pytest.raises(KnowledgeError):
        bridge.read_proposal('owner', first['id'])
    with pytest.raises(KnowledgeError):
        bridge.propose_memory('owner', sid, body, 'proposal')
    assert bridge.overview('owner', sid)['proposals'][0]['status'] == 'needs_review'


@pytest.mark.parametrize('tamper', ['source', 'payload', 'page'])
def test_memory_proposal_revalidates_hashes(svc, tamper):
    sid, source, change = prepare(svc); publish(svc, change)
    bridge = KnowledgeBridges(svc); first = bridge.propose_memory('owner', sid, request(change), 'p')
    with svc.engine.begin() as conn:
        if tamper == 'source':
            version = conn.execute(sa.select(t.versions)).mappings().first()
            (svc.root / version['blob_ref']).write_bytes(b'changed')
        elif tamper == 'payload':
            conn.execute(proposals.update().values(payload={}))
        else:
            conn.execute(t.pages.update().values(revision=2))
    with pytest.raises(KnowledgeError):
        bridge.read_proposal('owner', first['id'])


def test_periodic_maintenance_concurrent_idempotency_no_repeat_attention(svc):
    sid, source, change = prepare(svc)
    ops = KnowledgeOperations(svc); at = now()
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(lambda _: ops.maintain('owner', sid, 'daily', at), range(3)))
    assert len({r['id'] for r in receipts}) == 1 and count(svc, runs) == 1
    assert receipts[0]['report']['attention_required']
    assert not ops.maintain('owner', sid, 'daily', at + timedelta(days=1))['report']['attention_required']
    publish(svc, change)
    bridge = KnowledgeBridges(svc); proposal = bridge.propose_memory('owner', sid, request(change), 'p')
    svc.retract_source('owner', source['version_id'], 'withdraw')
    result = ops.maintain('owner', sid, 'daily', at + timedelta(days=2))
    assert result['report']['memory_needs_review'] == [proposal['id']]
    assert result['report']['attention_required'] and not result['report']['notification_sent']
    with svc.engine.connect() as conn:
        assert conn.execute(sa.select(proposals.c.status)).scalar_one() == 'needs_review'
    assert not ops.maintain('owner', sid, 'daily', at + timedelta(days=3))['report']['attention_required']


def test_scheduler_disabled_invalid_configuration_and_scope_fail_closed(svc, monkeypatch):
    monkeypatch.setenv('SECOND_BRAIN_ENABLED', 'true'); monkeypatch.setenv('SECOND_BRAIN_WRITE_ENABLED', 'true')
    monkeypatch.setenv('SECOND_BRAIN_MAINTENANCE_ENABLED', 'false')
    assert run_scheduled_once(svc, None) == 0
    monkeypatch.setenv('SECOND_BRAIN_MAINTENANCE_ENABLED', 'true')
    monkeypatch.setenv('SECOND_BRAIN_MAINTENANCE_SPACES', '{}')
    with pytest.raises(KnowledgeError):
        run_scheduled_once(svc, None)
    monkeypatch.setenv('SECOND_BRAIN_MAINTENANCE_SPACES', json.dumps([{'actor':'other','space_id':space(svc),'cadence':'weekly'}]))
    with pytest.raises(KnowledgeError):
        run_scheduled_once(svc, None)
    assert count(svc, runs) == 0


def test_real_workrun_reconciles_lost_receipt_without_duplicate_attempt(svc, tmp_path, monkeypatch):
    import importlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from .conftest import migration
    monkeypatch.setitem(sys.modules,'unified_data_manager',types.SimpleNamespace(UNIFIED_DB_PATH=str(tmp_path/'unused.db')))
    url = svc.engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv('WORK_RUN_DATABASE_URL', url)
    with svc.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration('20260919_work_run_postgres.py').upgrade()
    module = importlib.import_module('services.work_run_service')
    monkeypatch.delenv('WORK_RUN_DATABASE_URL')
    from repositories.command_center_repository import PostgresCommandCenterRepository
    repository = PostgresCommandCenterRepository(url)
    ledger = module.WorkRunService(repository=repository)
    try:
        sid = space(svc); ops = KnowledgeOperations(svc)
        receipt = ops.maintain('owner',sid)
        original = ledger.claim_at_most_once
        def lose_response(**kw):
            original(**kw)
            raise TimeoutError('simulated response loss')
        monkeypatch.setattr(ledger,'claim_at_most_once',lose_response)
        with pytest.raises(TimeoutError):
            ops.reconcile_work_run('owner',sid,receipt,ledger)
        monkeypatch.setattr(ledger,'claim_at_most_once',original)
        rid = ops.reconcile_work_run('owner',sid,receipt,ledger)
        assert ledger.get(rid)['status'] == 'completed'
        assert ops.reconcile_work_run('owner',sid,receipt,ledger) == rid
        with svc.engine.connect() as conn:
            assert conn.execute(sa.text('select count(*) from work_runs')).scalar_one() == 1
            assert conn.execute(sa.select(runs.c.work_run_id)).scalar_one() == rid
    finally:
        repository.close(); module.work_run_service.repository.close()
        sys.modules.pop('services.work_run_service',None)
