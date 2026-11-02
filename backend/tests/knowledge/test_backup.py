import json
import uuid
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from models import knowledge_schema_v1 as t
from services.knowledge import backup
from services.knowledge.context import KnowledgeContextService
from services.knowledge.service import KnowledgeError
from .conftest import migration
from .test_domain import prepare, publish


@pytest.fixture
def archive(svc, tmp_path):
    sid, source, change = prepare(svc); publish(svc, change)
    context = KnowledgeContextService(svc).build('owner',sid,'project-a','任务验收',persist=True)
    root = tmp_path.resolve() / 'backup'
    manifest = backup.capture(svc, root)
    return sid, source, context, root, manifest


@pytest.fixture
def restore_engine(svc):
    schema = 'sb_restore_' + uuid.uuid4().hex
    with svc.engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = sa.create_engine(svc.engine.url.update_query_dict({'options': '-csearch_path=' + schema}))
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                for suffix in ['domain','projection','context','operations']:
                    migration('20261006_knowledge_' + suffix + '.py').upgrade()
        yield engine
    finally:
        engine.dispose()
        with svc.engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_restore_replays_later_retraction_and_invalidates_snapshot(svc, archive, restore_engine, tmp_path):
    sid, source, snapshot, root, manifest = archive
    svc.retract_source('owner',source['version_id'],'withdraw-after-backup')
    journal = tmp_path.resolve() / 'withdrawals.json'; backup.revocations(svc,journal)
    restored = backup.restore_isolated(restore_engine,tmp_path.resolve() / 'restored',root,journal,svc.project_check)
    assert restored.query('owner',sid,'任务验收')['citations'] == []
    with pytest.raises(KnowledgeError):
        KnowledgeContextService(restored).read('owner',snapshot['id'],'project-a')
    with restored.engine.connect() as conn:
        assert conn.execute(sa.select(t.sources.c.status)).scalar_one() == 'retracted'
        assert conn.execute(sa.select(t.outbox.c.status)).scalar_one() == 'pending'


def test_restore_intact_evidence_and_rejects_existing_target(svc, archive, restore_engine, tmp_path):
    sid, _, _, root, _ = archive
    journal = tmp_path.resolve() / 'withdrawals.json'; backup.revocations(svc,journal)
    restored = backup.restore_isolated(restore_engine,tmp_path.resolve() / 'restored',root,journal,svc.project_check)
    assert restored.query('owner',sid,'任务验收')['citations']
    with pytest.raises(KnowledgeError, match='为空'):
        backup.restore_isolated(restore_engine,tmp_path.resolve() / 'another',root,journal,svc.project_check)


@pytest.mark.parametrize('failure', ['blob', 'table', 'missing', 'symlink'])
def test_backup_corruption_or_missing_files_fail_closed(archive, failure):
    _, _, _, root, manifest = archive
    path = root / 'blobs' / next(iter(manifest['blobs']))
    if failure == 'blob':
        path.write_bytes(b'corrupt')
    elif failure == 'table':
        (root / 'kb_pages.json').write_text('[]')
    elif failure == 'missing':
        path.unlink()
    else:
        path.unlink(); path.symlink_to(root / 'manifest.json')
    with pytest.raises((KnowledgeError,OSError)):
        backup.verify(root)


def test_stale_revocation_manifest_and_nonisolated_restore_rejected(svc, archive, restore_engine, tmp_path):
    _, _, _, root, _ = archive
    journal = tmp_path.resolve() / 'withdrawals.json'
    payload = backup.revocations(svc,journal)
    payload['captured_at'] = '2000-01-01T00:00:00+00:00'
    journal.write_bytes(backup.encode({'payload':payload,'sha256':backup.digest(payload)}))
    with pytest.raises(KnowledgeError, match='早于'):
        backup.restore_isolated(restore_engine,tmp_path.resolve() / 'restored',root,journal,svc.project_check)
    journal.unlink(); backup.revocations(svc,journal)
    with pytest.raises(KnowledgeError, match='隔离'):
        backup.restore_isolated(svc.engine,tmp_path.resolve() / 'restored',root,journal,svc.project_check)


def test_backup_rejects_public_directory(svc, tmp_path):
    root = tmp_path.resolve() / 'public'; root.mkdir(mode=0o755)
    with pytest.raises(KnowledgeError, match='0700'):
        backup.verify(root)
