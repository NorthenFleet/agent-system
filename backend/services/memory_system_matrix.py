"""Aggregate multi-agent memory gate cases and cross-case invariants."""

from __future__ import annotations

from typing import Any


def evaluate_matrix_invariants(
    cases: list[dict[str, Any]],
    invariants: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    successful = [case for case in cases if isinstance(case.get("summary"), dict)]
    if not successful:
        return [{"check": "matrix.cases", "expected": "at least one completed case", "actual": 0}]

    authority = str(invariants.get("authority_system") or "")
    if authority:
        for case in successful:
            actual = case["summary"].get("authority")
            if actual != authority:
                failures.append(
                    {
                        "check": f"matrix.{case['case_id']}.authority",
                        "expected": authority,
                        "actual": actual,
                    }
                )

    if invariants.get("identity_bound_for_all"):
        for case in successful:
            if case["summary"].get("identity_bound") is not True:
                failures.append(
                    {
                        "check": f"matrix.{case['case_id']}.identity_bound",
                        "expected": True,
                        "actual": case["summary"].get("identity_bound"),
                    }
                )

    keys = [str(key) for key in invariants.get("canonical_counts_equal") or []]
    baseline = successful[0]
    baseline_counts = baseline["summary"].get("counts") or {}
    for case in successful[1:]:
        counts = case["summary"].get("counts") or {}
        for key in keys:
            if counts.get(key) != baseline_counts.get(key):
                failures.append(
                    {
                        "check": f"matrix.{case['case_id']}.counts.{key}",
                        "expected": baseline_counts.get(key),
                        "actual": counts.get(key),
                    }
                )
    return failures


def summarize_matrix(
    cases: list[dict[str, Any]],
    invariants: dict[str, Any],
) -> dict[str, Any]:
    invariant_failures = evaluate_matrix_invariants(cases, invariants)
    failed_cases = [case["case_id"] for case in cases if not case.get("healthy")]
    return {
        "healthy": not failed_cases and not invariant_failures,
        "total_cases": len(cases),
        "passed_cases": len(cases) - len(failed_cases),
        "failed_cases": failed_cases,
        "invariant_failures": invariant_failures,
        "agents": [case.get("agent_id") for case in cases],
    }
