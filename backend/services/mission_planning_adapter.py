"""Typed service boundary between OpenClaw and the AI Planning product."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

import httpx


class MissionPlanningError(RuntimeError):
    def __init__(self, message: str, *, code: str = "product_error", status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class MissionPlanningAdapter:
    def __init__(self) -> None:
        self.base_url = os.getenv("AI_PLANNING_BASE_URL", "http://192.168.31.144:5130").rstrip("/")
        self.public_url = os.getenv("AI_PLANNING_PUBLIC_URL", "http://192.168.31.144:5130").rstrip("/")
        self.username = os.getenv("AI_PLANNING_USERNAME", "admin")
        self.password = os.getenv("AI_PLANNING_PASSWORD", "admin123")
        self._access_token = ""
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self._scenario_cache: list[dict[str, Any]] = []
        self._scenario_cache_at = 0.0
        self._timeout = httpx.Timeout(
            connect=float(os.getenv("AI_PLANNING_CONNECT_TIMEOUT", "3")),
            read=float(os.getenv("AI_PLANNING_READ_TIMEOUT", "20")),
            write=10.0,
            pool=3.0,
        )

    def _sync_http_request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        with httpx.Client(timeout=self._timeout, trust_env=False) as client:
            return client.request(method, url, headers=headers, json=json, params=params)

    async def _login(self, *, force: bool = False) -> str:
        if not force and self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        async with self._token_lock:
            if not force and self._access_token and time.monotonic() < self._token_expires_at:
                return self._access_token
            try:
                response = await asyncio.to_thread(
                    self._sync_http_request,
                    "POST",
                    f"{self.base_url}/api/auth/login",
                    json={"username": self.username, "password": self.password},
                )
            except httpx.TimeoutException as exc:
                raise MissionPlanningError("5130 认证接口超时", code="auth_timeout", status_code=504) from exc
            except httpx.RequestError as exc:
                cause = repr(exc.__cause__) if exc.__cause__ else type(exc).__name__
                raise MissionPlanningError(f"无法连接5130：{exc}（{cause}）", code="unreachable") from exc
            if response.status_code >= 400:
                raise MissionPlanningError(
                    f"5130 认证失败（HTTP {response.status_code}）",
                    code="auth_failed",
                    status_code=502,
                )
            payload = response.json()
            token = str(payload.get("access_token") or "")
            if not token:
                raise MissionPlanningError("5130 认证响应缺少 access_token", code="invalid_auth_response")
            expires_in = max(int(payload.get("expires_in") or 1800), 60)
            self._access_token = token
            self._token_expires_at = time.monotonic() + expires_in - 30
            return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        retry_auth: bool = True,
    ) -> Any:
        token = await self._login()
        try:
            response = await asyncio.to_thread(
                self._sync_http_request,
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise MissionPlanningError(f"5130 业务接口超时：{path}", code="product_timeout", status_code=504) from exc
        except httpx.RequestError as exc:
            cause = repr(exc.__cause__) if exc.__cause__ else type(exc).__name__
            raise MissionPlanningError(f"无法连接5130：{path}：{exc}（{cause}）", code="unreachable") from exc

        if response.status_code == 401 and retry_auth:
            await self._login(force=True)
            return await self._request(method, path, json=json, params=params, retry_auth=False)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text[:500]
            raise MissionPlanningError(
                f"5130 返回 HTTP {response.status_code}：{detail or path}",
                code="product_rejected",
                status_code=502,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise MissionPlanningError(f"5130 返回了非 JSON 响应：{path}", code="invalid_product_response") from exc

    async def health(self) -> dict[str, Any]:
        status = await self.supervisor_status()
        return {
            "online": True,
            "base_url": self.public_url,
            "transport": "ssh-tunnel" if self.base_url != self.public_url else "direct",
            "product": "无人集群任务规划系统",
            "supervisor_state": status.get("state", "unknown"),
            "running": bool(status.get("running")),
        }

    async def list_scenarios(self) -> list[dict[str, Any]]:
        if self._scenario_cache and time.monotonic() - self._scenario_cache_at < 300:
            return [dict(row) for row in self._scenario_cache]
        payload = await self._request("GET", "/api/scenarios")
        rows = payload.get("scenarios", []) if isinstance(payload, dict) else []
        scenarios = [
            {
                "id": str(row.get("id") or ""),
                "name": str(row.get("name") or row.get("id") or "未命名想定"),
                "description": str(row.get("description") or ""),
                "type": str(row.get("type") or "wargame"),
                "map_size": row.get("map_size") or [row.get("cols"), row.get("rows")],
            }
            for row in rows
            if isinstance(row, dict) and row.get("id")
        ]
        self._scenario_cache = scenarios
        self._scenario_cache_at = time.monotonic()
        return [dict(row) for row in scenarios]

    async def load_scenario(self, scenario_id: str, scenario_type: str, side: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/planning/load-scenario",
            json={"scenario_id": scenario_id, "scenario_type": scenario_type, "side": side},
        )

    async def generate_plan(self) -> dict[str, Any]:
        return await self._request("POST", "/api/planning/situation/generate-plan")

    async def start_supervisor(self) -> dict[str, Any]:
        return await self._request("POST", "/api/planning/supervisor/start")

    async def stop_supervisor(self) -> dict[str, Any]:
        return await self._request("POST", "/api/planning/supervisor/stop")

    async def replan(self, reason: str) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/api/planning/supervisor/replan",
            params={"reason": reason[:200]},
        )
        return payload if isinstance(payload, dict) else {}

    async def supervisor_status(self) -> dict[str, Any]:
        payload = await self._request("GET", "/api/planning/supervisor/status")
        return payload if isinstance(payload, dict) else {}

    async def simulation_snapshot(self) -> dict[str, Any]:
        """Read a compact one-sim snapshot from the embedded planning situation."""
        payload = await self._request(
            "GET",
            "/api/planning/situation/state",
            params={"raw": "false"},
        )
        if not isinstance(payload, dict):
            return {}
        units = payload.get("units") if isinstance(payload.get("units"), list) else []
        side_counts: dict[str, int] = {}
        destroyed = 0
        for unit in units:
            if not isinstance(unit, dict):
                continue
            side = str(unit.get("side") or "unknown")
            side_counts[side] = side_counts.get(side, 0) + 1
            if unit.get("is_destroyed"):
                destroyed += 1
        return {
            "provider": "one-sim",
            "mode": "embedded-planning-situation",
            "scenario_name": payload.get("scenario_name"),
            "frame": int(payload.get("frame") or 0),
            "turn": int(payload.get("turn") or 0),
            "phase": payload.get("phase"),
            "state_version": payload.get("state_version"),
            "unit_count": len(units),
            "side_counts": side_counts,
            "destroyed_count": destroyed,
            "timestamp": payload.get("timestamp"),
        }


mission_planning_adapter = MissionPlanningAdapter()
