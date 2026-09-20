from services.memory_release_orchestrator import orchestrate_memory_release


def _decision(ready=True):
    return {
        "release_id": "release-test",
        "decision_id": "decision-test",
        "candidate_digest": "digest-test",
        "version": "2026.09.18",
        "change_type": "memory-platform",
        "risk": {"level": "high", "label": "高风险"},
        "promotion_ready": ready,
        "blocking_failures": [] if ready else ["approval"],
    }


def test_orchestrator_promotes_after_canary_and_matrix():
    calls = []
    result = orchestrate_memory_release(
        _decision(),
        deploy=lambda: calls.append("deploy") or {"changed": True, "backup": "/backup/one"},
        restart=lambda: calls.append("restart"),
        verify_canary=lambda: calls.append("canary") or {"healthy": True, "failures": []},
        verify_matrix=lambda: calls.append("matrix") or {"healthy": True, "failures": []},
        rollback=lambda backup: calls.append(("rollback", backup)) or {"restored": True},
    )

    assert result["status"] == "promoted"
    assert result["candidate_digest"] == "digest-test"
    assert result["version"] == "2026.09.18"
    assert result["risk"]["level"] == "high"
    assert calls == ["deploy", "restart", "canary", "matrix"]


def test_orchestrator_rolls_back_failed_canary_and_restarts():
    calls = []
    result = orchestrate_memory_release(
        _decision(),
        deploy=lambda: calls.append("deploy") or {"changed": True, "backup": "/backup/one"},
        restart=lambda: calls.append("restart"),
        verify_canary=lambda: calls.append("canary") or {"healthy": False, "failures": [{"check": "identity.bound"}]},
        verify_matrix=lambda: calls.append("matrix") or {"healthy": True},
        rollback=lambda backup: calls.append(("rollback", backup)) or {"restored": True},
    )

    assert result["status"] == "rolled_back"
    assert calls == ["deploy", "restart", "canary", ("rollback", "/backup/one"), "restart"]
    assert any(event["stage"] == "automatic_rollback" and event["status"] == "passed" for event in result["events"])


def test_orchestrator_verifies_canary_and_matrix_when_deploy_is_noop():
    calls = []
    result = orchestrate_memory_release(
        _decision(),
        deploy=lambda: calls.append("deploy") or {"changed": False, "backup": ""},
        restart=lambda: calls.append("restart"),
        verify_canary=lambda: calls.append("canary") or {"healthy": True, "failures": []},
        verify_matrix=lambda: calls.append("matrix") or {"healthy": True, "failures": []},
        rollback=lambda backup: calls.append(("rollback", backup)) or {"restored": True},
    )

    assert result["status"] == "verified_noop"
    assert calls == ["deploy", "canary", "matrix"]
    assert any(
        event["stage"] == "restart_gateway" and event["status"] == "skipped"
        for event in result["events"]
    )


def test_orchestrator_reports_failed_noop_verification_without_rollback():
    calls = []
    result = orchestrate_memory_release(
        _decision(),
        deploy=lambda: calls.append("deploy") or {"changed": False, "backup": ""},
        restart=lambda: calls.append("restart"),
        verify_canary=lambda: calls.append("canary") or {"healthy": False, "failures": [{"check": "canary"}]},
        verify_matrix=lambda: calls.append("matrix") or {"healthy": True},
        rollback=lambda backup: calls.append(("rollback", backup)) or {"restored": True},
    )

    assert result["status"] == "verification_failed_no_change"
    assert calls == ["deploy", "canary"]
    assert not any(event["stage"] == "automatic_rollback" for event in result["events"])


def test_orchestrator_does_not_mutate_when_gate_is_blocked():
    calls = []
    result = orchestrate_memory_release(
        _decision(False),
        deploy=lambda: calls.append("deploy") or {},
        restart=lambda: calls.append("restart"),
        verify_canary=lambda: {"healthy": True},
        verify_matrix=lambda: {"healthy": True},
        rollback=lambda _backup: {"restored": True},
    )

    assert result["status"] == "blocked"
    assert calls == []
