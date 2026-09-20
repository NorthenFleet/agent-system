#!/usr/bin/env python3
"""Optimus client for the user-scoped 3021 memory introspection contract."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.getenv("COMMAND_CENTER_URL", "http://127.0.0.1:3021").rstrip("/")
SESSION_DIR = Path(
    os.getenv(
        "OPTIMUS_SESSION_DIR",
        "/Users/apple/.openclaw/agents/optimus/sessions",
    )
)
AGENT_STATE_DB = Path(
    os.getenv(
        "OPTIMUS_AGENT_STATE_DB",
        "/Users/apple/.openclaw/agents/optimus/agent/openclaw-agent.sqlite",
    )
)


def _external_id(value: Any) -> str:
    return str(value or "").strip().rsplit(":", 1)[-1]


def _session_indexes() -> list[Path]:
    primary = SESSION_DIR / "sessions.json"
    backups = sorted(
        SESSION_DIR.glob("sessions.json.bak.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [primary, *backups]


def _state_session_context() -> dict[str, str] | None:
    """Resolve the durable human participant; fail closed after DB migration."""
    if not AGENT_STATE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{AGENT_STATE_DB}?mode=ro", uri=True, timeout=3)
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
        for identity_raw, actor_id in rows:
            identity = json.loads(identity_raw or "{}")
            channel = str(identity.get("pluginId") or "").strip().lower()
            sender_kind = str(identity.get("senderKind") or "").strip().lower()
            external = _external_id(actor_id)
            if channel == "feishu" and sender_kind == "human" and external:
                return {"channel": channel, "external_user_id": external}
    except (OSError, sqlite3.Error, TypeError, json.JSONDecodeError):
        pass
    return {"channel": "", "external_user_id": ""}


def _session_context() -> dict[str, str]:
    state_context = _state_session_context()
    if state_context is not None:
        return state_context
    for index in _session_indexes():
        try:
            sessions = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            continue
        candidates: list[dict[str, Any]] = []
        for key, value in sessions.items():
            if not key.startswith("agent:optimus:") or not isinstance(value, dict):
                continue
            delivery = value.get("deliveryContext") or {}
            origin = value.get("origin") or {}
            channel = str(delivery.get("channel") or origin.get("provider") or "").lower()
            external = _external_id(origin.get("from") or delivery.get("to") or value.get("lastTo"))
            if channel == "feishu" and external:
                candidates.append(value)
        candidates.sort(key=lambda value: value.get("updatedAt") or 0, reverse=True)
        if candidates:
            session = candidates[0]
            delivery = session.get("deliveryContext") or {}
            origin = session.get("origin") or {}
            return {
                "channel": str(delivery.get("channel") or origin.get("provider") or "feishu").lower(),
                "external_user_id": _external_id(
                    origin.get("from") or delivery.get("to") or session.get("lastTo")
                ),
            }
    return {"channel": "", "external_user_id": ""}


def _request(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("COMMAND_CENTER_INGRESS_TOKEN", "").strip()
    if token:
        headers["X-Command-Center-Token"] = token
    request = urllib.request.Request(
        f"{BASE_URL}/api/v3/command-center/agent/memory-context",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("3021 returned an invalid memory response")
            return parsed
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"3021 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"3021 unavailable: {exc}") from exc


def inspect(
    query: str,
    *,
    project_id: str = "",
    external_user_id: str = "",
    channel: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    context = _session_context()
    resolved_external = _external_id(external_user_id) or context["external_user_id"]
    resolved_channel = str(channel or context["channel"] or "feishu").strip().lower()
    if not resolved_external:
        raise RuntimeError("Optimus Feishu session identity is unavailable")
    return _request(
        {
            "channel": resolved_channel,
            "external_user_id": resolved_external,
            "query": query,
            "agent_id": "optimus",
            "project_id": project_id,
            "limit": 12,
            "persist": persist,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--query", required=True)
    inspect_parser.add_argument("--project-id", default="")
    inspect_parser.add_argument("--external-user-id", default="")
    inspect_parser.add_argument("--channel", default="")
    inspect_parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(
            args.query,
            project_id=args.project_id,
            external_user_id=args.external_user_id,
            channel=args.channel,
            persist=not args.no_persist,
        )
    except (RuntimeError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"success": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
