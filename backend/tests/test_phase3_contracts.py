import copy
import pytest
from services.execution_contract_ids import contract_items
from services.execution_evidence_service import ExecutionEvidenceService
from services.command_center_worker import CommandCenterWorker


def fixture_contract():
    step = {'id': 'step-1', 'plan_version': 2, 'idempotency_key': 'mission:plan:2:step:1',
            'evidence_required': ['汉字统计过程与结果'], 'acceptance_criteria': ['正文包含三节并在字数范围内']}
    result = {'outcome': 'succeeded', 'summary': '独立核验通过',
              'evidence': [{'requirement_id': contract_items(step, 'evidence_required')[0]['id'],
                            'evidence_type': 'test_output', 'source_ref': 'run:count', 'summary': '实际统计166汉字'}],
              'acceptance_results': [{'criterion_id': contract_items(step, 'acceptance_criteria')[0]['id'],
                                      'criterion': '结构及字数均合格', 'status': 'pass', 'evidence_refs': ['run:count']}]}
    return step, result


def quality(step, result):
    return ExecutionEvidenceService().enrich_result(step, result, success=True,
        enforcement={'mode': 'strict', 'enforced': True})['execution_quality']


def test_ids_accept_rewording_with_real_references_and_are_in_prompt():
    step, result = fixture_contract()
    assert quality(step, result)['accepted']
    prompt = CommandCenterWorker._step_prompt({'id': 'mission', 'objective': '文档核验'}, {**step, 'title': '核验'})
    assert result['evidence'][0]['requirement_id'] in prompt
    assert result['acceptance_results'][0]['criterion_id'] in prompt


def test_acceptance_can_resolve_a_current_evidence_id_but_not_an_unbound_id():
    step, result = fixture_contract()
    result['acceptance_results'][0]['evidence_refs'] = [result['evidence'][0]['requirement_id']]
    assert quality(step, result)['accepted']
    result['evidence'][0]['requirement_id'] = 'ev-forged'
    result['acceptance_results'][0]['evidence_refs'] = ['ev-forged']
    assert not quality(step, result)['accepted']


@pytest.mark.parametrize('fault', ['old_plan', 'missing_source', 'unknown_ref', 'wrong_id', 'explicit_fail'])
def test_ids_do_not_weaken_strict_gate(fault):
    step, result = fixture_contract()
    if fault == 'old_plan': step['plan_version'] = 3
    if fault == 'missing_source': result['evidence'][0]['source_ref'] = ''
    if fault == 'unknown_ref': result['acceptance_results'][0]['evidence_refs'] = ['unrelated:ref']
    if fault == 'wrong_id': result['acceptance_results'][0]['criterion_id'] = 'ac-made-up'
    if fault == 'explicit_fail': result['acceptance_results'][0]['status'] = 'fail'
    assert not quality(step, result)['accepted']


def test_same_source_can_prove_two_distinct_contract_items():
    step, result = fixture_contract()
    step['evidence_required'].append('字数统计方法')
    extra = copy.deepcopy(result['evidence'][0])
    extra['requirement_id'] = contract_items(step, 'evidence_required')[1]['id']
    result['evidence'].append(extra)
    assert quality(step, result)['accepted']


def test_explicit_read_only_contract_can_deliver_evidence_without_a_file():
    from services.business_flow_service import BusinessFlowRegistry
    step = {'title': '审核', 'side_effect': False, 'deliverables': ['结构化审核证据'],
            'output_contract': {'artifact_types': []}}
    assert BusinessFlowRegistry._output_contract(step)['artifact_types'] == []
    assert BusinessFlowRegistry._output_contract({**step, 'side_effect': True})['artifact_types']


@pytest.mark.parametrize('side_effect', [False, True])
def test_rejected_review_replans_without_erasing_failure_or_reusing_approval(tmp_path, side_effect):
    from services.command_center_service import CommandCenterService
    service = CommandCenterService(str(tmp_path / 'revision.db'))
    mission = service.create_mission(objective='核验并修订测试文档', requested_by='admin')
    service.claim_planning_mission('planner')
    plan = {'summary': '只读复核', 'steps': [{'order_index': 1, 'title': '独立复核',
        'agent_id': 'optimus', 'task_type': 'coordination', 'side_effect': side_effect,
        'max_attempts': 1, 'depends_on': []}]}
    service.save_plan(mission['id'], plan)
    service.approve(mission['id'], decided_by='admin')
    service.activate_approved_missions()
    step = service.claim_ready_steps('reviewer', limit=1)[0]
    service.complete_step(step['id'], result={'outcome': 'blocked', 'summary': '缺少风险段落'},
        success=False, actor='reviewer', lease_token=step['lease_token'])
    service.claim_evaluation_mission('evaluator')
    assert service.get_mission(mission['id'])['status'] == 'waiting_feedback'
    resumed = service.add_feedback(mission['id'], actor='admin', content='补充风险段落后再次独立审核', replan=True)
    if side_effect:
        assert resumed['status'] == 'waiting_feedback'
        assert resumed['compensations']
        assert service.claim_ready_steps('runner', limit=1) == []
        return
    assert resumed['status'] == 'planning'
    with service.connect() as conn:
        old = conn.execute('SELECT status,result_json FROM mission_steps WHERE id=?', (step['id'],)).fetchone()
    assert old['status'] == 'failed'
    assert '缺少风险段落' in old['result_json']
    service.claim_planning_mission('planner')
    revised = service.save_plan(mission['id'], plan)
    assert revised['plan_version'] == 2
    assert revised['status'] == 'awaiting_approval'
    assert service.claim_ready_steps('runner', limit=1) == []
