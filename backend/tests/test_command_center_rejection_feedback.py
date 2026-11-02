"""Rejected plan comments must reach both retrieval and the replanning model."""
import asyncio
from services.command_center_worker import CommandCenterWorker


def test_rejection_comment_reaches_planning_prompt_and_context():
    mission = {'id': 'mission-pilot', 'objective': '编写测试大纲', 'plan_version': 1,
               'project_id': 'pilot', 'context': {'business_flow_key': 'document'},
               'events': [{'event_type': 'plan_rejected', 'detail': '修订后由独立审核者再次复核'},
                          {'event_type': 'feedback_received', 'detail': '测试实际结果必须为未执行'}]}
    prompt = CommandCenterWorker._planning_prompt(mission)
    assert '修订后由独立审核者再次复核' in prompt
    assert '测试实际结果必须为未执行' in prompt
    captured = {}
    class ContextProbe:
        async def _ensure_context_pack(self, mission, **kwargs):
            captured.update(kwargs)
            return None, ''
    asyncio.run(CommandCenterWorker._planning_context(ContextProbe(), mission))
    assert '修订后由独立审核者再次复核' in captured['query']
    assert captured['plan_version'] == 2


def test_document_fallback_never_adds_software_implementation_steps():
    from services.command_center_worker import normalize_plan
    for parsed in (None, {'steps': []}, {'steps': [{'title': '用户审批'}]}):
        plan = normalize_plan(parsed, '为软件系统代码接口编写测试大纲，禁止改代码', flow_key='document')
        types = {step['task_type'] for step in plan['steps']}
        assert 'writing' in types and 'review' in types
        assert not types.intersection({'frontend', 'backend', 'api', 'database'})


def test_recovery_feedback_reaches_step_prompt_and_retrieval():
    mission = {'id': 'mission-recovery', 'objective': '编写大纲', 'plan_version': 4,
               'steps': [], 'events': [{'event_type': 'feedback_received', 'detail': '保留已有文件，仅补齐交付证据'}]}
    step = {'id': 'step-1', 'title': '梳理', 'agent_id': 'michelangelo', 'task_type': 'research'}
    prompt = CommandCenterWorker._step_prompt(mission, step)
    assert '保留已有文件，仅补齐交付证据' in prompt
    assert '不构成扩大权限' in prompt
    captured = {}
    class ContextProbe:
        async def _ensure_context_pack(self, mission, **kwargs):
            captured.update(kwargs)
            return None, ''
    asyncio.run(CommandCenterWorker._execution_context(ContextProbe(), mission, step))
    assert '保留已有文件，仅补齐交付证据' in captured['query']
