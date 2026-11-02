"""Registered fixed versions in; export-only memory proposals out.

The existing Memory API deduplicates mission content, but has no proposal-ID
contract or synchronous knowledge dependency check at approval/execution.
Never impersonate a mission or write a native Memory Candidate here.
"""
from typing import Literal
import json
import sqlalchemy as sa
from pydantic import Field
from models import knowledge_schema_v1 as t
from models.knowledge_operations_v4 import imports, proposals
from services.knowledge.contracts import Contract
from services.knowledge.context import KnowledgeContextService
from services.knowledge.service import KnowledgeError, digest, ident, now, row


class ExternalReference(Contract):
    kind: Literal['artifact', 'document']
    container_id: str = Field(min_length=1, max_length=160)
    object_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    expected_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    selected: bool = False


class MemoryProposal(Contract):
    page_id: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=80)
    requested_scope: Literal['project', 'profile', 'agent'] = 'project'
    agent_id: str = Field(default='', max_length=160)
    memory_key: str = Field(min_length=1, max_length=200)
    proposed_content: str = Field(min_length=1, max_length=12000)
    reason: str = Field(min_length=1, max_length=2000)


def registered_reference(actor, project, request):
    """Only server-side registered IDs; never accept a path from the client."""
    if request['kind'] == 'artifact':
        from services.command_center_service import command_center_service
        from services.mission_artifact_reader import read_artifact
        with command_center_service.connect() as conn:
            record = conn.execute('''SELECT a.*, m.owner_user_id, m.project_id
                FROM mission_artifacts a JOIN orchestration_missions m ON m.id=a.mission_id
                WHERE a.id=? AND a.mission_id=? AND a.plan_version=?''',
                (request['object_id'], request['container_id'], request['version'])).fetchone()
            if not record or record['owner_user_id'] != actor or record['project_id'] != project:
                raise KnowledgeError('not_found', '登记成果不存在或不可访问', 404)
            record = dict(record)
        # Explicit selection is required: an artifact alone is not proof of acceptance.
        if not request['selected']:
            raise KnowledgeError('selection_required', '请明确选定该成果版本；登记不等于验收通过')
        if record['content_hash'] != request['expected_hash']:
            raise KnowledgeError('external_version_changed', '成果登记哈希不匹配', 409)
        try:
            name, data = read_artifact(record)
        except (OSError, ValueError) as exc:
            raise KnowledgeError('external_unverifiable', '登记成果文件或哈希不可核验', 409) from exc
        lineage = json.loads(record.get('metadata_json') or '{}')
        if len(json.dumps(lineage)) > 32768:
            raise KnowledgeError('lineage_budget', '成果来源链超过预算，需要单独核对')
        return name, data, {'lineage_snapshot': lineage, 'lifecycle': 'user_selected_unverified',
            'mission_id': record['mission_id'], 'work_run_id': record.get('work_run_id') or '',
            'lineage': 'registered_artifact', 'upstream_hash': record['content_hash']}
    from database import engine
    from services.structured_document_service import structured_document_codec
    # Core reflection avoids importing a service that initializes a document workspace.
    with engine.connect() as conn:
        versions = sa.Table('writing_document_versions', sa.MetaData(), autoload_with=conn)
        record = conn.execute(sa.select(versions).where(versions.c.project_id == project,
            versions.c.document_id == request['container_id'], versions.c.id == request['object_id'],
            versions.c.document_revision == request['version'])).mappings().first()
        if not record:
            raise KnowledgeError('not_found', '登记文档修订不存在或不可访问', 404)
        if structured_document_codec.document_sha256(record['content_json']) != record['content_sha256']:
            raise KnowledgeError('external_unverifiable', '文档修订哈希不可核验', 409)
        if record['content_sha256'] != request['expected_hash']:
            raise KnowledgeError('external_version_changed', '文档修订哈希不匹配', 409)
        if not request['selected']:
            raise KnowledgeError('selection_required', '请明确选定该文档修订')
        # Deterministic projection from the fixed authority, not a stale markdown cache.
        data = structured_document_codec.to_markdown(record['content_json']).encode()
        return 'document-r%d.md' % request['version'], data, {
            'lifecycle': record['lifecycle_status'], 'lineage': 'fixed_document_revision',
            'upstream_hash': record['content_sha256'], 'parent_revision': record.get('parent_revision', 0), 'projection': 'structured-markdown-v1'}


class KnowledgeBridges:
    def __init__(self, service, resolver=None):
        self.service, self.engine = service, service.engine
        self.resolver = resolver or registered_reference
        self.context = KnowledgeContextService(service)

    def import_reference(self, actor, sid, request, key):
        request = ExternalReference.model_validate(request).model_dump()
        with self.engine.begin() as conn:
            space = self.service.space(conn, actor, sid, lock=True)
            if not space['project_id']:
                raise KnowledgeError('project_required', '成果导入需要绑定项目')
            # Revalidate upstream authorization and bytes even on an idempotent retry.
            name, data, metadata = self.resolver(actor, space['project_id'], request)
            if not request['selected']:
                raise KnowledgeError('selection_required', '请明确选定该成果版本')
            ref_key = digest({k: v for k, v in request.items() if k not in {'selected', 'expected_hash'}})
            def apply():
                existing = conn.execute(sa.select(imports).where(imports.c.space_id == sid,
                    imports.c.reference_key == ref_key)).mappings().first()
                if existing:
                    return {'id': existing['id'], 'version_id': existing['source_version_id'], 'duplicate': True}
                result = self.service.upload(actor, sid, name, data, 'external:' + ref_key, _conn=conn)
                ref = {**request, **metadata, 'content_sha256': digest(data),
                    'independent_evidence': False, 'auto_extract': False}
                iid = ident('kimp')
                conn.execute(imports.insert().values(id=iid, space_id=sid,
                    source_version_id=result['version_id'], reference_key=ref_key, reference=ref, created_at=now()))
                self.service.audit(conn, actor, sid, 'external.registered', iid, {'reference_key': ref_key})
                return {'id': iid, 'version_id': result['version_id'], 'duplicate': result['duplicate']}
            result = self.service.idempotent(conn, actor, sid, 'external.import', key, request, apply)
            version = row(conn, t.versions, result['version_id'])
            if row(conn, t.sources, version['source_id'])['status'] != 'active':
                raise KnowledgeError('source_retracted', '已登记来源已撤回，不可重复恢复', 409)
            if version['content_sha256'] != digest(data):
                raise KnowledgeError('external_version_changed', '固定成果内容已变化', 409)
            return {**result, 'auto_extract': False, 'independent_evidence': False,
                'reference': row(conn, imports, result['id'])['reference']}

    def propose_memory(self, actor, sid, request, key):
        request = MemoryProposal.model_validate(request).model_dump()
        with self.engine.begin() as conn:
            space = self.service.space(conn, actor, sid, lock=True)
            if request['requested_scope'] == 'project' and not space['project_id']:
                raise KnowledgeError('project_required', '项目记忆需要绑定项目')
            if (request['requested_scope'] == 'agent') != bool(request['agent_id']):
                raise KnowledgeError('invalid_scope', 'Agent 范围必须填写 Agent ID，其他范围不可携带')
            entry = self.context._entry(conn, space, request, set())
            def apply():
                pid = ident('kmp')
                payload = {**request, 'proposal_id': pid, 'owner_user_id': actor,
                    'project_id': space['project_id'], 'knowledge_revision_ref': entry['source_ref'],
                    'evidence_refs': entry['evidence_refs'], 'entry': entry,
                    'mode': 'export_only', 'approved': False,
                    'restriction': 'Native Memory approval/execution needs synchronous dependency validation.'}
                conn.execute(proposals.insert().values(id=pid, space_id=sid, owner_user_id=actor,
                    payload=payload, content_hash=digest(payload), status='export_only', invalid_reason='', created_at=now()))
                self.service.audit(conn, actor, sid, 'memory.proposed', pid)
                return {'id': pid}
            result = self.service.idempotent(conn, actor, sid, 'memory.propose', key, request, apply)
        return self.read_proposal(actor, result['id'])

    def _validate_proposal(self, conn, space, proposal):
        if proposal['status'] != 'export_only':
            raise KnowledgeError('proposal_invalidated', '记忆提案依据已失效', 409)
        payload = proposal['payload']
        if digest(payload) != proposal['content_hash']:
            raise KnowledgeError('proposal_hash_mismatch', '记忆提案哈希不匹配', 409)
        entry = self.context._entry(conn, space, payload, set())
        if digest(entry) != digest(payload['entry']):
            raise KnowledgeError('proposal_invalidated', '记忆提案依据已变化，请重新提出', 409)
        return payload

    def read_proposal(self, actor, pid):
        with self.engine.begin() as conn:
            proposal, space = self.service.object_space(conn, actor, proposals, pid, lock=True)
            payload = self._validate_proposal(conn, space, proposal)
            return {'id': pid, 'content_hash': proposal['content_hash'], **payload}

    def overview(self, actor, sid):
        with self.engine.begin() as conn:
            space = self.service.space(conn, actor, sid, lock=True)
            items = []
            for p in conn.execute(sa.select(proposals).where(proposals.c.space_id == sid)
                                  .order_by(proposals.c.created_at.desc()).limit(100)).mappings():
                state, reason = p['status'], p['invalid_reason']
                try:
                    self._validate_proposal(conn, space, p)
                except KnowledgeError as exc:
                    state, reason = 'needs_review', exc.code
                items.append({'id': p['id'], 'status': state, 'reason': reason})
            refs = [{'id': r['id'], 'source_version_id': r['source_version_id'], 'reference': r['reference']}
                for r in conn.execute(sa.select(imports).where(imports.c.space_id == sid)
                    .order_by(imports.c.created_at.desc()).limit(100)).mappings()]
            return {'memory_mode': 'export_only', 'automatic_memory_bridge': False,
                    'proposals': items, 'imports': refs, 'limit': 100}
