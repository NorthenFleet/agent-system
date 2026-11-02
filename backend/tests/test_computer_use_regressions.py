"""Regression coverage for observed Computer Use failures."""
import asyncio
import hashlib
from types import SimpleNamespace
import pytest
from services.command_center_worker import CommandCenterWorker
from services.compensation_service import CompensationService
from services.plan_quality_service import PlanQualityService
from services.mission_artifact_reader import read_artifact


@pytest.mark.parametrize('output', ['not JSON', '{"steps":[]}', '{"steps":[{"title":"用户审批"}]}',
    '{"steps":[{"title":"审核","evidence_required":[{"type":"review_report"}]}]}',
    '{"steps":[{"title":"审核","output_contract":{"artifact_types":[{"type":"document"}]}}]}'])
def test_invalid_planning_never_saves_fallback(output):
    calls = []
    session_keys = []
    mission = {'id': 'test', 'objective': '只写文档', 'status': 'planning'}
    class Service:
        def claim_planning_mission(self, worker): return mission
        def get_mission(self, key): return mission
        def mark_planning_failed(self, *args, **kwargs): calls.append('blocked')
        def save_plan(self, *args, **kwargs): pytest.fail('fallback must not be saved')
    class Executor:
        async def execute(self, *args, **kwargs):
            session_keys.append(args[1]['session_key'])
            return SimpleNamespace(success=True, output=output)
    class Worker:
        worker_id = 'test'
        service = Service()
        executor = Executor()
        async def _planning_context(self, mission): return None, ''
        def _planning_prompt(self, *args): return 'prompt'
    asyncio.run(CommandCenterWorker._plan_one(Worker()))
    asyncio.run(CommandCenterWorker._plan_one(Worker()))
    assert calls == ['blocked', 'blocked']
    assert len(set(session_keys)) == 2


def test_pure_document_objective_blocks_code():
    mission = {'mission_type': 'software', 'objective': '只写文档，禁止改代码，无需联网或额外资料研究'}
    quality = PlanQualityService().enrich_plan({'steps': [
        {'title': '实施后端', 'task_type': 'backend', 'agent_id': 'raphael'}]}, mission=mission)['plan_quality']
    assert quality['flow_key'] == 'document'
    assert any('禁止代码' in b for b in quality['blockers'])


def test_unknown_effect_is_read_only_but_applied_keeps_rollback():
    step = {'idempotency_key': 'key', 'rollback_plan': '删除文件'}
    service = CompensationService()
    unknown = service.compensation_contract(step, {'status': 'unknown', 'resource': '/test'})
    applied = service.compensation_contract(step, {'status': 'applied', 'resource': '/test'})
    assert unknown['type'] == 'verify_effect'
    assert '禁止删除' in unknown['instructions']
    assert applied['instructions'] == '删除文件'
    assert unknown['contract_hash'] != applied['contract_hash']


def test_artifact_version_and_allowed_root(tmp_path, monkeypatch):
    root = tmp_path / 'delivery'; root.mkdir()
    file = root / 'brief.md'; file.write_text('交付内容')
    monkeypatch.setenv('COMMAND_CENTER_ARTIFACT_ROOTS', str(root))
    artifact = {'uri': str(file), 'content_hash': hashlib.sha256(file.read_bytes()).hexdigest()}
    assert read_artifact(artifact)[1] == file.read_bytes()
    file.write_text('已被改变')
    with pytest.raises(ValueError, match='版本'): read_artifact(artifact)
    outside = tmp_path / 'private.md'; outside.write_text('private')
    artifact = {'uri': str(outside), 'content_hash': hashlib.sha256(outside.read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match='交付目录'): read_artifact(artifact)
    link = root / 'link.md'; link.symlink_to(outside)
    with pytest.raises(ValueError, match='路径'): read_artifact({**artifact, 'uri': str(link)})


def test_step_prompt_supplies_literal_key():
    key = 'mission-test:plan:7:step:1'
    prompt = CommandCenterWorker._step_prompt({'id': 'test', 'objective': '写简报', 'steps': [], 'events': []},
        {'id': 'one', 'title': '写简报', 'agent_id': 'ultra-magnus', 'idempotency_key': key})
    assert f'"idempotency_key":"{key}"' in prompt


def test_workspace_failure_reports_existing_project(monkeypatch):
    from routers import writing_workspace as router
    projects = []
    monkeypatch.setattr(router.project_manager, 'list_projects', lambda: [])
    def create(value):
        project = {**value, 'id': 'isolated-test-project'}
        projects.append(project)
        return project
    monkeypatch.setattr(router.project_manager, 'create_project', create)
    monkeypatch.setattr(router.project_manager, 'update_project', lambda key, value: {**projects[0], **value})
    def fail(*args): raise OSError('fixture initialization failed')
    monkeypatch.setattr(router.document_workspace_service, 'initialize_project', fail)
    result = router.create_writing_project(router.WritingProjectCreate(name='fixture'), _user={'role': 'admin'})
    assert result['project']['id'] == 'isolated-test-project'
    assert result['workspace'] is None
    assert '项目已创建' in result['warning']
    assert len(projects) == 1


def test_download_requires_mission_access_before_reading(monkeypatch):
    from routers import command_center_router as router
    from services.command_center_service import MissionNotFound
    from fastapi import HTTPException
    def deny(*args, **kwargs): raise MissionNotFound('denied')
    monkeypatch.setattr(router.command_center_service, 'get_mission', deny)
    monkeypatch.setattr(router, 'read_artifact', lambda _: pytest.fail('must not read'))
    with pytest.raises(HTTPException) as exc:
        router.download_mission_artifact('other-owner', 'artifact', user={'id': 999, 'role': 'user'})
    assert exc.value.status_code == 404


def test_document_capability_accepts_named_markdown_not_arbitrary_exec():
    from services.execution_evidence_service import ExecutionEvidenceService
    proven = ExecutionEvidenceService._tool_capability_proven
    assert proven('document_workspace', {'exec'}, [{'artifact_type': 'brief.md', 'uri': '/delivery/brief.md'}], [], '')
    assert proven('document_workspace', {'exec'}, [{'artifact_type': 'review_report', 'uri': '/delivery/review.md'}], [], '')
    assert not proven('document_workspace', {'exec'}, [{'artifact_type': 'source', 'uri': '/delivery/code.py'}], [], '')


@pytest.mark.parametrize('selected_status,expected', [
    ('completed', 'completed'), ('cancelled', 'idle'),
    ('awaiting_approval', 'assigned'), ('waiting_feedback', 'blocked'),
])
def test_agent_space_does_not_claim_paused_work_is_running(tmp_path, monkeypatch, selected_status, expected):
    from services.command_center_service import CommandCenterService
    service = CommandCenterService(str(tmp_path / 'space.db'))
    items = [
        {'mission_id': 'selected', 'mission_status': selected_status, 'current_agent_id': 'optimus'},
        {'mission_id': 'paused', 'mission_status': 'waiting_feedback', 'current_agent_id': 'ratchet'},
        {'mission_id': 'approval', 'mission_status': 'awaiting_approval', 'current_agent_id': 'leonardo'},
        {'mission_id': 'running', 'mission_status': 'running', 'current_agent_id': 'raphael'},
    ]
    monkeypatch.setattr(service, 'list_missions', lambda **kw: items)
    monkeypatch.setattr(service, '_project_lookup', lambda: {})
    monkeypatch.setattr(service, '_load_task_ledger', lambda: [])
    monkeypatch.setattr(service, '_workbench_item', lambda mission, **kw: mission)
    monkeypatch.setattr(service, 'get_mission', lambda *a, **kw: {'id': 'selected', 'status': selected_status, 'steps': []})
    monkeypatch.setattr('services.command_center_service.unified_data_manager.get_agent_organization_document', lambda: {
        'nodes': [{'id': name, 'agent_id': name, 'node_type': 'agent'}
                  for name in ['optimus', 'ratchet', 'leonardo', 'raphael']],
    })
    nodes = {n['id']: n for n in service.agent_space(mission_id='selected')['nodes']}
    assert nodes['optimus']['status'] == expected
    assert nodes['ratchet']['status'] == 'blocked'
    assert nodes['leonardo']['status'] == 'assigned'
    assert nodes['raphael']['status'] == 'working'
