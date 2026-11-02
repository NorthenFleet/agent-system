"""Regression coverage for project context and mixed project/workflow types."""
from services.context_retrieval_service import ContextRetrievalService
from services.plan_quality_service import PlanQualityService


def test_explicit_project_requirements_survive_large_design_without_unrelated_settings():
    rendered = ContextRetrievalService._project_content({
        'name': '试点', 'design_doc': {'content': 'x' * 10000},
        'context': {'goal': '验证闭环', 'scope': '只编写文档',
                    'acceptance_marker': 'WF-PILOT-CONTEXT-20261002',
                    'minimum_acceptance': ['实际文件可打开'],
                    'integration_token': 'must-not-be-projected'}})
    assert 'WF-PILOT-CONTEXT-20261002' in rendered
    assert '实际文件可打开' in rendered
    assert 'must-not-be-projected' not in rendered
    assert len(rendered) <= 6000


def test_document_flow_in_software_project_does_not_require_code_implementation():
    mission = {'mission_type': 'software', 'objective': '为代码接口编写测试文档',
               'context': {'business_flow_key': 'document'}}
    steps = [{'order_index': n, 'title': t, 'task_type': t, 'agent_id': a,
              'depends_on': [] if n == 1 else [n-1]}
             for n, t, a in [(1, 'research', 'perceptor'), (2, 'writing', 'ultra-magnus'), (3, 'review', 'ratchet')]]
    quality = PlanQualityService().enrich_plan({'steps': steps}, mission=mission)['plan_quality']
    assert quality['flow_key'] == 'document'
    assert not any('软件任务' in warning for warning in quality['warnings'])
    assert not any('文档任务' in warning for warning in quality['warnings'])


def test_software_flow_still_requires_architecture_and_testing():
    quality = PlanQualityService().enrich_plan({'steps': [
        {'order_index': 1, 'title': '撰写说明', 'task_type': 'writing', 'agent_id': 'ultra-magnus'}]},
        mission={'mission_type': 'software', 'objective': '开发功能'})['plan_quality']
    assert any('软件任务必须' in warning for warning in quality['warnings'])
