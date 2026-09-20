from services.command_center_service import CommandCenterService
from services.execution_evidence_service import ExecutionEvidenceService


def _single_step_plan(max_attempts=2):
    return {
        "summary": "单步可验收任务",
        "risk_level": "low",
        "steps": [
            {
                "order_index": 1,
                "title": "执行与交付",
                "description": "完成目标并提交结构化证据",
                "task_type": "coordination",
                "agent_id": "optimus",
                "depends_on": [],
                "max_attempts": max_attempts,
            }
        ],
    }


def _running_step(service, mission_id):
    service.approve(mission_id, decided_by="admin")
    service.activate_approved_missions()
    return service.claim_ready_steps("runner", limit=1)[0]


def _valid_result(step):
    artifact_types = step["output_contract"]["artifact_types"]
    evidence_type = step["evidence_required"][0]
    return {
        "success": True,
        "summary": "已完成并核验交付",
        "output": "structured result",
        "tools_used": list(step["required_tools"]),
        "artifacts": [
            {
                "artifact_key": f"a{index}",
                "artifact_type": artifact_type,
                "title": f"可验收交付物 {index}",
                "uri": f"artifact://test/delivery-{index}.json",
                "content_hash": f"{index:x}" * 64,
            }
            for index, artifact_type in enumerate(artifact_types, start=1)
        ],
        "evidence": [
            {
                "evidence_type": evidence_type,
                "source_ref": "run:test:1",
                "summary": "可重现执行记录",
                "artifact_key": "a1",
                "confidence": 1,
            }
        ],
        "acceptance_results": [
            {
                "criterion": criterion,
                "status": "pass",
                "evidence_refs": ["run:test:1"],
            }
            for criterion in step["acceptance_criteria"]
        ],
        "risk_notes": "无剩余风险",
    }


def test_structured_result_normalization_and_strict_gate():
    service = ExecutionEvidenceService()
    step = {
        "required_tools": ["test_runner"],
        "evidence_required": ["test_output"],
        "acceptance_criteria": ["测试通过"],
        "output_contract": {
            "artifact_types": ["test_report"],
            "required_fields": ["summary", "evidence_refs", "risk_notes"],
        },
    }
    result = service.enrich_result(
        step,
        {
            "output": '{"summary":"ok","tools_used":["test_runner"],'
            '"artifacts":[{"artifact_type":"test_report","title":"report",'
            '"uri":"artifact://test/report.xml","content":"passed"}],'
            '"evidence":[{"evidence_type":"test_output","source_ref":"pytest:1",'
            '"summary":"1 passed"}],'
            '"acceptance_results":[{"criterion":"测试通过","status":"pass"}],'
            '"risk_notes":"none"}',
        },
        success=True,
        enforcement={"mode": "strict", "enforced": True},
    )

    assert result["execution_quality"]["accepted"] is True
    assert len(result["artifacts"][0]["content_hash"]) == 64
    assert result["evidence_refs"] == ["pytest:1"]


def test_executor_and_nested_cli_failure_normalize_to_failed_outcome():
    service = ExecutionEvidenceService()

    direct = service.normalize_result(
        {"success": False, "error": "rate limited", "output": ""}
    )
    nested = service.normalize_result(
        {
            "success": True,
            "output": '{"ok":false,"error":{"type":"cli_error"}}',
        }
    )

    assert direct["outcome"] == "failed"
    assert nested["outcome"] == "failed"


def test_placeholder_hash_and_ephemeral_path_are_hard_blockers_in_pilot():
    service = ExecutionEvidenceService()
    result = service.enrich_result(
        {},
        {
            "success": True,
            "outcome": "succeeded",
            "summary": "声称已完成",
            "artifacts": [
                {
                    "artifact_type": "source_code",
                    "title": "临时代码",
                    "uri": "/workspace/ephemeral/app.js",
                    "content_hash": "pending",
                }
            ],
        },
        success=True,
        enforcement={"mode": "pilot", "enforced": False},
    )

    assert result["execution_quality"]["accepted"] is False
    assert len(result["execution_quality"]["hard_blockers"]) == 2


def test_strict_gate_persists_delivery_records(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_CENTER_EVIDENCE_ENFORCEMENT", "strict")
    service = CommandCenterService(str(tmp_path / "evidence.db"))
    mission = service.create_mission(
        objective="执行一个可验收任务",
        requested_by="admin",
        context={"business_flow_key": "general"},
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _single_step_plan())
    step = _running_step(service, mission["id"])

    completed = service.complete_step(
        step["id"],
        result=_valid_result(step),
        success=True,
        actor="optimus",
        lease_token=step["lease_token"],
    )
    evaluating = service.claim_evaluation_mission("evaluator")
    delivery = service.get_delivery_evidence(mission["id"])

    assert completed["status"] == "completed"
    assert completed["acceptance_gate"]["accepted"] is True
    assert evaluating["status"] == "evaluating"
    assert delivery["summary"] == {
        "artifact_count": 2,
        "evidence_count": 1,
        "gate_count": 2,
        "blocked_gates": 0,
        "effect_count": 0,
        "unresolved_compensations": 0,
    }
    assert delivery["evidence"][0]["artifact_id"] == delivery["artifacts"][0]["id"]
    ledger = service.get_mission_run_ledger(mission["id"])
    run = ledger["run"]
    assert all(item["mission_run_id"] == run["id"] for item in delivery["artifacts"])
    assert all(item["correlation_id"] == run["correlation_id"] for item in delivery["evidence"])
    assert all(item["mission_run_id"] == run["id"] for item in delivery["acceptance_gates"])
    assert ledger["workflow_runs"][0]["correlation_id"] == run["correlation_id"]


def test_strict_gate_retries_then_fails_when_evidence_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_CENTER_EVIDENCE_ENFORCEMENT", "strict")
    service = CommandCenterService(str(tmp_path / "evidence-retry.db"))
    mission = service.create_mission(
        objective="验证证据重试",
        requested_by="admin",
        context={"business_flow_key": "general"},
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _single_step_plan(max_attempts=2))
    first = _running_step(service, mission["id"])

    retried = service.complete_step(
        first["id"],
        result={"success": True, "output": "done"},
        success=True,
        actor="optimus",
        lease_token=first["lease_token"],
    )
    second = service.claim_ready_steps("runner", limit=1)[0]
    failed = service.complete_step(
        second["id"],
        result={"success": True, "output": "done again"},
        success=True,
        actor="optimus",
        lease_token=second["lease_token"],
    )

    assert retried["status"] == "ready"
    assert retried["result"]["completion_decision"]["retry_scheduled"] is True
    assert failed["status"] == "failed"
    assert failed["acceptance_gate"]["status"] == "blocked"
    assert failed["result"]["completion_decision"]["attempt"] == 2


def test_blocked_business_outcome_is_never_completed_in_pilot_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_CENTER_EVIDENCE_ENFORCEMENT", "pilot")
    service = CommandCenterService(str(tmp_path / "semantic-block.db"))
    mission = service.create_mission(
        objective="验证业务阻塞不能假完成",
        requested_by="admin",
        context={"business_flow_key": "general"},
    )
    service.claim_planning_mission("planner")
    service.save_plan(mission["id"], _single_step_plan())
    step = _running_step(service, mission["id"])

    failed = service.complete_step(
        step["id"],
        result={
            "success": True,
            "outcome": "blocked",
            "summary": "阻塞：缺少上游交付物",
            "acceptance_results": [
                {"criterion": criterion, "status": "fail"}
                for criterion in step["acceptance_criteria"]
            ],
        },
        success=True,
        actor="optimus",
        lease_token=step["lease_token"],
    )

    assert failed["status"] == "failed"
    assert failed["result"]["outcome"] == "blocked"
    assert failed["result"]["completion_decision"]["accepted"] is False
    assert failed["result"]["execution_quality"]["hard_blockers"]
    assert service.claim_evaluation_mission("evaluator") is None
    assert service.get_mission(mission["id"])["status"] == "waiting_feedback"
