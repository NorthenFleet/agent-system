#!/usr/bin/env python3
"""Evaluate Phase G1.1 evidence reports without contacting GenOffice.

This is a local, machine-checkable portion of the G1.1 exit gate.  It reads
only previously generated, redacted repeatability reports and emits another
redacted report.  A passing result means only that the required evidence is
internally consistent; it deliberately remains pending human visual sign-off
and never changes ``GENOFFICE_G1_PILOT_GATE`` or grants G2 permissions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REVIEW_ROOT = (PROJECT_ROOT / "docs" / "review").resolve()
REPEATABILITY_SCHEMA = "openclaw.genoffice-phase-g1.1-repeatability.v1"
EVALUATION_SCHEMA = "openclaw.genoffice-phase-g1.1-gate-evaluation.v1"


class G11GateError(ValueError):
    """A safe report-validation failure that reveals no document content."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _review_path(value: Path) -> Path:
    path = value.resolve()
    try:
        path.relative_to(REVIEW_ROOT)
    except ValueError as exc:
        raise G11GateError("report_must_be_under_docs_review") from exc
    return path


def _read_report(value: Path) -> tuple[dict[str, Any], str]:
    path = _review_path(value)
    try:
        raw = path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise G11GateError("report_invalid") from exc
    if not isinstance(report, dict) or report.get("schema") != REPEATABILITY_SCHEMA:
        raise G11GateError("report_schema_invalid")
    return report, _sha256(raw)


def _sha(value: Any) -> str:
    normalized = str(value or "")
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise G11GateError("report_hash_invalid")
    return normalized


def _document_fingerprint(document: Mapping[str, Any]) -> tuple[str, str, int, str]:
    source = document.get("source")
    if not isinstance(source, Mapping):
        raise G11GateError("document_evidence_missing")
    document_id = str(document.get("id") or "")
    source_sha = _sha(source.get("sha256"))
    source_bytes = source.get("bytes")
    observation_sha = _sha(document.get("semantic_observation_sha256"))
    if not document_id or not isinstance(source_bytes, int) or source_bytes <= 0:
        raise G11GateError("document_evidence_missing")
    if document.get("status") != "passed" or document.get("renderer_source_cleanup") != "passed":
        raise G11GateError("document_audit_failed")
    if source.get("integrity") != "passed" or source.get("post_sha256") != source_sha:
        raise G11GateError("source_integrity_failed")
    if not isinstance(document.get("render_page_1"), Mapping):
        raise G11GateError("render_evidence_missing")
    return document_id, source_sha, source_bytes, observation_sha


def _report_fingerprint(report: Mapping[str, Any], *, expected_condition: str, expected_rounds: int) -> dict[str, Any]:
    if report.get("status") != "passed":
        raise G11GateError("repeatability_report_not_passed")
    run = report.get("run")
    engine = report.get("engine")
    manifest = report.get("manifest")
    consistency = report.get("semantic_consistency")
    rounds = report.get("rounds")
    if not all(isinstance(value, Mapping) for value in (run, engine, manifest, consistency)) or not isinstance(rounds, list):
        raise G11GateError("report_evidence_missing")
    if run.get("condition") != expected_condition or run.get("rounds_requested") != expected_rounds:
        raise G11GateError("report_condition_invalid")
    epoch = str(run.get("sidecar_epoch") or "")
    if not epoch:
        raise G11GateError("sidecar_epoch_missing")
    if consistency.get("status") != "passed":
        raise G11GateError("semantic_consistency_failed")
    if len(rounds) != expected_rounds:
        raise G11GateError("round_count_invalid")

    release_version = str(engine.get("release_version") or "")
    mcp_version = str(engine.get("mcp_version") or "")
    contract_sha = _sha(engine.get("g1_tool_contract_sha256"))
    tools = engine.get("required_readonly_tools")
    if not isinstance(tools, list) or set(tools) != {"docs_read", "docs_check", "render"}:
        raise G11GateError("readonly_tool_scope_invalid")
    config_sha = _sha(report.get("configuration_sha256"))
    manifest_sha = _sha(manifest.get("sha256"))
    documents: dict[str, tuple[str, int, str]] = {}
    for round_record in rounds:
        if not isinstance(round_record, Mapping) or round_record.get("status") != "passed":
            raise G11GateError("round_audit_failed")
        current_documents = round_record.get("documents")
        if not isinstance(current_documents, list) or not current_documents:
            raise G11GateError("document_evidence_missing")
        for document in current_documents:
            if not isinstance(document, Mapping):
                raise G11GateError("document_evidence_missing")
            document_id, source_sha, source_bytes, observation_sha = _document_fingerprint(document)
            fingerprint = (source_sha, source_bytes, observation_sha)
            previous = documents.setdefault(document_id, fingerprint)
            if previous != fingerprint:
                raise G11GateError("cross_round_document_drift")
    if len(documents) < 2:
        raise G11GateError("two_gold_documents_required")
    return {
        "configuration_sha256": config_sha,
        "documents": documents,
        "g1_tool_contract_sha256": contract_sha,
        "manifest_sha256": manifest_sha,
        "mcp_version": mcp_version,
        "release_version": release_version,
        "sidecar_epoch": epoch,
    }


def _same_candidate(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    keys = (
        "configuration_sha256",
        "documents",
        "g1_tool_contract_sha256",
        "manifest_sha256",
        "mcp_version",
        "release_version",
    )
    return all(baseline.get(key) == candidate.get(key) for key in keys)


def _evaluate(
    cold_reports: list[tuple[dict[str, Any], str]],
    warm_report: tuple[dict[str, Any], str],
    fresh_profile_report: tuple[dict[str, Any], str],
) -> dict[str, Any]:
    if len(cold_reports) != 3:
        raise G11GateError("three_cold_reports_required")
    cold = [
        (_report_fingerprint(report, expected_condition="cold_process", expected_rounds=1), report_sha)
        for report, report_sha in cold_reports
    ]
    warm, warm_sha = _report_fingerprint(warm_report[0], expected_condition="warm", expected_rounds=3), warm_report[1]
    fresh, fresh_sha = (
        _report_fingerprint(fresh_profile_report[0], expected_condition="fresh_profile", expected_rounds=1),
        fresh_profile_report[1],
    )
    baseline = cold[0][0]
    cold_epochs = [str(item[0]["sidecar_epoch"]) for item in cold]
    if len(set(cold_epochs)) != len(cold_epochs):
        raise G11GateError("cold_sidecar_epochs_not_distinct")
    if not all(_same_candidate(baseline, item[0]) for item in cold[1:]):
        raise G11GateError("cold_candidate_drift")
    if not _same_candidate(baseline, warm) or not _same_candidate(baseline, fresh):
        raise G11GateError("candidate_drift")
    if fresh["sidecar_epoch"] in cold_epochs:
        raise G11GateError("fresh_profile_epoch_not_distinct")

    return {
        "schema": EVALUATION_SCHEMA,
        "created_at": _utc_now(),
        "scope": "local evaluation of redacted G1.1 reports; no GenOffice, candidate, database, or source-document access",
        "machine_gate": "passed",
        "g1_exit_gate": "pending_human_visual_review_and_manual_verified_read_only_decision",
        "candidate": {
            "configuration_sha256": baseline["configuration_sha256"],
            "document_ids": sorted(baseline["documents"]),
            "g1_tool_contract_sha256": baseline["g1_tool_contract_sha256"],
            "manifest_sha256": baseline["manifest_sha256"],
            "mcp_version": baseline["mcp_version"],
            "release_version": baseline["release_version"],
        },
        "evidence": {
            "cold_process_report_sha256": [report_sha for _fingerprint, report_sha in cold],
            "cold_process_epochs": cold_epochs,
            "fresh_profile_epoch": fresh["sidecar_epoch"],
            "fresh_profile_report_sha256": fresh_sha,
            "warm_report_sha256": warm_sha,
        },
        "non_authorization": "This evaluation does not change pilot_gate, enable docs_apply, authorize G2, install an app, or replace Word Add-in.",
    }


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    output = _review_path(path)
    if output.exists():
        raise G11GateError("output_already_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise G11GateError("output_already_exists") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cold-report", action="append", type=Path, required=True)
    parser.add_argument("--warm-report", type=Path, required=True)
    parser.add_argument("--fresh-profile-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cold = [_read_report(path) for path in args.cold_report]
        warm = _read_report(args.warm_report)
        fresh = _read_report(args.fresh_profile_report)
        result = _evaluate(cold, warm, fresh)
        _write_report(args.output, result)
    except (G11GateError, OSError, ValueError) as exc:
        print(json.dumps({"reason_code": str(exc), "status": "failed"}, ensure_ascii=False))
        return 2
    print(json.dumps({"machine_gate": result["machine_gate"], "status": "passed"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
