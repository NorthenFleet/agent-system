import hashlib,json
from pathlib import Path
import pytest
from tests.test_phase10_recovery_proposal import failed_verification


def local_receipt(case, directory):
    resource=Path(case['resource']);resource.write_text('restored\n')
    path=directory/'receipt.json'
    body={'contract_hash':case['contract_hash'],'idempotency_key':case['idempotency_key'],'resource':case['resource'],'post_recovery_sha256':hashlib.sha256(resource.read_bytes()).hexdigest(),'verification':{'all_passed':True}}
    path.write_text(json.dumps(body))
    return path,body,{'status':'reverted','summary':'执行器声称成功','receipt_ref':str(path),'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'evidence_refs':[str(path)]}


@pytest.mark.parametrize('fault',['none','missing','corrupt','hash','key','contract','resource','content','verdict','evidence','outside','symlink','no_hash'])
def test_manual_recovery_receipt_gate(tmp_path,monkeypatch,fault):
    monkeypatch.setenv('COMMAND_CENTER_ARTIFACT_ROOTS',str(tmp_path))
    service,mission,old=failed_verification(tmp_path)
    proposal=service.propose_compensation_recovery(old['id'],expected_mission_id=mission['id'],contract_hash=old['contract_hash'],instructions='核实指定资源，仅复用有效回执',actor='test')['compensation']
    service.decide_compensation(proposal['id'],expected_mission_id=mission['id'],contract_hash=proposal['contract_hash'],decision='approved',decided_by='test')
    claim=service.claim_ready_compensation('test')
    path,body,result=local_receipt(claim,tmp_path)
    if fault=='missing': result['receipt_ref']=str(tmp_path/'absent.json')
    elif fault=='corrupt': path.write_text('{broken');result['receipt_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    elif fault=='hash': result['receipt_sha256']='0'*64
    elif fault in {'key','contract','resource','verdict'}:
        field={'key':'idempotency_key','contract':'contract_hash','resource':'resource','verdict':'verification'}[fault]
        body[field]={'all_passed':'true'} if fault=='verdict' else 'wrong'
        path.write_text(json.dumps(body));result['receipt_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    elif fault=='content': Path(claim['resource']).write_text('unexpected\n')
    elif fault=='evidence': result['evidence_refs']=['unrelated']
    elif fault=='outside': monkeypatch.setenv('COMMAND_CENTER_ARTIFACT_ROOTS',str(tmp_path/'different-root'))
    elif fault=='symlink':
        link=tmp_path/'link.json';link.symlink_to(path);result['receipt_ref']=str(link);result['evidence_refs']=[str(link)]
    elif fault=='no_hash': result.pop('receipt_sha256')
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in tmp_path.glob('*.json') if not p.is_symlink()}
    resource_before=Path(claim['resource']).read_bytes()
    actual=service.complete_compensation(claim['id'],lease_token=claim['lease_token'],result=result,actor='test')
    assert actual['status']==('completed' if fault=='none' else 'failed')
    assert actual['result']['receipt_validation']['accepted']==(fault=='none')
    assert service.get_mission(mission['id'])['effects'][0]['status']==('reverted' if fault=='none' else 'unknown')
    assert service.claim_ready_compensation('auto-retry') is None
    assert Path(claim['resource']).read_bytes()==resource_before
    assert all((tmp_path/n).read_bytes()==v[0] and (tmp_path/n).stat().st_mtime_ns==v[1] for n,v in before.items())
