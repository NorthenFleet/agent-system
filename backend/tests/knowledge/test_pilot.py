import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
import sqlalchemy as sa
from services.knowledge import pilot
from services.knowledge.pilot import PilotLedger, capture_task, observe
from services.knowledge.service import KnowledgeError, now
from services.knowledge.context import KnowledgeContextService
from .test_domain import prepare, publish


@pytest.fixture
def ledger(tmp_path):
    store = PilotLedger(tmp_path.resolve() / 'pilot')
    store.initialize({'owner':'owner','project_id':'project-a','space_id':'space'}, {'ready':True})
    return store


def review(event):
    return {'task_id':event['payload']['task_id'],'evidence_hash':event['hash'], 'reviewer':'human-fixture',
        'real_research_task':True,'baseline_lookup_seconds':100,'pilot_lookup_seconds':80,
        'citations_checked':10,'citations_supported':10,'citations_adopted':8,'corrections':0,'major_factual_error':False}


def test_preflight_failure_never_starts_clock_or_creates_directory(tmp_path):
    store = PilotLedger(tmp_path / 'blocked')
    with pytest.raises(KnowledgeError, match='预检'):
        store.initialize({'owner':'a','project_id':'p','space_id':'s'},{'ready':False})
    assert not store.root.exists()


def test_empty_pilot_reports_missing_evidence_not_success(ledger):
    report = ledger.report()
    assert report['verified_tasks'] == report['observation_days_utc'] == 0
    assert 'continuous_7_day_observation_missing' in report['blockers']
    assert not report['g_sb4_passed'] and not report['rollout_enabled']


def test_concurrent_task_capture_idempotency_and_conflict(ledger):
    with ThreadPoolExecutor(max_workers=4) as pool:
        events = list(pool.map(lambda _:ledger.append('task',{'task_id':'one','authority_verified':True}),range(4)))
    assert len({e['hash'] for e in events}) == 1
    assert ledger.report()['verified_tasks'] == 1
    with pytest.raises(KnowledgeError, match='不同证据'):
        ledger.append('task',{'task_id':'one','authority_verified':False})


def test_reviews_bind_exact_evidence_and_counts(ledger):
    event=ledger.append('task',{'task_id':'one','authority_verified':True})
    with pytest.raises(KnowledgeError, match='哈希'):
        ledger.review({**review(event),'evidence_hash':'0'*64})
    with pytest.raises(KnowledgeError, match='数量'):
        ledger.review({**review(event),'citations_supported':11})
    ledger.review(review(event)); ledger.review(review(event))
    assert ledger.report()['attested_task_reviews']==1


def test_10_same_day_tasks_do_not_fake_seven_days(ledger):
    for n in range(10):
        event=ledger.append('task',{'task_id':str(n),'authority_verified':True});ledger.review(review(event))
        ledger.append('observation',{'healthy':True})
    report=ledger.report()
    assert report['verified_tasks']==10 and report['observation_days_utc']==1
    assert not report['collection_criteria_met'] and not report['g_sb4_passed']


def test_elapsed_time_without_daily_observation_is_not_continuous(ledger, monkeypatch):
    start=now();ledger.append('observation',{'healthy':True})
    monkeypatch.setattr(pilot,'now',lambda:start+timedelta(days=8))
    ledger.append('observation',{'healthy':True})
    assert 'continuous_7_day_observation_missing' in ledger.report()['blockers']


def test_complete_synthetic_window_still_requires_independent_signoff(ledger, monkeypatch):
    start=now()
    for n in range(8):
        monkeypatch.setattr(pilot,'now',lambda n=n:start+timedelta(days=n))
        ledger.append('observation',{'healthy':True})
    for n in range(10):
        event=ledger.append('task',{'task_id':str(n),'authority_verified':True});ledger.review(review(event))
    report=ledger.report()
    assert report['collection_criteria_met'] and report['observation_elapsed_hours']==168
    assert report['lookup_seconds_saved']==200
    assert report['independent_signoffs_required'] and not report['g_sb4_passed']
    assert not report['rollout_enabled']
    monkeypatch.setattr(pilot,'now',lambda:start+timedelta(days=9))
    assert 'latest_observation_missing_or_stale' in ledger.report()['blockers']


def test_failure_and_major_error_remain_visible(ledger):
    ledger.append('observation',{'healthy':False,'error_code':'authority_unavailable'})
    ledger.append('observation',{'healthy':True})
    event=ledger.append('task',{'task_id':'one','authority_verified':True})
    ledger.review({**review(event),'major_factual_error':True,'real_research_task':False,'citations_supported':1})
    blockers=ledger.report()['blockers']
    assert 'unresolved_observation_failure' in blockers and 'major_factual_error' in blockers
    assert 'task_citation_faithfulness_below_95_percent' in blockers and 'non_real_task_attested' in blockers


@pytest.mark.parametrize('change',['content','clock','symlink'])
def test_tamper_clock_and_symlinks_are_rejected(ledger,monkeypatch,change):
    ledger.append('observation',{'healthy':True})
    if change=='content':
        path=ledger.root/'events.json'; value=json.loads(path.read_text());value[0]['payload']['healthy']=False;path.write_text(json.dumps(value))
    elif change=='clock':
        earlier=now()-timedelta(hours=1);monkeypatch.setattr(pilot,'now',lambda:earlier)
    else:
        path=ledger.root/'events.json';path.unlink();path.symlink_to(ledger.root/'config.json')
    with pytest.raises(KnowledgeError): ledger.report()


@pytest.fixture
def task_authority(svc):
    sid, source, change=prepare(svc);publish(svc,change)
    snapshot=KnowledgeContextService(svc).build('owner',sid,'project-a','任务验收',persist=True)
    stamp=now().isoformat()
    scope={'owner':'owner','project_id':'project-a','space_id':sid,'started_at':(now()-timedelta(minutes=1)).isoformat()}
    engine=sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE orchestration_missions(id TEXT,owner_user_id TEXT,project_id TEXT,status TEXT,completed_at TEXT,plan_version INTEGER)')
        conn.exec_driver_sql('CREATE TABLE work_runs(id TEXT,mission_id TEXT,project_id TEXT,status TEXT,input_context TEXT,ended_at TEXT,dispatch_id TEXT)')
        conn.exec_driver_sql('CREATE TABLE mission_context_bindings(id TEXT,mission_id TEXT,plan_version INTEGER,step_id TEXT,context_pack_id TEXT,status TEXT)')
        conn.exec_driver_sql("INSERT INTO mission_context_bindings VALUES ('binding','task',1,'step','pack','ready')")
        conn.execute(sa.text('INSERT INTO orchestration_missions VALUES (:id,:owner,:project,:state,:stamp,1)'),dict(id='task',owner='owner',project='project-a',state='completed',stamp=stamp))
        conn.execute(sa.text('INSERT INTO work_runs VALUES (:id,:mission,:project,:state,:context,:stamp,:dispatch)'),dict(id='run',mission='task',project='project-a',state='completed',context=json.dumps({'context_binding':{'id':'binding','context_pack_id':'pack'},'plan_version':1}),stamp=stamp,dispatch='mission-step:step'))
    metadata={'status':'captured','mode':'shadow','injected':False,'memory_order_changed':False,
        'snapshot_id':snapshot['id'],'content_hash':snapshot['content_hash'],'baseline_refs_hash':snapshot['baseline_refs_hash']}
    pack={'id':'pack','user_id':'owner','project_id':'project-a','mission_id':'task','retrieval_health':json.dumps({'reviewed_knowledge_shadow':metadata})}
    yield scope,engine,pack,metadata,source
    engine.dispose()


def capture(svc, fixture):
    scope,engine,pack,_,_=fixture
    return capture_task(svc,scope,engine,engine,lambda pid:pack,task_id='task',work_run_id='run',context_pack_id='pack')


def test_task_requires_registered_completed_scope_bound_shadow(svc,task_authority):
    result=capture(svc,task_authority)
    assert result['authority_verified'] and result['real_task_review']=='pending'
    assert result['knowledge_count']>0
    assert 'content' not in result and 'query' not in result
    # Authority connection was query_only; no task/WorkRun mutation was needed.
    with task_authority[1].connect() as conn:
        assert conn.exec_driver_sql('select status from work_runs').scalar_one()=='completed'


@pytest.mark.parametrize('bad',['owner','project','old_task','pack_scope','mode','snapshot_hash','baseline','withdrawal','binding','unfinished'])
def test_task_evidence_cannot_mix_scope_or_revoked_context(svc,task_authority,bad):
    scope,engine,pack,metadata,source=task_authority
    if bad=='owner': scope['owner']='other'
    elif bad=='project': scope['project_id']='other'
    elif bad=='old_task': scope['started_at']=(now()+timedelta(days=1)).isoformat()
    elif bad=='pack_scope': pack['mission_id']='another'
    elif bad=='mode': metadata['mode']='enabled'
    elif bad=='snapshot_hash': metadata['content_hash']='0'*64
    elif bad=='baseline': metadata['baseline_refs_hash']='0'*64
    elif bad in {'binding','unfinished'}:
        with engine.begin() as conn:
            conn.exec_driver_sql("UPDATE mission_context_bindings SET step_id='other'" if bad=='binding' else "UPDATE work_runs SET status='running'")
    else: svc.retract_source('owner',source['version_id'],'withdraw')
    pack['retrieval_health']=json.dumps({'reviewed_knowledge_shadow':metadata})
    with pytest.raises(KnowledgeError): capture(svc,task_authority)


def test_observation_checks_explicit_mapping_and_failure_counts(svc,task_authority,monkeypatch):
    scope,*_=task_authority
    for key in ['SECOND_BRAIN_ENABLED','SECOND_BRAIN_WRITE_ENABLED']:monkeypatch.setenv(key,'true')
    monkeypatch.setenv('SECOND_BRAIN_CONTEXT_MODE','shadow')
    monkeypatch.setenv('SECOND_BRAIN_CONTEXT_SPACES',json.dumps({'project-a':[scope['space_id']]}))
    assert observe(svc,scope,{'ready':True})['healthy']
    monkeypatch.setenv('SECOND_BRAIN_CONTEXT_SPACES','{}')
    assert not observe(svc,scope,{'ready':True})['healthy']
