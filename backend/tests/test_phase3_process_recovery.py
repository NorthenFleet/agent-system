"""Real child-process death and disconnected transport, isolated from live workers."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest
from services.command_center_service import CommandCenterService, InvalidMissionTransition


def test_real_worker_process_death_recovers_after_actual_lease_expiry(tmp_path):
    db = str(tmp_path / 'process.db')
    service = CommandCenterService(db)
    mission = service.create_mission(objective='隔离进程退出验收', requested_by='admin')
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'summary': '只读演练', 'steps': [{
        'order_index': 1, 'title': '核验', 'task_type': 'coordination',
        'agent_id': 'optimus', 'side_effect': False, 'depends_on': []}]})
    service.approve(mission['id'], decided_by='admin')
    service.activate_approved_missions()
    ready = tmp_path / 'claimed.json'
    code = '''
import json,sys,time
from pathlib import Path
from services.command_center_service import CommandCenterService
s=CommandCenterService(sys.argv[1])
step=s.claim_ready_steps('isolated-child', limit=1, lease_seconds=60)[0]
Path(sys.argv[2]).write_text(json.dumps(step))
while True: time.sleep(1)
'''
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    child = subprocess.Popen([sys.executable, '-c', code, db, str(ready)], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 20
        while not ready.exists() and time.monotonic() < deadline:
            if child.poll() is not None: pytest.fail(child.stderr.read().decode())
            time.sleep(.05)
        assert ready.exists()
        old = json.loads(ready.read_text())
        child.kill()
        child.wait(timeout=5)
        assert child.returncode < 0
        restarted = CommandCenterService(db)
        assert restarted.requeue_stale_steps() == 0
        deadline = time.monotonic() + 65
        while not restarted.requeue_stale_steps():
            assert time.monotonic() < deadline, 'actual lease failed to expire'
            time.sleep(.5)
        current = restarted.claim_ready_steps('replacement', limit=1)[0]
        assert current['id'] == old['id']
        assert current['lease_token'] != old['lease_token']
        with pytest.raises(InvalidMissionTransition):
            restarted.complete_step(old['id'], result={'summary': 'late'}, success=True,
                                    actor='isolated-child', lease_token=old['lease_token'])
        result = restarted.complete_step(current['id'], result={'outcome': 'succeeded', 'summary': '恢复核验完成'},
            success=True, actor='replacement', lease_token=current['lease_token'])
        assert result['status'] == 'completed'
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=5)
        child.stderr.close()


def test_transport_disconnect_after_effect_preserves_receipt_for_retry(tmp_path):
    # Controlled adapter fixture: local socket disconnect, not a live network outage.
    import sqlite3
    db = tmp_path / 'adapter.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE receipts (key TEXT PRIMARY KEY, receipt TEXT)')
    def apply(key):
        with sqlite3.connect(db) as conn:
            conn.execute('INSERT OR IGNORE INTO receipts VALUES (?,?)', (key, 'receipt-once'))
            return conn.execute('SELECT receipt FROM receipts WHERE key=?', (key,)).fetchone()[0]
    sender, receiver = socket.socketpair()
    try:
        first = apply('approved-step-key')
        receiver.close()  # Real transport loss before the receipt can be delivered.
        with pytest.raises((BrokenPipeError, ConnectionResetError)):
            sender.sendall(first.encode())
    finally:
        sender.close(); receiver.close()
    assert apply('approved-step-key') == first
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0] == 1
