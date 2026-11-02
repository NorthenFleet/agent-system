"""Evaluate a versioned corpus in a disposable PostgreSQL schema, never production.

Test approvals are fixture-only. This measures retrieval and resolvability, not
human semantic fidelity; it must never enable a rollout flag.
"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from services.knowledge.service import KnowledgeService, digest
from services.knowledge.context import KnowledgeContextService
import tempfile


def evaluate(service, corpus):
    sid = service.create_space('eval-owner','工程评测','eval-project','space')['id']
    versions, concepts = {}, {}
    def release(cid, hash_value):
        service.review('eval-owner',cid,hash_value,'approve','isolated_test_fixture_only','approve-'+cid)
        service.publish('eval-owner',cid,hash_value,'publish-'+cid)
    for source in corpus['sources']:
        uploaded = service.upload('eval-owner',sid,source['title']+'.txt',source['text'].encode(),'upload-'+source['id'])
        versions[source['id']] = uploaded['version_id']
        service.enqueue('eval-owner',sid,uploaded['version_id'],{'concept_title':source['title']},'ingest-'+source['id'])
        compiled = service.compile_job(service.claim_job())
        change = service.change('eval-owner',compiled['id'])
        concepts[source['id']] = change['payload']['pages'][1]['page_id']
        release(compiled['id'],compiled['payload_hash'])
    for i, relation in enumerate(corpus['relations']):
        a,b=concepts[relation['from']],concepts[relation['to']]
        current_a,current_b=service.get_page('eval-owner',a),service.get_page('eval-owner',b)
        candidate=service.maintenance_candidate('eval-owner',sid,{'action':'relate','page_id':a,'base_revision':current_a['revision'],
            'target_page_id':b,'target_revision':current_b['revision'],'relation':relation['relation'],'reason':relation['reason']},f'relation-{i}')
        release(candidate['id'],candidate['payload_hash'])
    reverse={value:key for key,value in versions.items()}
    adapter=KnowledgeContextService(service)
    results,latencies=[],[]
    citation_count=resolved=0
    for query in corpus['queries']:
        for source in query.get('withdraw_before',[]):
            service.retract_source('eval-owner',versions[source],'withdraw-'+source)
        started=time.perf_counter()
        answer=service.query('eval-owner',sid,query['query'],10)
        elapsed=(time.perf_counter()-started)*1000
        latencies.append(elapsed)
        returned={reverse[ref['source_version_id']] for citation in answer['citations'] for ref in citation['citations']}
        expected=set(query['expected_sources'])
        for citation in answer['citations']:
            citation_count+=1
            entry=adapter.resolve('eval-owner',sid,'eval-project',citation['page_id'],citation['revision'],citation['block_id'])
            resolved+=entry['content']==citation['excerpt'] and entry['content_hash']==citation['content_hash']
        recall=len(expected & returned)/len(expected) if expected else None
        abstained=not answer['citations']
        passed=(recall==1 if expected else (abstained or query.get('allow_other_results',False)))
        passed=passed and not (set(query.get('forbidden_sources',[])) & returned)
        passed=passed and (not query.get('expect_conflict') or bool(answer['conflicts']))
        results.append({'id':query['id'],'kind':query['kind'],'expected_sources':sorted(expected),
            'returned_sources':sorted(returned),'recall_at_10':recall,'abstained':abstained,
            'conflicts':len(answer['conflicts']),'passed':bool(passed),'latency_ms':round(elapsed,2)})
    answerable=[r for r in results if r['kind']=='answerable']
    absent=[r for r in results if r['kind']=='unanswerable']
    return {'corpus_version':corpus['version'],'corpus_hash':digest(corpus),'source_count':len(corpus['sources']),
        'query_count':len(results),'human_reviewed':corpus.get('human_reviewed',False),
        'approval_kind':'isolated_test_fixture_only','production_modified':False,
        'retrieval_policy':'kb-retrieval-v2','metrics':{
            'recall_at_10':sum(r['recall_at_10'] for r in answerable)/len(answerable),
            'unanswerable_abstention_rate':sum(r['abstained'] for r in absent)/len(absent),
            'citation_resolvability':resolved/max(1,citation_count),'citation_count':citation_count,
            'query_p95_ms':round(sorted(latencies)[math.ceil(len(latencies)*.95)-1],2),
            'cases_passed':sum(r['passed'] for r in results),'semantic_fidelity':'not_human_evaluated'},
        'scope_note':'60-page synthetic corpus; not a 1000-page performance or real-source semantic gate',
        'g_sb3_passed':False,'vector_decision':'keep_disabled_pending_real_quality_evidence','results':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,default=Path(__file__).resolve().parents[1]/'evals/knowledge/sb3-engineering-v1.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    url=os.getenv('KNOWLEDGE_TEST_DATABASE_URL','')
    parsed=sa.engine.make_url(url)
    if parsed.get_backend_name()!='postgresql' or 'test' not in (parsed.database or ''):
        raise RuntimeError('Explicit disposable PostgreSQL test database required')
    admin=sa.create_engine(url); schema='sb3_eval_'+uuid.uuid4().hex
    with admin.begin() as conn: conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine=sa.create_engine(parsed.update_query_dict({'options':f'-csearch_path={schema}'}))
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                for name in ['20261006_knowledge_domain','20261006_knowledge_projection','20261006_knowledge_context','20261006_knowledge_operations']:
                    file=Path(__file__).resolve().parents[1]/'alembic/versions'/f'{name}.py'
                    spec=importlib.util.spec_from_file_location(name,file); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.upgrade()
        with tempfile.TemporaryDirectory(prefix='sb3-eval-') as temporary:
            service=KnowledgeService(engine,Path(temporary)/'sources',project_check=lambda actor,pid:actor=='eval-owner' and pid=='eval-project')
            result=evaluate(service,json.loads(args.corpus.read_text()))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False,indent=2))
    finally:
        engine.dispose()
        with admin.begin() as conn: conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__=='__main__': main()
