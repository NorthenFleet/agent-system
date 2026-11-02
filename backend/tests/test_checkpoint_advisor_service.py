import asyncio
import json

import pytest

from services import checkpoint_advisor_service as advisor
from services.command_center_worker import CommandCenterWorker
from services.command_center_service import CommandCenterService
from services.openclaw_task_executor import ExecutionResult
from tests.test_execution_evidence_service import _single_step_plan


def mission_setup(tmp_path):
    service = CommandCenterService(str(tmp_path / 'advisor.db'))
    mission = service.create_mission(objective='review task', requested_by='admin', context={'business_flow_key': 'general'})
    service.claim_planning_mission('planner')
    mission = service.save_plan(mission['id'], _single_step_plan())
    return service, mission


def test_advisor_runs_once_and_cannot_approve(tmp_path, monkeypatch):
    service, mission = mission_setup(tmp_path)
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_ENABLED', 'true')
    calls = []
    async def fake(data):
        calls.append(data)
        return {'status': 'completed', 'advisory_only': True, 'verdict': 'pass', 'findings': [], 'suggested_action': 'review evidence'}
    monkeypatch.setattr(advisor, 'review', fake)
    async def scenario():
        worker = CommandCenterWorker(service=service)
        await asyncio.gather(worker._advise(mission, 'plan'), worker._advise(mission, 'plan'))
        await CommandCenterWorker(service=CommandCenterService(service.repository.db_path))._advise(mission, 'plan')
    asyncio.run(scenario())
    assert len(calls) == 1
    saved = service.get_mission(mission['id'])
    assert saved['status'] == mission['status']
    assert saved['approval']['decision'] == 'pending'
    assert len(saved['advisor_reviews']) == 1


def test_cancelled_result_discarded_and_missing_request_rejected(tmp_path):
    service, mission = mission_setup(tmp_path)
    assert not service.complete_advisor_checkpoint(mission['id'], 1, 'plan', {'status': 'completed'})
    assert service.claim_advisor_checkpoint(mission['id'], 1, 'plan', 'hash')
    service.cancel(mission['id'], actor='admin')
    assert service.complete_advisor_checkpoint(mission['id'], 1, 'plan', {'status': 'completed', 'verdict': 'pass'})
    assert service.get_mission(mission['id'])['advisor_reviews'][0]['status'] == 'discarded'
    assert not service.complete_advisor_checkpoint(mission['id'], 1, 'plan', {'status': 'completed'})


def test_unavailable_advisor_is_visible_and_does_not_block(tmp_path, monkeypatch):
    service, mission = mission_setup(tmp_path)
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_ENABLED', 'true')
    async def fail(_data):
        raise ValueError('no model')
    monkeypatch.setattr(advisor, 'review', fail)
    asyncio.run(CommandCenterWorker(service=service)._advise(mission, 'plan'))
    saved = service.get_mission(mission['id'])
    assert saved['advisor_reviews'][0]['status'] == 'unavailable'
    assert saved['status'] == mission['status']


def test_advisor_rejects_invented_evidence(monkeypatch):
    data = {'mission_id': 'm', 'plan_version': 1, 'steps': [{'id': 's', 'evidence_refs': ['e']} ]}
    async def execute(*args, **kwargs):
        return ExecutionResult(True, output=json.dumps({'verdict': 'concerns', 'findings': [{'message': 'test', 'evidence_refs': ['invented']}], 'suggested_action': 'fix'}))
    monkeypatch.setattr(advisor, 'execute_isolated', execute)
    with pytest.raises(ValueError, match='invented'):
        asyncio.run(advisor.review(data))


def test_disabled_advisor_never_called(tmp_path, monkeypatch):
    service, mission = mission_setup(tmp_path)
    monkeypatch.setenv('COMMAND_CENTER_ADVISOR_ENABLED', 'false')
    asyncio.run(CommandCenterWorker(service=service)._advise(mission, 'plan'))
    assert not service.get_mission(mission['id'])['advisor_reviews']


def test_new_plan_discards_old_advice_and_exposes_only_current(tmp_path):
    service, mission = mission_setup(tmp_path)
    assert service.claim_advisor_checkpoint(mission['id'], 1, 'plan', 'old')
    service.reject(mission['id'], decided_by='admin', comment='revise')
    service.claim_planning_mission('planner')
    revised = service.save_plan(mission['id'], _single_step_plan())
    assert revised['plan_version'] == 2
    service.complete_advisor_checkpoint(mission['id'], 1, 'plan', {'status': 'completed'})
    assert service.get_mission(mission['id'])['advisor_reviews'] == []
    assert service.claim_advisor_checkpoint(mission['id'], 2, 'plan', 'new')
