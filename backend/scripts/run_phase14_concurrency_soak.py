"""Bounded 150s/four full workers/60 cases PG experiment; no model or external sender."""
import asyncio,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
LAB=ROOT/'docs/review/computer-use-phase14-20261007';LAB.mkdir(exist_ok=True)
URL='postgresql+psycopg2:///agent_system_cu_phase14_20261007'
for key in ['COMMAND_CENTER_DATABASE_URL','WORK_RUN_DATABASE_URL']:os.environ[key]=URL
os.environ.update(COMMAND_CENTER_POLL_SECONDS='0.5',COMMAND_CENTER_WORKER_HEARTBEAT_SECONDS='2',COMMAND_CENTER_EVIDENCE_ENFORCEMENT='strict')
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH=str(LAB/'auxiliary.sqlite3')
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.command_center_service import CommandCenterService
from services.command_center_worker import CommandCenterWorker
from services.work_run_service import WorkRunService
from services.openclaw_task_executor import ExecutionResult
from tests.test_phase8_write_recovery import prepare

def service():return CommandCenterService(repository=PostgresCommandCenterRepository(URL),project_provider=lambda:[],workflow_runtime_selector=lambda _: {'runtime':'legacy','reason':'phase14','flow_key':'general'})
def save(name,data):(LAB/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
class Executor:
 def __init__(self,role):self.role=role
 async def execute(self,command,command_args=None,timeout_seconds=300):
  message=command_args['message'];assert '<COMPENSATION_CONTRACT>' in message,'Unexpected model/planning call'
  case=json.loads(message.split('<COMPENSATION_CONTRACT>\n')[1].split('\n</COMPENSATION_CONTRACT>')[0])
  fixture=json.loads((LAB/'fixtures.json').read_text())[case['compensation_id']]
  with (LAB/f'worker-{self.role}-calls.jsonl').open('a') as f:f.write(json.dumps({'id':case['compensation_id'],'key':case['idempotency_key'],'session':command_args['session_key']})+'\n')
  await asyncio.sleep(.6)
  return ExecutionResult(success=True,output=json.dumps({'status':'reverted','summary':'固定只读执行器返回回执，由生产门禁独立校验','receipt_ref':fixture['receipt'],'receipt_sha256':fixture['hash'],'evidence_refs':[fixture['receipt']]}))
class Sender:
 async def send(self,item):raise AssertionError('External delivery must never run')
async def child(role):
 s=service();w=CommandCenterWorker(service=s,executor=Executor(role),work_runs=WorkRunService(database_url=URL),sender=Sender(),context_service=None,memory_service=None);w.worker_id=f'phase14-worker-{role}';w.start()
 try:
  while not (LAB/'stop.json').exists():await asyncio.sleep(.2)
 finally:await w.stop()
def parent():
 s=service();assert not s.list_missions(limit=1),'Use empty dedicated DB';assert not (LAB/'fixtures.json').exists()
 fixtures={}
 for i in range(60):
  resource=LAB/f'sample-{i}.txt';resource.write_text('restored\n')
  m=prepare(s,resource);step=s.claim_ready_steps('fixture')[0]
  s.complete_step(step['id'],result={'success':False,'error':'fixture: missing original result'},success=False,actor='fixture',lease_token=step['lease_token']);s.claim_evaluation_mission('fixture')
  old=s.get_mission(m['id'])['compensations'][0]
  s.decide_compensation(old['id'],expected_mission_id=m['id'],contract_hash=old['contract_hash'],decision='approved',decided_by='fixture');claim=s.claim_ready_compensation('fixture')
  s.complete_compensation(old['id'],lease_token=claim['lease_token'],result={'status':'failed','summary':'fixture verification','receipt_ref':str(resource),'evidence_refs':[str(resource)]},actor='fixture')
  case=s.propose_compensation_recovery(old['id'],expected_mission_id=m['id'],contract_hash=old['contract_hash'],instructions='只读核实指定样本和回执，不执行任何文件写入，不外发',actor='fixture')['compensation']
  receipt=LAB/f'receipt-{i}.json';body={'contract_hash':case['contract_hash'],'idempotency_key':case['idempotency_key'],'resource':str(resource),'post_recovery_sha256':digest(resource),'verification':{'all_passed':True}}
  receipt.write_text(json.dumps(body));expected=digest(receipt)
  kind=['valid']*4+['changed_receipt']*2+['changed_resource']*2+['unapproved']*2
  fixtures[case['id']]={'index':i,'mission_id':m['id'],'contract_hash':case['contract_hash'],'receipt':str(receipt),'resource':str(resource),'hash':expected,'kind':kind[i%10]}
 save('fixtures.json',fixtures)
 procs=[];handles=[];observations=[];started=time.monotonic();batch=-1
 try:
  for role in range(4):
   f=(LAB/f'worker-{role}.log').open('w');handles.append(f);procs.append(subprocess.Popen([sys.executable,__file__,'--worker',str(role)],stdout=f,stderr=f))
  while time.monotonic()-started<150:
   elapsed=time.monotonic()-started;due=min(5,int(elapsed//20))
   if due>batch:
    for item in fixtures.values():
     if item['index']//10!=due or item['kind']=='unapproved':continue
     if item['kind']=='changed_receipt':
      path=Path(item['receipt']);(LAB/f"receipt-{item['index']}-original.json").write_bytes(path.read_bytes());path.write_text('{damaged-after-registration')
     if item['kind']=='changed_resource':
      path=Path(item['resource']);(LAB/f"sample-{item['index']}-original.txt").write_bytes(path.read_bytes());path.write_text('unexpected-change\n')
     s.decide_compensation(next(k for k,v in fixtures.items() if v is item),expected_mission_id=item['mission_id'],contract_hash=item['contract_hash'],decision='approved',decided_by='load-driver')
    batch=due
   assert all(p.poll() is None for p in procs),'worker exited'
   with s.connect() as c:
    counts={r['status']:r['n'] for r in c.execute('SELECT status,count(*) AS n FROM mission_compensations GROUP BY status').fetchall()}
   health=s.worker_runtime_status();observations.append({'elapsed':round(elapsed,2),'counts':counts,'live':health['live'],'stale':health['stale']})
   save('observations.json',observations)
   if len(observations)%10==0:print(observations[-1],flush=True)
   time.sleep(1)
 finally:
  save('stop.json',{})
  for p in procs:
   try:p.wait(timeout=15)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for f in handles:f.close()
 calls=[]
 for path in LAB.glob('worker-*-calls.jsonl'):calls += [json.loads(line) for line in path.read_text().splitlines()]
 assert len(calls)==48 and len({x['id'] for x in calls})==48,'duplicate or missing execution'
 with s.connect() as c:
  rows=[dict(r) for r in c.execute('SELECT * FROM mission_compensations').fetchall()]
  sent=c.execute("SELECT count(*) AS n FROM notification_outbox WHERE status='sent'").fetchone()['n']
 for row in rows:
  kind=fixtures[row['id']]['kind'];assert row['status']==('pending_approval' if kind=='unapproved' else 'completed' if kind=='valid' else 'failed')
  assert row['attempts']==(1 if kind=='unapproved' else 2)
 assert sent==0 and all(x['live']==4 and x['stale']==0 for x in observations if x['elapsed']>10)
 save('final-compensations.json',rows)
 save('summary.json',{'duration_seconds':round(time.monotonic()-started,2),'workers':4,'cases':60,'valid_completed':24,'changed_receipt_blocked':12,'changed_resource_blocked':12,'unapproved_not_executed':12,'executions':len(calls),'duplicate_executions':0,'sent_notifications':sent,'samples':len(observations),'passed':True})
 print((LAB/'summary.json').read_text(),flush=True)
if __name__=='__main__':
 if '--worker' in sys.argv:asyncio.run(child(sys.argv[-1]))
 else:parent()
