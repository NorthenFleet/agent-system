import pytest
from services.command_center_service import CommandCenterError, InvalidMissionTransition
from tests.test_phase9_recovery_verification import verification


def failed_verification(tmp_path):
    service, mission, claimed = verification(tmp_path)
    service.complete_compensation(claimed['id'],lease_token=claimed['lease_token'],result={
        'status':'failed','summary':'文件已经改变，需要明确恢复方案',
        'receipt_ref':'fixture:verification','evidence_refs':['fixture:verification']},actor='verifier')
    return service, mission, claimed


def test_new_recovery_contract_requires_fresh_approval_preserves_evidence(tmp_path,monkeypatch):
    service, mission, old = failed_verification(tmp_path)
    proposal=service.propose_compensation_recovery(old['id'],expected_mission_id=mission['id'],
        contract_hash=old['contract_hash'],instructions='校验前置状态，再从备份恢复并核验内容',actor='admin')
    current=proposal['compensation']
    assert current['status']=='pending_approval'
    assert current['resource']==old['resource']
    assert current['contract_hash']!=old['contract_hash']
    assert current['idempotency_key']!=old['idempotency_key']
    assert current['authorization_expires_at'] is None
    assert current['approved_by'] is None
    assert current['result']['receipt_ref']=='fixture:verification'
    assert service.claim_ready_compensation('worker') is None
    assert service.claim_ready_steps('worker')==[]
    with pytest.raises(InvalidMissionTransition):
        service.decide_compensation(old['id'],expected_mission_id=mission['id'],contract_hash=old['contract_hash'],decision='approved',decided_by='admin')
    with pytest.raises(InvalidMissionTransition):
        service.complete_compensation(old['id'],lease_token=old['lease_token'],result={'status':'reverted'},actor='late')
    service.decide_compensation(current['id'],expected_mission_id=mission['id'],contract_hash=current['contract_hash'],decision='approved',decided_by='admin')
    claim=service.claim_ready_compensation('worker')
    assert claim['instructions']==current['instructions']
    assert service.claim_ready_compensation('other') is None
    from tests.test_phase13_recovery_receipts import local_receipt
    monkeypatch.setenv('COMMAND_CENTER_ARTIFACT_ROOTS',str(tmp_path))
    _,_,recovery_result=local_receipt(claim,tmp_path)
    service.complete_compensation(claim['id'],lease_token=claim['lease_token'],result=recovery_result,actor='worker')
    final=service.get_mission(mission['id'])
    assert final['compensations'][0]['status']=='completed'
    assert final['effects'][0]['status']=='reverted'
    event=next(e for e in final['events'] if e['event_type']=='recovery_plan_proposed')
    assert 'fixture:verification' in str(event)
    assert service.claim_ready_steps('worker')==[]


@pytest.mark.parametrize('fault',['mission','hash','empty','missing_evidence','active'])
def test_recovery_proposal_fails_closed(tmp_path,fault):
    service, mission, old=failed_verification(tmp_path)
    if fault in {'missing_evidence','active'}:
        with service.connect(immediate=True) as conn:
            if fault=='missing_evidence': conn.execute("UPDATE mission_compensations SET result_json='{}' WHERE id=?",(old['id'],))
            else: conn.execute("UPDATE mission_compensations SET status='running' WHERE id=?",(old['id'],))
    with pytest.raises(CommandCenterError):
        service.propose_compensation_recovery(old['id'],expected_mission_id='wrong' if fault=='mission' else mission['id'],
            contract_hash='0'*64 if fault=='hash' else old['contract_hash'],instructions=' ' if fault=='empty' else '恢复原资源',actor='admin')
    assert service.get_mission(mission['id'])['compensations'][0]['contract_hash']==old['contract_hash']


def test_recovery_endpoint_requires_admin_and_current_contract(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import command_center_router as api
    service, mission, old=failed_verification(tmp_path)
    monkeypatch.setattr(api,'command_center_service',service)
    app=FastAPI();app.include_router(api.router)
    identity={'id':1,'username':'tester','role':'user'}
    app.dependency_overrides[api.get_current_user]=lambda:identity
    client=TestClient(app)
    url=f"/api/v3/command-center/missions/{mission['id']}/compensations/{old['id']}/recovery-plan"
    body={'contract_hash':old['contract_hash'],'instructions':'恢复指定资源并核验'}
    assert client.post(url,json=body).status_code==403
    assert service.get_mission(mission['id'])['compensations'][0]['status']=='failed'
    identity['role']='admin'
    assert client.post(url,json={**body,'contract_hash':'0'*64}).status_code==409
    assert client.post(url,json=body).status_code==200
    assert service.claim_ready_compensation('worker') is None
