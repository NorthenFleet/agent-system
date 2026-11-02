"""Isolated PG recovery approval drill using a controlled filesystem adapter.

Fixture identity, planning and evaluation; no production startup or external sender.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
URL = 'postgresql+psycopg2:///agent_system_cu_phase10_20261006'
LAB = ROOT/'docs/review/computer-use-phase10-20261006'
LAB.mkdir(exist_ok=True)
os.environ['COMMAND_CENTER_DATABASE_URL'] = URL
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH = str(LAB/'auxiliary.sqlite3')
from services.command_center_service import CommandCenterService, CommandCenterError, InvalidMissionTransition
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.work_run_service import WorkRunService
from services.execution_contract_ids import contract_items
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
service = CommandCenterService(repository=PostgresCommandCenterRepository(URL), project_provider=lambda: [])

def save(name, value):
    (LAB/name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

app=FastAPI()
user={'id':1,'username':'phase10-lab','display_name':'隔离恢复测试','role':'admin','is_active':True,'module_keys':[],'modules':[]}
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
def health(): return {'status':'degraded','storage':service.storage_info(),'storage_runtime':service.storage_runtime_metrics(),'work_runs':WorkRunService(repository=service.repository).operational_metrics(),'workflow_runtime':service.workflow_runtime_status(),'workers':service.worker_runtime_status()}
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
    if path.parent!=LAB.resolve() or not path.name.endswith('-verification.txt'): raise HTTPException(403)
    return FileResponse(path,filename=path.name,media_type='text/plain')

@app.get('/{path:path}')
def static(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Outside isolated read-only UI scope')
    dist=LAB/'ui-dist';target=(dist/path).resolve()
    if target.is_relative_to(dist) and target.is_file(): return FileResponse(target)
    return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div style="background:#663c00;color:white;padding:8px;text-align:center">第十阶段隔离测试 · 独立 PostgreSQL · 恢复审批闭环 · 受控文件适配器 · 无外发</div>'))


def setup():
    if (LAB/'fixtures.json').exists(): return
    assert not service.list_missions(limit=1), 'Use an empty phase10 database'
    fixtures={}
    for name, applied in [('applied',True)]:
        resource=LAB/(name+'-sample.txt')
        if applied:
            (LAB/'backup.txt').write_text('before-change\n')
            resource.write_text('changed-by-test\n')
        else: assert not resource.exists()
        m=service.create_mission(title='P10 '+('未写入：核实与重新审批' if not applied else '已写入：新恢复方案审批闭环'),objective='隔离恢复测试：仅核实指定样本，保留所有文件，不外发。',requested_by='phase10-lab',context={'business_flow_key':'general'})
        service.claim_planning_mission('fixture')
        service.save_plan(m['id'],{'summary':'模拟回执丢失','steps':[{'title':'受控写入样本','agent_id':'optimus','task_type':'coordination','side_effect':True,'risk_class':'L1','approval_required':False,'resources':[str(resource)],'depends_on':[]}]})
        service.approve(m['id'],decided_by='fixture');service.activate_approved_missions()
        step=service.claim_ready_steps('fixture',limit=1)[0]
        service.complete_step(step['id'],result={'success':False,'error':'测试夹具：未收到执行回执'},success=False,actor='fixture',lease_token=step['lease_token'])
        service.claim_evaluation_mission('fixture')
        fixtures[m['id']]={'name':name,'resource':str(resource)}
    save('fixtures.json',fixtures)


def fixtures(): return json.loads((LAB/'fixtures.json').read_text())

@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/approve')
def approve_verification(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.decide_compensation(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],decision='approved',decided_by='phase10-browser',comment=body.get('comment',''))
    item=service.claim_ready_compensation('phase10-filesystem-verifier')
    assert item['id']==cid
    resource=Path(fixtures()[mid]['resource'])
    receipt=LAB/(cid+'-'+str(item['attempts'])+'-receipt.json')
    if item['compensation_type']=='verify_effect':
        present=resource.exists()
        receipt.write_text(json.dumps({'resource':str(resource),'exists':present,'content':resource.read_text() if present else None},ensure_ascii=False,indent=2))
        status='failed' if present else 'not_needed'
        summary='只读核实：测试文件已被改写，需要新恢复方案，保留文件。'
    else:
        assert item['compensation_type']=='manual_recovery'
        assert resource==LAB/'applied-sample.txt'
        assert 'backup.txt' in item['instructions'] and 'changed-by-test' in item['instructions']
        assert resource.read_text()=='changed-by-test\n', 'Precondition mismatch; do not write'
        backup=LAB/'backup.txt'
        (LAB/'before-recovery.txt').write_bytes(resource.read_bytes())
        resource.write_bytes(backup.read_bytes())
        assert resource.read_bytes()==backup.read_bytes()
        receipt.write_text(json.dumps({'resource':str(resource),'restored_content':resource.read_text(),'idempotency_key':item['idempotency_key'],'backup':str(backup),'preserved_changed_copy':str(LAB/'before-recovery.txt')},ensure_ascii=False,indent=2))
        status='reverted';summary='已从 backup.txt 恢复原内容，逐字节核验一致；改写前状态另存保留。'
        assert service.claim_ready_compensation('duplicate-probe') is None
    service.complete_compensation(cid,lease_token=item['lease_token'],result={'status':status,'summary':summary,'receipt_ref':str(receipt),'evidence_refs':[str(receipt)],'risk_notes':'只验证本阶段隔离文件适配器，未调用外部系统。'},actor='phase10-filesystem-verifier')
    save(fixtures()[mid]['name']+'-verified.json',service.get_mission(mid))
    return result

@app.post('/api/v3/command-center/missions/{mid}/feedback')
def feedback(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.add_feedback(mid,actor='phase10-browser',content=body['content'],replan=body.get('replan',False))
    if result['status']=='planning':
        service.claim_planning_mission('phase10-plan-fixture')
        service.save_plan(mid,{'summary':'恢复后的独立只读验收：核实原内容已恢复，与备份一致，不再写入。','steps':[{'title':'复核恢复内容与备份一致','agent_id':'optimus','task_type':'coordination','side_effect':False,'depends_on':[],'required_tools':['test_runner'],'deliverables':['只读复核记录'],'evidence_required':['test_output'],'acceptance_criteria':['目标内容与 backup.txt 一致，原写入未被重试'],'output_contract':{'artifact_types':['test_report'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
    save(fixtures()[mid]['name']+'-feedback.json',service.get_mission(mid))
    assert service.claim_ready_steps('unapproved-probe')==[]
    return service.get_mission(mid)

@app.post('/api/v3/command-center/missions/{mid}/approve')
def approve_plan(mid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    service.approve(mid,decided_by='phase10-browser',comment=body.get('comment',''))
    service.activate_approved_missions()
    step=service.claim_ready_steps('phase10-controlled-executor',limit=1)[0]
    assert step['mission_id']==mid and step['side_effect'] is False
    resource=Path(fixtures()[mid]['resource'])
    probe=subprocess.run([sys.executable,'-c','from pathlib import Path; import sys; assert Path(sys.argv[1]).read_text()=="before-change\\n"; print("PASS: restored original content")',str(resource)],capture_output=True,text=True,check=True)
    artifact=LAB/(step['id']+'-verification.txt');artifact.write_text(probe.stdout)
    import hashlib
    ref=str(artifact)
    result={'success':True,'outcome':'succeeded','summary':probe.stdout,'tools_used':['exec'],'artifacts':[{'artifact_key':'a1','artifact_type':'test_report','title':'只读复核记录','uri':ref,'content_hash':hashlib.sha256(artifact.read_bytes()).hexdigest()}],'evidence':[{'requirement_id':i['id'],'evidence_type':'test_output','source_ref':ref,'summary':probe.stdout,'artifact_key':'a1'} for i in contract_items(step,'evidence_required')],'acceptance_results':[{'criterion_id':i['id'],'criterion':i['text'],'status':'pass','evidence_refs':[ref]} for i in contract_items(step,'acceptance_criteria')],'side_effects':[],'risk_notes':'受控本地文件适配器，仅验证隔离样本。'}
    completed=service.complete_step(step['id'],result=result,success=True,actor='phase10-controlled-executor',lease_token=step['lease_token'])
    save('execution-result.json',completed)
    if service.claim_evaluation_mission('phase10-controlled-evaluator'):
        service.complete_mission(mid,success=True,summary='已通过恢复后的只读核验，原写入未重复执行。',actor='phase10-controlled-evaluator')
    save('final-mission.json',service.get_mission(mid))
    return service.get_mission(mid)


@app.post('/api/v3/command-center/missions/{mid}/compensations/{cid}/recovery-plan')
def propose_recovery(mid:str,cid:str,body:dict):
    if mid not in fixtures(): raise HTTPException(403)
    result=service.propose_compensation_recovery(cid,expected_mission_id=mid,contract_hash=body['contract_hash'],instructions=body['instructions'],actor='phase10-browser')
    assert service.claim_ready_compensation('unapproved-probe') is None
    assert (LAB/'applied-sample.txt').read_text()=='changed-by-test\n'
    save('recovery-proposed.json',result)
    return result

if __name__=='__main__':
    setup()
    uvicorn.run(app,host='127.0.0.1',port=3040)
