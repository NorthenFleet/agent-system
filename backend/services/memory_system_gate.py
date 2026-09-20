"""Contract checks for the end-to-end memory introspection health gate.

This module deliberately evaluates the public OpenClaw-to-3021 response rather
than querying storage directly.  A passing result therefore proves identity
binding, canonical retrieval, and all configured auxiliary channels together.
"""

from __future__ import annotations

from typing import Any


class MemorySystemGateError(ValueError):
    """Raised when an evaluation contract is malformed."""


def execution_failure_status(
    *,
    case_id: str,
    error: Exception | str,
    attempt: int,
    attempts_configured: int,
    checked_at: str,
) -> dict[str, Any]:
    """Return the same sanitized fail-closed state used by the live gate."""
    return {
        "schema_version": "memory-system-health.v1",
        "checked_at": checked_at,
        "case_id": case_id,
        "attempt": attempt,
        "attempts_configured": attempts_configured,
        "healthy": False,
        "failures": [
            {"check": "gate_execution", "expected": "success", "actual": str(error)[:1000]}
        ],
        "summary": {},
    }


def enforce_bridge_deployment(
    status: dict[str, Any],
    bridge: dict[str, Any],
) -> dict[str, Any]:
    """Attach bridge evidence and fail the gate when deployment cannot be verified."""
    status.setdefault("summary", {})["bridge_deployment"] = bridge
    if bridge.get("ready") is not True:
        status["healthy"] = False
        status.setdefault("failures", []).append(
            {
                "check": "bridge_deployment",
                "expected": "version and source hashes verified",
                "actual": bridge.get("failed_checks") or [],
            }
        )
    return status


def evaluate_memory_report(
    report: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact, non-secret health result for one introspection report."""
    if not isinstance(report, dict):
        raise MemorySystemGateError("memory report must be an object")
    if not isinstance(contract, dict):
        raise MemorySystemGateError("memory gate contract must be an object")

    failures: list[dict[str, Any]] = []

    def fail(check: str, expected: Any, actual: Any) -> None:
        failures.append({"check": check, "expected": expected, "actual": actual})

    expected_schema = str(contract.get("schema_version") or "memory-introspection.v1")
    if report.get("schema_version") != expected_schema:
        fail("schema_version", expected_schema, report.get("schema_version"))

    accepted_statuses = [str(value) for value in contract.get("accepted_statuses") or ["ready"]]
    if str(report.get("status") or "") not in accepted_statuses:
        fail("status", accepted_statuses, report.get("status"))

    expected_authority = str(contract.get("authority_system") or "3021-unified-memory")
    authority = report.get("authority") if isinstance(report.get("authority"), dict) else {}
    if authority.get("system") != expected_authority:
        fail("authority.system", expected_authority, authority.get("system"))

    scope = report.get("scope") if isinstance(report.get("scope"), dict) else {}
    expected_agent = str(contract.get("agent_id") or "optimus")
    if scope.get("agent_id") != expected_agent:
        fail("scope.agent_id", expected_agent, scope.get("agent_id"))
    if scope.get("user_scoped") is not True:
        fail("scope.user_scoped", True, scope.get("user_scoped"))

    identity = report.get("identity") if isinstance(report.get("identity"), dict) else {}
    expected_channel = str(contract.get("identity_channel") or "feishu")
    if identity.get("channel") != expected_channel:
        fail("identity.channel", expected_channel, identity.get("channel"))
    if identity.get("bound") is not True:
        fail("identity.bound", True, identity.get("bound"))
    if contract.get("require_identity_display_name", True) and not str(identity.get("display_name") or "").strip():
        fail("identity.display_name", "non-empty", identity.get("display_name"))

    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    minimum_counts = contract.get("minimum_counts") or {}
    if not isinstance(minimum_counts, dict):
        raise MemorySystemGateError("minimum_counts must be an object")
    for key, expected in minimum_counts.items():
        try:
            minimum = int(expected)
            actual = int(counts.get(key) or 0)
        except (TypeError, ValueError) as exc:
            raise MemorySystemGateError(f"invalid minimum count for {key}") from exc
        if actual < minimum:
            fail(f"counts.{key}", {"minimum": minimum}, actual)

    maximum_counts = contract.get("maximum_counts") or {}
    if not isinstance(maximum_counts, dict):
        raise MemorySystemGateError("maximum_counts must be an object")
    for key, expected in maximum_counts.items():
        try:
            maximum = int(expected)
            actual = int(counts.get(key) or 0)
        except (TypeError, ValueError) as exc:
            raise MemorySystemGateError(f"invalid maximum count for {key}") from exc
        if actual > maximum:
            fail(f"counts.{key}", {"maximum": maximum}, actual)

    exact_counts = contract.get("exact_counts") or {}
    if not isinstance(exact_counts, dict):
        raise MemorySystemGateError("exact_counts must be an object")
    for key, expected in exact_counts.items():
        try:
            exact = int(expected)
            actual = int(counts.get(key) or 0)
        except (TypeError, ValueError) as exc:
            raise MemorySystemGateError(f"invalid exact count for {key}") from exc
        if actual != exact:
            fail(f"counts.{key}", exact, actual)

    minimum_items = int(contract.get("minimum_remembered_items") or 0)
    remembered_items = report.get("remembered_items")
    actual_items = len(remembered_items) if isinstance(remembered_items, list) else 0
    if actual_items < minimum_items:
        fail("remembered_items", {"minimum": minimum_items}, actual_items)

    channels = report.get("channels") if isinstance(report.get("channels"), dict) else {}
    required_channels = contract.get("required_channels") or {}
    if not isinstance(required_channels, dict):
        raise MemorySystemGateError("required_channels must be an object")
    channel_summary: dict[str, str] = {}
    for name, allowed_raw in required_channels.items():
        channel = channels.get(name) if isinstance(channels.get(name), dict) else {}
        actual = str(channel.get("status") or "missing")
        allowed = [str(value) for value in (allowed_raw if isinstance(allowed_raw, list) else [allowed_raw])]
        channel_summary[str(name)] = actual
        if actual not in allowed:
            fail(f"channels.{name}.status", allowed, actual)

    max_degraded = int(contract.get("max_degraded_channels", 0))
    degraded = report.get("degraded_channels")
    degraded_count = len(degraded) if isinstance(degraded, list) else 0
    if degraded_count > max_degraded:
        fail("degraded_channels", {"maximum": max_degraded}, degraded_count)

    interpretation = report.get("interpretation") if isinstance(report.get("interpretation"), dict) else {}
    for key in contract.get("interpretation_must_be_false") or []:
        if interpretation.get(str(key)) is not False:
            fail(f"interpretation.{key}", False, interpretation.get(str(key)))

    retrieval = report.get("retrieval") if isinstance(report.get("retrieval"), dict) else {}
    if contract.get("require_retrieval_citations", True):
        citations = retrieval.get("citations")
        if not isinstance(citations, list) or not citations:
            fail("retrieval.citations", "non-empty", 0 if not isinstance(citations, list) else len(citations))

    return {
        "healthy": not failures,
        "failures": failures,
        "summary": {
            "status": report.get("status"),
            "authority": authority.get("system"),
            "agent_id": scope.get("agent_id"),
            "identity_channel": identity.get("channel"),
            "identity_bound": identity.get("bound") is True,
            "counts": {
                str(key): counts.get(key, 0)
                for key in dict.fromkeys([*minimum_counts, *maximum_counts, *exact_counts])
            },
            "remembered_items": actual_items,
            "channels": channel_summary,
            "degraded_channels": degraded_count,
            "retrieval_citations": len(retrieval.get("citations") or []),
        },
    }
