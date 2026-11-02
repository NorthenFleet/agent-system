"""Isolated PG recovery approval drill using the real OpenClaw worker.

Fixture identity and initial failure/planning; real recovery, execution and evaluation; no production startup or external sender.
"""
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
URL = 'postgresql+psycopg2:///agent_system_cu_phase11_20261006'
LAB = ROOT/'docs/review/computer-use-phase11-20261006'
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
user={'id':1,'username':'phase11-lab','display_name':'隔离恢复测试','role':'admin','is_active':True,'module_keys':[],'modules':[]}
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
    if path.parent!=LAB.resolve() or path.name!='recovery-receipt.json': raise HTTPException(403)
    return FileResponse(path,filename=path.name,media_type='text/plain')

@app.get('/{path:path}')
def static(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Outside isolated read-only UI scope')
    dist=LAB/'ui-dist';target=(dist/path).resolve()
    if target.is_relative_to(dist) and target.is_file(): return FileResponse(target)
    return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div style="background:#663c00;color:white;padding:8px;text-align:center">第十一阶段隔离测试 · 独立 PostgreSQL · 恢复审批闭环 · 真实 OpenClaw 执行 · 无外发</div>'))


def setup():
    if (LAB/'fixtures.json').exists(): return
    assert not service.list_missions(limit=1), 'Use an empty phase11 database'
    fixtures={}
    for name, applied in [('applied',True)]:
        resource=LAB/(name+'-sample.txt')
        if applied:
            (LAB/'backup.txt').write_text('before-change\n')
            (LAB/'guard.txt').write_text('must-stay-unchanged\n')
            resource.write_text('changed-by-test\n')
        else: assert not resource.exists()
        m=service.create_mission(title='P11 '+('未写入：核实与重新审批' if not applied else '已写入：新恢复方案审批闭环'),objective='隔离恢复测试：仅核实指定样本，保留所有文件，不外发。',requested_by='phase11-lab',context={'business_flow_key':'general'})
        service.claim_planning_mission('fixture')
        service.save_plan(m['id'],{'summary':'模拟回执丢失','steps':[{'title':'受控写入样本','agent_id':'ratchet','task_type':'coordination','side_effect':True,'risk_class':'L1','approval_required':False,'resources':[str(resource)],'depends_on':[]}]})
        service.approve(m['id'],decided_by='fixture');service.activate_approved_missions()
        step=service.claim_ready_steps('fixture',limit=1)[0]
        service.complete_step(step['id'],result={'success':False,'error':'测试夹具：未收到执行回执'},success=False,actor='fixture',lease_token=step['lease_token'])
        service.claim_evaluation_mission('fixture')
        fixtures[m['id']]={'name':name,'resource':str(resource)}
    save('fixtures.json',fixtures)


def fixtures(): return json.loads((LAB/'fixtures.json').read_text())

@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/approve')
async def approve_verification(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    return service.decide_compensation(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],decision='approved',decided_by='phase11-browser',comment=body.get('comment',''))

@app.post('/api/v3/command-center/missions/{mid}/feedback')
async def feedback(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.add_feedback(mid,actor='phase11-browser',content=body['content'],replan=body.get('replan',False))
    if result['status']=='planning':
        service.claim_planning_mission('phase11-plan-fixture')
        service.save_plan(mid,{'summary':'恢复后的独立只读验收：核实原内容已恢复，与备份一致，不再写入。','steps':[{'title':'复核恢复内容与备份一致','description':f'仅使用 exec 执行只读断言：{LAB}/applied-sample.txt 与 backup.txt 内容为 before-change 换行，before-recovery.txt 为 changed-by-test 换行，guard.txt 为 must-stay-unchanged 换行。读取 recovery-receipt.json 作为现成交付物，计算其 SHA256 并附上真实执行证据。禁止修改任何文件或外发。','agent_id':'ratchet','task_type':'coordination','side_effect':False,'depends_on':[],'required_tools':['test_runner'],'deliverables':['现有 recovery-receipt.json 恢复回执'],'evidence_required':['test_output'],'acceptance_criteria':['目标内容与 backup.txt 一致，原写入未被重试'],'output_contract':{'artifact_types':['document'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
    save(fixtures()[mid]['name']+'-feedback.json',service.get_mission(mid))
    assert service.claim_ready_steps('unapproved-probe')==[]
    return service.get_mission(mid)

@app.post('/api/v3/command-center/missions/{mid}/approve')
async def approve_plan(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    return service.approve(mid,decided_by='phase11-browser',comment=body.get('comment',''))

@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/recovery-plan')
async def propose_recovery(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.propose_compensation_recovery(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],instructions=body['instructions'],actor='phase11-browser')
    assert service.claim_ready_compensation('unapproved-probe') is None
    assert (LAB/'applied-sample.txt').read_text()=='changed-by-test\n'
    save('recovery-proposed.json',result)
    return result

from services.command_center_worker import CommandCenterWorker
from services.openclaw_task_executor import OpenClawTaskExecutor
class RecordedExecutor:
    def __init__(self): self.real=OpenClawTaskExecutor(); self.count=max([int(p.name.split('-')[1]) for p in LAB.glob('call-*-invocation.json')],default=0)
    async def execute(self,command,command_args=None,timeout_seconds=300):
        self.count+=1; number=self.count
        save(f'call-{number}-invocation.json',command_args)
        result=await self.real.execute(command,command_args,timeout_seconds=timeout_seconds)
        save(f'call-{number}-result.json',result.to_dict())
        return result
class BlockSender:
    async def send(self,item):
        with (LAB/'blocked-notifications.jsonl').open('a') as f: f.write(json.dumps({'id':item['id'],'blocked':True})+'\n')
        return {'success':False,'error':'Isolated test; external delivery disabled'}
worker=CommandCenterWorker(service=service,executor=RecordedExecutor(),work_runs=WorkRunService(database_url=URL),sender=BlockSender(),context_service=None,memory_service=None)
worker.worker_id='phase11-real-recovery-worker'
@app.on_event('startup')
async def start_worker(): worker.start()
@app.on_event('shutdown')
async def stop_worker(): await worker.stop()
if __name__=='__main__':
    setup()
    uvicorn.run(app,host='127.0.0.1',port=3041)
