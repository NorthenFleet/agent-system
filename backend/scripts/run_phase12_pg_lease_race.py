"""One-shot real PostgreSQL transaction interleaving; leaves audit fixtures intact."""
import sys,json,threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from services.command_center_service import CommandCenterService
from repositories.command_center_repository import PostgresCommandCenterRepository
from tests.test_phase8_write_recovery import prepare
URL='postgresql+psycopg2:///agent_system_cu_phase12_race_20261006'
OUT=ROOT/'docs/review/computer-use-phase12-20261006/pg-race.json'
s=CommandCenterService(repository=PostgresCommandCenterRepository(URL),project_provider=lambda:[])
assert not s.list_missions(limit=1), 'Use an empty dedicated race database'
results=[]
for field in ['lease_expires_at','lease_token']:
    m=prepare(s,ROOT/'docs/review/computer-use-phase12-20261006'/f'race-{field}-absent.txt')
    step=s.claim_ready_steps('fixture')[0]
    s.complete_step(step['id'],result={'success':False,'error':'isolated concurrency fixture'},success=False,actor='fixture',lease_token=step['lease_token'])
    s.claim_evaluation_mission('fixture')
    case=s.get_mission(m['id'])['compensations'][0]
    s.decide_compensation(case['id'],expected_mission_id=m['id'],contract_hash=case['contract_hash'],decision='approved',decided_by='fixture')
    old=s.claim_ready_compensation('original')
    with s.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_compensations SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(old['id'],))
    scanner=CommandCenterService(repository=PostgresCommandCenterRepository(URL),project_provider=lambda:[])
    original=scanner.connect; scanned=threading.Event();changed=threading.Event()
    class Proxy:
        def __init__(self,conn):self.conn=conn
        def execute(self,sql,args=()):
            cursor=self.conn.execute(sql,args)
            if "SELECT * FROM mission_compensations" in sql and 'lease_expires_at <=' in sql:
                rows=cursor.fetchall();scanned.set();assert changed.wait(10)
                class Snapshot:
                    def fetchall(self):return rows
                return Snapshot()
            return cursor
        def __getattr__(self,name):return getattr(self.conn,name)
    @contextmanager
    def connection(*args,**kwargs):
        with original(*args,**kwargs) as conn:yield Proxy(conn)
    scanner.connect=connection
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(scanner.requeue_stale_compensations)
        assert scanned.wait(10)
        try:
            with s.connect(immediate=True) as conn:
                if field=='lease_expires_at':conn.execute("UPDATE mission_compensations SET lease_expires_at='2099-01-01T00:00:00+00:00' WHERE id=?",(old['id'],))
                else:conn.execute("UPDATE mission_compensations SET lease_token='replacement-token' WHERE id=?",(old['id'],))
        finally:changed.set()
        count=future.result(timeout=10)
    current=s.get_mission(m['id']);assert count==0
    assert current['compensations'][0]['status']=='running'
    assert not any(e['event_type']=='compensation_reapproval_required' for e in current['events'])
    results.append({'mission_id':m['id'],'changed_field':field,'stale_scan_updates':count,'new_lease_preserved':True,'false_reapproval_events':0})
OUT.write_text(json.dumps(results,ensure_ascii=False,indent=2));print(OUT.read_text())
