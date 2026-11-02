"""Read-only snapshot UI lab; real artifact download route, no worker or external calls."""
import copy, hashlib, json, os, sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
LAB=ROOT/'docs/review/computer-use-phase19-20261008'
URL='postgresql+psycopg2:///agent_system_cu_phase19_20261008'
os.environ['COMMAND_CENTER_DATABASE_URL']=URL
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH=str(LAB/'auxiliary.sqlite3')
os.environ['COMMAND_CENTER_ARTIFACT_ROOTS']=str(LAB)
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from routers import command_center_router as router
import uvicorn
app=FastAPI()
mission=copy.deepcopy(json.loads((ROOT/'docs/review/computer-use-phase13-20261006/final-missions.json').read_text())['missing'])
mission.update(id='phase19-delivery',title='P19 已验收文件下载复核',project_id='phase19-project',mission_type='document')
file=LAB/'delivery.txt'
if not file.exists():file.write_text('Phase 15 original delivery\n')
original=b'Phase 15 original delivery\n'
mission['artifacts']=[dict(id='phase19-artifact',step_id='',artifact_type='document',title='阶段十九交付样本',uri=str(file),content_hash=hashlib.sha256(original).hexdigest(),created_at=mission['created_at'])]
(LAB/'mission-snapshot.json').write_text(json.dumps(mission,ensure_ascii=False,indent=2))
from services.command_center_service import CommandCenterService
from repositories.command_center_repository import PostgresCommandCenterRepository
PROJECT={'id':'phase19-project','name':'阶段十九隔离项目','project_type':'document','status':'active'}
service=CommandCenterService(repository=PostgresCommandCenterRepository(URL),project_provider=lambda:[PROJECT],workflow_runtime_selector=lambda _: {'runtime':'legacy','reason':'idempotency_lab','flow_key':'general'})
def get_mission(mid,**kw):
 return mission if mid==mission['id'] else service.get_mission(mid,**kw)
class ServiceView:
 def get_mission(self,mid,**kw):return get_mission(mid,**kw)
 def __getattr__(self,name):return getattr(service,name)
router.command_center_service=ServiceView()
user={'id':101,'sub':'phase19','username':'phase19','display_name':'隔离交付测试','role':'user','is_active':True,'module_keys':['dashboard','command-center'],'modules':[]}
@app.get('/api/v2/auth/settings')
def settings():return {'login_enabled':False,'mode':'development'}
@app.post('/api/v2/auth/development-session')
def identity():return {'access_token':'isolated-lab-only','token_type':'bearer','expires_in':3600,'user':user}
@app.get('/api/v2/auth/me')
def me():return user
@app.get('/api/v3/projects')
def projects():return {'projects':[{'id':'phase19-project','name':'阶段十九隔离项目','project_type':'document','status':'active'}],'total':1}
@app.get('/api/v3/command-center/summary')
def summary():return {'total':1,'active':0,'by_status':{'completed':1},'memory_candidates':{'total':0,'pending_review':0,'published':0,'rejected':0,'by_status':{}}}
@app.get('/api/v3/command-center/memory-candidates')
def memory():return {'candidates':[],'summary':{'total':0},'can_review':False}
@app.get('/api/v3/command-center/messages')
def messages():return {'messages':[],'total':0}
def old_workbench():return {'items':[{'mission_id':mission['id'],'mission_title':mission['title'],'mission_status':'completed','mission_type':'document','project_id':'phase19-project','project_name':'阶段十九隔离项目','current_agent_id':'optimus','current_agent_name':'擎天柱','progress':100,'steps_summary':{'total':1,'completed':1},'linked_tasks':[],'updated_at':mission['updated_at']}],'total':1}
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
@app.get('/lab/user/{name}')
def switch_user(name:str):
 from fastapi.responses import RedirectResponse
 user['id']=101 if name=='a' else 102
 user['display_name']='草稿测试账号 '+name.upper()
 return RedirectResponse('/command-center')
@app.post('/api/v3/command-center/missions')
def submit(body:dict):
 result=router.create_mission(router.MissionCreateRequest(**body),user=user)
 marker=LAB/'response-lost.json'
 first=not marker.exists()
 with (LAB/'requests.jsonl').open('a') as f:f.write(json.dumps({'body':body,'mission_id':result['mission']['id'],'response':504 if first else 200},ensure_ascii=False)+'\n')
 if first:
  marker.write_text(json.dumps(result,ensure_ascii=False,indent=2))
  raise HTTPException(504,'隔离测试：任务已提交，但本次响应模拟丢失')
 return result
@app.get('/{path:path}')
def static(path:str):
 if path.startswith('api/'):raise HTTPException(404,'Outside read-only fixture scope')
 dist=Path('/private/tmp/agent-system-phase19-dist');target=(dist/path).resolve()
 if target.is_relative_to(dist) and target.is_file():return FileResponse(target)
 return HTMLResponse((dist/'index.html').read_text().replace('<body>','<body><div><a href="/lab/user/a">测试账号 A</a> | <a href="/lab/user/b">测试账号 B</a></div><div style="background:#663c00;color:white;padding:8px;text-align:center">第十九阶段隔离测试 · 历史任务快照 · 真实下载校验 · 不启动任务</div>'))
if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=3049)
