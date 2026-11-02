"""Real OpenClaw read-only execution against an isolated strict mission store.

No worker loop, sender, production database, or generated evidence is used.
Each invocation creates a new audit directory and never overwrites a run.
"""
import asyncio
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
RUN = ROOT / 'docs/review/computer-use-phase5-20261005' / ('run-' + uuid.uuid4().hex[:8])
RUN.mkdir(parents=True)
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
os.environ.pop('COMMAND_CENTER_DATABASE_URL', None)
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH = str(RUN / 'isolated.sqlite3')
from services.command_center_service import CommandCenterService
from services.execution_contract_ids import contract_items
from services.openclaw_task_executor import OpenClawTaskExecutor


def save(name, value):
    (RUN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))


async def main():
    expect_rejection = '--expect-rejection' in sys.argv
    lower, upper = (1000, 1800) if expect_rejection else (100, 180)
    source = ROOT / 'docs/review/computer-use-phase3-20261005/deliverables/H/revised.md'
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    service = CommandCenterService(str(RUN / 'isolated.sqlite3'))
    mission = service.create_mission(objective='P5 真实执行器只读严格验收', requested_by='phase5-test')
    service.claim_planning_mission('phase5-test')
    service.save_plan(mission['id'], {'summary': '只读核验既有修订稿', 'steps': [{
        'order_index': 1, 'title': '读取并核验既有修订稿', 'agent_id': 'ratchet',
        'task_type': 'coordination', 'side_effect': False, 'max_attempts': 1,
        'depends_on': [], 'required_tools': ['test_runner'],
        'deliverables': ['既有修订稿及只读核验回执'],
        'evidence_required': ['test_output'],
        'acceptance_criteria': [f'三个小节齐全，汉字数在{lower}至{upper}之间，且返回实际文件SHA-256'],
        'output_contract': {'artifact_types': ['document'],
                            'required_fields': ['summary', 'evidence_refs', 'risk_notes']},
    }]})
    service.approve(mission['id'], decided_by='phase5-test')
    service.activate_approved_missions()
    step = service.claim_ready_steps('phase5-real-executor', limit=1, lease_seconds=600)[0]
    save('contract.json', step)
    prompt = f'''这是已批准的隔离只读验收任务。只允许读取这个文件：{source}
必须实际调用 exec 使用 Python 读取 UTF-8，按 [\\u4e00-\\u9fff] 统计汉字，计算 SHA-256，检查目标、风险与应对、验收三小节。
禁止写文件、修改文件、联网搜索、发送消息或通知、创建其他任务。不要使用任何发送工具。
返回已有文件作为 document artifact；不创建新文件。不得使用旧会话结果或猜测统计数据。
严格按照以下当前合同返回 JSON，不要其他文字：
evidence_items={json.dumps(contract_items(step, 'evidence_required'), ensure_ascii=False)}
acceptance_items={json.dumps(contract_items(step, 'acceptance_criteria'), ensure_ascii=False)}
{{"outcome":"succeeded 或 blocked","summary":"实际核验结果", "tools_used":["exec"],
"artifacts":[{{"artifact_key":"a1","artifact_type":"document","title":"既有修订稿","uri":"{source}","content_hash":"实际SHA-256"}}],
"evidence":[{{"requirement_id":"复制 evidence_items.id","evidence_type":"test_output","source_ref":"exec:phase5-readonly-check","summary":"实际字数、三节核验结果、SHA-256","artifact_key":"a1"}}],
"acceptance_results":[{{"criterion_id":"复制 acceptance_items.id","criterion":"复制验收原文","status":"pass 或 fail","evidence_refs":["exec:phase5-readonly-check"]}}],
"side_effects":[],"risk_notes":"本次只读核验的范围限制"}}
提交前检查每条 evidence_refs 都在本次 evidence 中存在。缺证据则 blocked，不得补造。'''
    (RUN / 'prompt.txt').write_text(prompt)
    print(f'RUN_DIR={RUN}', flush=True)
    session_key = 'phase5-strict-' + uuid.uuid4().hex
    save('invocation.json', {'session_key': session_key, 'agent_id': 'ratchet',
        'expected_status': 'waiting_feedback' if expect_rejection else 'completed'})
    result = await OpenClawTaskExecutor().execute('agent_run', {
        'agent_id': 'ratchet', 'message': prompt,
        'session_key': session_key}, timeout_seconds=300)
    save('executor-result.json', result.to_dict())
    completed = service.complete_step(step['id'], result=result.to_dict(), success=result.success,
        actor='ratchet', lease_token=step['lease_token'])
    save('completed-step.json', completed)
    evaluation = service.claim_evaluation_mission('phase5-test')
    if evaluation:
        service.complete_mission(mission['id'], summary='真实执行器回执通过隔离 strict 门禁', success=True)
    final = service.get_mission(mission['id'])
    save('final-mission.json', final)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    with service.connect() as conn:
        remaining = conn.execute("SELECT COUNT(*) AS n FROM mission_steps WHERE status IN ('ready','running')").fetchone()['n']
    summary = {'mission_id': mission['id'], 'executor_success': result.success,
        'step_status': completed['status'], 'mission_status': final['status'],
        'preflight': completed['result'].get('receipt_preflight'),
        'source_sha256_before': before, 'source_sha256_after': after,
        'source_unchanged': before == after, 'database': str(RUN / 'isolated.sqlite3'),
        'notification_sender_started': False,
        'expected_mission_status': 'waiting_feedback' if expect_rejection else 'completed',
        'reported_business_outcome': completed['result'].get('outcome'),
        'remaining_dispatches': remaining}
    save('summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    expected = 'waiting_feedback' if expect_rejection else 'completed'
    if final['status'] != expected or not result.success or before != after:
        raise SystemExit(1)
    if expect_rejection and not any(item['status'] == 'fail'
            for item in completed['result'].get('acceptance_results', [])):
        raise SystemExit('Negative probe did not return the expected explicit acceptance failure')


if __name__ == '__main__':
    asyncio.run(main())
