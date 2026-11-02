import os,sys,time,json,signal,subprocess,hashlib,runpy
from pathlib import Path
root=Path(__file__).resolve().parents[2];lab=root/'docs/review/computer-use-phase12-20261006';sys.path.insert(0,str(root/'backend'))
assert not (lab/'crash-observed.json').exists(), 'This probe is one-shot; retain previous crash evidence'
ns=runpy.run_path(str(root/'backend/scripts/run_phase12_recovery_crash_lab.py'));s=ns['service'];save=ns['save'];mid=next(iter(ns['fixtures']()))
deadline=time.monotonic()+180
while not (lab/'crash-boundary.json').exists():
 assert time.monotonic()<deadline
 time.sleep(.1)
boundary=json.loads((lab/'crash-boundary.json').read_text());pid=boundary['pid'];old=boundary['compensation']
cmd=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True)
assert 'run_phase12_recovery_crash_lab.py --worker' in cmd
os.kill(pid,signal.SIGKILL); killed=time.monotonic();save('crash-observed.json',{'pid':pid,'signal':'SIGKILL','time':time.time()})
assert s.get_mission(mid)['compensations'][0]['status']=='running'
assert s.claim_ready_compensation('before-expiry-probe') is None
log=(lab/'replacement-worker.log').open('a');child=subprocess.Popen([sys.executable,str(root/'backend/scripts/run_phase12_recovery_crash_lab.py'),'--worker'],stdout=log,stderr=log);log.close();save('replacement-worker.json',{'pid':child.pid})
while s.get_mission(mid)['compensations'][0]['status']=='running':
 assert child.poll() is None
 assert time.monotonic()-killed<75
 time.sleep(.25)
state=s.get_mission(mid);case=state['compensations'][0];assert case['status']=='pending_approval'
assert case['authorization_expires_at'] is None and case['approved_by'] is None
assert s.claim_ready_compensation('unapproved-probe') is None
from services.command_center_service import InvalidMissionTransition
rejected=[]
for kind in ['heartbeat','completion']:
 try:
  if kind=='heartbeat': s.renew_compensation_lease(old['id'],lease_token=old['lease_token'])
  else: s.complete_compensation(old['id'],lease_token=old['lease_token'],result={'status':'reverted','summary':'迟到旧回执','receipt_ref':str(lab/'recovery-receipt.json'),'evidence_refs':[str(lab/'recovery-receipt.json')]},actor='dead-worker')
 except InvalidMissionTransition: rejected.append(kind)
assert rejected==['heartbeat','completion']
for n,expected in boundary['files'].items():
 f=lab/n;assert hashlib.sha256(f.read_bytes()).hexdigest()==expected['sha256'];assert f.stat().st_mtime_ns==expected['mtime_ns']
assert len((lab/'physical-writes.jsonl').read_text().splitlines())==1
save('interruption-check.json',{'elapsed_seconds':round(time.monotonic()-killed,2),'status':case['status'],'stale_operations_rejected':rejected,'actual_recovery_writes':1,'five_files_unchanged':True,'same_contract':case['contract_hash']==old['contract_hash'],'same_idempotency_key':case['idempotency_key']==old['idempotency_key']})
save('interrupted-mission.json',state);print((lab/'interruption-check.json').read_text(),flush=True)
