"""Explicit maintenance proposals. Every mutation goes through review/publication."""
from copy import deepcopy
import sqlalchemy as sa
from pydantic import ValidationError
from models import knowledge_schema_v1 as t
from services.knowledge.contracts import MaintenanceRequest, Proposal
from services.knowledge.service import KnowledgeError, digest, ident, now, row


def propose(service, actor, sid, request, key):
    request = MaintenanceRequest.model_validate(request).model_dump()
    with service.engine.begin() as conn:
        space = service.space(conn, actor, sid, lock=True)
        def apply():
            def current(pid, number):
                page = row(conn, t.pages, pid)
                if not page or page['space_id'] != sid or page['status'] != 'active':
                    raise KnowledgeError('not_found', '知识页不存在或不可访问', 404)
                if page['revision'] != number:
                    raise KnowledgeError('revision_conflict', '知识页已变化，请重新读取', 409)
                body = deepcopy(service._read_revision(conn, page)['body_json'])
                body['base_revision'] = number
                return body
            page = current(request['page_id'], request['base_revision'])
            pages, links, targets = [page], [], {}
            action = request['action']
            if action == 'rename':
                if not request['title']:
                    raise KnowledgeError('invalid_title', '需要新标题')
                page['aliases'] = list(dict.fromkeys(page.get('aliases', []) + [page['title']]))
                page['title'] = request['title']
            elif action == 'edit':
                if not request['blocks']:
                    raise KnowledgeError('invalid_blocks', '编辑必须保留有来源的内容段落')
                page['blocks'] = request['blocks']
            else:
                target = current(request['target_page_id'], request['target_revision'])
                if target['page_id'] == page['page_id']:
                    raise KnowledgeError('invalid_target', '请选择另一知识页')
                if action == 'merge':
                    if page['type'] == 'source' or target['type'] != page['type']:
                        raise KnowledgeError('invalid_merge', '只允许同类型概念、实体或综合页合并')
                    blocks = {}
                    for block in target['blocks'] + page['blocks']:
                        fingerprint = digest((block['text'], sorted(block['span_ids']), block['epistemic_status']))
                        blocks.setdefault(fingerprint, dict(block, block_id='b-' + fingerprint[:32]))
                    target['blocks'] = list(blocks.values())
                    target['aliases'] = list(dict.fromkeys(target.get('aliases', []) + page.get('aliases', []) + [page['title']]))
                    page['superseded_by'] = target['page_id']
                    pages.append(target)
                    source_rid = conn.execute(sa.select(t.revisions.c.id).where(t.revisions.c.page_id == page['page_id'],
                        t.revisions.c.revision_no == request['base_revision'])).scalar_one()
                    for relation in conn.execute(sa.select(t.links).where(t.links.c.from_revision_id == source_rid)).mappings():
                        destination_revision = row(conn, t.revisions, relation['to_revision_id'])
                        destination = row(conn, t.pages, destination_revision['page_id'])
                        if destination['id'] in {page['page_id'], target['page_id']}:
                            continue
                        if destination['status'] != 'active':
                            raise KnowledgeError('merge_link_unavailable', '旧页关系指向不可用页面，需先复核关系', 409)
                        service._read_revision(conn, destination)
                        targets[destination['id']] = destination['revision']
                        links.append({'from_page_id': target['page_id'], 'to_page_id': destination['id'],
                                      'relation': relation['relation'], 'rationale': relation['rationale']})
                    links.append({'from_page_id': target['page_id'], 'to_page_id': page['page_id'],
                                  'relation': 'SUPERSEDES', 'rationale': request['reason']})
                else:
                    targets[target['page_id']] = request['target_revision']
                    links.append({'from_page_id': page['page_id'], 'to_page_id': target['page_id'],
                                  'relation': request['relation'], 'rationale': request['reason']})
            versions = set()
            for operation in pages:
                for block in operation['blocks']:
                    for span_id in block['span_ids']:
                        span = row(conn, t.spans, span_id)
                        if not span:
                            raise KnowledgeError('invalid_evidence', '引用片段不存在或不可访问')
                        versions.add(span['source_version_id'])
            try:
                proposal = Proposal.model_validate({'space_epoch': space['access_epoch'],
                    'source_version_ids': sorted(versions), 'pages': pages, 'links': links,
                    'link_targets': targets, 'extraction_mode': 'reviewed-proposal-v1'}).model_dump()
            except ValidationError as exc:
                raise KnowledgeError('proposal_budget', '修改集超过段落、别名或来源预算，请缩小范围') from exc
            service.validate(conn, space, proposal)
            cid = ident('kc')
            conn.execute(t.changes.insert().values(id=cid, space_id=sid, status='awaiting_review',
                payload=proposal, payload_hash=digest(proposal), review_actor='', review_reason='', created_at=now()))
            service.audit(conn, actor, sid, 'maintenance.proposed', cid,
                          {'action': action, 'reason': request['reason'], 'hash': digest(proposal)})
            return {'id': cid, 'status': 'awaiting_review', 'payload_hash': digest(proposal)}
        return service.idempotent(conn, actor, sid, 'maintenance.propose', key, request, apply)


def report(service, actor, sid, *, _conn=None):
    from contextlib import nullcontext
    with (nullcontext(_conn) if _conn is not None else service.engine.begin()) as conn:
        space = service.space(conn, actor, sid, lock=True)
        pages = list(conn.execute(sa.select(t.pages).where(t.pages.c.space_id == sid)
            .order_by(t.pages.c.id).limit(1001)).mappings())
        if len(pages) > 1000:
            raise KnowledgeError('corpus_budget_exceeded', '维护检查最多处理 1000 页')
        issues, active_revs, visible = [], {}, {}
        for page in pages:
            if page['status'] != 'active':
                continue
            try:
                revision = service._read_revision(conn, page)
                active_revs[revision['revision_id']] = page['id']
                visible[page['id']] = page
            except KnowledgeError as exc:
                issues.append({'kind': exc.code, 'page_id': page['id'], 'message': '依据已撤回，需复核'})
        for rid, pid in active_revs.items():
            for link in conn.execute(sa.select(t.links).where(t.links.c.from_revision_id == rid)).mappings():
                target = row(conn, t.revisions, link['to_revision_id'])
                target_page = row(conn, t.pages, target['page_id']) if target else None
                if not target_page or target_page['id'] not in visible:
                    issues.append({'kind': 'unavailable_link', 'page_id': pid, 'message': '关联目标已合并或依据不可用，需复核'})
                else:
                    if target['revision_no'] != target_page['revision']:
                        issues.append({'kind': 'stale_link', 'page_id': pid, 'message': '关联引用旧修订，需核对新内容'})
                if target_page and target_page['id'] in visible and link['relation'] == 'CONTRADICTS':
                    issues.append({'kind': 'contradiction', 'page_id': pid, 'target_page_id': target_page['id'],
                                   'message': link['rationale']})
        pending = conn.execute(sa.select(sa.func.count()).select_from(t.changes).where(
            t.changes.c.space_id == sid, t.changes.c.status.in_(['awaiting_review', 'approved']))).scalar_one()
        return {'sequence': space['sequence'], 'access_epoch': space['access_epoch'],
                'pages_checked': len(pages), 'pending_changes': pending, 'issues': issues,
                'automatic_semantic_check': False}
