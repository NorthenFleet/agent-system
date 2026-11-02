import asyncio
import json
from services.command_center_worker import CommandCenterWorker
from services.openclaw_task_executor import ExecutionResult
from services.work_run_service import WorkRunService
from tests.test_phase9_recovery_verification import verification


def test_compensation_contracts_and_attempts_use_distinct_sessions(tmp_path):
    async def scenario():
        service, mission, claimed=verification(tmp_path)
        service.complete_compensation(claimed['id'],lease_token=claimed['lease_token'],
            result={'status':'failed','summary':'核实失败','receipt_ref':'fixture:verify','evidence_refs':['fixture:verify']},actor='verify')
        class Executor:
            def __init__(self): self.calls=[]
            async def execute(self,command,command_args=None,timeout_seconds=300):
                self.calls.append(command_args)
                return ExecutionResult(success=True,output=json.dumps({'status':'failed','summary':'保留阻塞','receipt_ref':'fixture:verify','evidence_refs':['fixture:verify']}))
        executor=Executor()
        worker=CommandCenterWorker(service=service,executor=executor,work_runs=WorkRunService(str(tmp_path/'state.db')))
        for _ in range(2):
            case=service.get_mission(mission['id'])['compensations'][0]
            service.decide_compensation(case['id'],expected_mission_id=mission['id'],contract_hash=case['contract_hash'],decision='approved',decided_by='test')
            await worker._drain_compensation()
        proposal=service.propose_compensation_recovery(case['id'],expected_mission_id=mission['id'],contract_hash=case['contract_hash'],instructions='恢复已核实资源并验证',actor='test')['compensation']
        service.decide_compensation(proposal['id'],expected_mission_id=mission['id'],contract_hash=proposal['contract_hash'],decision='approved',decided_by='test')
        await worker._drain_compensation()
        keys=[call['session_key'] for call in executor.calls]
        assert len(set(keys))==3
        assert keys[0].endswith('-a2') and keys[1].endswith('-a3') and keys[2].endswith('-a4')
        assert case['contract_hash'][:16] in keys[0]
        assert proposal['contract_hash'][:16] in keys[2]
    asyncio.run(scenario())
