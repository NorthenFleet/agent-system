#!/usr/bin/env python3
"""Soundwave client for the audited 3021 finance-intake contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


BASE_URL = os.getenv("COMMAND_CENTER_URL", "http://127.0.0.1:3021").rstrip("/")
SESSION_INDEX = Path(
    os.getenv(
        "SOUNDWAVE_SESSION_INDEX",
        "/Users/apple/.openclaw/agents/soundwave/sessions/sessions.json",
    )
)


def _external_id(value: Any) -> str:
    """Normalize OpenClaw channel targets such as user:ou_* or feishu:ou_*."""
    return str(value or "").strip().rsplit(":", 1)[-1]


def _session_context() -> dict[str, str]:
    target = ""
    user_id = ""
    try:
        sessions = json.loads(SESSION_INDEX.read_text(encoding="utf-8"))
        candidates = [
            value for key, value in sessions.items()
            if key.startswith("agent:soundwave:") and isinstance(value, dict)
        ]
        candidates.sort(key=lambda value: value.get("updatedAt") or 0, reverse=True)
        session = candidates[0] if candidates else {}
        delivery = session.get("deliveryContext") or {}
        origin = session.get("origin") or {}
        target = str(delivery.get("to") or session.get("lastTo") or origin.get("from") or "")
        user_id = _external_id(origin.get("from") or target)
    except (OSError, TypeError, json.JSONDecodeError):
        pass
    return {"target": target, "user_id": user_id}


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("COMMAND_CENTER_INGRESS_TOKEN", "").strip()
    if token:
        headers["X-Command-Center-Token"] = token
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=(json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"3021 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"3021 unavailable: {exc}") from exc


def route(message: str) -> dict[str, Any]:
    context = _session_context()
    if not context["target"] or not context["user_id"]:
        raise RuntimeError("Soundwave Feishu session identity is unavailable")
    result = _request(
        "POST",
        "/api/v3/command-center/inbox",
        {
            "channel": "feishu",
            "external_conversation_id": context["target"],
            "user_external_id": context["user_id"],
            "content": message,
            "external_message_id": f"soundwave-{uuid.uuid4().hex}",
            "intent_type": "finance_operation",
            "intent_confidence": 1.0,
            "intent_reason": "Soundwave finance channel contract",
            "execution_requested": False,
            "metadata": {
                "target": context["target"],
                "account_id": "soundwave",
                "source": "soundwave-finance-command-center",
                "authority": "intake-only",
            },
        },
    )
    finance_job = result.get("finance_job") or {}
    if (
        result.get("action") not in {"finance_intake", "duplicate"}
        or finance_job.get("mode") != "shadow"
        or finance_job.get("status") != "shadow_read"
    ):
        raise RuntimeError("3021 finance shadow intake contract is unavailable")
    return result


def respond(message_id: str, content: str) -> dict[str, Any]:
    return _request(
        "POST",
        f"/api/v3/command-center/agent/messages/{urllib.parse.quote(message_id)}/response",
        {"content": content, "sender_id": "soundwave"},
    )


def show(job_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/v3/command-center/agent/finance-jobs/{urllib.parse.quote(job_id)}?agent_id=soundwave",
    )


def extract(
    job_id: str,
    payload: dict[str, Any],
    evidence: list[str],
    confidence: float,
    expected_version: int,
) -> dict[str, Any]:
    return _request(
        "POST",
        f"/api/v3/command-center/agent/finance-jobs/{urllib.parse.quote(job_id)}/extraction",
        {
            "agent_id": "soundwave",
            "payload": payload,
            "evidence": evidence,
            "confidence": confidence,
            "expected_version": expected_version,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    route_parser = commands.add_parser("route")
    route_parser.add_argument("--message", required=True)
    response_parser = commands.add_parser("respond")
    response_parser.add_argument("--message-id", required=True)
    response_parser.add_argument("--content", required=True)
    show_parser = commands.add_parser("show")
    show_parser.add_argument("--job-id", required=True)
    extract_parser = commands.add_parser("extract")
    extract_parser.add_argument("--job-id", required=True)
    extract_parser.add_argument("--payload-json", required=True)
    extract_parser.add_argument("--evidence", action="append", default=[])
    extract_parser.add_argument("--confidence", type=float, required=True)
    extract_parser.add_argument("--expected-version", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "route":
            result = route(args.message)
        elif args.command == "respond":
            result = respond(args.message_id, args.content)
        elif args.command == "show":
            result = show(args.job_id)
        else:
            result = extract(
                args.job_id,
                json.loads(args.payload_json),
                args.evidence,
                args.confidence,
                args.expected_version,
            )
    except (RuntimeError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"success": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
