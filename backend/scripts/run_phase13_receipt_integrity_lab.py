"""Isolated PG recovery approval drill for deterministic rejection of invalid recovery receipts.

Fixture identity, initial state, recovery responses and V2 planning; real OpenClaw readonly acceptance and evaluation. No external sender.
"""
import json
import hashlib
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
URL = 'postgresql+psycopg2:///agent_system_cu_phase13_20261006'
LAB = ROOT/'docs/review/computer-use-phase13-20261006'
LAB.mkdir(exist_ok=True)
os.environ['COMMAND_CENTER_DATABASE_URL'] = URL
os.environ['WORK_RUN_DATABASE_URL'] = URL
os.environ['COMMAND_CENTER_STEP_TIMEOUT'] = '300'
os.environ['COMMAND_CENTER_POLL_SECONDS'] = '1'
os.environ['COMMAND_CENTER_MAX_PARALLEL'] = '1'
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH = str(LAB/'auxiliary.sqlite3')
from services.command_center_service import CommandCenterService, CommandCenterError, InvalidMissionTransition
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.work_run_service import WorkRunService
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
service = CommandCenterService(repository=PostgresCommandCenterRepository(URL), project_provider=lambda: [], workflow_runtime_selector=lambda _: {'runtime':'legacy','reason':'isolated_real_recovery','flow_key':'general'})

def save(name, value):
    (LAB/name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

app=FastAPI()
user={'id':1,'username':'phase13-lab','display_name':'隔离恢复测试','role':'admin','is_active':True,'module_keys':[],'modules':[]}
memory={'pending_review':0,'approved':0,'rejected':0,'total':0}
@app.exception_handler(CommandCenterError)
async def error(request,exc): return JSONResponse({'detail':str(exc)},status_code=409)
@app.get('/api/v2/auth/settings')
def settings(): return {'login_enabled':False,'mode':'development'}
@app.post('/api/v2/auth/development-session')
def identity(): return {'access_token':'isolated-lab-only','token_type':'bearer','expires_in':3600,'user':user}
@app.get('/api/v2/auth/me')
def me(): return user
@app.get('/api/v3/projects')
def projects(): return {'projects':[],'total':0}
@app.get('/api/v3/command-center/summary')
def summary(): return {**service.summary(),'memory_candidates':memory}
@app.get('/api/v3/command-center/production-health')
def health(): return {'status':'degraded','storage':service.storage_info(),'storage_runtime':service.storage_runtime_metrics(),'work_runs':WorkRunService(database_url=URL).operational_metrics(),'workflow_runtime':service.workflow_runtime_status(),'workers':service.worker_runtime_status()}
@app.get('/api/v3/command-center/memory-candidates')
def candidates(): return {'candidates':[],'summary':memory,'can_review':False}
@app.get('/api/v3/command-center/messages')
def messages(): return {'messages':[],'total':0}
@app.get('/api/v3/command-center/task-workbench')
def workbench(): return service.list_task_workbench(limit=150)
@app.get('/api/v3/command-center/space')
def space(mission_id:str=''): return service.agent_space(mission_id=mission_id)
@app.get('/api/v3/command-center/missions')
def missions():
    rows=service.list_missions(limit=100);return {'missions':rows,'total':len(rows)}
@app.get('/api/v3/command-center/missions/{mid}')
def detail(mid:str): return service.get_mission(mid)
@app.get('/api/v3/command-center/missions/{mid}/artifacts/{aid}/download')
def download(mid:str,aid:str):
    if mid not in fixtures(): raise HTTPException(403)
    artifact=next((a for a in service.get_delivery_evidence(mid)['artifacts'] if a['id']==aid),None)
    if not artifact: raise HTTPException(404)
    path=Path(artifact['uri']).resolve()
    if path.parent!=LAB.resolve() or path.name not in [Path(v['valid']).name for v in fixtures().values()]: raise HTTPException(403)
    return FileResponse(path,filename=path.name,media_type='text/plain')

@app.get('/{path:path}')
def static(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Outside isolated read-only UI scope')
    dist=ROOT/'frontend-v2/dist';target=(dist/path).resolve()
    if target.is_relative_to(dist) and target.is_file(): return FileResponse(target)
    return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div style="background:#663c00;color:white;padding:8px;text-align:center">第十三阶段隔离测试 · 独立 PostgreSQL · 恢复审批闭环 · 回执完整性验证 · 无外发</div>'))


def setup():
    if (LAB/'fixtures.json').exists(): return
    assert not service.list_missions(limit=1), 'Use an empty phase13 database'
    fixtures={}
    for name, applied in [('missing',True),('corrupt',True),('mismatch',True)]:
        resource=LAB/(name+'-sample.txt')
        if applied:
            (LAB/'backup.txt').write_text('before-change\n')
            (LAB/'guard.txt').write_text('must-stay-unchanged\n')
            resource.write_text('changed-by-test\n')
        else: assert not resource.exists()
        m=service.create_mission(title='P13 '+{'missing':'回执缺失','corrupt':'回执损坏','mismatch':'幂等键不匹配'}[name],objective='隔离恢复测试：仅核实指定样本，保留所有文件，不外发。',requested_by='phase13-lab',context={'business_flow_key':'general'})
        service.claim_planning_mission('fixture')
        service.save_plan(m['id'],{'summary':'模拟回执丢失','steps':[{'title':'受控写入样本','agent_id':'ratchet','task_type':'coordination','side_effect':True,'risk_class':'L1','approval_required':False,'resources':[str(resource)],'depends_on':[]}]})
        service.approve(m['id'],decided_by='fixture');service.activate_approved_missions()
        step=service.claim_ready_steps('fixture',limit=1)[0]
        service.complete_step(step['id'],result={'success':False,'error':'测试夹具：未收到执行回执'},success=False,actor='fixture',lease_token=step['lease_token'])
        service.claim_evaluation_mission('fixture')
        case=service.get_mission(m['id'])['compensations'][0]
        service.decide_compensation(case['id'],expected_mission_id=m['id'],contract_hash=case['contract_hash'],decision='approved',decided_by='fixture')
        claim=service.claim_ready_compensation('fixture')
        save(name+'-initial-verification.json',{'resource':str(resource),'observed_content':resource.read_text()})
        service.complete_compensation(case['id'],lease_token=claim['lease_token'],result={'status':'failed','summary':'夹具核实：资源已改变，必须单独审批恢复','receipt_ref':str(LAB/(name+'-initial-verification.json')),'evidence_refs':[str(LAB/(name+'-initial-verification.json'))]},actor='fixture')
        proposal=service.propose_compensation_recovery(case['id'],expected_mission_id=m['id'],contract_hash=case['contract_hash'],instructions='本次只读核实当前资源与回执，不再写入样本。缺失、损坏或合同不匹配时保持暂停；重新批准后仅允许引用预备的、经核实匹配合同的独立有效回执。不得覆盖旧证据，不外发。',actor='fixture')['compensation']
        resource.write_text('before-change\n')
        (LAB/'before-recovery.txt').write_text('changed-by-test\n')
        valid=LAB/(name+'-receipt-valid.json')
        body={'contract_hash':proposal['contract_hash'],'idempotency_key':proposal['idempotency_key'],'resource':str(resource),'post_recovery_sha256':hashlib.sha256(resource.read_bytes()).hexdigest(),'verification':{'all_passed':True}}
        valid.write_text(json.dumps(body,ensure_ascii=False,indent=2))
        invalid=LAB/(name+'-receipt-invalid.json')
        if name=='corrupt': invalid.write_text('{broken JSON')
        if name=='mismatch': invalid.write_text(json.dumps({**body,'idempotency_key':'different-contract-key'}))
        fixtures[m['id']]={'name':name,'resource':str(resource),'valid':str(valid),'invalid':str(invalid),'compensation_id':case['id']}

    save('fixtures.json',fixtures)


def fixtures(): return json.loads((LAB/'fixtures.json').read_text())

@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/approve')
async def approve_verification(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    return service.decide_compensation(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],decision='approved',decided_by='phase13-browser',comment=body.get('comment',''))

@app.post('/api/v3/command-center/missions/{mid}/feedback')
async def feedback(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.add_feedback(mid,actor='phase13-browser',content=body['content'],replan=body.get('replan',False))
    if result['status']=='planning':
        service.claim_planning_mission('phase13-plan-fixture')
        service.save_plan(mid,{'summary':'恢复后的独立只读验收：核实原内容已恢复，与备份一致，不再写入。','steps':[{'title':'复核恢复内容与备份一致','description':f'仅使用 exec 执行只读断言：{fixtures()[mid]["resource"]} 与 {LAB}/backup.txt 内容为 before-change 换行，before-recovery.txt 为 changed-by-test 换行，guard.txt 为 must-stay-unchanged 换行。读取 {fixtures()[mid]["valid"]} 作为现成交付物，计算其 SHA256 并附上真实执行证据。禁止修改任何文件或外发。','agent_id':'ratchet','task_type':'coordination','side_effect':False,'depends_on':[],'required_tools':['test_runner'],'deliverables':[fixtures()[mid]['valid']],'evidence_required':['test_output'],'acceptance_criteria':['目标内容与 backup.txt 一致，原写入未被重试'],'output_contract':{'artifact_types':['document'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
    save(fixtures()[mid]['name']+'-feedback.json',service.get_mission(mid))
    assert service.claim_ready_steps('unapproved-probe')==[]
    return service.get_mission(mid)

@app.post('/api/v3/command-center/missions/{mid}/approve')
async def approve_plan(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    return service.approve(mid,decided_by='phase13-browser',comment=body.get('comment',''))

from services.command_center_worker import CommandCenterWorker
from services.openclaw_task_executor import OpenClawTaskExecutor, ExecutionResult
class RecordedExecutor:
    def __init__(self): self.real=OpenClawTaskExecutor(); self.count=max([int(p.name.split('-')[1]) for p in LAB.glob('call-*-invocation.json')],default=0)
    async def execute(self,command,command_args=None,timeout_seconds=300):
        self.count+=1; number=self.count
        save(f'call-{number}-invocation.json',command_args)
        message=command_args.get('message','')
        if '<COMPENSATION_CONTRACT>' in message:
            contract=json.loads(message.split('<COMPENSATION_CONTRACT>\n',1)[1].split('\n</COMPENSATION_CONTRACT>',1)[0])
            mid,fixture=next((mid,v) for mid,v in fixtures().items() if v['compensation_id']==contract['compensation_id'])
            case=service.get_mission(mid)['compensations'][0]
            receipt=Path(fixture['invalid'] if case['attempts']==2 else fixture['valid'])
            result=ExecutionResult(success=True,output=json.dumps({'status':'reverted','summary':'测试夹具：执行器声称成功，必须由回执门禁核验；本次没有写入。','receipt_ref':str(receipt),'receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest() if receipt.exists() else '0'*64,'evidence_refs':[str(receipt)]},ensure_ascii=False))
        else:
            result=await self.real.execute(command,command_args,timeout_seconds=timeout_seconds)
        save(f'call-{number}-result.json',result.to_dict())
        return result
class BlockSender:
    async def send(self,item):
        with (LAB/'blocked-notifications.jsonl').open('a') as f: f.write(json.dumps({'id':item['id'],'blocked':True})+'\n')
        return {'success':False,'error':'Isolated test; external delivery disabled'}
worker=CommandCenterWorker(service=service,executor=RecordedExecutor(),work_runs=WorkRunService(database_url=URL),sender=BlockSender(),context_service=None,memory_service=None)
worker.worker_id='phase13-real-recovery-worker'
@app.on_event('startup')
async def start_worker(): worker.start()
@app.on_event('shutdown')
async def stop_worker(): await worker.stop()
if __name__=='__main__':
    setup()
    uvicorn.run(app,host='127.0.0.1',port=3043)
