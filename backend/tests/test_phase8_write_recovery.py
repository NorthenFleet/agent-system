"""Lost write receipts must require verification, never automatic replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from services.command_center_service import CommandCenterService, InvalidMissionTransition


def prepare(service, resource, side_effect=True):
    mission = service.create_mission(objective='隔离写入中断验收', requested_by='test')
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'summary': '受控测试', 'steps': [{
        'title': '写入隔离样本', 'task_type': 'coordination', 'agent_id': 'optimus',
        'side_effect': side_effect, 'risk_class': 'L1', 'approval_required': False,
        'resources': [str(resource)], 'depends_on': []}]})
    service.approve(mission['id'], decided_by='test')
    service.activate_approved_missions()
    return mission


def check_blocked(service, mission, step):
    assert service.claim_ready_steps('replacement') == []
    assert service.requeue_stale_steps() == 0
    assert service.claim_evaluation_mission('reviewer') is None
    current = service.get_mission(mission['id'])
    assert current['status'] == 'waiting_feedback'
    assert current['steps'][0]['status'] == 'failed'
    assert current['steps'][0]['attempt_count'] == 1
    assert len(current['effects']) == 1
    assert current['effects'][0]['status'] == 'unknown'
    recovery = current['compensations'][0]
    assert recovery['status'] == 'pending_approval'
    assert recovery['compensation_type'] == 'verify_effect'
    assert service.claim_ready_compensation('recovery') is None
    with pytest.raises(InvalidMissionTransition):
        service.complete_step(step['id'], result={'summary': 'late'}, success=True,
                              actor='old', lease_token=step['lease_token'])
    return recovery


@pytest.mark.parametrize('side_effect', [False, True])
def test_expired_lease_routes_by_write_contract(tmp_path, side_effect):
    service = CommandCenterService(str(tmp_path/'state.db'))
    mission = prepare(service, tmp_path/'effect.txt', side_effect)
    step = service.claim_ready_steps('old')[0]
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_steps SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (step['id'],))
    assert service.requeue_stale_steps() == 1
    if not side_effect:
        replacement = service.claim_ready_steps('new')[0]
        assert replacement['id'] == step['id']
        assert replacement['lease_token'] != step['lease_token']
        return
    recovery = check_blocked(service, mission, step)
    service.decide_compensation(recovery['id'], expected_mission_id=mission['id'],
        contract_hash=recovery['contract_hash'], decision='approved', decided_by='test')
    claimed = service.claim_ready_compensation('verification')
    # A verify-only contract cannot authorize rollback, even with a plausible receipt.
    completed = service.complete_compensation(claimed['id'], lease_token=claimed['lease_token'],
        result={'status': 'reverted', 'summary': '不允许的写入回滚', 'receipt_ref': 'fixture',
                'evidence_refs': ['fixture']}, actor='test')
    assert completed['status'] == 'failed'
    assert service.get_mission(mission['id'])['effects'][0]['status'] == 'unknown'


def test_real_process_death_after_write_does_not_write_twice(tmp_path):
    db = tmp_path/'crash.db'
    resource, ready = tmp_path/'effect.txt', tmp_path/'claimed.json'
    service = CommandCenterService(str(db))
    mission = prepare(service, resource)
    code = '''
import json,sys,time
from pathlib import Path
from services.command_center_service import CommandCenterService
s=CommandCenterService(sys.argv[1])
step=s.claim_ready_steps('crashing-writer',limit=1,lease_seconds=60)[0]
with Path(sys.argv[2]).open('a') as f: f.write('applied-once\\n')
Path(sys.argv[3]).write_text(json.dumps(step))
while True: time.sleep(1)
'''
    child = subprocess.Popen([sys.executable, '-c', code, str(db), str(resource), str(ready)],
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic()+15
        while not ready.exists():
            assert child.poll() is None, child.stderr.read().decode()
            assert time.monotonic() < deadline
            time.sleep(.1)
        step = json.loads(ready.read_text())
        child.kill()
        child.wait(timeout=5)
        restarted = CommandCenterService(str(db))
        assert restarted.requeue_stale_steps() == 0
        deadline = time.monotonic()+65
        while not restarted.requeue_stale_steps():
            assert time.monotonic() < deadline
            time.sleep(.25)
        check_blocked(restarted, mission, step)
        assert resource.read_text() == 'applied-once\n'
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stderr.close()
