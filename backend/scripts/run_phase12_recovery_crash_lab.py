"""Isolated PG recovery approval drill with full worker process death at the persistence boundary.

Fixture identity and initial failure/planning; controlled filesystem recovery with real process death; real OpenClaw readonly execution and evaluation; no production startup or external sender.
"""
import json
import asyncio
import hashlib
import subprocess
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
URL = 'postgresql+psycopg2:///agent_system_cu_phase12_20261006'
LAB = ROOT/'docs/review/computer-use-phase12-20261006'
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
user={'id':1,'username':'phase12-lab','display_name':'隔离恢复测试','role':'admin','is_active':True,'module_keys':[],'modules':[]}
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
    return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div style="background:#663c00;color:white;padding:8px;text-align:center">第十二阶段隔离测试 · 独立 PostgreSQL · 恢复审批闭环 · 恢复进程崩溃验证 · 无外发</div>'))


def setup():
    if (LAB/'fixtures.json').exists(): return
    assert not service.list_missions(limit=1), 'Use an empty phase12 database'
    fixtures={}
    for name, applied in [('applied',True)]:
        resource=LAB/(name+'-sample.txt')
        if applied:
            (LAB/'backup.txt').write_text('before-change\n')
            (LAB/'guard.txt').write_text('must-stay-unchanged\n')
            resource.write_text('changed-by-test\n')
        else: assert not resource.exists()
        m=service.create_mission(title='P12 '+('未写入：核实与重新审批' if not applied else '恢复写入后中断：核实与重新审批'),objective='隔离恢复测试：仅核实指定样本，保留所有文件，不外发。',requested_by='phase12-lab',context={'business_flow_key':'general'})
        service.claim_planning_mission('fixture')
        service.save_plan(m['id'],{'summary':'模拟回执丢失','steps':[{'title':'受控写入样本','agent_id':'ratchet','task_type':'coordination','side_effect':True,'risk_class':'L1','approval_required':False,'resources':[str(resource)],'depends_on':[]}]})
        service.approve(m['id'],decided_by='fixture');service.activate_approved_missions()
        step=service.claim_ready_steps('fixture',limit=1)[0]
        service.complete_step(step['id'],result={'success':False,'error':'测试夹具：未收到执行回执'},success=False,actor='fixture',lease_token=step['lease_token'])
        service.claim_evaluation_mission('fixture')
        fixtures[m['id']]={'name':name,'resource':str(resource)}
    save('fixtures.json',fixtures)
    mid=next(iter(fixtures))
    case=service.get_mission(mid)['compensations'][0]
    service.decide_compensation(case['id'],expected_mission_id=mid,contract_hash=case['contract_hash'],decision='approved',decided_by='fixture')
    claim=service.claim_ready_compensation('fixture-verification')
    save('initial-verification.json',{'resource':str(resource),'content':resource.read_text(),'sha256':hashlib.sha256(resource.read_bytes()).hexdigest()})
    service.complete_compensation(case['id'],lease_token=claim['lease_token'],result={'status':'failed','summary':'夹具只读核实：样本已改变，须审批恢复方案','receipt_ref':str(LAB/'initial-verification.json'),'evidence_refs':[str(LAB/'initial-verification.json')]},actor='fixture-verification')
    proposal=service.propose_compensation_recovery(case['id'],expected_mission_id=mid,contract_hash=case['contract_hash'],instructions='仅恢复本目录 applied-sample.txt：先确认 sample 为 changed-by-test 换行，backup 为 before-change 换行，guard 为 must-stay-unchanged 换行。保留 before-recovery.txt 后，从 backup 恢复样本，创建 recovery-receipt.json 并记录合同指纹、幂等键、前后哈希。若同键回执已存在且五份文件核实一致，只读复用回执，不再次写入。任一状态不符即停止；不删除、不外发。',actor='fixture-planner')
    save('initial-proposal.json',proposal)



def fixtures(): return json.loads((LAB/'fixtures.json').read_text())

@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/approve')
async def approve_verification(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    return service.decide_compensation(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],decision='approved',decided_by='phase12-browser',comment=body.get('comment',''))

@app.post('/api/v3/command-center/missions/{mid}/feedback')
async def feedback(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.add_feedback(mid,actor='phase12-browser',content=body['content'],replan=body.get('replan',False))
    if result['status']=='planning':
        service.claim_planning_mission('phase12-plan-fixture')
        service.save_plan(mid,{'summary':'恢复后的独立只读验收：核实原内容已恢复，与备份一致，不再写入。','steps':[{'title':'复核恢复内容与备份一致','description':f'仅使用 exec 执行只读断言：{LAB}/applied-sample.txt 与 backup.txt 内容为 before-change 换行，before-recovery.txt 为 changed-by-test 换行，guard.txt 为 must-stay-unchanged 换行。读取 recovery-receipt.json 作为现成交付物，计算其 SHA256 并附上真实执行证据。禁止修改任何文件或外发。','agent_id':'ratchet','task_type':'coordination','side_effect':False,'depends_on':[],'required_tools':['test_runner'],'deliverables':['现有 recovery-receipt.json 恢复回执'],'evidence_required':['test_output'],'acceptance_criteria':['目标内容与 backup.txt 一致，原写入未被重试'],'output_contract':{'artifact_types':['document'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
    save(fixtures()[mid]['name']+'-feedback.json',service.get_mission(mid))
    assert service.claim_ready_steps('unapproved-probe')==[]
    return service.get_mission(mid)

@app.post('/api/v3/command-center/missions/{mid}/approve')
async def approve_plan(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    return service.approve(mid,decided_by='phase12-browser',comment=body.get('comment',''))

@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/recovery-plan')
async def propose_recovery(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.propose_compensation_recovery(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],instructions=body['instructions'],actor='phase12-browser')
    assert service.claim_ready_compensation('unapproved-probe') is None
    assert (LAB/'applied-sample.txt').read_text()=='changed-by-test\n'
    save('recovery-proposed.json',result)
    return result

from services.command_center_worker import CommandCenterWorker
from services.openclaw_task_executor import OpenClawTaskExecutor, ExecutionResult
class RecordedExecutor:
    def __init__(self):
        self.real=OpenClawTaskExecutor()
        self.count=max([int(p.name.split('-')[1]) for p in LAB.glob('call-*-invocation.json')],default=0)
    async def execute(self,command,command_args=None,timeout_seconds=300):
        self.count+=1; number=self.count
        save(f'call-{number}-invocation.json',command_args)
        message=command_args.get('message','')
        if '<COMPENSATION_CONTRACT>' not in message:
            result=await self.real.execute(command,command_args,timeout_seconds=timeout_seconds)
        else:
            contract=json.loads(message.split('<COMPENSATION_CONTRACT>\n',1)[1].split('\n</COMPENSATION_CONTRACT>',1)[0])
            assert contract['type']=='manual_recovery'
            resource=Path(contract['resource']); assert resource==LAB/'applied-sample.txt'
            backup=LAB/'backup.txt'; guard=LAB/'guard.txt'; retained=LAB/'before-recovery.txt'; receipt=LAB/'recovery-receipt.json'
            assert backup.read_bytes()==b'before-change\n' and guard.read_bytes()==b'must-stay-unchanged\n'
            if receipt.exists():
                existing=json.loads(receipt.read_text())
                assert existing['idempotency_key']==contract['idempotency_key'] and existing['contract_hash']==contract['contract_hash']
                assert resource.read_bytes()==backup.read_bytes() and retained.read_bytes()==b'changed-by-test\n'
                save('receipt-reused.json',{'read_only':True,'pid':os.getpid(),'contract_hash':contract['contract_hash'],'idempotency_key':contract['idempotency_key']})
            else:
                assert resource.read_bytes()==b'changed-by-test\n' and not retained.exists()
                with retained.open('xb') as f: f.write(resource.read_bytes());f.flush();os.fsync(f.fileno())
                with resource.open('wb') as f: f.write(backup.read_bytes());f.flush();os.fsync(f.fileno())
                existing={'idempotency_key':contract['idempotency_key'],'contract_hash':contract['contract_hash'],'resource':str(resource),'pre_recovery_sha256':hashlib.sha256(retained.read_bytes()).hexdigest(),'post_recovery_sha256':hashlib.sha256(resource.read_bytes()).hexdigest(),'retention_copy_path':str(retained),'verification':{'all_passed':True}}
                with receipt.open('x') as f: json.dump(existing,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
                with (LAB/'physical-writes.jsonl').open('a') as f: f.write(json.dumps({'pid':os.getpid(),'idempotency_key':contract['idempotency_key'],'resource':str(resource)})+'\n');f.flush();os.fsync(f.fileno())
                with service.connect() as conn:
                    old=dict(conn.execute('SELECT * FROM mission_compensations WHERE id=?',(contract['compensation_id'],)).fetchone())
                save('crash-boundary.json',{'pid':os.getpid(),'compensation':old,'files':{p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mtime_ns':p.stat().st_mtime_ns} for p in [resource,backup,guard,retained,receipt]}})
                # Parent kills the full worker while its heartbeat is still live;
                # no successful compensation result has reached the service.
                await asyncio.Event().wait()
            result=ExecutionResult(success=True,output=json.dumps({'status':'reverted','summary':'只读核实恢复已落地，复用相同幂等键的真实文件回执；没有再次写入。','receipt_ref':str(receipt),'evidence_refs':[str(receipt),str(retained)],'risk_notes':'隔离固定文件适配器的崩溃恢复测试，不代表通用工具 exactly-once。'},ensure_ascii=False))
        save(f'call-{number}-result.json',result.to_dict())
        return result
class BlockSender:
    async def send(self,item):
        with (LAB/'blocked-notifications.jsonl').open('a') as f: f.write(json.dumps({'id':item['id'],'blocked':True})+'\n')
        return {'success':False,'error':'Isolated test; external delivery disabled'}
async def run_worker():
    worker=CommandCenterWorker(service=service,executor=RecordedExecutor(),work_runs=WorkRunService(database_url=URL),sender=BlockSender(),context_service=None,memory_service=None)
    worker.worker_id=f'phase12-worker-{os.getpid()}'
    worker.step_lease_seconds=60
    worker.step_heartbeat_seconds=5
    worker.start()
    save(f'worker-{os.getpid()}.json',{'pid':os.getpid(),'lease_seconds':60,'heartbeat_seconds':5})
    try: await asyncio.Event().wait()
    finally: await worker.stop()
@app.on_event('startup')
async def start_worker():
    # UI stays alive when the independent worker is killed.
    logfile=(LAB/'worker.log').open('a')
    app.state.worker=subprocess.Popen([sys.executable,__file__,'--worker'],stdout=logfile,stderr=logfile)
    logfile.close()
@app.on_event('shutdown')
async def stop_worker():
    child=getattr(app.state,'worker',None)
    if child and child.poll() is None: child.terminate()
if __name__=='__main__':
    if '--worker' in sys.argv: asyncio.run(run_worker())
    else:
        setup()
        uvicorn.run(app,host='127.0.0.1',port=3042)
