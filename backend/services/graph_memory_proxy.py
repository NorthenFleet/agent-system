"""Server-side, signed read-only bridge from dashboard 3021 to graph-memory."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException


DEFAULT_GATEWAY_URL = "http://127.0.0.1:18789"
DEFAULT_SECRET_PATH = "~/.openclaw/graph-memory-bridge.key"
MAX_RESPONSE_BYTES = 2_000_000
SUMMARY_FIELDS = {
    "agentId",
    "initialized",
    "state",
    "totalNodes",
    "totalEdges",
    "communities",
    "byType",
    "byEdgeType",
    "pendingMessages",
    "queueState",
    "oldestPendingAt",
    "pendingSessions",
    "nextRetryAt",
    "lastUpdatedAt",
    "lastExtraction",
    "lastSuccessfulExtraction",
    "vectorCount",
    "retrievalMode",
    "deadLetterCount",
    "extractionFailureCount",
}
EXTRACTION_FIELDS = {
    "outcome",
    "messageCount",
    "nodeCount",
    "edgeCount",
    "errorCode",
    "createdAt",
}
ATTENTION_QUEUE_STATES = {"attention", "blocked", "dead_letter", "error", "failed"}
BACKLOG_QUEUE_STATES = {"backlog", "pending", "retrying", "stalled"}


def _canonical_request(
    method: str,
    raw_url: str,
    timestamp: str,
    nonce: str,
    request_id: str,
    actor_id: str,
    actor_role: str,
    permissions: str,
) -> str:
    return "\n".join((method.upper(), raw_url, timestamp, nonce, request_id, actor_id, actor_role, permissions))


class GraphMemoryProxy:
    def __init__(self, gateway_url: str | None = None, secret_path: str | None = None, timeout: float = 5.0):
        self.gateway_url = (gateway_url or os.getenv("GRAPH_MEMORY_GATEWAY_URL") or DEFAULT_GATEWAY_URL).rstrip("/")
        self.secret_path = Path(secret_path or os.getenv("GRAPH_MEMORY_BRIDGE_SECRET_PATH") or DEFAULT_SECRET_PATH).expanduser()
        self.timeout = timeout

    def _secret(self) -> bytes:
        try:
            mode = stat.S_IMODE(self.secret_path.stat().st_mode)
            if mode & 0o077:
                raise HTTPException(status_code=503, detail="记忆服务凭证权限不安全")
            secret = self.secret_path.read_bytes()
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="记忆服务连接凭证不可用") from exc
        if len(secret) < 32:
            raise HTTPException(status_code=503, detail="记忆服务连接凭证不可用")
        return secret

    @staticmethod
    def _actor(user: dict[str, Any]) -> tuple[str, str]:
        actor_id = str(user.get("sub") or user.get("username") or user.get("id") or "")
        actor_role = str(user.get("role") or "")
        if not actor_id or actor_role != "admin":
            raise HTTPException(status_code=403, detail="权限不足")
        return actor_id, actor_role

    def get(
        self,
        raw_path: str,
        user: dict[str, Any],
        permissions: tuple[str, ...],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
        raw_url = f"{raw_path}?{query}" if query else raw_path
        actor_id, actor_role = self._actor(user)
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        request_id = uuid.uuid4().hex
        permissions_value = ",".join(permissions)
        signature = hmac.new(
            self._secret(),
            _canonical_request(
                "GET", raw_url, timestamp, nonce, request_id,
                actor_id, actor_role, permissions_value,
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = urllib.request.Request(
            f"{self.gateway_url}{raw_url}",
            method="GET",
            headers={
                "X-GM-Timestamp": timestamp,
                "X-GM-Nonce": nonce,
                "X-GM-Request-Id": request_id,
                "X-GM-Actor-Id": actor_id,
                "X-GM-Actor-Role": actor_role,
                "X-GM-Permissions": permissions_value,
                "X-GM-Signature": signature,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310 - loopback/configured gateway only
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                raise HTTPException(status_code=exc.code, detail="未找到记忆数据" if exc.code == 404 else "记忆查询参数无效") from exc
            raise HTTPException(status_code=503, detail="记忆服务暂时不可用") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HTTPException(status_code=503, detail="记忆服务暂时不可用") from exc
        if len(payload) > MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=502, detail="记忆服务响应超过安全上限")
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="记忆服务返回无效数据") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=502, detail="记忆服务返回无效数据")
        return parsed

    @staticmethod
    def _summary(payload: dict[str, Any]) -> dict[str, Any]:
        """Project the upstream summary onto the dashboard's metadata-only contract."""
        summary = {key: value for key, value in payload.items() if key in SUMMARY_FIELDS}
        for key in ("byType", "byEdgeType"):
            value = summary.get(key)
            summary[key] = (
                {str(name): count for name, count in value.items() if isinstance(count, int) and not isinstance(count, bool)}
                if isinstance(value, dict)
                else {}
            )
        last_extraction_value = summary.get("lastExtraction")
        if isinstance(last_extraction_value, dict):
            summary["lastExtraction"] = {
                field: item for field, item in last_extraction_value.items() if field in EXTRACTION_FIELDS
            }
        elif last_extraction_value is not None:
            summary["lastExtraction"] = None

        for key in ("oldestPendingAt", "nextRetryAt", "lastUpdatedAt", "lastSuccessfulExtraction"):
            if key in summary:
                value = summary[key]
                if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                    summary[key] = None

        initialized = bool(summary.get("initialized"))
        nodes = summary.get("totalNodes") if type(summary.get("totalNodes")) is int else 0
        pending = summary.get("pendingMessages") if type(summary.get("pendingMessages")) is int else 0
        pending_sessions = summary.get("pendingSessions") if type(summary.get("pendingSessions")) is int else 0
        dead_letters = summary.get("deadLetterCount") if type(summary.get("deadLetterCount")) is int else 0
        queue_state = str(summary.get("queueState") or "unknown").lower()
        reported_state = str(summary.get("state") or "unknown").lower()
        oldest_pending = summary.get("oldestPendingAt")
        last_extraction = summary.get("lastExtraction")
        latest_failed = isinstance(last_extraction, dict) and last_extraction.get("outcome") == "failed"

        if not initialized:
            state = "not_initialized"
        elif reported_state == "attention" or dead_letters > 0 or latest_failed or queue_state in ATTENTION_QUEUE_STATES:
            state = "attention"
        elif (
            reported_state == "backlog"
            or pending > 0
            or pending_sessions > 0
            or (isinstance(oldest_pending, (int, float)) and not isinstance(oldest_pending, bool) and oldest_pending > 0)
            or queue_state in BACKLOG_QUEUE_STATES
        ):
            state = "backlog"
        elif nodes == 0:
            state = "empty"
        else:
            state = "ready"
        summary["state"] = state
        return summary

    def get_summary(self, raw_path: str, user: dict[str, Any], permissions: tuple[str, ...]) -> dict[str, Any]:
        return self._summary(self.get(raw_path, user, permissions))


graph_memory_proxy = GraphMemoryProxy()
