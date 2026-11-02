from contextlib import contextmanager
import pytest
from services.command_center_service import InvalidMissionTransition
from tests.test_phase9_recovery_verification import verification, receipt


def expire(service, case):
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_compensations SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(case['id'],))


def test_expired_compensation_cannot_be_revived_by_late_heartbeat(tmp_path):
    service, mission, case=verification(tmp_path)
    expire(service,case)
    with pytest.raises(InvalidMissionTransition):
        service.renew_compensation_lease(case['id'],lease_token=case['lease_token'])
    assert service.requeue_stale_compensations()==1
    assert service.requeue_stale_compensations()==0
    assert service.claim_ready_compensation('replacement') is None
    state=service.get_mission(mission['id'])['compensations'][0]
    assert state['status']=='pending_approval'
    assert state['approved_by'] is None and state['authorization_expires_at'] is None
    with pytest.raises(InvalidMissionTransition):
        service.complete_compensation(case['id'],lease_token=case['lease_token'],result=receipt(),actor='late')


@pytest.mark.parametrize('changed_field',['lease_token','lease_expires_at'])
def test_stale_scan_does_not_clear_a_newer_lease_snapshot(tmp_path,monkeypatch,changed_field):
    service, mission, case=verification(tmp_path)
    expire(service,case)
    original=service.connect
    class Connection:
        def __init__(self,conn): self.conn=conn
        def execute(self,sql,args=()):
            result=self.conn.execute(sql,args)
            if "SELECT * FROM mission_compensations" in sql and "lease_expires_at <=" in sql:
                rows=result.fetchall()
                # Model another committed renewal/owner change after scan but before CAS.
                if changed_field=='lease_token':
                    self.conn.execute("UPDATE mission_compensations SET lease_token='new-token' WHERE id=?",(case['id'],))
                else:
                    self.conn.execute("UPDATE mission_compensations SET lease_expires_at='2099-01-01T00:00:00+00:00' WHERE id=?",(case['id'],))
                class Snapshot:
                    def fetchall(self): return rows
                return Snapshot()
            return result
        def __getattr__(self,name): return getattr(self.conn,name)
    @contextmanager
    def interleaved(*args,**kwargs):
        with original(*args,**kwargs) as conn: yield Connection(conn)
    monkeypatch.setattr(service,'connect',interleaved)
    assert service.requeue_stale_compensations()==0
    state=service.get_mission(mission['id'])
    assert state['compensations'][0]['status']=='running'
    assert not any(e['event_type']=='compensation_reapproval_required' for e in state['events'])
