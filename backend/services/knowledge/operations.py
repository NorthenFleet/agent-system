"""Bounded, explicit periodic maintenance. Local receipts, no outbound messages."""
from datetime import datetime
import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from models.knowledge_operations_v4 import proposals, runs
from services.knowledge.bridges import KnowledgeBridges
from services.knowledge.service import KnowledgeError, digest, ident, now


class KnowledgeOperations:
    def __init__(self, service):
        self.service, self.engine = service, service.engine

    def maintain(self, actor, sid, cadence='weekly', at=None):
        at = at or now()
        if cadence not in {'daily', 'weekly', 'monthly'} or not isinstance(at, datetime):
            raise KnowledgeError('invalid_cadence', '仅支持每日、每周或每月维护')
        # UTC bucket is explicit and stable across hosts and concurrent workers.
        period = {'daily': at.strftime('%Y-%m-%d'), 'weekly': at.strftime('%G-W%V'),
                  'monthly': at.strftime('%Y-%m')}[cadence]
        period_key = cadence + ':' + period
        with self.engine.begin() as conn:
            space = self.service.space(conn, actor, sid, lock=True)
            found = conn.execute(sa.select(runs).where(runs.c.space_id == sid,
                runs.c.period_key == period_key)).mappings().first()
            if found:
                return dict(found)
            from services.knowledge.maintenance import report
            structural = report(self.service, actor, sid, _conn=conn)
            bridge = KnowledgeBridges(self.service)
            invalidated = []
            for p in conn.execute(sa.select(proposals).where(proposals.c.space_id == sid)).mappings():
                try:
                    bridge._validate_proposal(conn, space, p)
                except KnowledgeError as exc:
                    invalidated.append(p['id'])
                    if p['status'] == 'export_only':
                        conn.execute(proposals.update().where(proposals.c.id == p['id']).values(
                            status='needs_review', invalid_reason=exc.code))
                        self.service.audit(conn, actor, sid, 'memory.needs_review', p['id'], {'reason': exc.code})
            failures = sorted(conn.execute(sa.select(t.jobs.c.id).where(t.jobs.c.space_id == sid,
                t.jobs.c.stage == 'failed')).scalars())
            dead = sorted(conn.execute(sa.select(t.outbox.c.id).where(t.outbox.c.space_id == sid,
                t.outbox.c.status.in_(['dead', 'blocked_drift']))).scalars())
            body = {'sequence': space['sequence'], 'access_epoch': space['access_epoch'],
                'structural': structural, 'failed_jobs': failures, 'dead_letters': dead,
                'memory_needs_review': sorted(invalidated), 'auto_publish': False, 'auto_ingest': False}
            checksum = digest(body)
            previous = conn.execute(sa.select(runs).where(runs.c.space_id == sid)
                .order_by(runs.c.created_at.desc(), runs.c.id).limit(1)).mappings().first()
            changed = previous is None or previous['content_hash'] != checksum
            actionable = bool(structural['issues'] or structural['pending_changes'] or failures or dead or invalidated)
            result = {'id': ident('kmr'), 'space_id': sid, 'period_key': period_key,
                'report': {**body, 'changed': changed, 'attention_required': changed and actionable,
                           'notification_sent': False}, 'content_hash': checksum, 'work_run_id': '', 'created_at': now()}
            conn.execute(runs.insert().values(**result))
            self.service.audit(conn, actor, sid, 'maintenance.recorded', result['id'],
                               {'hash': checksum, 'period': period_key, 'attention_required': changed and actionable})
            return result

    def history(self, actor, sid):
        with self.engine.connect() as conn:
            self.service.space(conn, actor, sid)
            return {'items': [dict(r) for r in conn.execute(sa.select(runs).where(runs.c.space_id == sid)
                .order_by(runs.c.created_at.desc(), runs.c.id).limit(30)).mappings()]}

    def reconcile_work_run(self, actor, sid, receipt, work_runs):
        """Same receipt ID is the ledger idempotency key, including lost-response retries."""
        with self.engine.begin() as conn:
            space = self.service.space(conn, actor, sid, lock=True)
            current = conn.execute(sa.select(runs).where(runs.c.id == receipt['id'],
                runs.c.space_id == sid)).mappings().one()
            # Lock across ledger operation prevents competing reconcilers; no atomicity claim.
            run, _ = work_runs.claim_at_most_once(dispatch_id=current['id'], agent_id='knowledge-maintainer',
                request_binding={'space_id': sid, 'content_hash': current['content_hash']},
                executor='knowledge-maintenance-v1', project_id=space['project_id'],
                idempotency_key='knowledge-maintenance:' + current['id'],
                input_context={'space_id': sid, 'maintenance_id': current['id']})
            if run['status'] == 'claimed':
                run = work_runs.transition(run['id'], 'running', actor='knowledge-maintainer')
            if run['status'] == 'running':
                run = work_runs.transition(run['id'], 'review', actor='knowledge-maintainer')
            if run['status'] == 'review':
                work_runs.transition(run['id'], 'completed', actor='knowledge-maintainer',
                    result_summary='maintenance:' + current['id'])
            if run['status'] in {'failed', 'cancelled', 'blocked'}:
                raise KnowledgeError('maintenance_ledger_recovery', '维护执行记录需要人工恢复', 409)
            conn.execute(runs.update().where(runs.c.id == current['id']).values(work_run_id=run['id']))
            return run['id']


def run_scheduled_once(service, work_runs):
    """Only explicitly configured owner+space entries; disabled by default."""
    import json
    import os
    from services.knowledge.runtime import flag, require_enabled
    require_enabled(write=True)
    if not flag('SECOND_BRAIN_MAINTENANCE_ENABLED'):
        return 0
    try:
        config = json.loads(os.getenv('SECOND_BRAIN_MAINTENANCE_SPACES', '[]'))
        if not isinstance(config, list) or len(config) > 20:
            raise ValueError()
        if any(not isinstance(x, dict) or set(x) != {'actor', 'space_id', 'cadence'} or not all(isinstance(v, str) and v for v in x.values()) for x in config):
            raise ValueError()
    except (ValueError, TypeError):
        raise KnowledgeError('maintenance_config', '周期维护配置不合法', 503)
    operations = KnowledgeOperations(service)
    for entry in config:
        receipt = operations.maintain(entry['actor'], entry['space_id'], entry['cadence'])
        operations.reconcile_work_run(entry['actor'], entry['space_id'], receipt, work_runs)
    return len(config)
