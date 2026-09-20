#!/usr/bin/env python3
"""Run the real Optimus memory question as an operational health gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.memory_system_gate import (
    MemorySystemGateError,
    enforce_bridge_deployment,
    evaluate_memory_report,
    execution_failure_status,
)
from services.memory_system_slo import append_health_sample


DEFAULT_EVAL = BACKEND_ROOT / "evals" / "memory_introspection_system.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "data" / "memory-system-health.json"
DEFAULT_STATE_DB = Path(
    os.getenv(
        "OPTIMUS_AGENT_STATE_DB",
        "/Users/apple/.openclaw/agents/optimus/agent/openclaw-agent.sqlite",
    )
)
DEFAULT_BRIDGE_DEPLOYER = (
    BACKEND_ROOT.parent / "integrations" / "openclaw" / "graph-memory" / "deploy.py"
)
DEFAULT_BRIDGE_TARGET = Path(os.path.expanduser("~/.openclaw/extensions/graph-memory"))
DEFAULT_NOTIFY_ENDPOINT = "http://127.0.0.1:3021/api/v3/command-center/agent/memory-health"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_identity(state_db: Path) -> dict[str, str]:
    if not state_db.is_file():
        raise RuntimeError(f"Optimus state database is missing: {state_db}")
    try:
        conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=3)
        try:
            rows = conn.execute(
                """
                SELECT identity_namespace, actor_id
                FROM session_participants
                WHERE session_key='agent:optimus:main'
                ORDER BY last_prompted_at DESC
                """
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise RuntimeError(f"cannot read Optimus identity state: {exc}") from exc
    for identity_raw, actor_id in rows:
        try:
            identity = json.loads(identity_raw or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        channel = str(identity.get("pluginId") or "").strip().lower()
        sender_kind = str(identity.get("senderKind") or "").strip().lower()
        external_id = str(actor_id or "").strip().rsplit(":", 1)[-1]
        if channel == "feishu" and sender_kind == "human" and external_id:
            return {"channel": channel, "external_user_id": external_id}
    raise RuntimeError("Optimus has no durable Feishu human identity binding")


def load_case(path: Path, case_id: str = "") -> dict[str, Any]:
    try:
        dataset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load memory evaluation dataset: {exc}") from exc
    cases = dataset.get("cases") if isinstance(dataset, dict) else None
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("memory evaluation dataset has no cases")
    if case_id:
        selected = next((case for case in cases if case.get("id") == case_id), None)
        if not selected:
            raise RuntimeError(f"memory evaluation case does not exist: {case_id}")
    else:
        selected = cases[0]
    if not isinstance(selected, dict) or not str(selected.get("prompt") or "").strip():
        raise RuntimeError("memory evaluation case has no prompt")
    return selected


def request_report(
    endpoint: str,
    *,
    identity: dict[str, str],
    case: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request_config = case.get("request") if isinstance(case.get("request"), dict) else {}
    payload = {
        "channel": identity["channel"],
        "external_user_id": identity["external_user_id"],
        "query": str(case["prompt"]),
        "agent_id": str(request_config.get("agent_id") or "optimus"),
        "project_id": str(request_config.get("project_id") or ""),
        "limit": max(1, min(int(request_config.get("limit") or 12), 50)),
        "persist": bool(request_config.get("persist", False)),
    }
    headers = {"Content-Type": "application/json"}
    token = os.getenv("COMMAND_CENTER_INGRESS_TOKEN", "").strip()
    if token:
        headers["X-Command-Center-Token"] = token
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"memory endpoint HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"memory endpoint unavailable: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("memory endpoint returned a non-object response")
    return result


def write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(status, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def previous_health(path: Path) -> bool | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return bool(value["healthy"]) if isinstance(value, dict) and "healthy" in value else None
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def bridge_deployment_status(deployer: Path, target: Path) -> dict[str, Any]:
    if not deployer.is_file():
        raise RuntimeError(f"graph-memory bridge deployer is missing: {deployer}")
    spec = importlib.util.spec_from_file_location("graph_memory_bridge_gate", deployer)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load graph-memory bridge deployer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.inspect_deployment(target)
    return {
        "ready": result.get("ready") is True,
        "plugin_version": result.get("plugin_version"),
        "bridge_schema": result.get("bridge_schema"),
        "failed_checks": result.get("failed_checks") or [],
    }


def publish_health(
    endpoint: str,
    status: dict[str, Any],
    timeout: float,
    *,
    monitor_key: str = "primary",
) -> dict[str, Any]:
    payload = {
        "monitor_key": monitor_key,
        "schema_version": status.get("schema_version"),
        "checked_at": status.get("checked_at"),
        "healthy": status.get("healthy") is True,
        "case_id": status.get("case_id") or "",
        "failures": status.get("failures") or [],
        "summary": status.get("summary") or {},
    }
    headers = {"Content-Type": "application/json"}
    token = os.getenv("COMMAND_CENTER_INGRESS_TOKEN", "").strip()
    if token:
        headers["X-Command-Center-Token"] = token
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"notification endpoint HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"notification endpoint unavailable: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("notification endpoint returned a non-object response")
    return result


def main() -> int:
    started_at = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:3021/api/v3/command-center/agent/memory-context",
    )
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--case-id", default="")
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--attempts",
        type=int,
        default=2,
        help="retry transient startup failures before publishing an unhealthy state",
    )
    parser.add_argument("--retry-delay", type=float, default=10.0)
    parser.add_argument("--bridge-deployer", type=Path, default=DEFAULT_BRIDGE_DEPLOYER)
    parser.add_argument("--bridge-target", type=Path, default=DEFAULT_BRIDGE_TARGET)
    parser.add_argument("--notify-endpoint", default=DEFAULT_NOTIFY_ENDPOINT)
    parser.add_argument("--external-user-id", default="", help=argparse.SUPPRESS)
    parser.add_argument("--channel", default="feishu", help=argparse.SUPPRESS)
    args = parser.parse_args()

    old_health = previous_health(args.output)
    case_id = args.case_id
    attempts = max(1, min(int(args.attempts), 5))
    status: dict[str, Any] = {}
    attempt_failures: list[list[dict[str, Any]]] = []
    for attempt in range(1, attempts + 1):
        try:
            case = load_case(args.eval_file, case_id)
            case_id = str(case.get("id") or "")
            identity = (
                {"channel": str(args.channel).lower(), "external_user_id": str(args.external_user_id).strip()}
                if str(args.external_user_id).strip()
                else resolve_identity(args.state_db)
            )
            report = request_report(
                args.endpoint,
                identity=identity,
                case=case,
                timeout=max(1.0, args.timeout),
            )
            evaluated = evaluate_memory_report(report, case.get("contract") or {})
            status = {
                "schema_version": "memory-system-health.v1",
                "checked_at": _now(),
                "case_id": case_id,
                "prompt_sha256": hashlib.sha256(str(case["prompt"]).encode("utf-8")).hexdigest(),
                "attempt": attempt,
                "attempts_configured": attempts,
                **evaluated,
            }
        except (RuntimeError, MemorySystemGateError, OSError, ValueError) as exc:
            status = execution_failure_status(
                case_id=case_id,
                error=exc,
                attempt=attempt,
                attempts_configured=attempts,
                checked_at=_now(),
            )
        if status["healthy"]:
            break
        attempt_failures.append(status["failures"])
        if attempt < attempts:
            time.sleep(max(0.0, min(float(args.retry_delay), 60.0)))

    if attempt_failures:
        status["failed_attempts"] = len(attempt_failures)
    try:
        bridge = bridge_deployment_status(args.bridge_deployer, args.bridge_target)
    except Exception as exc:
        bridge = {
            "ready": False,
            "plugin_version": None,
            "bridge_schema": None,
            "failed_checks": [f"inspection failed: {str(exc)[:500]}"],
        }
    enforce_bridge_deployment(status, bridge)

    try:
        delivery = publish_health(args.notify_endpoint, status, max(1.0, args.timeout))
        status.setdefault("summary", {})["notification_delivery"] = delivery
    except RuntimeError as exc:
        status["healthy"] = False
        status.setdefault("summary", {})["notification_delivery"] = {
            "status": "failed",
            "reason": str(exc)[:500],
        }
        status.setdefault("failures", []).append(
            {
                "check": "notification_delivery",
                "expected": "accepted by 3021 notification center",
                "actual": str(exc)[:500],
            }
        )

    duration_ms = (time.monotonic() - started_at) * 1000
    status["duration_ms"] = round(duration_ms, 1)
    try:
        append_health_sample(status, monitor_key="primary", duration_ms=duration_ms)
        status.setdefault("summary", {})["history_recording"] = {"status": "recorded"}
    except (OSError, ValueError) as exc:
        status.setdefault("summary", {})["history_recording"] = {
            "status": "failed",
            "reason": str(exc)[:300],
        }
    write_status(args.output, status)
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    if not status["healthy"]:
        transition = old_health is not False
        level = "MEMORY_SYSTEM_ALERT" if transition else "MEMORY_SYSTEM_UNHEALTHY"
        print(f"{level}: {len(status['failures'])} memory gate check(s) failed", file=sys.stderr)
        return 2
    if old_health is False:
        print("MEMORY_SYSTEM_RECOVERED: all memory gate checks passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
