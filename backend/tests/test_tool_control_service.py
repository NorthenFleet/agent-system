import asyncio
import json
import os
from pathlib import Path

import pytest

from services.command_center_service import CommandCenterService, InvalidMissionTransition
from services.mission_code_workspace_service import MissionCodeWorkspaceService
from services.tool_control_bridge import ToolControlBridge, PLUGIN_PATH
from tests.test_mission_code_workspace_service import configured


def running(tmp_path, monkeypatch):
    repo, raw = configured(tmp_path, monkeypatch)
    service = CommandCenterService(str(tmp_path / 'tool.db'))
    mission = service.create_mission(objective='guarded code candidate', requested_by='admin', context={'business_flow_key':'general'})
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'steps':[raw], 'risk_level':'low'})
    service.approve(mission['id'], decided_by='admin')
    service.activate_approved_missions()
    step = service.claim_ready_steps('runner')[0]
    workspace = MissionCodeWorkspaceService().prepare_step(step)
    service.record_code_workspace(step['id'], step['lease_token'], workspace)
    return service, mission, step, Path(workspace['execution_repo'])


def invoke(service, step, call_id, action, **args):
    return service.execute_controlled_tool(step['id'], step['lease_token'], call_id, action, args)


def test_before_after_receipts_and_no_duplicate_execution(tmp_path, monkeypatch):
    service, _, step, root = running(tmp_path, monkeypatch)
    first = invoke(service, step, 'one', 'write', path='hello.py', content='new\n')
    assert first['ok']
    assert first['receipt']['before_sha256'] != first['receipt']['after_sha256']
    duplicate = invoke(service, step, 'one', 'write', path='hello.py', content='duplicate\n')
    assert not duplicate['ok']
    assert (root/'hello.py').read_text() == 'new\n'
    read = invoke(service, step, 'two', 'read', path='hello.py')
    assert read['output'] == 'new\n'
    summary = service.tool_control_summary(step['id'], step['attempt_count'])
    assert summary['calls'] == summary['receipts'] == 2
    assert not summary['accepted']  # replay attempt is permanently audited


@pytest.mark.parametrize('path', ['../outside', '/etc/passwd', '.git/config', 'sub/../../outside'])
def test_path_escape_denied_before_operation(tmp_path, monkeypatch, path):
    service, _, step, _ = running(tmp_path, monkeypatch)
    assert not invoke(service, step, 'escape', 'write', path=path, content='bad')['ok']
    summary = service.tool_control_summary(step['id'], step['attempt_count'])
    assert summary['denied'] == 1
    assert summary['receipts'] == 0


def test_symlink_hardlink_and_fifo_refused(tmp_path, monkeypatch):
    service, _, step, root = running(tmp_path, monkeypatch)
    outside = tmp_path/'outside'
    outside.write_text('preserved')
    (root/'link').symlink_to(outside)
    os.link(outside, root/'hardlink')
    os.mkfifo(root/'pipe')
    for name in ['link','hardlink','pipe']:
        assert not invoke(service, step, name, 'write', path=name, content='bad')['ok']
    assert outside.read_text() == 'preserved'
    assert service.tool_control_summary(step['id'], step['attempt_count'])['unknown'] == 3


def test_cancelled_or_stale_lease_cannot_write(tmp_path, monkeypatch):
    service, mission, step, root = running(tmp_path, monkeypatch)
    service.cancel(mission['id'], actor='admin')
    with pytest.raises(InvalidMissionTransition):
        invoke(service, step, 'late', 'write', path='hello.py', content='bad')
    assert (root/'hello.py').read_text() == 'old\n'
    assert service.tool_control_summary(step['id'], step['attempt_count'])['calls'] == 0


def test_crash_after_write_leaves_unresolved_intent_and_never_replays(tmp_path, monkeypatch):
    service, _, step, root = running(tmp_path, monkeypatch)
    original = service._add_event
    def crash(conn, mission_id, event_type, *args, **kwargs):
        if event_type == 'tool_receipt':
            raise RuntimeError('simulated crash before receipt commit')
        return original(conn, mission_id, event_type, *args, **kwargs)
    monkeypatch.setattr(service, '_add_event', crash)
    with pytest.raises(RuntimeError):
        invoke(service, step, 'crash', 'write', path='hello.py', content='applied')
    assert (root/'hello.py').read_text() == 'applied'
    restarted = CommandCenterService(service.repository.db_path)
    assert restarted.tool_control_summary(step['id'], step['attempt_count'])['incomplete'] == 1
    assert not invoke(restarted, step, 'crash', 'write', path='hello.py', content='replayed')['ok']
    assert (root/'hello.py').read_text() == 'applied'


def test_budget_and_edit_exact_match(tmp_path, monkeypatch):
    service, _, step, root = running(tmp_path, monkeypatch)
    assert invoke(service, step, 'edit', 'edit', path='hello.py', old_text='old', new_text='new')['ok']
    for index in range(63):
        assert invoke(service, step, str(index), 'read', path='hello.py')['ok']
    assert invoke(service, step, 'limit', 'read', path='hello.py')['error'] == 'tool_call_budget_exhausted'
    assert (root/'hello.py').read_text() == 'new\n'


def test_plugin_rpc_executes_through_real_controller(tmp_path, monkeypatch):
    service, _, step, root = running(tmp_path, monkeypatch)
    async def scenario():
        async with ToolControlBridge(service, step) as controller:
            config = {'socketPath':controller.socket_path, 'token':controller.token}
            # Dynamic import uses the checked-in entry, never model-provided code.
            script = '''
const {default:plugin} = await import(process.env.PLUGIN_URL);
const tools = new Map();
plugin.register({pluginConfig:JSON.parse(process.env.CONTROLLER_CONFIG),registerTool:t=>tools.set(t.name,t)});
if (tools.size !== 4) throw Error('missing tools');
await tools.get('dr4_write').execute('native-call', {path:'hello.py',content:'controlled'});
const result = await tools.get('dr4_read').execute('native-read', {path:'hello.py'});
if (result.content[0].text !== 'controlled') throw Error('unexpected result');
'''
            proc = await asyncio.create_subprocess_exec('node', '--input-type=module', '-e', script,
                     env={**os.environ,'PLUGIN_URL':(PLUGIN_PATH/'index.js').as_uri(), 'CONTROLLER_CONFIG':json.dumps(config)},
                     stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            assert proc.returncode == 0, err.decode()
            assert controller.summary()['accepted']
        assert not Path(controller.socket_path).exists()
    asyncio.run(scenario())
    assert (root/'hello.py').read_text() == 'controlled'


@pytest.mark.parametrize('write_file', [True, False])
def test_worker_requires_closed_tool_receipts(tmp_path, monkeypatch, write_file):
    from services import command_center_worker as workers
    from services.openclaw_task_executor import ExecutionResult
    from services.work_run_service import WorkRunService
    repo, raw = configured(tmp_path, monkeypatch)
    monkeypatch.setenv('COMMAND_CENTER_TOOL_CONTROL_ENABLED', 'true')
    service = CommandCenterService(str(tmp_path / 'worker.db'))
    mission = service.create_mission(objective='controlled candidate', requested_by='admin', context={'business_flow_key':'general'})
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'steps':[raw], 'risk_level':'low'})
    service.approve(mission['id'], decided_by='admin')
    service.activate_approved_missions()
    step = service.claim_ready_steps('runner')[0]

    class LocalBridge(ToolControlBridge):
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass

    async def execute(role, prompt, *, cwd, timeout, tool_control):
        if write_file:
            assert invoke(tool_control.service, tool_control.step, 'worker-write', 'write', path='hello.py', content='candidate')['ok']
        return ExecutionResult(True, output='model claims success')

    monkeypatch.setattr(workers.tool_control_bridge, 'ToolControlBridge', LocalBridge)
    monkeypatch.setattr(workers, 'execute_isolated', execute)
    worker = workers.CommandCenterWorker(service=service, work_runs=WorkRunService(str(tmp_path/'runs.db')))
    asyncio.run(worker._execute_step(step))
    saved = service.get_mission(mission['id'])['steps'][0]
    assert saved['result']['tool_control']['accepted'] is write_file
    assert (saved['status'] == 'completed') is write_file
    assert (repo/'hello.py').read_text() == 'old\n'
