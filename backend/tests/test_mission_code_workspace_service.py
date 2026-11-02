import json
import subprocess
from pathlib import Path

import pytest

from services.mission_code_workspace_service import MissionCodeWorkspaceService, validate, defaults, EXECUTOR
from services.command_center_service import CommandCenterService
from services.command_center_worker import normalize_plan


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def configured(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init')
    git(repo, 'config', 'user.name', 'Test')
    git(repo, 'config', 'user.email', 'test@local')
    (repo / 'hello.py').write_text('old\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')
    base = git(repo, 'rev-parse', 'HEAD')
    monkeypatch.setenv('COMMAND_CENTER_CODE_WORKSPACE_ENABLED', 'true')
    monkeypatch.setenv('COMMAND_CENTER_WORKER_MODEL', 'provider/model')
    monkeypatch.setenv('COMMAND_CENTER_CODE_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    monkeypatch.setenv('COMMAND_CENTER_CODE_REPOSITORIES', json.dumps({'test': str(repo)}))
    step = {'id': 's', 'attempt_count': 1, 'executor': EXECUTOR, 'task_type': 'backend', 'agent_id': 'raphael', 'title': 'edit code', 'input': {'repository_id': 'test', 'base_commit': base}}
    defaults(step)
    return repo, step


def test_isolation_retained_candidate_and_pinned_base(tmp_path, monkeypatch):
    repo, step = configured(tmp_path, monkeypatch)
    service = MissionCodeWorkspaceService()
    workspace = service.prepare_step(step)
    (Path(workspace['execution_repo']) / 'hello.py').write_text('new\n')
    candidate = service.candidate(workspace)
    assert (repo / 'hello.py').read_text() == 'old\n'
    assert git(repo, 'rev-parse', 'HEAD') == step['input']['base_commit']
    assert candidate['workspace_status'] == 'candidate'
    assert not candidate['integrated']
    assert candidate['commit_sha'] != candidate['base_commit']
    assert len(candidate['diff_sha256']) == 64
    with pytest.raises(Exception, match='已存在'):
        service.prepare_step(step)


def test_unknown_repo_and_changed_base_rejected(tmp_path, monkeypatch):
    repo, step = configured(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='未授权'):
        validate({**step, 'input': {**step['input'], 'repository_id': 'other'}})
    with pytest.raises(ValueError, match='基线'):
        MissionCodeWorkspaceService().prepare_step({**step, 'input': {**step['input'], 'base_commit': '0'*40}})
    normalized = normalize_plan({'steps': [step]}, 'edit code')
    assert normalized['steps'][0]['executor'] == EXECUTOR
    digest = CommandCenterService._step_contract_hash(step)
    assert digest != CommandCenterService._step_contract_hash({**step, 'input': {**step['input'], 'base_commit': '0'*40}})


def test_code_worker_persists_candidate_and_fences_workspace_receipt(tmp_path, monkeypatch):
    import asyncio
    from services import command_center_worker as worker_module
    from services.openclaw_task_executor import ExecutionResult
    from services.work_run_service import WorkRunService
    from services.command_center_service import InvalidMissionTransition
    repo, raw = configured(tmp_path, monkeypatch)
    service = CommandCenterService(str(tmp_path / 'mission.db'))
    mission = service.create_mission(objective='create code candidate', requested_by='admin', context={'business_flow_key': 'general'})
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'steps': [raw], 'risk_level': 'low'})
    service.approve(mission['id'], decided_by='admin')
    service.activate_approved_missions()
    claimed = service.claim_ready_steps('worker')[0]
    async def edit(role, prompt, *, cwd, timeout):
        assert role == 'worker'
        (Path(cwd) / 'hello.py').write_text('new code\n')
        return ExecutionResult(True, output='I also ran tests!')  # ignored as evidence
    monkeypatch.setattr(worker_module, 'execute_isolated', edit)
    worker = worker_module.CommandCenterWorker(service=service, work_runs=WorkRunService(str(tmp_path / 'runs.db')))
    asyncio.run(worker._execute_step(claimed))
    saved = service.get_mission(mission['id'])['steps'][0]
    assert saved['status'] == 'completed', saved['result']
    assert saved['result']['code_workspace']['integrated'] is False
    handoff = worker_module.CommandCenterWorker._compact_step_handoff(saved, relation='dependency')
    assert handoff['code_candidate']['commit_sha'] == saved['result']['code_workspace']['commit_sha']
    assert Path(handoff['code_candidate']['execution_repo']).is_dir()
    assert '未运行测试' in saved['result']['summary']
    assert (repo / 'hello.py').read_text() == 'old\n'
    with pytest.raises(InvalidMissionTransition):
        service.record_code_workspace(claimed['id'], claimed['lease_token'], {})
