"""Private pilot evidence collection. Read authorities; never enable a rollout.

Local hashes detect accidental drift, not an operator rewriting the ledger.
Human labels are attestations, not authenticated approval of a production gate.
"""
import fcntl
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
import sqlalchemy as sa
from pydantic import Field
from models import knowledge_schema_v1 as t
from services.knowledge.backup import private_directory, read_private, write_private, encode
from services.knowledge.contracts import Contract
from services.knowledge.context import KnowledgeContextService
from services.knowledge.service import KnowledgeError, digest, now


class PilotScope(Contract):
    owner: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    space_id: str = Field(min_length=1, max_length=80)


class TaskReview(Contract):
    task_id: str = Field(min_length=1, max_length=160)
    evidence_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewer: str = Field(min_length=1, max_length=160)
    real_research_task: bool
    baseline_lookup_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    pilot_lookup_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    citations_checked: int = Field(ge=1, le=10000)
    citations_supported: int = Field(ge=0, le=10000)
    citations_adopted: int = Field(ge=0, le=10000)
    corrections: int = Field(ge=0, le=10000)
    major_factual_error: bool


class PilotLedger:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()

    def initialize(self, scope, preflight):
        scope = PilotScope.model_validate(scope).model_dump()
        if not preflight.get('ready'):
            raise KnowledgeError('pilot_preflight_failed', '预检尚未通过，不能开始真实观察', 409)
        private_directory(self.root, create=True)
        config = {'format': 'kb-pilot-v1', **scope, 'started_at': now().isoformat(),
                  'preflight_hash': digest(preflight), 'mode': 'shadow', 'rollout_enabled': False}
        write_private(self.root / 'config.json', encode(config))
        write_private(self.root / 'events.json', b'[]')
        write_private(self.root / '.lock', b'')
        return config

    def read(self):
        private_directory(self.root)
        config = json.loads(read_private(self.root / 'config.json', 16384))
        if config.get('format') != 'kb-pilot-v1' or config.get('mode') != 'shadow' or config.get('rollout_enabled') is not False:
            raise KnowledgeError('pilot_invalid', '试点配置格式不合法')
        PilotScope.model_validate({k: config[k] for k in ('owner', 'project_id', 'space_id')})
        events = json.loads(read_private(self.root / 'events.json', 10 * 1024 * 1024))
        previous, last_time = digest(config), datetime.fromisoformat(config['started_at'])
        if last_time.tzinfo is None or last_time > now():
            raise KnowledgeError('pilot_clock_invalid', '试点起始时间不合法', 409)
        if not isinstance(events, list) or len(events) > 1000:
            raise KnowledgeError('pilot_budget', '试点记录超过预算')
        for number, event in enumerate(events, 1):
            body = {k: v for k, v in event.items() if k != 'hash'}
            timestamp = datetime.fromisoformat(event['captured_at'])
            if event['sequence'] != number or event['previous_hash'] != previous or event['hash'] != digest(body):
                raise KnowledgeError('pilot_hash_mismatch', '试点记录链校验失败', 409)
            if event['kind'] not in {'observation', 'task', 'review'}:
                raise KnowledgeError('pilot_event', '试点事件类型不合法')
            if timestamp.tzinfo is None or timestamp < last_time or timestamp > now():
                raise KnowledgeError('pilot_clock_invalid', '观察时间倒退或来自未来', 409)
            previous, last_time = event['hash'], timestamp
        return config, events

    def append(self, kind, payload):
        if kind not in {'observation', 'task', 'review'}:
            raise KnowledgeError('pilot_event', '未知试点记录')
        private_directory(self.root)
        fd = os.open(self.root / '.lock', os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(fd, 'r+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            config, events = self.read()
            if kind in {'task', 'review'}:
                existing = next((e for e in events if e['kind'] == kind and e['payload']['task_id'] == payload['task_id']), None)
                if existing:
                    if existing['payload'] != payload:
                        raise KnowledgeError('pilot_duplicate_conflict', '同一任务已有不同证据或评审；不可覆盖', 409)
                    return existing
            if len(events) >= 1000:
                raise KnowledgeError('pilot_budget', '试点最多保存 1000 条记录')
            event = {'sequence': len(events) + 1, 'kind': kind, 'captured_at': now().isoformat(),
                     'previous_hash': events[-1]['hash'] if events else digest(config), 'payload': payload}
            event['hash'] = digest(event)
            data = encode([*events, event])
            if len(data) > 10 * 1024 * 1024:
                raise KnowledgeError('pilot_budget', '试点记录超过 10 MiB')
            handle, temporary = tempfile.mkstemp(prefix='.events-', dir=self.root)
            try:
                with os.fdopen(handle, 'wb') as out:
                    out.write(data); out.flush(); os.fsync(out.fileno())
                os.replace(temporary, self.root / 'events.json')
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return event

    def review(self, payload):
        payload = TaskReview.model_validate(payload).model_dump()
        if max(payload['citations_supported'], payload['citations_adopted']) > payload['citations_checked']:
            raise KnowledgeError('invalid_review', '支持/采用数量不能超过已核对引用数量')
        _, events = self.read()
        task = next((e for e in events if e['kind'] == 'task' and e['payload']['task_id'] == payload['task_id']), None)
        if not task or task['hash'] != payload['evidence_hash']:
            raise KnowledgeError('review_unbound', '人工评审必须绑定已采集的任务证据哈希', 409)
        return self.append('review', payload)

    def report(self):
        config, events = self.read()
        observations = [e for e in events if e['kind'] == 'observation']
        tasks = [e for e in events if e['kind'] == 'task']
        reviews = [e['payload'] for e in events if e['kind'] == 'review']
        times = [datetime.fromisoformat(e['captured_at']) for e in observations]
        days = len({dt.astimezone(timezone.utc).date() for dt in times})
        elapsed = (times[-1] - times[0]).total_seconds() if len(times) >= 2 else 0
        max_gap = max(((b-a).total_seconds() for a,b in zip(times,times[1:])), default=0)
        stale = not times or (now()-times[-1]).total_seconds() > 86400
        checked = sum(r['citations_checked'] for r in reviews)
        supported = sum(r['citations_supported'] for r in reviews)
        blockers = []
        if len(tasks) < 10: blockers.append('fewer_than_10_verified_tasks')
        if any(e['payload'].get('authority_verified') is not True for e in tasks): blockers.append('task_authority_unverified')
        if len(reviews) != len(tasks) or len(reviews) < 10: blockers.append('human_task_reviews_missing')
        if any(not r['real_research_task'] for r in reviews): blockers.append('non_real_task_attested')
        if elapsed < 7*86400 or days < 7 or max_gap > 36*3600: blockers.append('continuous_7_day_observation_missing')
        if stale: blockers.append('latest_observation_missing_or_stale')
        if any(not e['payload'].get('healthy') for e in observations): blockers.append('unresolved_observation_failure')
        if not checked or supported/checked < .95: blockers.append('task_citation_faithfulness_below_95_percent')
        if any(r['major_factual_error'] for r in reviews): blockers.append('major_factual_error')
        # These are independent signed-off artifacts; task-level labels cannot replace them.
        external = ['independent_human_gold_and_security_gate', '1000_page_performance_gate',
                    'production_backup_recovery_and_retention_signoff', 'authenticated_final_acceptance']
        return {'format': 'kb-pilot-report-v1', 'started_at': config['started_at'],
            'verified_tasks': len(tasks), 'attested_task_reviews': len(reviews),
            'observation_days_utc': days, 'observation_elapsed_hours': round(elapsed/3600, 3),
            'max_observation_gap_hours': round(max_gap/3600, 3),
            'task_citation_faithfulness': supported/checked if checked else None,
            'lookup_seconds_saved': sum(r['baseline_lookup_seconds']-r['pilot_lookup_seconds'] for r in reviews),
            'citations_adopted': sum(r['citations_adopted'] for r in reviews),
            'human_corrections': sum(r['corrections'] for r in reviews),
            'collection_criteria_met': not blockers, 'blockers': blockers,
            'independent_signoffs_required': external, 'g_sb4_passed': False,
            'rollout_enabled': False, 'last_event_hash': events[-1]['hash'] if events else digest(config)}


def observe(service, scope, preflight):
    """No body text or credentials in exported health evidence."""
    from services.knowledge.runtime import flag
    from services.knowledge.context import mode
    with service.engine.connect() as conn:
        conn.exec_driver_sql('SET TRANSACTION READ ONLY')
        conn.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
        space = service.space(conn, scope['owner'], scope['space_id'])
        if space['project_id'] != scope['project_id']:
            raise KnowledgeError('pilot_scope_mismatch', '试点项目与空间不匹配', 404)
        def count(table, *filters):
            return conn.execute(sa.select(sa.func.count()).select_from(table).where(table.c.space_id == space['id'], *filters)).scalar_one()
        counts = {'pages': count(t.pages, t.pages.c.status == 'active'),
            'pending_changes': count(t.changes, t.changes.c.status.in_(['awaiting_review','approved'])),
            'failed_jobs': count(t.jobs, t.jobs.c.stage == 'failed'),
            'blocked_projections': count(t.outbox, t.outbox.c.status.in_(['dead','blocked_drift']))}
        mapping = json.loads(os.getenv('SECOND_BRAIN_CONTEXT_SPACES', '{}'))
        mapped = isinstance(mapping, dict) and mapping.get(scope['project_id']) == [scope['space_id']]
        healthy = bool(mapped and flag('SECOND_BRAIN_WRITE_ENABLED') and preflight.get('ready') and mode() == 'shadow' and flag('SECOND_BRAIN_ENABLED')
                       and not counts['failed_jobs'] and not counts['blocked_projections'])
        return {'healthy': healthy, 'preflight_ready': bool(preflight.get('ready')),
            'preflight_hash': digest(preflight), 'context_mode': mode(), 'counts': counts,
            'sequence': space['sequence'], 'access_epoch': space['access_epoch']}


def read_record(engine, sql, params):
    with engine.connect() as conn:
        if engine.dialect.name == 'postgresql':
            conn.exec_driver_sql('SET TRANSACTION READ ONLY')
            conn.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
        elif engine.dialect.name == 'sqlite':
            conn.exec_driver_sql('PRAGMA query_only = ON')
        result = conn.execute(sa.text(sql), params).mappings().first()
        return dict(result) if result else None


def capture_task(service, scope, mission_engine, work_engine, pack_reader, *, task_id, work_run_id, context_pack_id):
    mission = read_record(mission_engine, '''SELECT id, owner_user_id, project_id, status, completed_at, plan_version
        FROM orchestration_missions WHERE id=:id''', {'id': task_id})
    run = read_record(work_engine, '''SELECT id, mission_id, project_id, status, input_context, ended_at, dispatch_id
        FROM work_runs WHERE id=:id''', {'id': work_run_id})
    if not mission or not run or mission['owner_user_id'] != scope['owner'] or mission['project_id'] != scope['project_id']:
        raise KnowledgeError('pilot_task_scope', '任务不存在或不在试点范围', 404)
    if mission['status'] != 'completed' or run['status'] != 'completed' or run['mission_id'] != task_id or run['project_id'] != scope['project_id']:
        raise KnowledgeError('pilot_task_incomplete', '需要同项目已完成的 Mission 和 WorkRun', 409)
    if not mission['completed_at'] or not run['ended_at']:
        raise KnowledgeError('pilot_task_incomplete', '任务完成时间缺失', 409)
    completed, ended = datetime.fromisoformat(mission['completed_at']), datetime.fromisoformat(run['ended_at'])
    start = datetime.fromisoformat(scope['started_at'])
    if any(dt.tzinfo is None or dt < start or dt > now() for dt in [completed, ended]):
        raise KnowledgeError('pilot_task_predates_start', '不能把试点开始前的任务计为新观察')
    context = json.loads(run['input_context'] or '{}')
    binding_ref = context.get('context_binding') or {}
    if not isinstance(binding_ref, dict) or binding_ref.get('context_pack_id') != context_pack_id:
        raise KnowledgeError('pilot_pack_unbound', 'WorkRun 未绑定该 Context Pack', 409)
    binding = read_record(mission_engine, '''SELECT id,mission_id,plan_version,step_id,context_pack_id,status
        FROM mission_context_bindings WHERE id=:id''', {'id':binding_ref.get('id','')})
    if (not binding or binding['mission_id'] != task_id or binding['context_pack_id'] != context_pack_id
            or binding['plan_version'] != mission['plan_version'] or binding['plan_version'] != context.get('plan_version')
            or not binding['step_id'] or run['dispatch_id'] != 'mission-step:' + binding['step_id']
            or binding['status'] not in {'ready','empty'}):
        raise KnowledgeError('pilot_binding_mismatch', '原始任务绑定与执行记录不一致', 409)
    pack = pack_reader(context_pack_id)
    if not pack or (pack['user_id'], pack['project_id'], pack['mission_id']) != (scope['owner'],scope['project_id'],task_id):
        raise KnowledgeError('pilot_pack_scope', 'Context Pack 作用域不匹配', 404)
    metadata = json.loads(pack['retrieval_health'] or '{}').get('reviewed_knowledge_shadow', {})
    if metadata.get('status') != 'captured' or metadata.get('mode') != 'shadow' or metadata.get('injected') is not False or metadata.get('memory_order_changed') is not False:
        raise KnowledgeError('pilot_not_shadow', '任务缺少有效的独立 shadow 记录', 409)
    snapshot = KnowledgeContextService(service).read(scope['owner'], metadata.get('snapshot_id',''), scope['project_id'])
    if snapshot['space_id'] != scope['space_id'] or snapshot['content_hash'] != metadata.get('content_hash'):
        raise KnowledgeError('pilot_snapshot_mismatch', 'Shadow 快照空间或哈希不匹配', 409)
    if snapshot['baseline_refs_hash'] != metadata.get('baseline_refs_hash'):
        raise KnowledgeError('pilot_baseline_mismatch', '基线引用集合哈希不匹配', 409)
    return {'task_id': task_id, 'work_run_id': work_run_id, 'context_pack_id': context_pack_id,
        'mission_hash': digest(mission), 'work_run_hash': digest(run),
        'snapshot_id': snapshot['id'], 'snapshot_hash': snapshot['content_hash'],
        'baseline_refs_hash': snapshot['baseline_refs_hash'], 'knowledge_count': len(snapshot['items']),
        'completed_at': mission['completed_at'], 'authority_verified': True, 'real_task_review': 'pending'}
