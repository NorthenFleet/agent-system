import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_genoffice_g11_repeatability.py"
SPEC = importlib.util.spec_from_file_location("audit_genoffice_g11_repeatability", SCRIPT_PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

EVALUATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_genoffice_g11_gate.py"
EVALUATOR_SPEC = importlib.util.spec_from_file_location("evaluate_genoffice_g11_gate", EVALUATOR_PATH)
assert EVALUATOR_SPEC and EVALUATOR_SPEC.loader
evaluator = importlib.util.module_from_spec(EVALUATOR_SPEC)
EVALUATOR_SPEC.loader.exec_module(evaluator)


def _args(**overrides):
    values = {
        "allow_unverified_candidate": False,
        "condition": "warm",
        "expected_contract_sha256": None,
        "expected_mcp_version": None,
        "expected_release_version": None,
        "output": audit.REVIEW_ROOT / "unit-g11-repeatability.json",
        "render_limit_seconds": 170.0,
        "render_target_seconds": 150.0,
        "rounds": 3,
        "run_id": "g11-unit",
        "sidecar_epoch": "test-sidecar-1",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _document(*, status="passed", render_ms=100_000):
    return {"status": status, "stage_elapsed_ms": {"render_page_1": render_ms}}


def test_non_warm_conditions_require_a_separate_evidence_report():
    with pytest.raises(audit.G11AuditError, match="independent_condition_requires_one_round"):
        audit._validate_options(_args(condition="cold_process", rounds=2))


def test_g11_round_summary_keeps_operational_and_experience_gates_distinct():
    attention = audit._round_summary(
        [_document(render_ms=155_000), _document(render_ms=100_000)],
        render_target_seconds=150.0,
        render_limit_seconds=170.0,
    )
    hard_failure = audit._round_summary(
        [_document(render_ms=171_000), _document(render_ms=100_000)],
        render_target_seconds=150.0,
        render_limit_seconds=170.0,
    )
    tool_failure = audit._round_summary(
        [_document(status="failed", render_ms=180_000), _document(render_ms=100_000)],
        render_target_seconds=150.0,
        render_limit_seconds=170.0,
    )

    assert attention["operation_status"] == "passed"
    assert attention["performance"]["status"] == "attention"
    assert attention["status"] == "attention"
    assert hard_failure["performance"]["status"] == "failed"
    assert hard_failure["status"] == "failed"
    assert tool_failure["operation_status"] == "failed"
    assert tool_failure["status"] == "failed"


def test_g11_contract_fingerprint_requires_a_canonical_sha256_when_supplied():
    with pytest.raises(audit.G11AuditError, match="invalid_expected_contract_sha256"):
        audit._validate_options(_args(expected_contract_sha256="not-a-sha"))

    audit._validate_options(_args(expected_contract_sha256="a" * 64))


def test_g11_formal_runner_refuses_the_production_g1_sidecar_port():
    with pytest.raises(audit.G11AuditError, match="independent_test_sidecar_required"):
        audit._require_test_sidecar(SimpleNamespace(mcp_url="http://127.0.0.1:3094/mcp"))

    audit._require_test_sidecar(SimpleNamespace(mcp_url="http://127.0.0.1:3195/mcp"))


def test_g11_marks_read_check_metric_drift_as_a_failed_round():
    rounds = [
        {
            "status": "passed",
            "documents": [{"id": "course", "status": "passed", "semantic_observation_sha256": "a" * 64}],
        },
        {
            "status": "passed",
            "documents": [{"id": "course", "status": "passed", "semantic_observation_sha256": "b" * 64}],
        },
    ]

    summary = audit._mark_semantic_consistency(rounds)

    assert summary["status"] == "failed"
    assert summary["drifted_document_ids"] == ["course"]
    assert rounds[0]["status"] == "passed"
    assert rounds[1]["status"] == "failed"
    assert rounds[1]["documents"][0]["semantic_observation_status"] == "drift"


def _gate_report(*, condition, rounds, epoch, source_sha="c" * 64):
    course = {
        "id": "course",
        "renderer_source_cleanup": "passed",
        "render_page_1": {"sha256": "d" * 64},
        "semantic_observation_sha256": "e" * 64,
        "source": {"bytes": 123, "integrity": "passed", "post_sha256": source_sha, "sha256": source_sha},
        "status": "passed",
    }
    thesis_sha = "9" * 64
    thesis = {
        "id": "thesis",
        "renderer_source_cleanup": "passed",
        "render_page_1": {"sha256": "8" * 64},
        "semantic_observation_sha256": "7" * 64,
        "source": {"bytes": 456, "integrity": "passed", "post_sha256": thesis_sha, "sha256": thesis_sha},
        "status": "passed",
    }
    return {
        "schema": evaluator.REPEATABILITY_SCHEMA,
        "status": "passed",
        "configuration_sha256": "a" * 64,
        "engine": {
            "g1_tool_contract_sha256": "b" * 64,
            "mcp_version": "0.10.0",
            "release_version": "0.10.1038",
            "required_readonly_tools": ["docs_read", "docs_check", "render"],
        },
        "manifest": {"sha256": "f" * 64},
        "run": {"condition": condition, "rounds_requested": rounds, "sidecar_epoch": epoch},
        "semantic_consistency": {"status": "passed"},
        "rounds": [{"status": "passed", "documents": [course.copy(), thesis.copy()]} for _ in range(rounds)],
    }


def test_g11_gate_evaluator_requires_distinct_cold_epochs_and_keeps_human_gate_pending():
    cold = [(_gate_report(condition="cold_process", rounds=1, epoch=f"cold-{index}"), f"{index}" * 64) for index in range(1, 4)]
    warm = (_gate_report(condition="warm", rounds=3, epoch="warm-1"), "4" * 64)
    fresh = (_gate_report(condition="fresh_profile", rounds=1, epoch="fresh-1"), "5" * 64)

    result = evaluator._evaluate(cold, warm, fresh)

    assert result["machine_gate"] == "passed"
    assert result["g1_exit_gate"] == "pending_human_visual_review_and_manual_verified_read_only_decision"
    assert result["evidence"]["cold_process_epochs"] == ["cold-1", "cold-2", "cold-3"]

    duplicate_epoch = [(_gate_report(condition="cold_process", rounds=1, epoch="cold-1"), f"{index}" * 64) for index in range(1, 4)]
    with pytest.raises(evaluator.G11GateError, match="cold_sidecar_epochs_not_distinct"):
        evaluator._evaluate(duplicate_epoch, warm, fresh)
