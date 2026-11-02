import asyncio
import json
from pathlib import Path

import pytest

from services import isolated_agent_executor as isolated
from services.agent_execution_profile_service import resolve_profile
from services.openclaw_task_executor import OpenClawTaskExecutor, ExecutionResult


def test_tool_policy_and_actual_model_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_MODEL', 'provider/requested')
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_THINKING', 'high')
    seen = {}
    class Process:
        returncode = 0
        async def communicate(self, stdin):
            seen['prompt'] = stdin
            return json.dumps({'ok': True, 'final': '{}', 'model': 'actual', 'provider': 'provider', 'usage': {'input': 12}}).encode(), b''
    async def spawn(*args, **kwargs):
        seen['args'] = args
        seen['config'] = json.loads(Path(args[args.index('--config') + 1]).read_text())
        assert args[args.index('--message-file') + 1] == '-'
        assert 'private prompt' not in args
        return Process()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    result = asyncio.run(isolated.execute_isolated('advisor', 'private prompt'))
    assert seen['config']['tools']['deny'] == ['*']
    assert seen['config']['plugins']['enabled'] is False
    assert result.execution_profile['requested_model'] == 'provider/requested'
    assert result.execution_profile['actual_model'] == 'actual'
    assert result.execution_profile['cost_usd'] is None
    assert isolated.tool_config('worker')['tools']['allow'] == ['read', 'write', 'edit']
    assert isolated.tool_config('worker')['tools']['fs']['workspaceOnly'] is True


def test_explicit_model_does_not_fall_back_to_http(monkeypatch):
    monkeypatch.setenv('COMMAND_CENTER_PLANNER_MODEL', 'provider/model')
    executor = OpenClawTaskExecutor()
    async def no_cli(*args, **kwargs):
        assert kwargs['model'] == 'provider/model'
        raise FileNotFoundError()
    async def no_http(*args, **kwargs):
        raise AssertionError('must not downgrade profile')
    monkeypatch.setattr(executor, '_execute_via_cli', no_cli)
    monkeypatch.setattr(executor, '_execute_via_http_api', no_http)
    result = asyncio.run(executor.execute('agent_run', {'agent_id': 'optimus', 'message': 'plan', 'execution_role': 'planner'}))
    assert not result.success


def test_unknown_profile_values_rejected(monkeypatch):
    monkeypatch.setenv('COMMAND_CENTER_WORKER_THINKING', 'unsupported')
    with pytest.raises(ValueError):
        resolve_profile('worker')


def test_isolated_roles_refuse_cli_agent_backends(monkeypatch):
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_MODEL', 'codex-cli/model')
    with pytest.raises(ValueError, match='CLI agent'):
        asyncio.run(isolated.execute_isolated('advisor', 'review'))


def test_timeout_terminates_child(monkeypatch):
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_MODEL', 'provider/model')
    class Process:
        returncode = None
        killed = False
        async def communicate(self, stdin):
            raise asyncio.TimeoutError()
        def kill(self):
            self.killed = True
        async def wait(self):
            self.returncode = -9
    process = Process()
    async def spawn(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(isolated.execute_isolated('advisor', 'review'))
    assert process.killed
