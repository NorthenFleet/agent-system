"""Planning must expose the snapshot being used before the next plan is saved."""
from services.command_center_service import CommandCenterService


def test_planning_context_visible_before_plan_and_after_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(CommandCenterService, '_sync_mission_ledger_safe', lambda *args: None)
    service = CommandCenterService(str(tmp_path / 'planning.db'), project_provider=lambda: [])
    mission = service.create_mission(objective='编写测试大纲', requested_by='pilot')
    mission_id = mission['id']
    service.claim_planning_mission('planner')
    service.bind_context_pack(mission_id, plan_version=1, purpose='planning', agent_id='optimus',
                              pack={'id': 'context-v1', 'status': 'ready'})
    planning = service.get_mission(mission_id)
    assert planning['plan_version'] == 0
    assert planning['planning_context']['context_pack_id'] == 'context-v1'
    assert planning['planning_context']['plan_version'] == 1
    plan = {'summary': '编写与审核', 'risk_level': 'low', 'steps': [
        {'order_index': 1, 'title': '编写', 'description': '编写文档', 'task_type': 'writing',
         'agent_id': 'ultra-magnus', 'depends_on': []},
        {'order_index': 2, 'title': '审核', 'description': '独立审核', 'task_type': 'review',
         'agent_id': 'ratchet', 'depends_on': [1]}]}
    saved = service.save_plan(mission_id, plan)
    assert saved['planning_context']['context_pack_id'] == 'context-v1'
    service.reject(mission_id, decided_by='pilot', comment='补齐验收')
    service.claim_planning_mission('planner')
    service.bind_context_pack(mission_id, plan_version=2, purpose='planning', agent_id='optimus',
                              pack={'id': 'context-v2', 'status': 'ready'})
    replanning = service.get_mission(mission_id)
    assert replanning['plan_version'] == 1
    assert replanning['planning_context']['context_pack_id'] == 'context-v2'
    assert replanning['planning_context']['plan_version'] == 2
    saved_again = service.save_plan(mission_id, plan)
    assert saved_again['planning_context']['context_pack_id'] == 'context-v2'
    assert all(binding['plan_version'] == 2 for binding in saved_again['context_bindings'])
