"""Receipt correction never executes tools or invents a missing evidence link."""
import copy
import pytest
from services.execution_evidence_service import ExecutionEvidenceService
from services.execution_contract_ids import contract_items
from services.command_center_service import CommandCenterService
from tests.test_phase3_contracts import fixture_contract
from tests.test_execution_evidence_service import _valid_result


def inspect(step, result):
    return ExecutionEvidenceService().enrich_result(step, result, success=True,
        enforcement={'mode': 'strict', 'enforced': True})


def test_canonicalization_preserves_original_receipt_and_is_idempotent():
    step, result = fixture_contract()
    identifier = result['evidence'][0]['requirement_id']
    result['acceptance_results'][0]['evidence_refs'] = [identifier]
    original = copy.deepcopy(result)
    fixed = inspect(step, {'structured_output': result})
    assert result == original
    assert fixed['structured_output'] == original
    assert fixed['receipt_preflight']['changes'] == [
        {'acceptance_index': 0, 'from': identifier, 'to': 'run:count'}]
    assert fixed['receipt_preflight']['strict_accepted']
    assert not fixed['receipt_preflight']['execution_repeated']
    assert inspect(step, fixed)['receipt_preflight']['changes'] == []


@pytest.mark.parametrize('fault', ['unknown', 'old_id', 'explicit_failure', 'missing_source'])
def test_preflight_does_not_repair_unproven_or_failed_claims(fault):
    step, result = fixture_contract()
    if fault == 'unknown':
        result['acceptance_results'][0]['evidence_refs'] = ['exec:sha256 校验']
    elif fault == 'old_id':
        result['acceptance_results'][0]['evidence_refs'] = [result['evidence'][0]['requirement_id']]
        step['plan_version'] += 1
    elif fault == 'explicit_failure':
        result['acceptance_results'][0]['status'] = 'fail'
    else:
        result['evidence'][0]['source_ref'] = ''
    fixed = inspect(step, result)
    assert not fixed['receipt_preflight']['strict_accepted']
    assert not fixed['execution_quality']['accepted']
    assert fixed['receipt_preflight']['changes'] == []


def test_ambiguous_evidence_id_is_not_arbitrarily_rewritten():
    step, result = fixture_contract()
    result['acceptance_results'][0]['evidence_refs'] = [result['evidence'][0]['requirement_id']]
    result['evidence'].append({**result['evidence'][0], 'source_ref': 'run:other'})
    assert inspect(step, result)['receipt_preflight']['changes'] == []


@pytest.mark.parametrize('side_effect,reported_not_applied', [(False, False), (True, False), (True, True)])
def test_strict_completion_fences_retry_using_approved_contract(tmp_path, monkeypatch, side_effect, reported_not_applied):
    monkeypatch.setenv('COMMAND_CENTER_EVIDENCE_ENFORCEMENT', 'strict')
    service = CommandCenterService(str(tmp_path / 'strict.db'))
    mission = service.create_mission(objective='隔离回执验收', requested_by='admin')
    service.claim_planning_mission('planner')
    service.save_plan(mission['id'], {'summary': '隔离测试', 'steps': [{
        'order_index': 1, 'title': '核验', 'agent_id': 'optimus',
        'task_type': 'coordination', 'side_effect': side_effect,
        'max_attempts': 2, 'depends_on': []}]})
    service.approve(mission['id'], decided_by='admin')
    service.activate_approved_missions()
    step = service.claim_ready_steps('runner', limit=1)[0]
    result = _valid_result(step)
    if reported_not_applied:
        result['side_effects'] = [{'status': 'not_applied', 'resource': 'test:document',
            'action': 'write', 'idempotency_key': step['idempotency_key'],
            'receipt_ref': 'test:receipt', 'evidence_refs': ['run:test:1']}]
    result['acceptance_results'][0]['criterion_id'] = contract_items(step, 'acceptance_criteria')[0]['id']
    result['acceptance_results'][0]['evidence_refs'] = ['nonexistent:receipt']
    completed = service.complete_step(step['id'], result=result, success=True,
        actor='runner', lease_token=step['lease_token'])
    assert not completed['result']['receipt_preflight']['strict_accepted']
    assert completed['status'] == ('failed' if side_effect else 'ready')
    if side_effect:
        assert service.claim_ready_steps('replacement', limit=1) == []
        service.claim_evaluation_mission('evaluator')
        blocked = service.get_mission(mission['id'])
        assert blocked['status'] == 'waiting_feedback'
        assert '验收标准未逐项通过' in blocked['last_error']
    else:
        retry = service.claim_ready_steps('replacement', limit=1)[0]
        accepted = service.complete_step(retry['id'], result=_valid_result(retry), success=True,
            actor='replacement', lease_token=retry['lease_token'])
        assert accepted['status'] == 'completed'
        assert accepted['result']['receipt_preflight']['strict_accepted']
        evaluating = service.claim_evaluation_mission('evaluator')
        assert evaluating['id'] == mission['id']
        final = service.complete_mission(mission['id'], summary='隔离严格验收通过', success=True)
        assert final['status'] == 'completed'
