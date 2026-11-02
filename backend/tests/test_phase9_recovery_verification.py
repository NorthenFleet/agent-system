import pytest
from services.command_center_service import CommandCenterService, InvalidMissionTransition
from tests.test_phase8_write_recovery import prepare


def verification(tmp_path):
    service = CommandCenterService(str(tmp_path/'state.db'))
    mission = prepare(service, tmp_path/'absent.txt')
    step = service.claim_ready_steps('writer')[0]
    service.complete_step(step['id'], result={'success':False,'error':'Lost receipt'},
        success=False, actor='writer', lease_token=step['lease_token'])
    service.claim_evaluation_mission('reviewer')
    case = service.get_mission(mission['id'])['compensations'][0]
    service.decide_compensation(case['id'], expected_mission_id=mission['id'],
        contract_hash=case['contract_hash'], decision='approved', decided_by='test')
    claimed = service.claim_ready_compensation('verify')
    return service, mission, claimed


def receipt():
    return {'status':'not_needed','summary':'只读检查：目标不存在，未写入',
        'receipt_ref':'fixture:absence-check','evidence_refs':['fixture:absence-check']}


def test_verified_absence_preserved_and_replan_requires_approval(tmp_path):
    service, mission, case = verification(tmp_path)
    service.complete_compensation(case['id'], lease_token=case['lease_token'], result=receipt(), actor='verify')
    current = service.get_mission(mission['id'])
    assert current['effects'][0]['status'] == 'not_applied'
    assert current['compensations'][0]['status'] == 'completed'
    assert service.claim_ready_steps('worker') == []
    service.add_feedback(mission['id'], actor='test', content='重新制定恢复计划，等审批', replan=True)
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'summary':'恢复只读检查','steps':[{
        'title':'核实不存在', 'task_type':'coordination','agent_id':'optimus','side_effect':False,'depends_on':[]}]})
    assert service.get_mission(mission['id'])['status'] == 'awaiting_approval'
    assert service.claim_ready_steps('worker') == []


def test_expired_verification_receipt_rejected_before_requeue(tmp_path):
    service, mission, case = verification(tmp_path)
    with service.connect(immediate=True) as conn:
        conn.execute("UPDATE mission_compensations SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (case['id'],))
    with pytest.raises(InvalidMissionTransition):
        service.complete_compensation(case['id'], lease_token=case['lease_token'], result=receipt(), actor='late')
    current=service.get_mission(mission['id'])
    assert current['effects'][0]['status']=='unknown'
    assert current['compensations'][0]['status']=='running'
    assert service.requeue_stale_compensations()==1
    assert service.claim_ready_compensation('retry') is None
