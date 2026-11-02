"""Authorized, fixed-revision shadow contexts; never an execution input.

No imports of the legacy ContextRetrievalService: its startup touches SQLite.
The bridge attaches only a count/snapshot reference after memory ranking is done.
"""
import json
import os
from datetime import timedelta
import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from models.knowledge_context_v3 import snapshots
from services.knowledge.service import KnowledgeError, digest, ident, now, row
from services.knowledge.retrieval import POLICY, retrieve


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _project(service, conn, actor, sid, project):
    space = service.space(conn, actor, sid, lock=True)
    if not project or space['project_id'] != project:
        raise KnowledgeError('context_scope_mismatch', '上下文必须绑定同一明确项目与空间', 404)
    return space


class KnowledgeContextService:
    def __init__(self, service):
        self.service, self.engine = service, service.engine

    def _entry(self, conn, space, candidate, verified):
        p = row(conn, t.pages, candidate['page_id'])
        if not p or p['space_id'] != space['id'] or p['status'] != 'active':
            raise KnowledgeError('context_invalidated', '知识页不可用于该上下文', 409)
        if p['revision'] != candidate['revision']:
            raise KnowledgeError('context_stale', '知识修订已变化，请重新生成上下文', 409)
        page = self.service._read_revision(conn, p)
        block = next((b for b in page['body_json']['blocks'] if b['block_id'] == candidate['block_id']), None)
        if not block:
            raise KnowledgeError('context_invalidated', '知识段落不存在', 409)
        versions = {}
        for ref in page['citations']:
            vid = ref['source_version_id']
            v = row(conn, t.versions, vid)
            if vid not in verified:
                try:
                    self.service.read_source_bytes(v)
                except OSError as exc:
                    raise KnowledgeError('source_unavailable', '固定来源暂不可读取', 503) from exc
                verified.add(vid)
            versions[vid] = v['content_sha256']
        evidence = []
        for span_id in sorted(set(block['span_ids'])):
            span = row(conn, t.spans, span_id)
            evidence.append({'ref': 'kb-span:' + span_id, 'source_version_id': span['source_version_id'],
                             'text_sha256': span['text_sha256'], 'locator': span['locator']})
        return {'item_type': 'knowledge', 'authority': 'reviewed_knowledge',
            'space_id': space['id'], 'project_id': space['project_id'], 'page_id': p['id'],
            'revision': p['revision'], 'page_revision_id': page['revision_id'], 'source_ref': page['source_ref'],
            'content_hash': page['content_hash'], 'block_id': block['block_id'], 'title': page['title'],
            'content': block['text'], 'epistemic_status': block['epistemic_status'],
            'source_version_refs': sorted('kb-source-version:' + vid for vid in versions),
            'source_hashes': versions, 'evidence_refs': [r['ref'] for r in evidence], 'evidence': evidence,
            'access_epoch': space['access_epoch'], 'retrieval_policy_version': POLICY,
            'relation_path': candidate.get('relation_path', [])}

    def _relations(self, conn, space, entries, verified):
        # Revalidate every expanded endpoint, including its source dependencies.
        for entry in entries:
            for path in entry.get('relation_path', []):
                ends = []
                for pid, number in [(path['from_page_id'], path['from_revision']),
                                    (path['to_page_id'], path['target_evidence_revision'])]:
                    p = row(conn, t.pages, pid)
                    if not p or p['space_id'] != space['id'] or p['status'] != 'active' or p['revision'] != number:
                        raise KnowledgeError('context_stale', '关系依据已变化', 409)
                    fixed = self.service._read_revision(conn, p)
                    self._entry(conn, space, {'page_id': pid, 'revision': number,
                        'block_id': fixed['body_json']['blocks'][0]['block_id']}, verified)
                    ends.append(fixed['revision_id'])
                found = conn.execute(sa.select(t.links.c.id).where(t.links.c.from_revision_id == ends[0],
                    t.links.c.to_revision_id == ends[1], t.links.c.relation == path['relation'],
                    t.links.c.rationale == path['rationale'])).first()
                if not found:
                    raise KnowledgeError('context_invalidated', '固定关系不再可用', 409)

    def build(self, actor, sid, project, question, *, total_chars=12000, baseline_chars=0,
              baseline_refs=None, persist=False, _conn=None):
        if not 1000 <= total_chars <= 30000 or baseline_chars < 0 or not 2 <= len(question.strip()) <= 2000:
            raise KnowledgeError('context_budget', '上下文预算或问题长度不合法')
        budget = max(0, min(total_chars // 4, total_chars - baseline_chars))
        from contextlib import nullcontext
        with (nullcontext(_conn) if _conn is not None else self.engine.begin()) as conn:
            space = _project(self.service, conn, actor, sid, project)
            result = retrieve(conn, self.service, actor, sid, question, 10)
            items, verified, chars = [], set(), 0
            for candidate in result['citations']:
                entry = self._entry(conn, space, candidate, verified)
                size = len(encoded(entry)) + 1
                if chars + size > budget or len(items) >= 5:
                    continue
                items.append(entry); chars += size
            self._relations(conn, space, items, verified)
            payload = {'schema_version': 'kb-context-shadow-v1', 'mode': 'shadow', 'injected': False,
                'space_id': sid, 'project_id': project, 'access_epoch': space['access_epoch'],
                'query_hash': digest(question.encode()), 'retrieval_policy_version': POLICY,
                'baseline_refs_hash': digest(baseline_refs or []), 'items': items,
                'knowledge_refs': list(dict.fromkeys(x['source_ref'] for x in items)),
                'budget': {'total_chars': total_chars, 'baseline_chars': baseline_chars,
                    'knowledge_chars_limit': budget, 'knowledge_chars_used': chars, 'unit': 'unicode_chars'},
                'gaps': ['no_evidence'] if not result['citations'] else (['budget_exhausted'] if not items else []),
                'conflict_count': len(result['conflicts']), 'candidate_count': len(result['citations']),
                'comparison': {'memory_order_changed': False, 'served_knowledge_count': 0}}
            sid_snapshot = ident('kctx') if persist else ''
            content_hash = digest(payload)
            if persist:
                conn.execute(snapshots.insert().values(id=sid_snapshot, space_id=sid, owner_user_id=actor,
                    project_id=project, access_epoch=space['access_epoch'], payload=payload, content_hash=content_hash,
                    created_at=now(), expires_at=now() + timedelta(hours=1)))
                self.service.audit(conn, actor, sid, 'context.shadow_captured', sid_snapshot,
                    {'hash': content_hash, 'item_count': len(items), 'query_hash': payload['query_hash']})
            return {'id': sid_snapshot, 'content_hash': content_hash, **payload}

    def capture(self, actor, sid, request, key):
        with self.engine.begin() as conn:
            _project(self.service, conn, actor, sid, request['project_id'])
            def apply():
                result = self.build(actor, sid, request['project_id'], request['query'],
                    total_chars=request['total_chars'], baseline_chars=request['baseline_chars'], persist=True, _conn=conn)
                # Idempotency responses retain only an opaque ID, never stale content.
                return {'id': result['id']}
            result = self.service.idempotent(conn, actor, sid, 'context.capture', key, request, apply)
        return self.read(actor, result['id'], request['project_id'])

    def read(self, actor, snapshot_id, project):
        with self.engine.begin() as conn:
            snapshot = row(conn, snapshots, snapshot_id)
            if not snapshot or snapshot['owner_user_id'] != actor or snapshot['project_id'] != project:
                raise KnowledgeError('not_found', '知识上下文不存在或不可访问', 404)
            space = _project(self.service, conn, actor, snapshot['space_id'], project)
            if snapshot['expires_at'] <= now():
                raise KnowledgeError('context_expired', '知识上下文已过期，请重新生成', 409)
            if snapshot['access_epoch'] != space['access_epoch']:
                raise KnowledgeError('context_invalidated', '知识访问状态已变化，请重新生成', 409)
            payload = snapshot['payload']
            if digest(payload) != snapshot['content_hash']:
                raise KnowledgeError('context_hash_mismatch', '知识上下文哈希不一致', 409)
            verified = set()
            for entry in payload['items']:
                fresh = self._entry(conn, space, entry, verified)
                if digest(fresh) != digest(entry):
                    raise KnowledgeError('context_hash_mismatch', '知识上下文引用不一致', 409)
            self._relations(conn, space, payload['items'], verified)
            return {'id': snapshot_id, 'content_hash': snapshot['content_hash'], **payload}

    def resolve(self, actor, sid, project, page_id, revision, block_id):
        with self.engine.begin() as conn:
            space = _project(self.service, conn, actor, sid, project)
            return self._entry(conn, space, {'page_id': page_id, 'revision': revision, 'block_id': block_id}, set())


def mode():
    configured = os.getenv('SECOND_BRAIN_CONTEXT_MODE', 'disabled').strip().lower()
    return configured if configured in {'disabled', 'shadow', 'enabled'} else 'disabled'


def require_shadow():
    from services.knowledge.runtime import require_enabled
    require_enabled()
    if mode() != 'shadow':
        raise KnowledgeError('context_gate_closed', '当前仅开放显式 shadow；正式注入仍关闭', 503)


def observe(pack, *, persist):
    """Legacy hook. Failure is redacted and never changes baseline selection."""
    from services.knowledge.runtime import flag, get_service
    configured = mode()
    if configured == 'disabled' or not flag('SECOND_BRAIN_ENABLED'):
        return None
    if configured == 'enabled':
        return {'status': 'blocked', 'reason': 'quality_gate_not_approved', 'mode': 'enabled', 'injected': False}
    try:
        project = str(pack.get('project_id') or '')
        mapping = json.loads(os.getenv('SECOND_BRAIN_CONTEXT_SPACES', '{}'))
        configured_spaces = mapping.get(project, []) if project else []
        # One explicit space per project in this rollout avoids aggregate-budget ambiguity.
        if not isinstance(configured_spaces, list) or len(configured_spaces) != 1 or not isinstance(configured_spaces[0], str):
            return {'status': 'not_configured', 'mode': 'shadow', 'injected': False}
        if persist and not flag('SECOND_BRAIN_WRITE_ENABLED'):
            return {'status': 'write_disabled', 'mode': 'shadow', 'injected': False}
        baseline = pack.get('items') or []
        snapshot = KnowledgeContextService(get_service()).build(str(pack['user_id']), configured_spaces[0], project,
            str(pack['query']), total_chars=12000,
            baseline_chars=sum(len(str(x.get('content') or '')) + len(str(x.get('title') or '')) + 100 for x in baseline),
            baseline_refs=[str(x.get('source_ref') or '') for x in baseline], persist=persist)
        return {'status': 'captured' if persist else 'previewed', 'mode': 'shadow', 'injected': False,
                'snapshot_id': snapshot['id'], 'content_hash': snapshot['content_hash'],
                'item_count': len(snapshot['items']), 'candidate_count': snapshot['candidate_count'],
                'budget': snapshot['budget'], 'baseline_refs_hash': snapshot['baseline_refs_hash'],
                'memory_order_changed': False, 'rollout_version': digest(mapping)[:16]}
    except Exception as exc:
        return {'status': 'unavailable', 'mode': 'shadow', 'injected': False,
                'reason': exc.code if isinstance(exc, KnowledgeError) else 'authority_unavailable'}
