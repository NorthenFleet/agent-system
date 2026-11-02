"""Actual logical backup/restore drill in disposable PostgreSQL schemas."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from services.knowledge.service import KnowledgeService, KnowledgeError
from services.knowledge.context import KnowledgeContextService
from services.knowledge.projection import ProjectionService
from services.knowledge.bridges import KnowledgeBridges
from services.knowledge import backup


def migrate(engine):
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            for suffix in ['domain','projection','context','operations']:
                path = Path(__file__).resolve().parents[1] / 'alembic/versions' / ('20261006_knowledge_' + suffix + '.py')
                spec = importlib.util.spec_from_file_location(path.stem, path)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.upgrade()


def drill(source_engine, target_engine, root):
    service = KnowledgeService(source_engine, root/'sources', project_check=lambda a,p:a=='drill-owner' and p=='drill-project')
    sid = service.create_space('drill-owner','恢复演练','drill-project','space')['id']
    created = []
    for number, text in enumerate(['可保留的证据：项目决定需要核对固定来源。', '随后撤回的证据：旧的结论不得继续使用。']):
        source = service.upload('drill-owner',sid,f'source-{number}.md',text.encode(),f'upload-{number}')
        service.enqueue('drill-owner',sid,source['version_id'],{},f'enqueue-{number}')
        candidate = service.compile_job(service.claim_job())
        service.review('drill-owner',candidate['id'],candidate['payload_hash'],'approve','isolated_test_fixture_only','review-'+candidate['id'])
        service.publish('drill-owner',candidate['id'],candidate['payload_hash'],'publish-'+candidate['id'])
        created.append(source)
    snapshot = KnowledgeContextService(service).build('drill-owner',sid,'drill-project','证据',persist=True)
    started = time.perf_counter()
    manifest = backup.capture(service,root/'archive')
    backup_seconds = time.perf_counter()-started
    # This event is deliberately newer than the archive to test resurrection safety.
    service.retract_source('drill-owner',created[1]['version_id'],'withdraw-after-backup')
    journal = backup.revocations(service,root/'withdrawals.json')
    started = time.perf_counter()
    restored = backup.restore_isolated(target_engine,root/'restored-sources',root/'archive',root/'withdrawals.json',service.project_check)
    answer = restored.query('drill-owner',sid,'证据')
    returned = {r['source_version_id'] for c in answer['citations'] for r in c['citations']}
    active_ok = created[0]['version_id'] in returned
    revoked_ok = created[1]['version_id'] not in returned
    snapshot_blocked = False
    try:
        KnowledgeContextService(restored).read('drill-owner',snapshot['id'],'drill-project')
    except KnowledgeError:
        snapshot_blocked = True
    projection = ProjectionService(restored,root/'restored-projection')
    for _ in range(10):
        if not projection.run_once():
            break
    health = projection.health('drill-owner',sid)
    recovery_seconds = time.perf_counter()-started
    projection_ok = health['status'] == 'ready'
    # Actual feature rollback check: observer is inert in disabled mode.
    from services.knowledge.context import observe
    os.environ['SECOND_BRAIN_ENABLED']='true'
    os.environ['SECOND_BRAIN_CONTEXT_MODE']='disabled'
    rollback_ok = observe({},persist=False) is None
    checks = {'active_fixed_evidence_restored':active_ok,'later_retraction_replayed':revoked_ok,
        'old_context_invalidated':snapshot_blocked,'private_projection_rebuilt':projection_ok,
        'context_disabled_rollback':rollback_ok}
    return {'format':'sb4-recovery-drill-v1','passed':all(checks.values()),'checks':checks,
        'backup_at':manifest['captured_at'],'revocations_at':journal['captured_at'],
        'backup_bytes':manifest['bytes'],'backup_seconds':round(backup_seconds,3),
        'recovery_and_verification_seconds':round(recovery_seconds,3), 'projection_status':health['status'],
        'source_count':2,'approval_kind':'isolated_test_fixture_only','production_modified':False,
        'g_sb4_passed':False,'real_research_tasks':0,'observation_days':0,
        'scope_note':'Logical KB recovery only; not production RPO/RTO or full-system disaster recovery.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    url=sa.engine.make_url(os.getenv('KNOWLEDGE_TEST_DATABASE_URL',''))
    if url.get_backend_name()!='postgresql' or 'test' not in (url.database or ''):
        raise RuntimeError('Explicit disposable PostgreSQL test database required')
    admin=sa.create_engine(url); engines=[]; schemas=[]
    try:
        for prefix in ['sb_drill_','sb_restore_']:
            schema=prefix+uuid.uuid4().hex
            with admin.begin() as conn:
                conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            schemas.append(schema)
            engine=sa.create_engine(url.update_query_dict({'options':'-csearch_path='+schema})); engines.append(engine)
            migrate(engine)
        with tempfile.TemporaryDirectory(prefix='sb4-recovery-') as directory:
            result=drill(engines[0],engines[1],Path(directory).resolve())
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if not result['passed']:
            raise SystemExit(1)
    finally:
        for engine in engines:
            engine.dispose()
        for schema in schemas:
            with admin.begin() as conn:
                conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__=='__main__':
    main()
