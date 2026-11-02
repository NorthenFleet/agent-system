"""Full worker loop crash recovery with real OpenClaw in a dedicated PG store."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
URL = 'postgresql+psycopg2:///agent_system_cu_phase7_20261006'
OUT = ROOT / 'docs/review/computer-use-phase7-20261006'
OUT.mkdir(exist_ok=True)
for key in ['COMMAND_CENTER_DATABASE_URL', 'WORK_RUN_DATABASE_URL', 'DATABASE_URL']:
    os.environ[key] = URL
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
os.environ['COMMAND_CENTER_STEP_TIMEOUT'] = '60'
os.environ['COMMAND_CENTER_POLL_SECONDS'] = '1'
os.environ['COMMAND_CENTER_WORKER_HEARTBEAT_SECONDS'] = '2'
os.environ['COMMAND_CENTER_MAX_PARALLEL'] = '1'
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH = str(OUT/'auxiliary.sqlite3')
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.command_center_service import CommandCenterService, InvalidMissionTransition
from services.command_center_worker import CommandCenterWorker
from services.openclaw_task_executor import OpenClawTaskExecutor
from services.work_run_service import WorkRunService


def service():
    return CommandCenterService(repository=PostgresCommandCenterRepository(URL), project_provider=lambda: [],
        workflow_runtime_selector=lambda _: {'runtime':'legacy','reason':'isolated_worker_test','flow_key':'general'})


def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


class BlockExternalSender:
    def __init__(self, directory, role): self.directory,self.role=directory,role
    async def send(self, item):
        with (self.directory/f'{self.role}-blocked-notifications.jsonl').open('a') as f:
            f.write(json.dumps({'id':item['id'],'action':'blocked_without_external_call'})+'\n')
        return {'success':False,'error':'Isolated test: external delivery disabled'}


class RecordedExecutor:
    def __init__(self, directory, role):
        self.directory,self.role=directory,role
        self.real=OpenClawTaskExecutor()
    async def execute(self, command, command_args=None, timeout_seconds=300):
        args=command_args or {}
        is_step=args.get('agent_id')=='ratchet'
        kind='step' if is_step else 'evaluation'
        save(self.directory/f'{self.role}-{kind}-invocation.json',args)
        if is_step: save(self.directory/f'{self.role}-entered.json',{'pid':os.getpid()})
        result=await self.real.execute(command,args,timeout_seconds=timeout_seconds)
        save(self.directory/f'{self.role}-{kind}-result.json',result.to_dict())
        if self.role=='a' and is_step:
            # Deliberate crash window after provider return, before worker persists.
            save(self.directory/'a-returned.json',{'success':result.success})
            await asyncio.Event().wait()
        return result


async def child(role, directory):
    s=service()
    worker=CommandCenterWorker(service=s,executor=RecordedExecutor(directory,role),
        work_runs=WorkRunService(database_url=URL),
        sender=BlockExternalSender(directory,role),context_service=None,memory_service=None)
    worker.worker_id='phase7-full-worker-'+role
    worker.start()
    save(directory/f'{role}-started.json',{'pid':os.getpid(),'lease_seconds':worker.step_lease_seconds,
        'heartbeat_seconds':worker.step_heartbeat_seconds,'worker_id':worker.worker_id})
    try:
        while not (directory/'stop.json').exists(): await asyncio.sleep(.5)
    finally:
        await worker.stop()


def wait_file(path, timeout):
    deadline=time.monotonic()+timeout
    while not path.exists():
        if time.monotonic()>deadline: raise TimeoutError(str(path))
        time.sleep(.25)


def parent():
    s=service()
    with s.connect() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM orchestration_missions WHERE status NOT IN ('cancelled','completed','waiting_feedback')").fetchone()['n']==0, 'Lab has unfinished active work'
    d=OUT/('run-'+uuid.uuid4().hex[:8]);d.mkdir()
    source=ROOT/'docs/review/computer-use-phase3-20261005/deliverables/H/revised.md'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    m=s.create_mission(title='P7 完整worker回执前崩溃恢复',requested_by='phase7-test',
        objective=f'隔离只读核验 {source}，不得写入、删除、联网搜索、发送消息或创建其他任务。核验三节及100至180汉字、实际SHA-256。最终评估仅依据回执与证据，不进行其他操作。',
        context={'business_flow_key':'general'})
    s.claim_planning_mission('phase7-plan-fixture')
    s.save_plan(m['id'],{'summary':'只读核验；真实执行器返回后故障接管','steps':[{
        'order_index':1,'title':'只读核验既有修订稿','agent_id':'ratchet','task_type':'coordination',
        'description':f'只用 exec 调用 Python 读取 {source}；统计 [\\u4e00-\\u9fff] 汉字，核验目标/风险与应对/验收三节，计算SHA-256。已有文件作为document产物，不创建文件。risk_notes填写本次只读核验的范围限制，不为空。禁止发送消息。',
        'side_effect':False,'max_attempts':2,'depends_on':[],'required_tools':['test_runner'],
        'deliverables':['既有修订稿及真实核验回执'],'evidence_required':['test_output'],
        'acceptance_criteria':['三节齐全且100至180汉字，并返回实际SHA-256'],
        'output_contract':{'artifact_types':['document'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
    s.approve(m['id'],decided_by='phase7-test')
    procs=[]; handles=[]
    try:
        def spawn(role):
            f=(d/f'{role}-worker.log').open('w');handles.append(f)
            p=subprocess.Popen([sys.executable,__file__,role,str(d)],stdout=f,stderr=subprocess.STDOUT)
            procs.append(p);return p
        a=spawn('a');wait_file(d/'a-returned.json',120)
        assert json.loads((d/'a-returned.json').read_text())['success'], 'First real executor call failed'
        old=s.get_mission(m['id'])['steps'][0]
        save(d/'before-crash.json',s.get_mission(m['id']))
        b=spawn('b');wait_file(d/'b-started.json',30)
        assert a.poll() is None and b.poll() is None
        a.kill();a.wait(timeout=5)
        started=time.monotonic()
        immediate=s.get_mission(m['id'])['steps'][0]
        assert immediate['status']=='running' and immediate['lease_token']==old['lease_token']
        print(f'RUN_DIR={d}; full worker A killed after real result; waiting for natural lease expiry',flush=True)
        observations=[];last_notice=0
        while not (d/'b-entered.json').exists():
            elapsed=time.monotonic()-started
            if elapsed>360: raise TimeoutError('Full worker did not recover within lease window')
            if elapsed-last_notice>=30:
                state=s.get_mission(m['id'])
                observations.append({'elapsed':round(elapsed,1),'mission_status':state['status'],'workers':s.worker_runtime_status()})
                print(f'Lease wait {elapsed:.0f}s; mission={state["status"]}',flush=True);last_notice=elapsed
            if b.poll() is not None: raise RuntimeError('Worker B exited')
            time.sleep(.5)
        current=s.get_mission(m['id'])['steps'][0]
        assert old['id']==current['id'] and old['lease_token']!=current['lease_token']
        stale_rejected=False
        try:
            s.complete_step(old['id'],result={'outcome':'succeeded','summary':'stale return'},success=True,
                actor='old-worker',lease_token=old['lease_token'])
        except InvalidMissionTransition: stale_rejected=True
        assert stale_rejected
        recovered_at=round(time.monotonic()-started,2)
        deadline=time.monotonic()+240
        while True:
            final=s.get_mission(m['id'])
            if final['status'] in {'completed','waiting_feedback','cancelled'}: break
            if time.monotonic()>deadline: raise TimeoutError('Final evaluation did not finish')
            time.sleep(1)
        save(d/'final-mission.json',final);save(d/'worker-observations.json',observations)
        after=hashlib.sha256(source.read_bytes()).hexdigest()
        with s.connect() as c:
            sent=c.execute("SELECT COUNT(*) AS n FROM notification_outbox WHERE status='sent'").fetchone()['n']
        report={'mission_id':m['id'],'final_status':final['status'],'same_step_new_token':True,
            'stale_write_rejected':stale_rejected,'recovery_seconds':recovered_at,
            'lease_config':json.loads((d/'a-started.json').read_text()),
            'source_unchanged':before==after,'sent_notifications':sent,
            'attempt_count':final['steps'][0]['attempt_count']}
        save(d/'summary.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
        assert final['status']=='completed' and before==after and sent==0
    finally:
        save(d/'stop.json',{})
        for p in procs:
            if p.poll() is None:
                try: p.wait(timeout=10)
                except subprocess.TimeoutExpired: p.kill();p.wait(timeout=5)
        for f in handles:f.close()


if __name__=='__main__':
    asyncio.run(child(sys.argv[1],Path(sys.argv[2]))) if len(sys.argv)>1 else parent()
