"""A handoff summary or unfinished tool call is not a successful deliverable."""
import pytest
from services.execution_evidence_service import ExecutionEvidenceService


@pytest.mark.parametrize('output', [
    '<analysis>files prepared</analysis><summary>Continue by submitting the final result</summary>',
    '<parameter=command>echo done</parameter>',
    'echo done\n</parameter>\n<parameter=timeoutSeconds>30</parameter>',
])
def test_non_final_protocol_output_blocks_even_without_negative_keywords(output):
    service = ExecutionEvidenceService()
    result = service.normalize_result({'success': True, 'output': output})
    assert result['outcome'] == 'failed'
    assert result['protocol_error']
    gate = service.evaluate({}, result, success=True, enforcement={'mode': 'shadow', 'enforced': False})
    assert not gate['accepted']
    assert any('结构化交付结果' in issue for issue in gate['hard_blockers'])


def test_valid_structured_result_can_discuss_protocol_tags():
    service = ExecutionEvidenceService()
    result = service.normalize_result({'success': True, 'output':
        '{"outcome":"succeeded","summary":"验证<summary>样本完成","artifacts":[],"evidence":[]}'})
    assert result['outcome'] == 'succeeded'
    assert not result.get('protocol_error')
