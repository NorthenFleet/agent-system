import json

import pytest

from services.memory_release_governance import (
    MemoryReleaseGovernanceError,
    approve_release_candidate,
    attach_release_execution,
    attest_candidate_validation,
    evaluate_release_gate,
    prepare_release_candidate,
    read_release_candidate,
    read_latest_release_execution,
    read_release_audit,
    record_release_decision,
    revoke_release_candidate,
    summarize_release_history,
    update_release_candidate_approval,
    write_release_candidate,
)


def _workspace(tmp_path):
    root = tmp_path / "workspace"
    (root / "managed").mkdir(parents=True)
    (root / "managed" / "bridge.ts").write_text("export const bridge = 1;\n", encoding="utf-8")
    (root / "managed" / "skill.md").write_text("# Memory skill\n", encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": "memory-release-policy.v1",
                "requirements": {
                    "matrix_cases": 5,
                    "primary_slo_min_samples": 20,
                    "matrix_slo_min_samples": 1,
                    "drill_scenarios": 4,
                },
                "risk_policy": {
                    "memory-platform": {
                        "level": "high",
                        "label": "高风险",
                        "approval_mode": "human-admin-separated",
                        "requires_creator_separation": True,
                        "required_validations": [],
                    }
                },
                "managed_artifacts": ["managed/bridge.ts", "managed/skill.md"],
            }
        ),
        encoding="utf-8",
    )
    return root, policy


def _snapshots():
    health = {"status": "healthy", "healthy": True}
    matrix = {"status": "healthy", "healthy": True, "summary": {"passed_cases": 5, "total_cases": 5}}
    slo = {
        "data_quality": {"valid": True, "errors": []},
        "monitors": {
            "primary": {"status": "healthy", "sample_count": 23},
            "matrix": {"status": "healthy", "sample_count": 2},
        },
    }
    drill = {"status": "healthy", "healthy": True, "summary": {"passed_scenarios": 4, "total_scenarios": 4}}
    return health, matrix, slo, drill


def _evaluate(candidate, root):
    health, matrix, slo, drill = _snapshots()
    return evaluate_release_gate(
        candidate,
        health=health,
        matrix=matrix,
        slo=slo,
        drill=drill,
        workspace_root=root,
    )


def test_release_gate_requires_integrity_health_and_explicit_approval(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.17",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
        release_id="release-test",
    )

    unvalidated = _evaluate(candidate, root)
    assert unvalidated["status"] == "blocked"
    assert "candidate.validation" in unvalidated["blocking_failures"]

    candidate = attest_candidate_validation(
        candidate,
        checks=[
            {"name": "backend", "passed": True, "return_code": 0},
            {"name": "frontend", "passed": True, "return_code": 0},
        ],
    )
    pending = _evaluate(candidate, root)
    assert pending["status"] == "awaiting_approval"
    assert pending["technical_ready"] is True
    assert pending["promotion_ready"] is False
    assert pending["rollout_plan"]["strategy"] == "optimus-canary-then-matrix"
    assert pending["risk"]["level"] == "high"

    approved = approve_release_candidate(
        candidate,
        approved_by="admin",
        expected_digest=candidate["candidate_digest"],
    )
    ready = _evaluate(approved, root)
    assert ready["status"] == "ready"
    assert ready["promotion_ready"] is True
    assert ready["candidate_digest"] == approved["candidate_digest"]
    assert ready["approval"]["approved_by"] == "admin"

    revoked = revoke_release_candidate(
        approved,
        revoked_by="release-manager",
        expected_digest=approved["candidate_digest"],
    )
    pending_again = _evaluate(revoked, root)
    assert pending_again["status"] == "awaiting_approval"
    assert pending_again["approval"]["revoked_by"] == "release-manager"


def test_release_execution_terminal_state_matches_only_current_release(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.18",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
        release_id="release-terminal",
    )
    candidate = attest_candidate_validation(
        candidate,
        checks=[{"name": "all", "passed": True, "return_code": 0}],
    )
    candidate = approve_release_candidate(
        candidate,
        approved_by="admin",
        expected_digest=candidate["candidate_digest"],
    )
    decision = _evaluate(candidate, root)

    completed = attach_release_execution(
        decision,
        {
            "release_id": "release-terminal",
            "status": "verified_noop",
            "completed_at": "2026-09-18T00:00:00+00:00",
        },
    )
    assert completed["status"] == "completed"
    assert completed["release_completed"] is True
    assert completed["execution_required"] is False
    assert completed["execution_status"] == "verified_noop"

    unrelated = attach_release_execution(
        decision,
        {"release_id": "another-release", "status": "promoted"},
    )
    assert unrelated["status"] == "ready"
    assert unrelated["release_completed"] is False
    assert unrelated["execution_required"] is True

    failed = attach_release_execution(
        decision,
        {"release_id": "release-terminal", "status": "rolled_back"},
    )
    assert failed["status"] == "execution_failed"
    assert failed["release_completed"] is False
    assert failed["execution_required"] is True

    preflight_blocked = attach_release_execution(
        decision,
        {"release_id": "release-terminal", "status": "blocked"},
    )
    assert preflight_blocked["status"] == "ready"
    assert preflight_blocked["execution_required"] is True


def test_completed_execution_does_not_hide_new_artifact_drift(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.18",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
        release_id="release-drift",
    )
    candidate = attest_candidate_validation(
        candidate,
        checks=[{"name": "all", "passed": True, "return_code": 0}],
    )
    candidate = approve_release_candidate(
        candidate,
        approved_by="admin",
        expected_digest=candidate["candidate_digest"],
    )
    (root / "managed" / "bridge.ts").write_text("drift\n", encoding="utf-8")

    decision = attach_release_execution(
        _evaluate(candidate, root),
        {"release_id": "release-drift", "status": "promoted"},
    )
    assert decision["release_completed"] is True
    assert decision["status"] == "blocked"
    assert "candidate.artifacts" in decision["blocking_failures"]


def test_release_gate_blocks_artifact_drift_and_unhealthy_runtime(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.17",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
    )
    (root / "managed" / "bridge.ts").write_text("export const bridge = 2;\n", encoding="utf-8")
    health, matrix, slo, drill = _snapshots()
    health["healthy"] = False
    health["status"] = "unhealthy"

    decision = evaluate_release_gate(
        candidate,
        health=health,
        matrix=matrix,
        slo=slo,
        drill=drill,
        workspace_root=root,
    )

    assert decision["status"] == "blocked"
    assert "candidate.artifacts" in decision["blocking_failures"]
    assert "primary.current_health" in decision["blocking_failures"]


def test_approval_rejects_changed_candidate_digest(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.17",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
    )
    candidate = attest_candidate_validation(
        candidate,
        checks=[{"name": "all", "passed": True, "return_code": 0}],
    )
    candidate["version"] = "tampered"

    with pytest.raises(MemoryReleaseGovernanceError, match="digest changed"):
        approve_release_candidate(
            candidate,
            approved_by="admin",
            expected_digest=candidate["candidate_digest"],
        )


def test_approval_requires_validation_for_same_digest(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.17",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
    )

    with pytest.raises(MemoryReleaseGovernanceError, match="validation has not passed"):
        approve_release_candidate(
            candidate,
            approved_by="admin",
            expected_digest=candidate["candidate_digest"],
        )


def test_candidate_creator_cannot_self_approve(tmp_path):
    root, policy = _workspace(tmp_path)
    candidate = prepare_release_candidate(
        version="2026.09.17",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
    )
    candidate = attest_candidate_validation(
        candidate,
        checks=[{"name": "all", "passed": True, "return_code": 0}],
    )

    with pytest.raises(MemoryReleaseGovernanceError, match="creator cannot approve"):
        approve_release_candidate(
            candidate,
            approved_by="codex",
            expected_digest=candidate["candidate_digest"],
        )


def test_candidate_file_approval_uses_digest_guard_and_is_reversible(tmp_path):
    root, policy = _workspace(tmp_path)
    path = tmp_path / "candidate.json"
    candidate = prepare_release_candidate(
        version="2026.09.17",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
    )
    candidate = attest_candidate_validation(
        candidate,
        checks=[{"name": "all", "passed": True, "return_code": 0}],
    )
    write_release_candidate(candidate, path)

    approved = update_release_candidate_approval(
        actor="admin",
        expected_digest=candidate["candidate_digest"],
        approve=True,
        path=path,
    )
    assert approved["approval"]["status"] == "approved"
    assert read_release_candidate(path)["approval"]["approved_by"] == "admin"

    with pytest.raises(MemoryReleaseGovernanceError, match="digest changed"):
        update_release_candidate_approval(
            actor="admin",
            expected_digest="0" * 64,
            approve=False,
            path=path,
        )
    assert read_release_candidate(path)["approval"]["status"] == "approved"

    revoked = update_release_candidate_approval(
        actor="release-manager",
        expected_digest=candidate["candidate_digest"],
        approve=False,
        path=path,
    )
    assert revoked["approval"]["status"] == "pending"
    assert revoked["approval"]["revoked_by"] == "release-manager"


def test_release_policy_rejects_artifacts_outside_workspace(tmp_path):
    root, policy = _workspace(tmp_path)
    value = json.loads(policy.read_text(encoding="utf-8"))
    value["managed_artifacts"] = ["../outside.txt"]
    policy.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(MemoryReleaseGovernanceError, match="escapes workspace"):
        prepare_release_candidate(
            version="2026.09.17",
            created_by="codex",
            policy_path=policy,
            workspace_root=root,
        )


def test_release_decisions_and_executions_use_distinct_latest_files(tmp_path):
    decision_path = tmp_path / "decision.json"
    execution_path = tmp_path / "execution.json"
    audit_path = tmp_path / "audit.jsonl"
    decision = {"schema_version": "memory-release-decision.v1", "status": "awaiting_approval"}
    execution = {"schema_version": "memory-release-execution.v1", "status": "blocked"}

    record_release_decision(decision, latest_path=decision_path, audit_path=audit_path)
    record_release_decision(execution, latest_path=execution_path, audit_path=audit_path)

    assert json.loads(decision_path.read_text(encoding="utf-8"))["status"] == "awaiting_approval"
    assert read_latest_release_execution(execution_path)["status"] == "blocked"
    assert [item["status"] for item in read_release_audit(audit_path)] == ["blocked", "awaiting_approval"]


def test_risk_policy_requires_named_validations_before_approval(tmp_path):
    root, policy = _workspace(tmp_path)
    configured = json.loads(policy.read_text(encoding="utf-8"))
    configured["risk_policy"]["memory-platform"]["required_validations"] = ["backend", "frontend"]
    policy.write_text(json.dumps(configured), encoding="utf-8")
    candidate = prepare_release_candidate(
        version="2026.09.18",
        created_by="codex",
        policy_path=policy,
        workspace_root=root,
    )
    candidate = attest_candidate_validation(
        candidate,
        checks=[{"name": "backend", "passed": True, "return_code": 0}],
    )

    decision = _evaluate(candidate, root)
    assert decision["technical_ready"] is False
    assert "candidate.validation" in decision["blocking_failures"]
    with pytest.raises(MemoryReleaseGovernanceError, match="frontend"):
        approve_release_candidate(
            candidate,
            approved_by="admin",
            expected_digest=candidate["candidate_digest"],
        )


def test_release_history_collapses_audit_rows_by_release_id():
    rows = [
        {
            "schema_version": "memory-release-execution.v1",
            "release_id": "release-two",
            "version": "2",
            "status": "blocked",
            "completed_at": "2026-09-18T02:05:00+00:00",
            "events": [{"stage": "preflight_gate", "status": "blocked"}],
        },
        {
            "schema_version": "memory-release-execution.v1",
            "release_id": "release-two",
            "version": "2",
            "status": "rolled_back",
            "completed_at": "2026-09-18T02:00:00+00:00",
            "events": [{"stage": "automatic_rollback", "status": "passed"}],
        },
        {
            "schema_version": "memory-release-decision.v1",
            "release_id": "release-two",
            "version": "2",
            "change_type": "memory-platform",
            "status": "ready",
            "calculated_at": "2026-09-18T01:50:00+00:00",
            "risk": {"level": "high", "label": "高风险"},
            "approval": {"approved_by": "admin"},
        },
        {
            "schema_version": "memory-release-execution.v1",
            "release_id": "release-one",
            "version": "1",
            "status": "verified_noop",
            "completed_at": "2026-09-18T01:00:00+00:00",
            "events": [],
        },
    ]

    history = summarize_release_history(rows)

    assert [item["release_id"] for item in history] == ["release-two", "release-one"]
    assert history[0]["status"] == "rolled_back"
    assert history[0]["approved_by"] == "admin"
    assert history[0]["event_count"] == 3
    assert history[0]["execution_status"] == "rolled_back"
    assert history[1]["status"] == "completed"

    legacy = summarize_release_history(
        [{
            "schema_version": "memory-release-execution.v1",
            "release_id": "release-legacy",
            "version": "legacy",
            "status": "completed_noop",
            "completed_at": "2026-09-17T00:00:00+00:00",
        }]
    )
    assert legacy[0]["status"] == "completed"
