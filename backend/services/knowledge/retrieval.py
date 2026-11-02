"""Scoped lexical retrieval and one-hop reviewed relation expansion."""
import re
import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from services.knowledge.service import KnowledgeError, digest, normalized, row

POLICY = 'kb-retrieval-v2'


def retrieve(conn, service, actor, sid, question, limit=10):
    service.space(conn, actor, sid, lock=True)
    if not 1 <= limit <= 20:
        raise KnowledgeError('invalid_limit', '检索条数必须为 1–20')
    terms = [x for x in re.findall(r'[a-z0-9_-]+|[\u3400-\u9fff]+', normalized(question)) if len(x) >= 2]
    grams = set(terms)
    for term in terms:
        if re.fullmatch(r'[\u3400-\u9fff]+', term):
            grams.update(term[i:i+2] for i in range(len(term)-1))
    rows = list(conn.execute(sa.select(t.pages).where(t.pages.c.space_id == sid,
        t.pages.c.status == 'active').order_by(t.pages.c.id).limit(1001)).mappings())
    if len(rows) > 1000:
        raise KnowledgeError('corpus_budget_exceeded', '空间超过 1000 页检索预算')
    pages, candidates = {}, []
    for page in rows:
        try:
            fixed = service._read_revision(conn, page)
        except KnowledgeError as exc:
            if exc.code == 'source_retracted':
                continue
            raise
        pages[page['id']] = fixed
        for block in fixed['body_json']['blocks']:
            content = normalized(fixed['title'] + ' ' + ' '.join(fixed['body_json'].get('aliases', [])) + ' ' + block['text'])
            matches = {g for g in grams if g in content}
            if matches and len(matches) / max(1, len(grams)) >= .3:
                candidates.append(item(fixed, block, len(matches)))
    candidates.sort(key=lambda x: (-x['score'], 1 if pages[x['page_id']]['type'] == 'source' else 0, x['source_ref'], x['block_id']))
    unique, equivalent_pages = {}, {}
    for candidate in candidates:
        # Do not collapse differently sourced or differently qualified statements.
        key = digest((candidate['excerpt'], candidate['epistemic_status'], sorted(c['span_id'] for c in candidate['citations'])))
        unique.setdefault(key, candidate)
        equivalent_pages.setdefault(key, set()).add(candidate['page_id'])
    selected_keys = list(unique)[:limit]
    chosen = [unique[key] for key in selected_keys]
    # Text dedup must not discard relations attached to an equivalent concept
    # page when its source page supplied the displayed excerpt (or vice versa).
    seeds = set().union(*(equivalent_pages[key] for key in selected_keys)) if selected_keys else set()
    conflicts, paths = [], []
    revision_ids = {p['revision_id']: pid for pid, p in pages.items()}
    # A link is eligible only when its source revision is current and both ends
    # are readable in this exact space. Metadata cannot grant graph access.
    if seeds and revision_ids:
        links = conn.execute(sa.select(t.links).where(t.links.c.from_revision_id.in_(revision_ids))).mappings()
        for link in links:
            source = revision_ids[link['from_revision_id']]
            target_revision = row(conn, t.revisions, link['to_revision_id'])
            target = target_revision['page_id'] if target_revision else ''
            if target not in pages or (source not in seeds and target not in seeds):
                continue
            path = {'from_page_id': source, 'to_page_id': target, 'relation': link['relation'],
                    'from_revision': pages[source]['revision'], 'target_evidence_revision': target_revision['revision_no'],
                    'target_current_revision': pages[target]['revision'], 'rationale': link['rationale'],
                    'stale': target_revision['revision_no'] != pages[target]['revision']}
            if link['relation'] == 'CONTRADICTS':
                conflicts.append({**path, 'source_ref': pages[source]['source_ref'], 'target_ref': pages[target]['source_ref'],
                    'source_title': pages[source]['title'], 'target_title': pages[target]['title']})
            if not path['stale'] and link['relation'] in {'CONTRADICTS', 'SUPPORTS', 'RELATED_TO', 'DERIVED_FROM'}:
                other = target if source in seeds else source
                if other not in seeds:
                    paths.append((0 if link['relation'] == 'CONTRADICTS' else 1, other, path))
    expanded = set(seeds)
    for _, pid, path in sorted(paths, key=lambda x: (x[0], x[1]))[:5]:
        if len(chosen) >= limit or pid in expanded:
            continue
        fixed = pages[pid]
        chosen.append(item(fixed, fixed['body_json']['blocks'][0], 0, [path]))
        expanded.add(pid)
    labels = {'reported': '知识页陈述', 'inference': '推论', 'uncertain': '待核实'}
    answer = '\n\n'.join(f"知识页摘录（{labels[x['epistemic_status']]}）：{x['excerpt']} [{i+1}]" for i, x in enumerate(chosen))
    if conflicts:
        answer = '存在已标记的矛盾，请核对双方固定来源；此处不自动裁决。\n\n' + answer
    return {'answer_mode': 'extractive', 'answer': answer or '知识库没有找到足够依据。', 'citations': chosen,
            'gaps': [] if chosen else [question], 'conflicts': conflicts[:20],
            'read_refs': list(dict.fromkeys(x['source_ref'] for x in chosen)),
            'retrieval_health': {'strategy': POLICY, 'max_pages': 1000, 'relation_hops': 1,
                'relation_expanded': len(expanded - seeds), 'vector_enabled': False,
                'conflicts_truncated': len(conflicts) > 20}}


def item(page, block, score, path=None):
    return {'source_ref': page['source_ref'], 'page_id': page['id'], 'page_revision_id': page['revision_id'],
        'revision': page['revision'], 'content_hash': page['content_hash'], 'title': page['title'],
        'block_id': block['block_id'], 'excerpt': block['text'], 'epistemic_status': block['epistemic_status'],
        'citations': [c for c in page['citations'] if c['span_id'] in block['span_ids']],
        'score': score, 'authority': 'reviewed_knowledge', 'relation_path': path or []}
