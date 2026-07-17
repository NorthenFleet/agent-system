"""Deterministic signal rules for mission-planning agent proposals."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any


DEFAULT_COOLDOWN_SECONDS = 300
STAGNANT_CHECK_THRESHOLD = 3
REPLAN_STORM_THRESHOLD = 3


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _event_fingerprint(event: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "timestamp": event.get("timestamp"),
            "event_type": event.get("event_type"),
            "level": event.get("level"),
            "message": event.get("message"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _diagnosis_label(snapshot: dict[str, Any]) -> str:
    diagnosis = snapshot.get("last_diagnosis")
    if not isinstance(diagnosis, dict):
        return ""
    return str(
        diagnosis.get("root_cause")
        or diagnosis.get("level")
        or diagnosis.get("condition")
        or ""
    )[:120]


def evaluate_signals(
    snapshot: dict[str, Any],
    previous_state: dict[str, Any] | None = None,
    *,
    run_id: str = "",
    run_started_epoch: float = 0,
    now_epoch: float | None = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return at most one highest-priority proposal and the next persisted state."""
    now = float(now_epoch if now_epoch is not None else time.time())
    state = dict(previous_state or {})
    running = bool(snapshot.get("running"))
    tick_count = _integer(snapshot.get("tick_count"))
    summary = snapshot.get("plan_summary") if isinstance(snapshot.get("plan_summary"), dict) else {}
    done = _integer(summary.get("done"))
    total_replans = _integer(snapshot.get("total_replans"))
    previous_tick = _integer(state.get("last_tick_count"))
    previous_done = _integer(state.get("last_done"))
    previous_replans = _integer(state.get("last_total_replans"))
    same_run = bool(state.get("run_id")) and state.get("run_id") == run_id

    if running and same_run and tick_count == previous_tick and done == previous_done:
        stagnant_checks = _integer(state.get("stagnant_checks")) + 1
    else:
        stagnant_checks = 0
    replan_delta = max(total_replans - previous_replans, 0) if same_run else 0

    state.update({
        "run_id": run_id,
        "last_tick_count": tick_count,
        "last_done": done,
        "last_total_replans": total_replans,
        "last_eval_score": _number(snapshot.get("eval_score")),
        "last_eval_status": str(snapshot.get("last_eval_status") or ""),
        "stagnant_checks": stagnant_checks,
        "last_sample_epoch": now,
    })

    seen_events = list(state.get("seen_event_fingerprints") or [])[-20:]
    new_error_event = None
    events = snapshot.get("recent_events") if isinstance(snapshot.get("recent_events"), list) else []
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        fingerprint = _event_fingerprint(event)
        if fingerprint not in seen_events:
            seen_events.append(fingerprint)
            event_type = str(event.get("event_type") or "")
            level = str(event.get("level") or "").lower()
            event_epoch = _number(event.get("timestamp"))
            belongs_to_run = not run_started_epoch or not event_epoch or event_epoch >= run_started_epoch
            if belongs_to_run and (level == "error" or event_type in {"tick_error", "tick_exception"}):
                new_error_event = {**event, "fingerprint": fingerprint}
                break
    state["seen_event_fingerprints"] = seen_events[-20:]

    urgent_count = _integer(snapshot.get("consecutive_urgent"))
    eval_status = str(snapshot.get("last_eval_status") or "").upper()
    last_tick = snapshot.get("last_tick") if isinstance(snapshot.get("last_tick"), dict) else {}
    diagnosis = _diagnosis_label(snapshot)
    candidates: list[dict[str, Any]] = []

    if new_error_event:
        message = str(new_error_event.get("message") or new_error_event.get("event_type") or "执行异常")[:240]
        candidates.append({
            "rule_id": "execution_error",
            "tool_name": "stop_run",
            "severity": "critical",
            "reason": f"5130执行异常，建议停止并检查：{message}",
            "evidence": {"event": message, "event_type": new_error_event.get("event_type")},
        })
    if replan_delta >= REPLAN_STORM_THRESHOLD:
        candidates.append({
            "rule_id": "replan_storm",
            "tool_name": "stop_run",
            "severity": "critical",
            "reason": f"单次监控间隔内发生 {replan_delta} 次重规划，建议暂停运行并检查规划稳定性",
            "evidence": {"replan_delta": replan_delta, "total_replans": total_replans},
        })
    if eval_status == "URGENT" and urgent_count >= 5:
        candidates.append({
            "rule_id": "persistent_urgent_critical",
            "tool_name": "stop_run",
            "severity": "critical",
            "reason": f"态势连续 {urgent_count} 次处于紧急状态，建议暂停推演并人工复核",
            "evidence": {"consecutive_urgent": urgent_count, "eval_score": snapshot.get("eval_score"), "diagnosis": diagnosis},
        })
    if (
        eval_status == "URGENT"
        and urgent_count >= 2
        and not bool(last_tick.get("replan_triggered"))
        and replan_delta == 0
    ):
        suffix = f"，诊断：{diagnosis}" if diagnosis else ""
        candidates.append({
            "rule_id": "persistent_urgent",
            "tool_name": "replan",
            "severity": "high",
            "reason": f"态势连续 {urgent_count} 次处于紧急状态且最近未触发重规划{suffix}",
            "evidence": {"consecutive_urgent": urgent_count, "eval_score": snapshot.get("eval_score"), "diagnosis": diagnosis},
        })
    if running and stagnant_checks >= STAGNANT_CHECK_THRESHOLD:
        candidates.append({
            "rule_id": "execution_stagnation",
            "tool_name": "replan",
            "severity": "medium",
            "reason": f"连续 {stagnant_checks} 次采样未发现推演步或任务进展，建议重新规划",
            "evidence": {"tick_count": tick_count, "done": done, "stagnant_checks": stagnant_checks},
        })

    severity_rank = {"critical": 3, "high": 2, "medium": 1}
    candidates.sort(key=lambda row: severity_rank.get(str(row.get("severity")), 0), reverse=True)
    emitted = dict(state.get("last_emitted_at") or {})
    suggestions: list[dict[str, Any]] = []
    for candidate in candidates:
        trigger_key = f"{run_id or 'no-run'}:{candidate['rule_id']}"
        last_emitted = _number(emitted.get(trigger_key))
        if now - last_emitted < max(cooldown_seconds, 0):
            continue
        emitted[trigger_key] = now
        candidate["trigger_key"] = trigger_key
        candidate["triggered_at_epoch"] = now
        suggestions.append(candidate)
        break
    state["last_emitted_at"] = emitted
    state["health"] = "attention" if candidates else "healthy"
    return suggestions, state
