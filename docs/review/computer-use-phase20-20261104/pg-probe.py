import sys,json,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
root=Path('/Users/apple/工作桌面/Workspace/agent-system');sys.path.insert(0,str(root/'backend'))
from services.command_center_service import CommandCenterService,InvalidMissionTransition
from repositories.command_center_repository import PostgresCommandCenterRepository
s=CommandCenterService(repository=PostgresCommandCenterRepository('postgresql+psycopg2:///agent_system_cu_phase19_20261008'),workflow_runtime_selector=lambda _: {'runtime':'legacy','reason':'phase20_probe','flow_key':'general'})
owner='phase20-'+uuid.uuid4().hex;b=Barrier(8)
def create(owner=owner,objective='phase20 isolated retry'):
 return s.create_mission(objective=objective,requested_by='phase20-probe',profile_user_id=owner,idempotency_key='retry')['id']
def call(_):
 b.wait(timeout=15);return create()
with ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(call,range(8)))
assert len(set(ids))==1
assert create()==ids[0]
try:create(objective='changed')
except InvalidMissionTransition:conflict=True
else:raise AssertionError('conflict accepted')
assert create(owner=owner+'-other')!=ids[0]
with s.connect() as c:count=c.execute('SELECT COUNT(*) AS n FROM orchestration_missions WHERE owner_user_id=?',(owner,)).fetchone()['n']
assert count==1
result=dict(database='agent_system_cu_phase19_20261008',owner=owner,requests=8,unique_tasks=len(set(ids)),subsequent_retry_same=True,conflict_rejected=conflict,owner_count=count,workers_started=0)
(root/'docs/review/computer-use-phase20-20261104/pg-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));s.repository.close()
