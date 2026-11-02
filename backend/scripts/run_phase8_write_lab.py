"""Isolated PG write crash drill and production frontend recovery view.

Controlled file writer, fixture identity/plan; no production startup or external sender.
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
URL = 'postgresql+psycopg2:///agent_system_cu_phase8_20261006'
LAB = ROOT/'docs/review/computer-use-phase8-20261006'
LAB.mkdir(exist_ok=True)
os.environ['COMMAND_CENTER_DATABASE_URL'] = URL
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH = str(LAB/'auxiliary.sqlite3')
from services.command_center_service import CommandCenterService, CommandCenterError, InvalidMissionTransition
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.work_run_service import WorkRunService
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
service = CommandCenterService(repository=PostgresCommandCenterRepository(URL), project_provider=lambda: [])

def save(name, value):
    (LAB/name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

def writer(directory):
    step = service.claim_ready_steps('phase8-crashing-writer', limit=1, lease_seconds=60)[0]
    with (directory/'effect.txt').open('a') as f:
        f.write('applied-once\n')
        f.flush()
        os.fsync(f.fileno())
    (directory/'claimed.json').write_text(json.dumps(step))
    while True: time.sleep(1)

def drill():
    assert not service.list_missions(limit=1), 'Use the dedicated empty phase8 database'
    directory = LAB/('run-'+uuid.uuid4().hex[:8]); directory.mkdir()
    resource = directory/'effect.txt'
    m=service.create_mission(title='P8 写入后中断：禁止重复执行',objective='隔离文件写入后丢失回执，等待核实，不自动重试。',requested_by='phase8-lab')
    service.claim_planning_mission('fixture')
    service.save_plan(m['id'],{'summary':'隔离受控文件写入', 'steps':[{'title':'写入测试样本', 'agent_id':'optimus','task_type':'coordination','side_effect':True,'risk_class':'L1','approval_required':False,'resources':[str(resource)],'depends_on':[]}]})
    service.approve(m['id'],decided_by='phase8-lab');service.activate_approved_missions()
    child=subprocess.Popen([sys.executable,__file__,'writer',str(directory)])
    try:
        deadline=time.monotonic()+20
        while not (directory/'claimed.json').exists():
            if child.poll() is not None: raise RuntimeError('Writer exited early')
            if time.monotonic()>deadline: raise TimeoutError('Writer did not start')
            time.sleep(.1)
        step=json.loads((directory/'claimed.json').read_text())
        child.kill();child.wait(timeout=5)
        start=time.monotonic()
        assert service.requeue_stale_steps()==0
        while not service.requeue_stale_steps():
            if time.monotonic()-start>65: raise TimeoutError('Lease did not expire')
            time.sleep(.25)
        assert service.claim_ready_steps('replacement')==[]
        assert service.requeue_stale_steps()==0
        assert service.claim_evaluation_mission('reviewer') is None
        try:
            service.complete_step(step['id'],result={'summary':'late'},success=True,actor='old',lease_token=step['lease_token'])
        except InvalidMissionTransition: pass
        else: raise AssertionError('Stale completion accepted')
        current=service.get_mission(m['id'])
        assert current['status']=='waiting_feedback'
        assert current['steps'][0]['attempt_count']==1
        assert current['effects'][0]['status']=='unknown'
        assert current['compensations'][0]['compensation_type']=='verify_effect'
        assert resource.read_text()=='applied-once\n'
        save('pg-result.json',{'mission':current,'natural_expiry_seconds':round(time.monotonic()-start,2),'write_count':1,'stale_completion_rejected':True,'automatic_replay':False,'resource':str(resource),'run_directory':str(directory)})
        save('ui-mission.json',{'mission_id':m['id'],'resource':str(resource)})
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=5)

app=FastAPI()
user={'id':1,'username':'phase8-lab','display_name':'隔离恢复测试','role':'admin','is_active':True,'module_keys':[],'modules':[]}
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
@app.get('/{path:path}')
def static(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Outside isolated read-only UI scope')
    dist=ROOT/'frontend-v2/dist';target=(dist/path).resolve()
    if target.is_relative_to(dist) and target.is_file(): return FileResponse(target)
    return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div style="background:#663c00;color:white;padding:8px;text-align:center">第八阶段隔离测试 · 独立 PostgreSQL · 受控写入故障 · 只读展示 · 无外发</div>'))
if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'serve'
    if mode=='writer': writer(Path(sys.argv[2]))
    elif mode=='drill': drill()
    else: uvicorn.run(app,host='127.0.0.1',port=3038)
