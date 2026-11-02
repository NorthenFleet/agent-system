"""Isolated PG creation retry probe. Never starts workers or external executors."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.command_center_service import CommandCenterService, InvalidMissionTransition

LAB = ROOT / 'docs/review/computer-use-phase19-20261008'
URL = 'postgresql+psycopg2:///agent_system_cu_phase19_20261008'
service = CommandCenterService(repository=PostgresCommandCenterRepository(URL), workflow_runtime_selector=lambda _: {'runtime': 'legacy', 'reason': 'isolated_probe', 'flow_key': 'general'})
rows = [json.loads(line) for line in (LAB / 'requests.jsonl').read_text().splitlines()]
assert len(rows) == 2 and [r['response'] for r in rows] == [504, 200]
assert rows[0]['body']['idempotency_key'] == rows[1]['body']['idempotency_key']
assert rows[0]['mission_id'] == rows[1]['mission_id']
with service.connect() as conn:
    ui_count = conn.execute('SELECT COUNT(*) AS n FROM orchestration_missions WHERE owner_user_id=?', ('phase19',)).fetchone()['n']
assert ui_count == 1, ui_count
owner = 'pg-probe-' + uuid4().hex
barrier = Barrier(8)
def create(index):
    barrier.wait(timeout=15)
    return service.create_mission(objective='isolated retry probe', requested_by='same-display-name', profile_user_id=owner, idempotency_key='same-request')['id']
with ThreadPoolExecutor(max_workers=8) as pool:
    ids = list(pool.map(create, range(8)))
assert len(set(ids)) == 1
try:
    service.create_mission(objective='changed payload', requested_by='same-display-name', profile_user_id=owner, idempotency_key='same-request')
except InvalidMissionTransition:
    conflict = 'rejected'
else:
    raise AssertionError('conflicting payload accepted')
other = service.create_mission(objective='isolated retry probe', requested_by='same-display-name', profile_user_id=owner+'-other', idempotency_key='same-request')['id']
assert other != ids[0]
with service.connect() as conn:
    count = conn.execute('SELECT COUNT(*) AS n FROM orchestration_missions WHERE owner_user_id=?', (owner,)).fetchone()['n']
assert count == 1
result = dict(ui_requests=len(rows), ui_responses=[r['response'] for r in rows], ui_mission_id=rows[0]['mission_id'], ui_mission_count=ui_count, concurrent_requests=8, concurrent_unique_missions=len(set(ids)), concurrent_mission_id=ids[0], owner_mission_count=count, conflicting_payload=conflict, different_owner_mission_id=other, workers_started=0)
(LAB/'pg-idempotency-audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
print(json.dumps(result, indent=2, ensure_ascii=False))
service.repository.close()
