import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import pytest
import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from models.knowledge_projection_v2 import receipts
from services.knowledge.projection import ProjectionService
from services.knowledge.service import KnowledgeError, now, row
from .test_domain import prepare, publish, count


def proposal(svc, sid, page, action='rename', **extra):
    request = {'action': action, 'page_id': page['page_id'], 'base_revision': page['base_revision'] + 1,
               'title': '新的概念名称', 'reason': '核对来源后维护', **extra}
    result = svc.maintenance_candidate('owner', sid, request, 'maint-' + str(count(svc, t.changes)))
    return svc.change('owner', result['id'])


@pytest.fixture
def projected(svc, tmp_path):
    sid, source, change = prepare(svc)
    publish(svc, change)
    return ProjectionService(svc, tmp_path / 'projection'), sid, source, change


def pointer(projection, sid):
    return json.loads((projection.root / sid / 'current.json').read_text())


def generation(projection, sid):
    return projection.root / sid / 'generations' / pointer(projection, sid)['generation']


def test_rename_is_reviewed_stable_id_preserves_old_title_and_relationships(projected):
    projection, sid, _, change = projected
    svc = projection.service
    page = change['payload']['pages'][1]
    candidate = proposal(svc, sid, page)
    assert svc.get_page('owner', page['page_id'])['title'] == page['title']
    assert count(svc, t.releases) == 1
    publish(svc, candidate)
    current = svc.get_page('owner', page['page_id'])
    assert current['title'] == '新的概念名称'
    assert page['title'] in current['body_json']['aliases']
    assert svc.get_page('owner', page['page_id'], 1)['title'] == page['title']
    assert len(svc.page_history('owner', page['page_id'])['items']) == 2
    while projection.run_once():
        pass
    health = projection.health('owner', sid)
    assert health['status'] == 'ready'
    graph = json.loads((generation(projection, sid) / 'graph-index.json').read_text())
    assert {e['relation'] for e in graph['edges']} == {'MENTIONS', 'DERIVED_FROM'}
    assert pointer(projection, sid)['sequence'] == 2


def test_merge_keeps_both_sources_history_and_blocks_until_approved(projected):
    projection, sid, first_source, first = projected
    svc = projection.service
    _, second_source, second = prepare(svc, sid, '另一个来源指出必须保留检查日志。'.encode(), key='second')
    publish(svc, second)
    a, b = first['payload']['pages'][1], second['payload']['pages'][1]
    candidate = proposal(svc, sid, a, 'merge', target_page_id=b['page_id'], target_revision=1)
    assert len(candidate['payload']['source_version_ids']) == 2
    assert svc.get_page('owner', a['page_id'])['status'] == 'active'
    publish(svc, candidate)
    with pytest.raises(KnowledgeError):
        svc.get_page('owner', a['page_id'])
    history = svc.page_history('owner', a['page_id'])
    assert history['superseded_by'] == b['page_id']
    assert svc.get_page('owner', a['page_id'], 1)['body_json']['blocks']
    combined = svc.get_page('owner', b['page_id'])
    assert {ref['source_version_id'] for ref in combined['citations']} == {first_source['version_id'], second_source['version_id']}
    while projection.run_once():
        pass
    manifest = json.loads((generation(projection, sid) / 'manifest.json').read_text())
    assert a['page_id'] not in manifest['pages'] and b['page_id'] in manifest['pages']
    graph = json.loads((generation(projection, sid) / 'graph-index.json').read_text())
    assert all(e['from'] != e['to'] for e in graph['edges'])
    svc.retract_source('owner', first_source['version_id'], 'retract')
    assert projection.run_once()
    assert projection.health('owner', sid)['status'] == 'ready'
    manifest = json.loads((generation(projection, sid) / 'manifest.json').read_text())
    assert b['page_id'] not in manifest['pages']


def test_contradiction_records_both_fixed_endpoints_and_stale_target_rejects(projected):
    projection, sid, _, first = projected
    svc = projection.service
    _, _, second = prepare(svc, sid, '相反观点：保留证据不足以证明结果。'.encode(), key='opposing')
    publish(svc, second)
    a, b = first['payload']['pages'][1], second['payload']['pages'][1]
    candidate = proposal(svc, sid, a, 'relate', target_page_id=b['page_id'], target_revision=1, relation='CONTRADICTS')
    assert len(candidate['sources']) == 2
    assert candidate['relation_targets'][0]['page_id'] == b['page_id']
    assert '相反观点' in str(candidate['relation_targets'][0]['body_json'])
    publish(svc, candidate)
    assert any(x['kind'] == 'contradiction' for x in svc.maintenance_report('owner', sid)['issues'])
    newer = proposal(svc, sid, b)
    pending = proposal(svc, sid, {**a, 'base_revision': 1}, 'relate', target_page_id=b['page_id'], target_revision=1)
    publish(svc, newer)
    with pytest.raises(KnowledgeError) as err:
        publish(svc, pending)
    assert err.value.code == 'revision_conflict'


def test_edit_requires_authorized_evidence_and_never_implicitly_publishes(projected):
    projection, sid, _, first = projected
    svc = projection.service
    a = first['payload']['pages'][1]
    blocks = [{**a['blocks'][0], 'text': '人工修订结论', 'epistemic_status': 'inference'}]
    c = proposal(svc, sid, a, 'edit', blocks=blocks)
    assert c['payload']['extraction_mode'] == 'reviewed-proposal-v1'
    assert svc.get_page('owner', a['page_id'])['revision'] == 1
    with pytest.raises(KnowledgeError):
        proposal(svc, sid, a, 'edit', blocks=[{**blocks[0], 'span_ids': ['missing']}])
    other = svc.create_space('other', 'private', '', 'other')['id']
    with pytest.raises(KnowledgeError) as err:
        svc.maintenance_candidate('other', other, {'action': 'rename', 'page_id': a['page_id'], 'base_revision': 1, 'title': '伪造', 'reason': 'bad'}, 'x')
    assert err.value.status == 404
    publish(svc, c)
    answer = svc.query('owner', sid, '人工修订结论')
    assert '推论' in answer['answer'] and '来源摘录' not in answer['answer']
    assert answer['citations'][0]['epistemic_status'] == 'inference'


def test_projection_writes_complete_generation_without_original_attachments(projected):
    projection, sid, _, change = projected
    assert projection.run_once()
    assert projection.health('owner', sid)['status'] == 'ready'
    folder = generation(projection, sid)
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['pages'] == {p['page_id']: 1 for p in change['payload']['pages']}
    assert set(manifest['files']) == {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()} - {'manifest.json'}
    assert not list(folder.rglob('*.pdf'))
    assert not projection.run_once()


def test_external_drift_is_preserved_until_explicit_regeneration(projected):
    projection, sid, _, first = projected
    assert projection.run_once()
    old_folder = generation(projection, sid)
    edited = old_folder / 'index.md'
    edited.write_text('用户外部编辑，不能丢失')
    assert projection.health('owner', sid)['status'] == 'drift'
    c = proposal(projection.service, sid, first['payload']['pages'][1])
    publish(projection.service, c)
    assert projection.run_once()
    event = projection.health('owner', sid)['events'][0]
    assert event['status'] == 'blocked_drift'
    assert generation(projection, sid) == old_folder
    with pytest.raises(KnowledgeError):
        projection.replay('owner', sid, event['id'], 'no-confirm')
    replayed = projection.replay('owner', sid, event['id'], 'explicit', regenerate=True)
    assert replayed['id'] == event['id']
    assert projection.run_once()
    assert projection.health('owner', sid)['status'] == 'ready'
    assert generation(projection, sid) != old_folder
    assert edited.read_text() == '用户外部编辑，不能丢失'
    assert list((projection.root / sid).glob('preserved-*.json'))


def test_retraction_and_late_old_event_never_restore_revoked_text(projected):
    projection, sid, source, _ = projected
    assert projection.run_once()
    old_event = pointer(projection, sid)['event_id']
    projection.service.retract_source('owner', source['version_id'], 'withdraw')
    assert projection.health('owner', sid)['status'] == 'lagging'
    assert projection.run_once()
    assert json.loads((generation(projection, sid) / 'manifest.json').read_text())['pages'] == {}
    projection.replay('owner', sid, old_event, 'late')
    assert projection.run_once()
    assert pointer(projection, sid)['access_epoch'] == 1
    assert json.loads((generation(projection, sid) / 'manifest.json').read_text())['pages'] == {}


def test_old_release_is_superseded_not_pointer_downgraded(projected):
    projection, sid, _, c = projected
    svc = projection.service
    first_event = projection.claim()
    newer = proposal(svc, sid, c['payload']['pages'][1])
    publish(svc, newer)
    assert projection.run_once()
    latest = pointer(projection, sid)
    projection.process(first_event)
    assert pointer(projection, sid) == latest
    with svc.engine.connect() as conn:
        assert row(conn, t.outbox, first_event['id'])['status'] == 'superseded'


def test_fencing_rejects_late_worker_and_concurrent_claims_once(projected):
    projection, sid, _, _ = projected
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: projection.claim(), range(2)))
    first = next(e for e in claims if e)
    assert sum(e is not None for e in claims) == 1
    with projection.engine.begin() as conn:
        conn.execute(receipts.update().where(receipts.c.id == first['id']).values(lease_until=now() - timedelta(seconds=1)))
    second = projection.claim()
    assert second['fence'] == first['fence'] + 1
    with pytest.raises(KnowledgeError) as err:
        projection.process(first)
    assert err.value.code == 'projection_lease_conflict'
    projection.process(second)
    assert projection.health('owner', sid)['status'] == 'ready'


def test_crash_after_pointer_before_receipt_recovers_without_duplicate_release(projected):
    projection, sid, _, _ = projected
    event = projection.claim()
    def crash(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE kb_projection_receipts'):
            raise RuntimeError('simulated crash after pointer switch')
    sa.event.listen(projection.engine, 'before_cursor_execute', crash)
    try:
        with pytest.raises(RuntimeError):
            projection.process(event)
    finally:
        sa.event.remove(projection.engine, 'before_cursor_execute', crash)
    assert (generation(projection, sid) / 'manifest.json').exists()
    with projection.engine.begin() as conn:
        conn.execute(receipts.update().where(receipts.c.id == event['id']).values(lease_until=now() - timedelta(seconds=1)))
    assert projection.run_once()
    assert projection.health('owner', sid)['status'] == 'ready'
    assert count(projection.service, t.releases) == 1


def test_retry_budget_dead_letter_and_manual_replay(projected, monkeypatch):
    projection, sid, _, _ = projected
    original = projection._files
    def fail(*args):
        raise OSError('simulated disk failure, path not logged')
    monkeypatch.setattr(projection, '_files', fail)
    for attempt in range(8):
        assert projection.run_once()
        event = projection.health('owner', sid)['events'][0]
        assert event['attempts'] == attempt + 1
        with projection.engine.begin() as conn:
            conn.execute(receipts.update().values(next_attempt_at=now() - timedelta(seconds=1)))
    assert event['status'] == 'dead'
    assert not projection.run_once()
    with pytest.raises(KnowledgeError):
        projection.replay('other', sid, event['id'], 'forged')
    projection.replay('owner', sid, event['id'], 'retry-again')
    monkeypatch.setattr(projection, '_files', original)
    assert projection.run_once()
    assert projection.health('owner', sid)['status'] == 'ready'


def test_symlink_generation_and_markdown_injection_are_not_executed(projected, tmp_path):
    projection, sid, _, c = projected
    svc = projection.service
    blocks = [{**c['payload']['pages'][1]['blocks'][0], 'text': '<script>alert(1)</script> ![x](https://evil.test/x)'}]
    changed = proposal(svc, sid, c['payload']['pages'][1], 'edit', blocks=blocks)
    publish(svc, changed)
    while projection.run_once():
        pass
    exported = next((generation(projection, sid) / 'wiki/concepts').glob('*.md')).read_text()
    assert '<script>' not in exported and '![x](' not in exported
    index = generation(projection, sid) / 'index.md'
    index.unlink(); index.symlink_to(tmp_path / 'outside')
    assert projection.health('owner', sid)['status'] == 'drift'


def test_30_sources_engineering_corpus_projection_and_evidence(svc, tmp_path):
    sid = None
    for i in range(30):
        sid, _, c = prepare(svc, sid, f'中文工程样例 {i}：核对来源编号 {i}，保留原始证据。'.encode(), concept=f'概念 {i}', key=f'corpus-{i}')
        publish(svc, c)
    projection = ProjectionService(svc, tmp_path / 'projection')
    while projection.run_once():
        pass
    assert projection.health('owner', sid)['status'] == 'ready'
    manifest = json.loads((generation(projection, sid) / 'manifest.json').read_text())
    assert len(manifest['pages']) == 60
    for pid in manifest['pages']:
        page = svc.get_page('owner', pid)
        assert all(c['locator'] and c['source_version_id'] for c in page['citations'])
    assert not svc.maintenance_report('owner', sid)['issues']


def test_rename_alias_is_searchable_and_merge_carries_outgoing_evidence(projected):
    projection, sid, _, first = projected
    svc = projection.service
    a = first['payload']['pages'][1]
    renamed = proposal(svc, sid, a, title='完全不同的新标题')
    publish(svc, renamed)
    assert any(c['page_id'] == a['page_id'] for c in svc.query('owner', sid, a['title'])['citations'])
    _, _, second = prepare(svc, sid, '对比来源：记录后续验证。'.encode(), key='compare')
    publish(svc, second)
    b = second['payload']['pages'][1]
    merged = proposal(svc, sid, {**a, 'base_revision': 1}, 'merge', target_page_id=b['page_id'], target_revision=1)
    assert any(l['from_page_id'] == b['page_id'] and l['to_page_id'] == first['payload']['pages'][0]['page_id'] for l in merged['payload']['links'])
    publish(svc, merged)
    assert svc.get_page('owner', b['page_id'])['revision'] == 2


def test_projection_runtime_checks_gate_even_after_cache_and_allows_readonly_health(svc, tmp_path, monkeypatch):
    from services.knowledge import runtime
    from knowledge_manager import knowledge_manager
    runtime._projection_service.cache_clear()
    monkeypatch.setenv('SECOND_BRAIN_ENABLED', 'true')
    monkeypatch.setenv('SECOND_BRAIN_WRITE_ENABLED', 'false')
    monkeypatch.setenv('SECOND_BRAIN_PROJECTION_ENABLED', 'true')
    monkeypatch.setenv('SECOND_BRAIN_PROJECTION_ROOT', str(tmp_path / 'projection'))
    monkeypatch.setattr(runtime, 'get_service', lambda: svc)
    monkeypatch.setattr(knowledge_manager, 'vault_path', tmp_path / 'legacy')
    try:
        assert runtime.get_projection().engine is svc.engine
        monkeypatch.setenv('SECOND_BRAIN_PROJECTION_ENABLED', 'false')
        with pytest.raises(KnowledgeError) as err:
            runtime.get_projection()
        assert err.value.code == 'projection_disabled'
    finally:
        runtime._projection_service.cache_clear()


def test_projection_root_cannot_enter_actual_legacy_vault_or_source_root(svc, tmp_path, monkeypatch):
    from services.knowledge import runtime
    from knowledge_manager import knowledge_manager
    runtime._projection_service.cache_clear()
    monkeypatch.setenv('SECOND_BRAIN_ENABLED', 'true')
    monkeypatch.setenv('SECOND_BRAIN_PROJECTION_ENABLED', 'true')
    monkeypatch.setattr(runtime, 'get_service', lambda: svc)
    monkeypatch.setattr(knowledge_manager, 'vault_path', tmp_path / 'legacy')
    monkeypatch.setenv('SECOND_BRAIN_PROJECTION_ROOT', str(tmp_path / 'legacy' / 'export'))
    try:
        with pytest.raises(KnowledgeError):
            runtime.get_projection()
        with pytest.raises(KnowledgeError):
            ProjectionService(svc, svc.root / 'export')
    finally:
        runtime._projection_service.cache_clear()


@pytest.mark.parametrize('damage', ['missing', 'extra', 'pointer'])
def test_reconciliation_detects_file_set_and_pointer_drift(projected, damage):
    projection, sid, _, _ = projected
    projection.run_once()
    folder = generation(projection, sid)
    if damage == 'missing':
        (folder / 'index.md').unlink()
    elif damage == 'extra':
        (folder / 'user-note.md').write_text('保留我的备注')
    else:
        ptr = pointer(projection, sid)
        ptr['sequence'] += 1
        (projection.root / sid / 'current.json').write_text(json.dumps(ptr))
    assert projection.health('owner', sid)['status'] == 'drift'
