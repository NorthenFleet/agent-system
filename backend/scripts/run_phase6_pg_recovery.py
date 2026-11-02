"""Two isolated processes exercise real PostgreSQL leases, not live workers."""
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
URL = 'postgresql+psycopg2:///agent_system_cu_phase6_20261005'
os.environ['COMMAND_CENTER_DATABASE_URL'] = URL
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
from services.command_center_service import CommandCenterService, InvalidMissionTransition
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.execution_contract_ids import contract_items


def service():
    return CommandCenterService(repository=PostgresCommandCenterRepository(URL), project_provider=lambda: [])


def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def wait_file(path, seconds=90):
    deadline = time.monotonic() + seconds
    while not path.exists():
        if time.monotonic() > deadline: raise TimeoutError(str(path))
        time.sleep(.2)


def child(role, directory):
    s = service()
    if role == 'a':
        step = s.claim_ready_steps('phase6-process-a', limit=1, lease_seconds=60)[0]
        save(directory/'a.json', step)
        while True: time.sleep(1)
    wait_file(directory/'a.json')
    save(directory/'b-alive.json', {'pid': os.getpid()})
    wait_file(directory/'a-killed.json')
    deadline = time.monotonic()+90
    while not s.requeue_stale_steps():
        if time.monotonic()>deadline: raise TimeoutError('lease did not expire')
        time.sleep(.5)
    step=s.claim_ready_steps('phase6-process-b',limit=1,lease_seconds=60)[0]
    save(directory/'b.json',step)
    wait_file(directory/'allow-finish.json',20)
    source=ROOT/'docs/review/computer-use-phase3-20261005/deliverables/H/revised.md'
    checksum=hashlib.sha256(source.read_bytes()).hexdigest()
    result={'outcome':'succeeded','summary':'接管进程实际只读计算文件SHA-256',
        'tools_used':['exec'],'artifacts':[{'artifact_key':'a1','artifact_type':'document',
        'title':'既有修订稿','uri':str(source),'content_hash':checksum}],
        'evidence':[{'requirement_id':contract_items(step,'evidence_required')[0]['id'],
        'evidence_type':'test_output','source_ref':'process-b:sha256','summary':checksum,'artifact_key':'a1'}],
        'acceptance_results':[{'criterion_id':contract_items(step,'acceptance_criteria')[0]['id'],
        'criterion':step['acceptance_criteria'][0],'status':'pass','evidence_refs':['process-b:sha256']}],
        'side_effects':[],'risk_notes':'隔离测试，读取已有文件，无写入副作用'}
    complete=s.complete_step(step['id'],result=result,success=True,actor='phase6-process-b',lease_token=step['lease_token'])
    s.claim_evaluation_mission('phase6-process-b')
    final=s.complete_mission(step['mission_id'],summary='PostgreSQL实际租约接管通过',success=True)
    save(directory/'completed.json',{'step':complete,'mission':final})


def parent():
    s=service()
    with s.connect() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM mission_steps WHERE status IN ('ready','running')").fetchone()['n']==0, 'Lab has active work'
    d=ROOT/'docs/review/computer-use-phase6-20261005'/('recovery-'+uuid.uuid4().hex[:8]);d.mkdir()
    m=s.create_mission(title='P6 PostgreSQL隔离进程接管',objective='只读计算文件哈希',requested_by='phase6-process-test',context={'business_flow_key':'general'})
    s.claim_planning_mission('phase6-fixture')
    s.save_plan(m['id'],{'summary':'只读租约接管测试','steps':[{'order_index':1,'title':'只读哈希核验','agent_id':'ratchet',
        'task_type':'coordination','side_effect':False,'max_attempts':2,'depends_on':[],
        'required_tools':['test_runner'],'evidence_required':['test_output'],'acceptance_criteria':['返回实际文件SHA-256'],
        'deliverables':['既有文件和哈希'],'output_contract':{'artifact_types':['document'],'required_fields':['summary','evidence_refs','risk_notes']}}]})
    s.approve(m['id'],decided_by='phase6-fixture');s.activate_approved_missions()
    procs=[]
    try:
        a=subprocess.Popen([sys.executable,__file__,'a',str(d)]);procs.append(a)
        wait_file(d/'a.json',20)
        b=subprocess.Popen([sys.executable,__file__,'b',str(d)]);procs.append(b)
        wait_file(d/'b-alive.json',20)
        old=json.loads((d/'a.json').read_text())
        a.kill();a.wait(timeout=5)
        started=time.monotonic()
        immediate=s.requeue_stale_steps();assert immediate==0
        save(d/'a-killed.json',{'pid':a.pid,'exit_code':a.returncode})
        print('Waiting for actual 60-second PostgreSQL lease expiry',flush=True)
        wait_file(d/'b.json')
        current=json.loads((d/'b.json').read_text())
        assert old['id']==current['id'] and old['lease_token']!=current['lease_token']
        rejected=False
        try:
            s.complete_step(old['id'],result={'outcome':'succeeded','summary':'过期回写'},success=True,actor='old-worker',lease_token=old['lease_token'])
        except InvalidMissionTransition: rejected=True
        assert rejected
        save(d/'allow-finish.json',{})
        assert b.wait(timeout=20)==0
        complete=json.loads((d/'completed.json').read_text())
        assert complete['mission']['status']=='completed'
        report={'database':URL,'mission_id':m['id'],'two_processes_started':True,'killed_process_exit':a.returncode,
            'early_requeue_count':immediate,'elapsed_until_recovery_seconds':round(time.monotonic()-started,2),
            'same_step':True,'new_token':True,'stale_write_rejected':rejected,'final_status':complete['mission']['status']}
        save(d/'summary.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
    finally:
        for p in procs:
            if p.poll() is None: p.kill();p.wait(timeout=5)


if __name__=='__main__':
    child(sys.argv[1],Path(sys.argv[2])) if len(sys.argv)>1 else parent()
