"""Local-only production frontend over isolated PostgreSQL service adapters.

Plans and the local test identity are fixtures; execution uses real OpenClaw.
No production app startup, sender, scheduler, or external message routes.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
LAB = ROOT / 'docs/review/computer-use-phase6-20261005'
LAB.mkdir(exist_ok=True)
URL = 'postgresql+psycopg2:///agent_system_cu_phase6_20261005'
os.environ['COMMAND_CENTER_DATABASE_URL'] = URL
os.environ['COMMAND_CENTER_EVIDENCE_ENFORCEMENT'] = 'strict'
import unified_data_manager
unified_data_manager.UNIFIED_DB_PATH = str(LAB / 'auxiliary.sqlite3')
from services.command_center_service import CommandCenterService, CommandCenterError
from repositories.command_center_repository import PostgresCommandCenterRepository
from services.execution_contract_ids import contract_items
from services.openclaw_task_executor import OpenClawTaskExecutor
from services.work_run_service import WorkRunService
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from services.mission_artifact_reader import read_artifact
import uvicorn

service = CommandCenterService(repository=PostgresCommandCenterRepository(URL), project_provider=lambda: [])
SOURCE = ROOT / 'docs/review/computer-use-phase3-20261005/deliverables/H/revised.md'
user = {'id': 1, 'username': 'phase6-lab', 'display_name': '隔离严格验收',
        'role': 'admin', 'is_active': True, 'module_keys': [], 'modules': []}
memory = {'pending_review': 0, 'approved': 0, 'rejected': 0, 'total': 0}


def plan(lower=1000, upper=1800):
    return {'summary': f'隔离预置计划：只读核验字数 {lower}–{upper}，不修改文件、不外发', 'steps': [{
        'order_index': 1, 'title': f'核验修订稿：{lower}–{upper} 汉字', 'agent_id': 'ratchet',
        'task_type': 'coordination', 'side_effect': False, 'max_attempts': 1,
        'depends_on': [], 'required_tools': ['test_runner'],
        'deliverables': ['既有修订稿与只读核验结果'], 'evidence_required': ['test_output'],
        'acceptance_criteria': [f'三个小节齐全，汉字数在{lower}至{upper}之间，且返回实际SHA-256'],
        'output_contract': {'artifact_types': ['document'],
                            'required_fields': ['summary', 'evidence_refs', 'risk_notes']}}]}


existing = [m for m in service.list_missions(limit=100) if m['title'] == 'P6 隔离界面：严格拒绝与恢复']
if existing:
    mission_id = existing[0]['id']
else:
    mission = service.create_mission(title='P6 隔离界面：严格拒绝与恢复',
        objective='只读核验既有修订稿；先验证不满足字数要求时拒绝，再按界面反馈重规划并审批恢复。',
        requested_by='phase6-lab')
    mission_id = mission['id']
    service.claim_planning_mission('phase6-plan-fixture')
    service.save_plan(mission_id, plan())
(LAB / 'ui-mission.json').write_text(json.dumps({'mission_id': mission_id, 'database': URL}))


async def execute_approved():
    service.activate_approved_missions()
    steps = service.claim_ready_steps('phase6-ui-executor', limit=1, lease_seconds=600)
    if not steps:
        return
    step = steps[0]
    if step['mission_id'] != mission_id:
        raise RuntimeError('Lab must not dispatch unrelated tasks')
    audit = LAB / f"ui-v{step['plan_version']}"
    audit.mkdir(exist_ok=True)
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    prompt = f'''已批准的隔离只读任务。只允许 exec 用Python读取 {SOURCE}，按 [\\u4e00-\\u9fff] 统计汉字，检查目标/风险与应对/验收三节，计算SHA-256。
禁止写文件、修改或删除、联网搜索、发送消息、创建其他任务。以下合同必须逐项核验：
{json.dumps({'evidence_items':contract_items(step,'evidence_required'),'acceptance_items':contract_items(step,'acceptance_criteria')},ensure_ascii=False)}
只返回结构化 JSON：outcome(succeeded/blocked)、summary、tools_used、artifacts、evidence、acceptance_results、side_effects、risk_notes。
tools_used必须填写实际调用的原生工具名 ["exec"]，不能填写 source_ref 的 exec:p6-readonly。
risk_notes 是必需的非空字符串：说明本次只读核验的范围限制；不能省略、填空字符串、null或空数组。
artifacts仅引用已有文件：artifact_key=a1, artifact_type=document, title=既有修订稿, uri=实际路径, content_hash=实际SHA-256。
evidence包含 requirement_id(原样复制合同ID), evidence_type=test_output, source_ref=exec:p6-readonly, summary=实际字数、章节和SHA-256, artifact_key=a1。
acceptance_results包含 criterion_id(原样复制合同ID), criterion(合同原文), status(pass/fail), evidence_refs=[exec:p6-readonly]。
side_effects=[]。不得猜测或补造证据，所有引用必须在本次evidence中存在。
outcome必须表达业务验收结论：任何验收项fail时必须blocked，不能把完成检查本身当作通过。'''
    session = 'phase6-ui-' + uuid.uuid4().hex
    (audit / 'invocation.json').write_text(json.dumps({'session_key': session, 'contract': step, 'prompt': prompt}, ensure_ascii=False, indent=2))
    result = await OpenClawTaskExecutor().execute('agent_run', {'agent_id': 'ratchet',
        'message': prompt, 'session_key': session}, timeout_seconds=300)
    (audit / 'raw-result.json').write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    completed = service.complete_step(step['id'], result=result.to_dict(), success=result.success,
        actor='ratchet', lease_token=step['lease_token'])
    evaluation = service.claim_evaluation_mission('phase6-evaluator')
    if evaluation:
        service.complete_mission(mission_id, summary='真实核验通过隔离 strict 门禁', success=True)
    (audit / 'result.json').write_text(json.dumps({'step': completed,
        'mission': service.get_mission(mission_id), 'before_sha256': before,
        'after_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest()}, ensure_ascii=False, indent=2))


app = FastAPI()


@app.exception_handler(CommandCenterError)
async def service_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.get('/api/v2/auth/settings')
def settings(): return {'login_enabled': False, 'mode': 'development'}


@app.post('/api/v2/auth/development-session')
def identity(): return {'access_token': 'isolated-lab-only', 'token_type': 'bearer', 'expires_in': 3600, 'user': user}


@app.get('/api/v2/auth/me')
def me(): return user


@app.get('/api/v3/projects')
def projects(): return {'projects': [], 'total': 0}


@app.get('/api/v3/command-center/summary')
def summary(): return {**service.summary(), 'memory_candidates': memory}


@app.get('/api/v3/command-center/production-health')
def health():
    return {'status': 'degraded', 'storage': service.storage_info(),
        'storage_runtime': service.storage_runtime_metrics(),
        'work_runs': WorkRunService(repository=service.repository).operational_metrics(),
        'workflow_runtime': service.workflow_runtime_status(),
        'workers': service.worker_runtime_status()}


@app.get('/api/v3/command-center/memory-candidates')
def candidates(): return {'candidates': [], 'summary': memory, 'can_review': False}


@app.get('/api/v3/command-center/messages')
def messages(): return {'messages': [], 'total': 0}


@app.get('/api/v3/command-center/task-workbench')
def workbench(request: Request):
    args = {k: v for k, v in request.query_params.items() if k in {'status','mission_type','project_id','agent_id','source','search'}}
    return service.list_task_workbench(**args, limit=150)


@app.get('/api/v3/command-center/space')
def space(mission_id: str = ''): return service.agent_space(mission_id=mission_id)


@app.get('/api/v3/command-center/missions')
def missions(status: str = ''):
    rows = service.list_missions(status=status, limit=100)
    return {'missions': rows, 'total': len(rows)}


@app.get('/api/v3/command-center/missions/{mid}')
def detail(mid: str): return service.get_mission(mid)


@app.get('/api/v3/command-center/missions/{mid}/artifacts/{aid}/download')
def download(mid: str, aid: str):
    entries = service.get_delivery_evidence(mid)['artifacts']
    artifact = next((a for a in entries if a['id'] == aid), None)
    if not artifact or Path(artifact['uri']).resolve() != SOURCE.resolve(): raise HTTPException(404)
    name, data = read_artifact(artifact)
    return Response(data, media_type='text/markdown', headers={'Content-Disposition': 'attachment; filename="revised.md"'})


@app.post('/api/v3/command-center/missions/{mid}/{action}')
async def action(mid: str, action: str, request: Request, background: BackgroundTasks):
    if mid != mission_id: raise HTTPException(403, 'Only the isolated UI fixture is editable')
    body = await request.json()
    if action == 'approve':
        result = service.approve(mid, decided_by='phase6-browser', comment=body.get('comment',''))
        background.add_task(execute_approved)
        return result
    if action == 'feedback':
        result = service.add_feedback(mid, actor='phase6-browser', content=body['content'], replan=body.get('replan',False))
        if result['status'] == 'planning':
            service.claim_planning_mission('phase6-plan-fixture')
            service.save_plan(mid, plan(100,180))
        return result
    if action == 'reject': return service.reject(mid, decided_by='phase6-browser', comment=body.get('comment',''))
    if action == 'cancel': return service.cancel(mid, actor='phase6-browser', comment=body.get('comment',''))
    raise HTTPException(404)


@app.get('/{path:path}')
def static(path: str):
    if path.startswith('api/'): raise HTTPException(404, 'Outside isolated test scope')
    dist = ROOT / 'frontend-v2/dist'
    target = (dist / path).resolve()
    if target.is_relative_to(dist) and target.is_file(): return FileResponse(target)
    html = (dist / 'index.html').read_text().replace('<body>', '<body><div style="background:#663c00;color:white;padding:8px;text-align:center">隔离 STRICT 验收 · 独立 PostgreSQL · 预置计划 · 真实执行器 · 不外发通知</div>')
    return HTMLResponse(html)


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=3036)
