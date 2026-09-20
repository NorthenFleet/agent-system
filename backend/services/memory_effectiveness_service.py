"""Real-effect memory evaluation and privacy-minimized outcome evidence.

Retrieval quality and task effectiveness are deliberately separated here:
offline cases tell us whether the right memory was selected, while append-only
effect events tell us whether a selected memory was actually used and whether
the task succeeded or required a correction.  Query text, memory content and
free-form user feedback are never copied into the effect-event table.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EFFECTIVENESS_VERSION = "memory-effectiveness.v1"
DATASET_VERSION = "memory-effectiveness-dataset.v1"
EFFECT_EVENT_TYPES = {"selected", "used", "task_outcome", "correction"}
OUTCOMES = {
    "unknown",
    "accepted",
    "rejected",
    "success",
    "partial",
    "failure",
    "corrected",
    "forgotten",
}
REQUIRED_SCENARIOS = {
    "recall",
    "abstention",
    "update",
    "conflict",
    "expiry",
    "forget",
    "user_isolation",
    "project_isolation",
    "agent_isolation",
}
SCOPE_SCENARIOS = {"user_isolation", "project_isolation", "agent_isolation"}
LIFECYCLE_SCENARIOS = {"update", "conflict", "expiry", "forget"}
ALLOWED_METADATA_KEYS = {
    "task_type",
    "consumer",
    "channel",
    "latency_bucket",
    "result_bucket",
    "correction_kind",
}


class MemoryEffectivenessError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _fingerprint(value: Any) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _safe_metadata(value: Any) -> dict[str, str | int | float | bool]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str | int | float | bool] = {}
    for key in sorted(ALLOWED_METADATA_KEYS):
        item = value.get(key)
        if isinstance(item, bool):
            result[key] = item
        elif isinstance(item, (int, float)):
            result[key] = item
        elif isinstance(item, str) and item.strip():
            result[key] = item.strip()[:120]
    return result


def ensure_memory_effect_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_effect_events (
            id TEXT PRIMARY KEY,
            pack_id TEXT NOT NULL,
            user_fingerprint TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source_ref_fingerprints TEXT NOT NULL DEFAULT '[]',
            task_id_fingerprint TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL DEFAULT 'unknown',
            reason_code TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(pack_id) REFERENCES context_packs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_effect_events_recent
            ON memory_effect_events(created_at DESC, event_type, outcome);

        CREATE INDEX IF NOT EXISTS idx_memory_effect_events_pack
            ON memory_effect_events(pack_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_memory_effect_events_user
            ON memory_effect_events(user_fingerprint, created_at DESC);
        """
    )


def _pack_source_refs(conn: sqlite3.Connection, pack_id: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT source_ref FROM context_pack_items WHERE pack_id=?", (pack_id,)
        ).fetchall()
        if str(row[0] or "").strip()
    }


def _insert_effect_event(
    conn: sqlite3.Connection,
    *,
    pack_id: str,
    user_id: str,
    event_type: str,
    source_refs: list[str],
    task_id: str = "",
    outcome: str = "unknown",
    reason_code: str = "",
    metadata: dict[str, Any] | None = None,
    idempotency_key: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    ensure_memory_effect_schema(conn)
    fingerprints = sorted({_fingerprint(ref) for ref in source_refs if str(ref).strip()})
    event_id = f"memory-effect-{uuid.uuid4().hex[:16]}"
    timestamp = created_at or _now()
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_effect_events
        (id, pack_id, user_fingerprint, event_type, source_ref_fingerprints,
         task_id_fingerprint, outcome, reason_code, metadata, idempotency_key,
         created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            str(pack_id),
            _fingerprint(user_id),
            event_type,
            _json(fingerprints),
            _fingerprint(task_id) if str(task_id or "").strip() else "",
            outcome,
            reason_code,
            _json(_safe_metadata(metadata)),
            idempotency_key,
            timestamp,
        ),
    )
    row = conn.execute(
        "SELECT * FROM memory_effect_events WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    result = dict(row)
    result["source_ref_fingerprints"] = _loads(
        result["source_ref_fingerprints"], []
    )
    result["metadata"] = _loads(result["metadata"], {})
    return result


def record_retrieval_selection(
    conn: sqlite3.Connection,
    *,
    pack_id: str,
    user_id: str,
    source_refs: list[str],
    task_id: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record the selected-memory stage without duplicating raw memory data."""
    refs = [str(ref).strip() for ref in source_refs if str(ref).strip()]
    identity = _fingerprint((pack_id, sorted(refs)))
    return _insert_effect_event(
        conn,
        pack_id=pack_id,
        user_id=user_id,
        event_type="selected",
        source_refs=refs,
        task_id=task_id,
        idempotency_key=f"selected:{pack_id}:{identity}",
        created_at=created_at,
    )


def record_effect_observation(
    conn: sqlite3.Connection,
    *,
    pack_id: str,
    user_id: str,
    event_type: str,
    source_refs: list[str] | None = None,
    task_id: str = "",
    outcome: str = "unknown",
    reason_code: str = "",
    metadata: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    clean_event = str(event_type or "").strip().lower()
    if clean_event not in EFFECT_EVENT_TYPES - {"selected"}:
        raise MemoryEffectivenessError(
            "event_type must be used, task_outcome, or correction"
        )
    clean_outcome = str(outcome or "unknown").strip().lower()
    if clean_outcome not in OUTCOMES:
        raise MemoryEffectivenessError("unsupported memory-effect outcome")
    clean_reason = str(reason_code or "").strip().lower()
    if clean_reason and not re.fullmatch(r"[a-z0-9_.-]{1,80}", clean_reason):
        raise MemoryEffectivenessError("reason_code must be a stable machine code")
    ensure_memory_effect_schema(conn)
    pack = conn.execute(
        "SELECT id, user_id FROM context_packs WHERE id=?", (str(pack_id),)
    ).fetchone()
    if not pack:
        raise MemoryEffectivenessError("context pack not found")
    if str(pack["user_id"]) != str(user_id):
        raise MemoryEffectivenessError("context pack belongs to another user")
    refs = list(dict.fromkeys(str(ref).strip() for ref in (source_refs or []) if str(ref).strip()))
    unknown_refs = set(refs) - _pack_source_refs(conn, str(pack_id))
    if unknown_refs:
        raise MemoryEffectivenessError(
            "effect observation references memory outside the context pack"
        )
    clean_key = str(idempotency_key or "").strip()[:240]
    if not clean_key:
        clean_key = "effect:" + _fingerprint(
            {
                "pack_id": pack_id,
                "event_type": clean_event,
                "refs": refs,
                "task_id": task_id,
                "outcome": clean_outcome,
                "reason": clean_reason,
            }
        )
    else:
        # Caller keys are scoped before persistence so two users or packs cannot
        # collide and receive another observation through INSERT OR IGNORE.
        clean_key = "effect:" + _fingerprint(
            {"user_id": str(user_id), "pack_id": str(pack_id), "key": clean_key}
        )
    return _insert_effect_event(
        conn,
        pack_id=str(pack_id),
        user_id=str(user_id),
        event_type=clean_event,
        source_refs=refs,
        task_id=task_id,
        outcome=clean_outcome,
        reason_code=clean_reason,
        metadata=metadata,
        idempotency_key=clean_key,
    )


def summarize_effect_observations(
    conn: sqlite3.Connection, *, user_id: str
) -> dict[str, Any]:
    ensure_memory_effect_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM memory_effect_events
        WHERE user_fingerprint=? ORDER BY created_at
        """,
        (_fingerprint(user_id),),
    ).fetchall()
    records = [dict(row) for row in rows]
    by_type = Counter(str(row["event_type"]) for row in records)
    selected_packs = {
        str(row["pack_id"]) for row in records if row["event_type"] == "selected"
    }
    used_packs = {
        str(row["pack_id"]) for row in records if row["event_type"] == "used"
    }
    outcome_rows = [row for row in records if row["event_type"] == "task_outcome"]
    correction_packs = {
        str(row["pack_id"]) for row in records if row["event_type"] == "correction"
    }
    successful = sum(row["outcome"] == "success" for row in outcome_rows)
    observed_packs = used_packs | {str(row["pack_id"]) for row in outcome_rows}
    return {
        "version": EFFECTIVENESS_VERSION,
        "privacy": {
            "stores_query_text": False,
            "stores_memory_content": False,
            "source_references_hashed": True,
            "metadata_allowlisted": True,
        },
        "events": {"total": len(records), "by_type": dict(sorted(by_type.items()))},
        "funnel": {
            "selected_packs": len(selected_packs),
            "used_packs": len(used_packs),
            "outcome_packs": len({str(row["pack_id"]) for row in outcome_rows}),
            "corrected_packs": len(correction_packs),
            "selection_to_usage_rate": _ratio(len(used_packs), len(selected_packs)),
            "usage_observation_rate": _ratio(len(observed_packs), len(selected_packs)),
        },
        "outcomes": {
            "observed": len(outcome_rows),
            "success": successful,
            "success_rate": _ratio(successful, len(outcome_rows)),
            "correction_rate": _ratio(len(correction_packs), len(observed_packs)),
        },
        "evidence_ready": bool(selected_packs and len(observed_packs) == len(selected_packs)),
    }


def _authority_rows(conn: sqlite3.Connection, owner_user_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    profile = conn.execute(
        "SELECT id FROM user_context_profiles WHERE user_id=? AND status='active'",
        (str(owner_user_id),),
    ).fetchone()
    if profile:
        for row in conn.execute(
            """
            SELECT id, fact_key AS title, fact_value AS content, importance,
                   updated_at FROM profile_facts
            WHERE profile_id=? AND status='active'
            ORDER BY CASE importance WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                     updated_at DESC, id
            """,
            (profile["id"],),
        ).fetchall():
            rows.append(
                {
                    **dict(row),
                    "source_ref": f"fact:{row['id']}",
                    "source_type": "profile_fact",
                    "user_id": str(owner_user_id),
                    "project_id": "",
                    "agent_id": "optimus",
                }
            )
    for row in conn.execute(
        """
        SELECT id, title, content, importance, project_id, updated_at
        FROM project_context_memories
        WHERE user_id=? AND status='active'
        ORDER BY updated_at DESC, id
        """,
        (str(owner_user_id),),
    ).fetchall():
        rows.append(
            {
                **dict(row),
                "source_ref": f"project-memory:{row['id']}",
                "source_type": "project_memory",
                "user_id": str(owner_user_id),
                "agent_id": "optimus",
            }
        )
    for row in conn.execute(
        """
        SELECT id, title, content, project_id, agent_id, metadata, updated_at
        FROM agent_memories
        WHERE user_id=? AND status='active' AND source LIKE 'mission:%'
        ORDER BY updated_at DESC, id
        """,
        (str(owner_user_id),),
    ).fetchall():
        metadata = _loads(row["metadata"], {})
        rows.append(
            {
                **dict(row),
                "importance": str(metadata.get("importance") or "normal"),
                "source_ref": f"agent-memory:{row['id']}",
                "source_type": "agent_memory",
                "user_id": str(owner_user_id),
            }
        )
    return rows


def build_provisional_dataset(
    conn: sqlite3.Connection, *, owner_user_id: str, target_cases: int = 80
) -> dict[str, Any]:
    """Build a reproducible, de-identified *provisional* dataset.

    It intentionally does not claim human truth. The source text is reduced to
    stable hashes and only the existing title/key is used to form test queries.
    """
    sources = _authority_rows(conn, owner_user_id)
    templates = (
        "{title}",
        "关于{title}，当前有效规则是什么？",
        "处理{title}相关任务时需要遵循什么？",
        "如果遇到{title}，有哪些限制和注意事项？",
        "请根据已经确认的记忆说明{title}。",
    )
    cases: list[dict[str, Any]] = []
    positive_target = max(0, int(target_cases) - 5)
    for source in sources:
        for variant, template in enumerate(templates, start=1):
            if len(cases) >= positive_target:
                break
            cases.append(
                {
                    "id": f"phase1-recall-{_fingerprint((source['source_ref'], variant))[:16]}",
                    "scenario": "recall",
                    "source_type": source["source_type"],
                    "variant_key": f"template_{variant}",
                    "query": template.format(title=str(source["title"])[:160]),
                    "user_id": str(owner_user_id),
                    "project_id": str(source.get("project_id") or ""),
                    "agent_id": str(source.get("agent_id") or "optimus"),
                    "limit": 10,
                    "expected_source_refs": [source["source_ref"]],
                    "forbidden_source_refs": [],
                    "importance": str(source.get("importance") or "normal"),
                    "label_status": "provisional",
                    "relevance_judgment": "partial",
                    "source_snapshot_hash": _fingerprint(source.get("content")),
                }
            )
        if len(cases) >= positive_target:
            break

    negative_candidates: list[dict[str, Any]] = []
    for source in sources:
        if source["source_type"] == "project_memory":
            negative_candidates.append(
                {
                    "scenario": "project_isolation",
                    "user_id": str(owner_user_id),
                    "project_id": "phase1-isolated-project",
                    "agent_id": str(source.get("agent_id") or "optimus"),
                    "source": source,
                }
            )
        elif source["source_type"] == "agent_memory":
            negative_candidates.append(
                {
                    "scenario": "agent_isolation",
                    "user_id": str(owner_user_id),
                    "project_id": str(source.get("project_id") or ""),
                    "agent_id": "phase1-isolated-agent",
                    "source": source,
                }
            )
        else:
            negative_candidates.append(
                {
                    "scenario": "user_isolation",
                    "user_id": "phase1-isolated-user",
                    "project_id": "",
                    "agent_id": "optimus",
                    "source": source,
                }
            )
    scenario_counts: Counter[str] = Counter()
    for candidate in negative_candidates:
        if len(cases) >= int(target_cases):
            break
        scenario = str(candidate["scenario"])
        if scenario_counts[scenario] >= 2:
            continue
        source = candidate["source"]
        cases.append(
            {
                "id": f"phase1-{scenario}-{_fingerprint(source['source_ref'])[:16]}",
                "scenario": scenario,
                "source_type": source["source_type"],
                "variant_key": "isolation",
                "query": f"请说明{str(source['title'])[:160]}。",
                "user_id": candidate["user_id"],
                "project_id": candidate["project_id"],
                "agent_id": candidate["agent_id"],
                "limit": 10,
                "expected_source_refs": [],
                "forbidden_source_refs": [source["source_ref"]],
                "importance": str(source.get("importance") or "normal"),
                "label_status": "provisional",
                "relevance_judgment": "partial",
                "source_snapshot_hash": _fingerprint(source.get("content")),
            }
        )
        scenario_counts[scenario] += 1

    cases = cases[: max(1, min(int(target_cases), 1000))]
    dataset_hash = _fingerprint(
        [
            {
                key: case[key]
                for key in (
                    "id",
                    "scenario",
                    "source_type",
                    "variant_key",
                    "query",
                    "user_id",
                    "project_id",
                    "agent_id",
                    "expected_source_refs",
                    "forbidden_source_refs",
                    "label_status",
                    "relevance_judgment",
                    "source_snapshot_hash",
                )
            }
            for case in cases
        ]
    )
    return {
        "schema_version": DATASET_VERSION,
        "dataset_id": f"phase1-authority-snapshot-{dataset_hash[:12]}",
        "dataset_hash": dataset_hash,
        "owner_user_id": str(owner_user_id),
        "generated_at": _now(),
        "provenance": {
            "authority": "3021-unified-memory",
            "source_count": len(sources),
            "contains_memory_content": False,
            "label_status": "provisional",
            "human_verification_required": True,
        },
        "cases": cases,
    }


def save_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json(payload) + "\n", encoding="utf-8")


def load_dataset(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != DATASET_VERSION:
        raise MemoryEffectivenessError("unsupported effectiveness dataset version")
    if not isinstance(payload.get("cases"), list) or not payload["cases"]:
        raise MemoryEffectivenessError("effectiveness dataset has no cases")
    return payload


def evaluate_effectiveness_dataset(
    context_service: Any, dataset: dict[str, Any]
) -> dict[str, Any]:
    cases = list(dataset.get("cases") or [])
    observations: list[dict[str, Any]] = []
    attributions: Counter[str] = Counter()
    by_scenario: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "passed": 0, "expected": 0, "recalled": 0, "forbidden_hits": 0}
    )
    expected_total = recalled_total = forbidden_hits = important_total = important_recalled = 0
    top5_expected_cases = top5_hit_cases = 0
    precision_hits = precision_denominator = precision_cases = degraded_cases = 0
    scope_leaks = stale_hits = deletion_residue = 0
    failures_by_source_type: Counter[str] = Counter()
    failures_by_variant: Counter[str] = Counter()
    abstention_cases = abstention_passed = false_supports = 0

    for case in cases:
        expected = list(dict.fromkeys(case.get("expected_source_refs") or []))
        forbidden = set(case.get("forbidden_source_refs") or [])
        scenario = str(case.get("scenario") or "recall")
        try:
            pack = context_service.retrieve(
                user_id=str(case.get("user_id") or dataset.get("owner_user_id") or ""),
                query=str(case.get("query") or ""),
                project_id=str(case.get("project_id") or ""),
                agent_id=str(case.get("agent_id") or "optimus"),
                purpose="memory-effectiveness-evaluation",
                limit=max(1, min(int(case.get("limit") or 10), 50)),
                persist=False,
                graph_mode="disabled",
            )
            refs = [str(item.get("source_ref") or "") for item in pack.get("items") or []]
            health = pack.get("retrieval_health") or {}
            decision = pack.get("retrieval_decision") or (
                health.get("retrieval_decision", {})
                if isinstance(health, dict)
                else {}
            )
            actual_decision = str(
                decision.get("status") if isinstance(decision, dict) else ""
            )
            degraded_channels = []
            for key, value in health.items():
                if key not in {"profile", "approved_memory", "vector_memory"} or not isinstance(value, dict):
                    continue
                status = value.get("status")
                if status in {"degraded", "error"} or (
                    status == "missing"
                    and not (scenario == "user_isolation" and key == "profile")
                ):
                    degraded_channels.append(key)
            degraded = bool(degraded_channels)
            error = ""
        except Exception as exc:
            refs, degraded, error, actual_decision = [], True, str(exc)[:500], ""
        recalled = [ref for ref in expected if ref in refs]
        forbidden_found = sorted(forbidden & set(refs))
        expected_decision = str(case.get("expected_decision") or "").strip()
        if not expected_decision and scenario == "abstention":
            expected_decision = "abstain"
        decision_passed = (
            not expected_decision or actual_decision == expected_decision
        )
        passed = (
            len(recalled) == len(expected)
            and not forbidden_found
            and decision_passed
        )
        expected_total += len(expected)
        recalled_total += len(recalled)
        important = str(case.get("importance") or "normal") in {"critical", "high"}
        if important:
            important_total += len(expected)
            important_recalled += len(recalled)
        top5 = refs[:5]
        if expected:
            top5_expected_cases += 1
            top5_hit_cases += int(bool(set(expected) & set(top5)))
        if case.get("relevance_judgment") == "exhaustive":
            precision_cases += 1
            precision_hits += len(set(expected) & set(top5))
            precision_denominator += len(top5)
        forbidden_hits += len(forbidden_found)
        degraded_cases += int(degraded)
        if forbidden_found and scenario in SCOPE_SCENARIOS:
            scope_leaks += len(forbidden_found)
            attributions["scope_filter_failure"] += 1
        elif forbidden_found and scenario in LIFECYCLE_SCENARIOS:
            stale_hits += len(forbidden_found)
            deletion_residue += len(forbidden_found) if scenario == "forget" else 0
            attributions["lifecycle_filter_failure"] += 1
        if expected and len(recalled) != len(expected):
            attributions["retrieval_miss"] += 1
        if degraded:
            attributions["retrieval_infrastructure_degraded"] += 1
        if scenario == "abstention":
            abstention_cases += 1
            abstention_passed += int(decision_passed)
            if actual_decision != "abstain":
                false_supports += 1
                attributions["abstention_failure"] += 1
        if passed:
            attributions["passed"] += 1
        else:
            failures_by_source_type[str(case.get("source_type") or "unknown")] += 1
            failures_by_variant[str(case.get("variant_key") or "unknown")] += 1
        scenario_bucket = by_scenario[scenario]
        scenario_bucket["cases"] += 1
        scenario_bucket["passed"] += int(passed)
        scenario_bucket["expected"] += len(expected)
        scenario_bucket["recalled"] += len(recalled)
        scenario_bucket["forbidden_hits"] += len(forbidden_found)
        observations.append(
            {
                "case_id": case.get("id"),
                "scenario": scenario,
                "passed": passed,
                "returned_refs": refs,
                "recalled_refs": recalled,
                "forbidden_hits": forbidden_found,
                "expected_decision": expected_decision or None,
                "actual_decision": actual_decision or None,
                "decision_passed": decision_passed,
                "degraded": degraded,
                "error": error,
            }
        )

    verified_cases = sum(case.get("label_status") == "verified" for case in cases)
    controlled_verified_cases = sum(
        case.get("label_status") == "verified"
        and case.get("verification_method") == "controlled_fixture"
        for case in cases
    )
    human_verified_cases = verified_cases - controlled_verified_cases
    present_scenarios = {str(case.get("scenario") or "") for case in cases}
    metrics = {
        "cases": len(cases),
        "case_pass_rate": _ratio(sum(item["passed"] for item in observations), len(cases)),
        "recall": _ratio(recalled_total, expected_total),
        "important_recall": _ratio(important_recalled, important_total),
        "top5_hit_rate": _ratio(top5_hit_cases, top5_expected_cases),
        "precision_at_5": (
            _ratio(precision_hits, precision_denominator) if precision_cases else None
        ),
        "precision_at_5_evaluable_cases": precision_cases,
        "forbidden_hits": forbidden_hits,
        "false_memory_rate": _ratio(
            sum(bool(item["forbidden_hits"]) for item in observations), len(cases)
        ),
        "stale_recall_hits": stale_hits,
        "cross_scope_leakage_hits": scope_leaks,
        "deletion_projection_residue_hits": deletion_residue,
        "degraded_cases": degraded_cases,
        "abstention_cases": abstention_cases,
        "abstention_accuracy": (
            _ratio(abstention_passed, abstention_cases)
            if abstention_cases
            else None
        ),
        "false_supports": false_supports,
    }
    quality_checks = {
        "important_recall_gte_0_90": metrics["important_recall"] >= 0.90,
        "precision_at_5_gte_0_85": bool(
            metrics["precision_at_5"] is not None
            and metrics["precision_at_5"] >= 0.85
        ),
        "false_memory_rate_lte_0_02": metrics["false_memory_rate"] <= 0.02,
        "stale_recall_zero": stale_hits == 0,
        "cross_scope_leakage_zero": scope_leaks == 0,
        "deletion_projection_residue_zero": deletion_residue == 0,
        "retrieval_not_degraded": degraded_cases == 0,
        "abstention_accuracy_gte_0_95": bool(
            abstention_cases
            and metrics["abstention_accuracy"] is not None
            and metrics["abstention_accuracy"] >= 0.95
        ),
    }
    data_checks = {
        "minimum_80_cases": len(cases) >= 80,
        "minimum_80_verified_cases": human_verified_cases >= 80,
        "required_scenarios_covered": REQUIRED_SCENARIOS <= present_scenarios,
        "content_not_embedded": not bool(
            (dataset.get("provenance") or {}).get("contains_memory_content")
        ),
    }
    scenario_report = {}
    for name, values in sorted(by_scenario.items()):
        scenario_report[name] = {
            **values,
            "pass_rate": _ratio(values["passed"], values["cases"]),
            "recall": _ratio(values["recalled"], values["expected"]),
        }
    return {
        "version": EFFECTIVENESS_VERSION,
        "dataset_id": dataset.get("dataset_id"),
        "dataset_hash": dataset.get("dataset_hash"),
        "generated_at": _now(),
        "metrics": metrics,
        "by_scenario": scenario_report,
        "quality_checks": quality_checks,
        "data_quality": {
            "verified_cases": verified_cases,
            "human_verified_cases": human_verified_cases,
            "controlled_verified_cases": controlled_verified_cases,
            "provisional_cases": len(cases) - verified_cases,
            "present_scenarios": sorted(present_scenarios),
            "missing_scenarios": sorted(REQUIRED_SCENARIOS - present_scenarios),
            "checks": data_checks,
            "ready": all(data_checks.values()),
        },
        "effectiveness_gate": {
            "ready": all(quality_checks.values()) and all(data_checks.values()),
            "automatic_rollout": False,
            "blockers": [
                *[f"quality:{name}" for name, passed in quality_checks.items() if not passed],
                *[f"data:{name}" for name, passed in data_checks.items() if not passed],
            ],
        },
        "error_attribution": dict(sorted(attributions.items())),
        "failure_breakdown": {
            "by_source_type": dict(sorted(failures_by_source_type.items())),
            "by_variant": dict(sorted(failures_by_variant.items())),
        },
        "observations": observations,
    }
