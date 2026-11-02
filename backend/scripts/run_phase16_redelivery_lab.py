"""Redelivery UI lab: frozen old task, isolated PG new mission, fixed plan, real execution and evaluation."""
import copy, hashlib, json, os, sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
LAB=ROOT/'docs/review/computer-use-phase16-20261007'
URL='postgresql+psycopg2:///agent_system_cu_phase16_20261007'
os.environ.update(COMMAND_CENTER_DATABASE_URL=URL,WORK_RUN_DATABASE_URL=URL,COMMAND_CENTER_EVIDENCE_ENFORCEMENT='strict',COMMAND_CENTER_STEP_TIMEOUT='300',COMMAND_CENTER_POLL_SECONDS='1')
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH=str(LAB/'auxiliary.sqlite3')
os.environ['COMMAND_CENTER_ARTIFACT_ROOTS']=str(LAB)
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from routers import command_center_router as router
import uvicorn
app=FastAPI()
mission=copy.deepcopy(json.loads((ROOT/'docs/review/computer-use-phase13-20261006/final-missions.json').read_text())['missing'])
mission.update(id='phase16-delivery',title='P16 历史交付异常样本',project_id='phase16-project',mission_type='document')
file=LAB/'delivery.txt'
if not file.exists():file.write_text('Phase 16 changed historical delivery\n')
original=b'Phase 16 original delivery\n'
mission['artifacts']=[dict(id='phase16-artifact',step_id='',artifact_type='document',title='阶段十六交付样本',uri=str(file),content_hash=hashlib.sha256(original).hexdigest(),created_at=mission['created_at'])]
(LAB/'mission-snapshot.json').write_text(json.dumps(mission,ensure_ascii=False,indent=2))
from services.command_center_service import CommandCenterService, CommandCenterError
from repositories.command_center_repository import PostgresCommandCenterRepository
PROJECT={'id':'phase16-project','name':'阶段十六隔离项目','project_type':'document','status':'active'}
service=CommandCenterService(repository=PostgresCommandCenterRepository(URL),project_provider=lambda:[PROJECT],workflow_runtime_selector=lambda _: {'runtime':'legacy','reason':'isolated_redelivery','flow_key':'general'})
def save(name,data):(LAB/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
def get_mission(mid,**kw):
 return mission if mid==mission['id'] else service.get_mission(mid,**kw)
router.command_center_service=SimpleNamespace(get_mission=get_mission)
@app.exception_handler(CommandCenterError)
async def command_error(request,exc):
 from fastapi.responses import JSONResponse
 return JSONResponse({'detail':str(exc)},status_code=409)
user={'sub':'phase16','username':'phase16','display_name':'隔离交付测试','role':'user','is_active':True,'module_keys':['dashboard','command-center'],'modules':[]}
@app.get('/api/v2/auth/settings')
def settings():return {'login_enabled':False,'mode':'development'}
@app.post('/api/v2/auth/development-session')
def identity():return {'access_token':'isolated-lab-only','token_type':'bearer','expires_in':3600,'user':user}
@app.get('/api/v2/auth/me')
def me():return user
@app.get('/api/v3/projects')
def projects():return {'projects':[{'id':'phase16-project','name':'阶段十六隔离项目','project_type':'document','status':'active'}],'total':1}
@app.get('/api/v3/command-center/summary')
def summary():return {**service.summary(),'memory_candidates':{'total':0,'pending_review':0,'published':0,'rejected':0,'by_status':{}}}
@app.get('/api/v3/command-center/memory-candidates')
def memory():return {'candidates':[],'summary':{'total':0},'can_review':False}
@app.get('/api/v3/command-center/messages')
def messages():return {'messages':[],'total':0}
def old_workbench():return {'items':[{'mission_id':mission['id'],'mission_title':mission['title'],'mission_status':'completed','mission_type':'document','project_id':'phase16-project','project_name':'阶段十六隔离项目','current_agent_id':'optimus','current_agent_name':'擎天柱','progress':100,'steps_summary':{'total':1,'completed':1},'linked_tasks':[],'updated_at':mission['updated_at']}],'total':1}
@app.get('/api/v3/command-center/task-workbench')
def workbench():
 data=service.list_task_workbench(limit=150);data['items']+=old_workbench()['items'];return data
@app.get('/api/v3/command-center/space')
def space(mission_id:str=''):
 return {'nodes':[],'edges':[],'lanes':[],'mission':mission} if not mission_id or mission_id==mission['id'] else service.agent_space(mission_id=mission_id)
@app.get('/api/v3/command-center/missions')
def missions():
 rows=service.list_missions(limit=100);return {'missions':rows+[mission],'total':len(rows)+1}
@app.get('/api/v3/command-center/missions/{mid}')
def detail(mid:str):return get_mission(mid)
@app.get('/api/v3/command-center/missions/{mid}/artifacts/{aid}/download')
def download(mid:str,aid:str):
 try:
  result=router.download_mission_artifact(mid,aid,user=user)
  with (LAB/'downloads.jsonl').open('a') as f:f.write(json.dumps({'status':200,'hash':hashlib.sha256(result.body).hexdigest()})+'\n')
  return result
 except HTTPException as exc:
  with (LAB/'downloads.jsonl').open('a') as f:f.write(json.dumps({'status':exc.status_code,'detail':exc.detail},ensure_ascii=False)+'\n')
  raise
@app.get('/{path:path}')
def static(path:str):
 if path.startswith('api/'):raise HTTPException(404,'Outside read-only fixture scope')
 dist=Path('/private/tmp/agent-system-phase15-dist');target=(dist/path).resolve()
 if target.is_relative_to(dist) and target.is_file():return FileResponse(target)
 return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div style="background:#663c00;color:white;padding:8px;text-align:center">第十六阶段隔离测试 · 独立 PostgreSQL · 新任务须审批 · 真实执行与验收 · 无外发</div>'))


from services.command_center_worker import CommandCenterWorker
from services.openclaw_task_executor import OpenClawTaskExecutor
from services.work_run_service import WorkRunService
class Recorder:
 def __init__(self):self.real=OpenClawTaskExecutor();self.count=0
 async def execute(self,command,command_args=None,timeout_seconds=300):
  self.count+=1; n=self.count;save(f'call-{n}-invocation.json',command_args)
  result=await self.real.execute(command,command_args,timeout_seconds=timeout_seconds)
  save(f'call-{n}-result.json',result.to_dict());return result
class Sender:
 async def send(self,item):return {'success':False,'error':'Isolated lab, external delivery disabled'}
worker=CommandCenterWorker(service=service,executor=Recorder(),work_runs=WorkRunService(database_url=URL),sender=Sender(),context_service=None,memory_service=None)
worker.worker_id='phase16-redelivery-worker'
@app.post('/api/v3/command-center/missions')
def create(body:dict):
 assert not service.list_missions(limit=1), 'This lab admits one new mission only'
 service.validate_project_target(body['project_id'],body['mission_type'])
 m=service.create_mission(title=body.get('title',''),objective=body['objective'],project_id=body['project_id'],mission_type=body['mission_type'],requested_by='phase16-browser',profile_user_id='phase16',context={'business_flow_key':'general'})
 service.claim_planning_mission('phase16-plan-fixture')
 newfile=LAB/'redelivery-v2.txt'; oldhash=hashlib.sha256(file.read_bytes()).hexdigest()
 description=f"仅允许使用 exec/Python：读取旧文件 {file} 并验证其 SHA256 为 {oldhash}；使用独占创建模式 x 创建新文件 {newfile}，内容严格为 Phase 16 redelivery verified 加一个换行。若新路径已存在则只读核对，不覆盖。创建后回读并计算实际 SHA256，确认旧文件哈希未变。返回新文件为 document artifact，并为写入返回 side_effects applied、当前合同幂等键以及真实工具回执。只允许写入该新路径，不修改旧文件或任何其他文件，不外发、不联网。"
 service.save_plan(m['id'],{'summary':'受控重新交付：保留原证据，在独立路径创建并核验新文件。','steps':[{'title':'创建并核验独立交付版本','description':description,'agent_id':'ratchet','task_type':'coordination','side_effect':True,'risk_class':'L1','approval_required':False,'resources':[str(newfile)],'rollback_plan':'不删除或覆盖文件；出现异常时仅只读核实并报告，人工决定后续处理。','depends_on':[],'required_tools':['test_runner'],'deliverables':[str(newfile)],'evidence_required':['test_output'],'acceptance_criteria':['新文件内容严格为 Phase 16 redelivery verified 加换行，旧文件哈希保持不变，返回实际内容哈希及工具证据'],'output_contract':{'artifact_types':['document'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
 assert service.claim_ready_steps('before-approval-probe')==[]
 assert not newfile.exists()
 save('before-approval.json',service.get_mission(m['id']))
 save('submitted-body.json',body)
 return {'success':True,'mission':service.get_mission(m['id'])}
@app.post('/api/v3/command-center/missions/{mid}/approve')
async def approve(mid:str,body:dict):
 result=service.approve(mid,decided_by='phase16-browser',comment=body.get('comment',''))
 worker.start();return result
@app.on_event('shutdown')
async def shutdown():await worker.stop()
if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=3046)
