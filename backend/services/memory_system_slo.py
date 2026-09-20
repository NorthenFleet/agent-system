"""Sanitized memory-health history, SLO aggregation, and drill status readers."""

from __future__ import annotations

import json
import math
import os
import fcntl
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = BACKEND_ROOT / "data" / "memory-system-history.jsonl"
DEFAULT_DRILL_PATH = BACKEND_ROOT / "data" / "memory-system-drill.json"
MAX_HISTORY_BYTES = 20_000_000
COMPACT_HISTORY_AT_BYTES = 10_000_000
RETAIN_HISTORY_LINES = 12_000
MAX_DRILL_BYTES = 1_000_000
SLO_TARGETS = {"primary": 99.0, "matrix": 95.0}
SAMPLE_EXCLUSION_REASONS = {"execution_environment_invalid"}


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _history_path(path: str | Path | None = None) -> Path:
    return Path(
        path or os.getenv("MEMORY_SYSTEM_HISTORY_PATH") or DEFAULT_HISTORY_PATH
    ).expanduser()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[rank], 1)


def _sample_id(sample: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in sample.items()
        if key not in {
            "_checked_at",
            "_classification",
            "sample_id",
            "slo_eligible",
            "exclusion_reason",
        }
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_health_sample(
    status: dict[str, Any],
    *,
    monitor_key: str,
    duration_ms: float | None = None,
) -> dict[str, Any]:
    """Build a deliberately content-free operational sample."""
    if monitor_key not in SLO_TARGETS:
        raise ValueError(f"unsupported memory monitor key: {monitor_key}")
    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    failures = status.get("failures") if isinstance(status.get("failures"), list) else []
    channels = summary.get("channels") if isinstance(summary.get("channels"), dict) else {}
    authority = str(summary.get("authority") or "")
    identity_bound = summary.get("identity_bound") is True
    if monitor_key == "matrix":
        cases = status.get("cases") if isinstance(status.get("cases"), list) else []
        case_summaries = [
            item.get("summary")
            for item in cases
            if isinstance(item, dict) and isinstance(item.get("summary"), dict)
        ]
        if case_summaries:
            authorities = {str(item.get("authority") or "") for item in case_summaries}
            authority = authorities.pop() if len(authorities) == 1 else "mixed"
            identity_bound = all(item.get("identity_bound") is True for item in case_summaries)
            channel_names = {
                str(name)
                for item in case_summaries
                for name in (item.get("channels") or {})
            }
            channels = {}
            for name in channel_names:
                values = {str((item.get("channels") or {}).get(name) or "missing") for item in case_summaries}
                channels[name] = values.pop() if len(values) == 1 else "mixed"
    bridge = (
        summary.get("bridge_deployment")
        if isinstance(summary.get("bridge_deployment"), dict)
        else {}
    )
    sample = {
        "schema_version": "memory-system-sample.v1",
        "monitor_key": monitor_key,
        "checked_at": str(status.get("checked_at") or datetime.now(timezone.utc).isoformat()),
        "healthy": status.get("healthy") is True,
        "duration_ms": round(max(0.0, float(duration_ms)), 1) if duration_ms is not None else None,
        "attempt": status.get("attempt"),
        "failure_checks": [
            str(item.get("check") or "unknown")
            for item in failures
            if isinstance(item, dict)
        ][:20],
        "authority": authority,
        "identity_bound": identity_bound,
        "channels": {str(name): str(value) for name, value in channels.items()},
        "bridge_ready": bridge.get("ready") is True if bridge else None,
    }
    if monitor_key == "matrix":
        sample["total_cases"] = int(summary.get("total_cases") or 0)
        sample["passed_cases"] = int(summary.get("passed_cases") or 0)
    sample["sample_id"] = _sample_id(sample)
    return sample


def append_health_sample(
    status: dict[str, Any],
    *,
    monitor_key: str,
    duration_ms: float | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    selected = _history_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    sample = build_health_sample(status, monitor_key=monitor_key, duration_ms=duration_ms)
    encoded = (json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(selected, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        current_size = os.fstat(descriptor).st_size
        if current_size >= COMPACT_HISTORY_AT_BYTES:
            os.lseek(descriptor, max(0, current_size - MAX_HISTORY_BYTES), os.SEEK_SET)
            existing = os.read(descriptor, MAX_HISTORY_BYTES)
            retained = existing.splitlines(keepends=True)[-RETAIN_HISTORY_LINES:]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            for line in retained:
                os.write(descriptor, line)
        os.lseek(descriptor, 0, os.SEEK_END)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)
    return sample


def read_health_samples(
    path: str | Path | None = None,
    *,
    since: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    selected = _history_path(path)
    if not selected.is_file():
        return [], []
    try:
        size = selected.stat().st_size
        if size > MAX_HISTORY_BYTES:
            return [], ["history_file_exceeds_size_limit"]
        lines = selected.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"history_read_failed:{str(exc)[:200]}"]
    samples: list[dict[str, Any]] = []
    classifications: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"invalid_json_line:{line_number}")
            continue
        if not isinstance(value, dict):
            errors.append(f"invalid_sample_line:{line_number}")
            continue
        if value.get("schema_version") == "memory-system-sample-classification.v1":
            sample_id = str(value.get("sample_id") or "")
            reason = str(value.get("reason") or "")
            classified_at = _parse_time(value.get("classified_at"))
            if (
                len(sample_id) != 64
                or any(character not in "0123456789abcdef" for character in sample_id)
                or reason not in SAMPLE_EXCLUSION_REASONS
                or not classified_at
                or not str(value.get("classified_by") or "").strip()
            ):
                errors.append(f"invalid_classification_line:{line_number}")
                continue
            classifications[sample_id] = {**value, "_classified_at": classified_at}
            continue
        if value.get("monitor_key") not in SLO_TARGETS:
            errors.append(f"invalid_sample_line:{line_number}")
            continue
        checked = _parse_time(value.get("checked_at"))
        if not checked:
            errors.append(f"invalid_time_line:{line_number}")
            continue
        value = dict(value)
        expected_id = _sample_id(value)
        recorded_id = str(value.get("sample_id") or expected_id)
        if recorded_id != expected_id:
            errors.append(f"sample_id_mismatch_line:{line_number}")
            continue
        if since and checked < since:
            continue
        value["_checked_at"] = checked
        value["sample_id"] = expected_id
        samples.append(value)
    for value in samples:
        classification = classifications.get(value["sample_id"])
        value["slo_eligible"] = classification is None
        if classification:
            value["exclusion_reason"] = classification["reason"]
            value["_classification"] = classification
    samples.sort(key=lambda item: item["_checked_at"])
    return samples, errors[:50]


def append_sample_classification(
    sample_id: str,
    *,
    reason: str,
    classified_by: str,
    detail: str = "",
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Append an auditable exclusion; never edits or removes the original sample."""
    clean_id = str(sample_id).strip().lower()
    clean_reason = str(reason).strip().lower()
    actor = str(classified_by).strip()[:160]
    if clean_reason not in SAMPLE_EXCLUSION_REASONS:
        raise ValueError(f"unsupported sample exclusion reason: {clean_reason}")
    if len(clean_id) != 64 or any(character not in "0123456789abcdef" for character in clean_id):
        raise ValueError("sample_id must be a sha256 digest")
    if not actor:
        raise ValueError("classified_by is required")
    selected = _history_path(path)
    existing, errors = read_health_samples(selected)
    if errors:
        raise ValueError("cannot classify sample while history has data-quality errors")
    target = next((item for item in existing if item.get("sample_id") == clean_id), None)
    if not target:
        raise ValueError("sample_id does not exist in memory health history")
    if target.get("slo_eligible") is False:
        return {
            "status": "duplicate",
            "sample_id": clean_id,
            "reason": target.get("exclusion_reason"),
        }
    classification = {
        "schema_version": "memory-system-sample-classification.v1",
        "sample_id": clean_id,
        "action": "exclude_from_slo",
        "reason": clean_reason,
        "classified_by": actor,
        "classified_at": datetime.now(timezone.utc).isoformat(),
        "detail": str(detail).strip()[:500],
    }
    encoded = (json.dumps(classification, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)
    return {"status": "recorded", **classification}


def _monitor_slo(
    monitor_key: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    target = SLO_TARGETS[monitor_key]
    healthy = sum(1 for item in samples if item.get("healthy") is True)
    total = len(samples)
    success_rate = round(healthy / total * 100, 3) if total else None
    allowed_failure_rate = 100.0 - target
    observed_failure_rate = 100.0 - success_rate if success_rate is not None else None
    budget_remaining = (
        round(max(0.0, (allowed_failure_rate - observed_failure_rate) / allowed_failure_rate * 100), 1)
        if observed_failure_rate is not None and allowed_failure_rate > 0
        else None
    )
    if success_rate is None:
        status = "insufficient_data"
    elif success_rate < target:
        status = "breached"
    elif budget_remaining is not None and budget_remaining < 25:
        status = "at_risk"
    else:
        status = "healthy"

    durations = [
        float(item["duration_ms"])
        for item in samples
        if isinstance(item.get("duration_ms"), (int, float))
    ]
    incidents = 0
    active_incident: datetime | None = None
    recovery_seconds: list[float] = []
    previous_healthy = True
    for item in samples:
        current_healthy = item.get("healthy") is True
        checked = item["_checked_at"]
        if not current_healthy and previous_healthy:
            incidents += 1
            active_incident = checked
        elif current_healthy and not previous_healthy and active_incident:
            recovery_seconds.append((checked - active_incident).total_seconds())
            active_incident = None
        previous_healthy = current_healthy

    failures = Counter(
        check
        for item in samples
        for check in item.get("failure_checks") or []
        if isinstance(check, str) and check
    )
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "healthy": 0})
    for item in samples:
        day = item["_checked_at"].date().isoformat()
        daily[day]["total"] += 1
        daily[day]["healthy"] += int(item.get("healthy") is True)
    trend = [
        {
            "date": day,
            "total": counts["total"],
            "healthy": counts["healthy"],
            "success_rate": round(counts["healthy"] / counts["total"] * 100, 3),
        }
        for day, counts in sorted(daily.items())
    ]
    return {
        "monitor_key": monitor_key,
        "status": status,
        "target_percent": target,
        "sample_count": total,
        "healthy_samples": healthy,
        "success_rate_percent": success_rate,
        "error_budget_remaining_percent": budget_remaining,
        "p50_duration_ms": _percentile(durations, 0.50),
        "p95_duration_ms": _percentile(durations, 0.95),
        "incident_count": incidents,
        "open_incident": active_incident is not None,
        "mean_recovery_seconds": (
            round(sum(recovery_seconds) / len(recovery_seconds), 1) if recovery_seconds else None
        ),
        "top_failure_checks": [
            {"check": check, "count": count} for check, count in failures.most_common(5)
        ],
        "trend": trend,
    }


def calculate_memory_slo(
    path: str | Path | None = None,
    *,
    days: int = 7,
    now: datetime | None = None,
) -> dict[str, Any]:
    window_days = max(1, min(int(days), 90))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = current - timedelta(days=window_days)
    samples, errors = read_health_samples(path, since=since)
    eligible_samples = [item for item in samples if item.get("slo_eligible") is not False]
    excluded_samples = [item for item in samples if item.get("slo_eligible") is False]
    monitors = {
        key: _monitor_slo(key, [item for item in eligible_samples if item.get("monitor_key") == key])
        for key in SLO_TARGETS
    }
    statuses = [value["status"] for value in monitors.values()]
    overall = (
        "breached"
        if "breached" in statuses
        else "at_risk"
        if "at_risk" in statuses
        else "insufficient_data"
        if all(status == "insufficient_data" for status in statuses)
        else "healthy"
    )
    return {
        "schema_version": "memory-system-slo.v1",
        "status": overall,
        "window_days": window_days,
        "window_start": since.isoformat(),
        "calculated_at": current.isoformat(),
        "sample_count": len(eligible_samples),
        "excluded_sample_count": len(excluded_samples),
        "monitors": monitors,
        "data_quality": {
            "valid": not errors,
            "errors": errors,
            "excluded_samples": len(excluded_samples),
            "exclusion_reasons": dict(Counter(
                str(item.get("exclusion_reason") or "unknown") for item in excluded_samples
            )),
        },
    }


def read_memory_system_drill(
    path: str | Path | None = None,
    *,
    stale_after_seconds: int = 8 * 24 * 60 * 60,
    now: datetime | None = None,
) -> dict[str, Any]:
    selected = Path(
        path or os.getenv("MEMORY_SYSTEM_DRILL_PATH") or DEFAULT_DRILL_PATH
    ).expanduser()
    missing = {
        "status": "missing",
        "healthy": False,
        "checked_at": None,
        "age_seconds": None,
        "summary": {"total_scenarios": 0, "passed_scenarios": 0},
        "failures": [{"check": "drill_state", "expected": "present", "actual": "missing"}],
    }
    if not selected.is_file():
        return missing
    try:
        if selected.stat().st_size > MAX_DRILL_BYTES:
            raise ValueError("drill state exceeds size limit")
        payload = json.loads(selected.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("drill state must be an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            **missing,
            "status": "invalid",
            "failures": [{"check": "drill_state", "expected": "valid JSON", "actual": str(exc)[:300]}],
        }
    checked = _parse_time(payload.get("checked_at"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = max(0, int((current - checked).total_seconds())) if checked else None
    stale = checked is None or age is None or age > stale_after_seconds
    healthy = payload.get("healthy") is True and not stale
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if stale:
        failures = [*failures, {"check": "drill_freshness", "expected": {"maximum_age_seconds": stale_after_seconds}, "actual": age}]
    return {
        "status": "stale" if stale else ("healthy" if healthy else "unhealthy"),
        "healthy": healthy,
        "checked_at": checked.isoformat() if checked else None,
        "age_seconds": age,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "failures": failures[:50],
        "scenarios": payload.get("scenarios") if isinstance(payload.get("scenarios"), list) else [],
    }
