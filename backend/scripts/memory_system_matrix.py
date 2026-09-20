#!/usr/bin/env python3
"""Run the multi-agent memory regression matrix against the live 3021 ingress."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
for root in (BACKEND_ROOT, SCRIPT_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from memory_system_gate import (
    DEFAULT_NOTIFY_ENDPOINT,
    DEFAULT_STATE_DB,
    publish_health,
    request_report,
    resolve_identity,
    write_status,
)
from services.memory_system_gate import evaluate_memory_report
from services.memory_system_matrix import summarize_matrix
from services.memory_system_slo import append_health_sample


DEFAULT_EVAL = BACKEND_ROOT / "evals" / "memory_introspection_matrix.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "data" / "memory-system-matrix.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_dataset(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load memory matrix dataset: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list) or not value["cases"]:
        raise RuntimeError("memory matrix dataset has no cases")
    return value


def main() -> int:
    started_at = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:3021/api/v3/command-center/agent/memory-context",
    )
    parser.add_argument("--notify-endpoint", default=DEFAULT_NOTIFY_ENDPOINT)
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument("--external-user-id", default="", help=argparse.SUPPRESS)
    parser.add_argument("--channel", default="feishu", help=argparse.SUPPRESS)
    args = parser.parse_args()

    checked_at = _now()
    try:
        dataset = load_dataset(args.eval_file)
        identity = (
            {"channel": str(args.channel).lower(), "external_user_id": str(args.external_user_id).strip()}
            if str(args.external_user_id).strip()
            else resolve_identity(args.state_db)
        )
        case_results: list[dict[str, Any]] = []
        attempts = max(1, min(int(args.attempts), 3))
        for case in dataset["cases"]:
            request_config = case.get("request") if isinstance(case.get("request"), dict) else {}
            evaluated: dict[str, Any] = {}
            for attempt in range(1, attempts + 1):
                try:
                    report = request_report(
                        args.endpoint,
                        identity=identity,
                        case=case,
                        timeout=max(1.0, args.timeout),
                    )
                    evaluated = evaluate_memory_report(report, case.get("contract") or {})
                except Exception as exc:
                    evaluated = {
                        "healthy": False,
                        "failures": [
                            {"check": "case_execution", "expected": "success", "actual": str(exc)[:500]}
                        ],
                        "summary": {},
                    }
                if evaluated["healthy"] or attempt == attempts:
                    break
                time.sleep(max(0.0, min(float(args.retry_delay), 30.0)))
            case_results.append(
                {
                    "case_id": str(case.get("id") or ""),
                    "agent_id": str(request_config.get("agent_id") or "optimus"),
                    "healthy": evaluated["healthy"],
                    "failures": evaluated["failures"],
                    "summary": evaluated["summary"],
                }
            )
        matrix = summarize_matrix(case_results, dataset.get("invariants") or {})
        failures = [
            *matrix["invariant_failures"],
            *[
                {"check": f"case.{case['case_id']}", "expected": "healthy", "actual": case["failures"]}
                for case in case_results
                if not case["healthy"]
            ],
        ]
        status = {
            "schema_version": "memory-system-matrix.v1",
            "checked_at": checked_at,
            "healthy": matrix["healthy"],
            "summary": matrix,
            "failures": failures,
            "cases": case_results,
        }
    except Exception as exc:
        status = {
            "schema_version": "memory-system-matrix.v1",
            "checked_at": checked_at,
            "healthy": False,
            "summary": {"total_cases": 0, "passed_cases": 0, "failed_cases": []},
            "failures": [{"check": "matrix_execution", "expected": "success", "actual": str(exc)[:1000]}],
            "cases": [],
        }

    try:
        delivery = publish_health(
            args.notify_endpoint,
            {**status, "case_id": "multi-agent-memory-matrix"},
            max(1.0, args.timeout),
            monitor_key="matrix",
        )
        status["summary"]["notification_delivery"] = delivery
    except RuntimeError as exc:
        status["healthy"] = False
        status["summary"]["notification_delivery"] = {"status": "failed", "reason": str(exc)[:500]}
        status["failures"].append(
            {"check": "notification_delivery", "expected": "accepted", "actual": str(exc)[:500]}
        )

    duration_ms = (time.monotonic() - started_at) * 1000
    status["duration_ms"] = round(duration_ms, 1)
    try:
        append_health_sample(status, monitor_key="matrix", duration_ms=duration_ms)
        status.setdefault("summary", {})["history_recording"] = {"status": "recorded"}
    except (OSError, ValueError) as exc:
        status.setdefault("summary", {})["history_recording"] = {
            "status": "failed",
            "reason": str(exc)[:300],
        }
    write_status(args.output, status)
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status["healthy"] else 2


if __name__ == "__main__":
    sys.exit(main())
