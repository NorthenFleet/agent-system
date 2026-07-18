"""Controlled HTTP health probes for registered product runtime instances."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class RuntimeHealthProbeError(ValueError):
    """Raised when a runtime health endpoint is not safe to probe."""


class ProductRuntimeHealthService:
    """Probe explicitly registered HTTP(S) endpoints without executing deployment actions."""

    max_response_bytes = 4096

    @staticmethod
    def _validate_url(url: str) -> str:
        normalized = str(url or "").strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeHealthProbeError("health_url must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise RuntimeHealthProbeError("health_url must not contain credentials")
        return normalized

    async def probe_url(self, url: str, *, timeout_seconds: float = 3.0) -> dict[str, Any]:
        normalized = self._validate_url(url)
        timeout = max(0.5, min(float(timeout_seconds), 10.0))
        return await asyncio.to_thread(self._probe_sync, normalized, timeout)

    def _probe_sync(self, url: str, timeout_seconds: float) -> dict[str, Any]:
        started = time.monotonic()
        request = Request(url, method="GET", headers={"Accept": "application/json, text/plain;q=0.8"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - admin-configured runtime endpoint
                status_code = int(response.getcode())
                body = response.read(self.max_response_bytes)
                payload = self._parse_payload(body, response.headers.get("Content-Type", ""))
                elapsed_ms = round((time.monotonic() - started) * 1000)
                return self._result_for_http_status(url, status_code, elapsed_ms, payload)
        except HTTPError as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            return self._result_for_http_status(url, int(exc.code), elapsed_ms, None)
        except (URLError, TimeoutError, OSError) as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            return {
                "state": "offline",
                "online": False,
                "summary": f"健康检查不可达：{self._error_message(exc)}",
                "details": {"health_url": url, "latency_ms": elapsed_ms, "error": self._error_message(exc)},
            }

    @staticmethod
    def _parse_payload(body: bytes, content_type: str) -> Any:
        if not body:
            return None
        text = body.decode("utf-8", errors="replace").strip()
        if "json" in content_type.lower():
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text[:240]
        return text[:240]

    @staticmethod
    def _error_message(error: BaseException) -> str:
        reason = getattr(error, "reason", None)
        return str(reason or error)[:240]

    @staticmethod
    def _result_for_http_status(url: str, status_code: int, elapsed_ms: int, payload: Any) -> dict[str, Any]:
        online = 200 <= status_code < 300
        state = "online" if online else "degraded"
        payload_state = payload.get("status") if isinstance(payload, dict) else None
        if online and isinstance(payload_state, str) and payload_state.lower() not in {"ok", "online", "healthy", "ready", "running"}:
            state = "degraded"
            online = False
        summary = f"健康检查 {status_code} · {elapsed_ms}ms"
        if payload_state:
            summary = f"{summary} · {payload_state}"
        return {
            "state": state,
            "online": online,
            "summary": summary,
            "details": {"health_url": url, "http_status": status_code, "latency_ms": elapsed_ms, "payload": payload},
        }


product_runtime_health_service = ProductRuntimeHealthService()
