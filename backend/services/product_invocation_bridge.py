"""Product Invocation Bridge — 让擎天柱显式决策后调用外部产品 API。

架构：
    孙总飞书 → 擎天柱 → 3021 任务规划 → 桥接服务 → 外部产品 API
                                                  ↓
                                           结果回传 3021 → 飞书

支持产品：
    - one-sim (5100/5110/5120/5130)
    - ai-planning-5130 (5130)
    - openclaw-3021 (3021, 本地调用)
    - 后续动态注册的新产品

特性：
    - 从产品注册中心动态读取产品配置
    - 自动 token 管理（带过期缓冲）
    - 超时控制（连接/读写分别）
    - 调用日志记录（审计追踪）
    - 错误重试（可配置）
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from path_config import data_path
from services.product_service import product_registry_service

# ---------------------------------------------------------------------------
# 调用日志存储（SQLite 追加写入，与产品注册共用 unified_db）
# ---------------------------------------------------------------------------

INVOKE_LOG_FILE = data_path("product-invoke-log.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_log(entry: dict[str, Any]) -> None:
    """追加一行调用日志到 JSONL 文件。"""
    Path(INVOKE_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(INVOKE_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


class InvocationRecord:
    """单次产品调用的记录。"""

    def __init__(
        self,
        product_id: str,
        action: str,
        endpoint: str,
        method: str,
        invoked_by: str = "optimus",
    ):
        self.invocation_id = str(uuid.uuid4())[:8]
        self.product_id = product_id
        self.action = action
        self.endpoint = endpoint
        self.method = method
        self.invoked_by = invoked_by
        self.started_at = _now_iso()
        self.finished_at: str | None = None
        self.status: str = "pending"  # pending | success | error | timeout
        self.status_code: int | None = None
        self.latency_ms: int = 0
        self.request_payload: dict | None = None
        self.response_payload: Any = None
        self.error_message: str | None = None

    def mark_success(self, status_code: int, response: Any, latency_ms: int) -> dict[str, Any]:
        self.finished_at = _now_iso()
        self.status = "success"
        self.status_code = status_code
        self.latency_ms = latency_ms
        self.response_payload = _truncate_response(response)
        return self.to_dict()

    def mark_error(self, error: str, status_code: int | None = None) -> dict[str, Any]:
        self.finished_at = _now_iso()
        self.status = "error"
        self.status_code = status_code
        self.error_message = error
        return self.to_dict()

    def mark_timeout(self, error: str) -> dict[str, Any]:
        self.finished_at = _now_iso()
        self.status = "timeout"
        self.error_message = error
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "product_id": self.product_id,
            "action": self.action,
            "endpoint": self.endpoint,
            "method": self.method,
            "invoked_by": self.invoked_by,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "request_payload": self.request_payload,
            "response_payload": self.response_payload,
            "response_summary": _response_summary(self.response_payload),
            "error_message": self.error_message,
        }


def _truncate_response(data: Any, max_len: int = 2000) -> Any:
    """截断过长的响应，避免日志膨胀。"""
    if data is None:
        return None
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= max_len:
        return data
    return {"_truncated": True, "_original_length": len(text), "preview": text[:max_len]}


def _response_summary(data: Any) -> str | None:
    if data is None:
        return None
    if isinstance(data, dict):
        keys = list(data.keys())[:5]
        return f"dict[{', '.join(keys)}]"
    if isinstance(data, list):
        return f"list[{len(data)} items]"
    text = str(data)[:200]
    return text


# ---------------------------------------------------------------------------
# 产品 HTTP 客户端（复用 mission_planning_adapter 的认证模式）
# ---------------------------------------------------------------------------

class ProductHttpClient:
    """通用产品 HTTP 客户端，支持 token 认证和超时控制。"""

    def __init__(
        self,
        base_url: str,
        auth_endpoint: str | None = None,
        auth_payload: dict | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_endpoint = auth_endpoint
        self.auth_payload = auth_payload
        self._access_token = ""
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=10.0,
            pool=5.0,
        )

    async def _ensure_token(self, *, force: bool = False) -> str:
        """懒加载 token，带过期缓冲。"""
        if not self.auth_endpoint:
            return ""
        if not force and self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        async with self._token_lock:
            if not force and self._access_token and time.monotonic() < self._token_expires_at:
                return self._access_token
            try:
                resp = await asyncio.to_thread(
                    self._sync_request,
                    "POST",
                    f"{self.base_url}{self.auth_endpoint}",
                    json=self.auth_payload,
                )
            except httpx.RequestError as exc:
                raise ProductInvocationError(f"认证接口不可达：{exc}")
            if resp.status_code >= 400:
                raise ProductInvocationError(f"认证失败 HTTP {resp.status_code}")
            try:
                body = resp.json()
            except ValueError:
                raise ProductInvocationError("认证响应非 JSON")
            token = body.get("access_token") or body.get("token") or ""
            if not token:
                raise ProductInvocationError("认证响应缺少 token")
            expires_in = max(int(body.get("expires_in") or 1800), 60)
            self._access_token = token
            self._token_expires_at = time.monotonic() + expires_in - 30
            return token

    def _sync_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            return client.request(method, url, headers=headers, json=json, params=params)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """发送 HTTP 请求，自动附加 token。"""
        token = await self._ensure_token()
        req_headers = dict(headers or {})
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        try:
            resp = await asyncio.to_thread(
                self._sync_request,
                method,
                f"{self.base_url}{path}",
                headers=req_headers,
                json=json,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise ProductInvocationTimeoutError(f"请求超时：{path} — {exc}")
        except httpx.RequestError as exc:
            raise ProductInvocationError(f"请求失败：{path} — {exc}")

        # 401 自动刷新 token 重试一次
        if resp.status_code == 401 and token:
            await self._ensure_token(force=True)
            req_headers["Authorization"] = f"Bearer {await self._ensure_token()}"
            try:
                resp = await asyncio.to_thread(
                    self._sync_request,
                    method,
                    f"{self.base_url}{path}",
                    headers=req_headers,
                    json=json,
                    params=params,
                )
            except httpx.TimeoutException as exc:
                raise ProductInvocationTimeoutError(f"重试超时：{path}")
            except httpx.RequestError as exc:
                raise ProductInvocationError(f"重试失败：{path}")
        return resp


class ProductInvocationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "invocation_error"):
        super().__init__(message)
        self.code = code


class ProductInvocationTimeoutError(ProductInvocationError):
    def __init__(self, message: str):
        super().__init__(message, code="invocation_timeout")


# ---------------------------------------------------------------------------
# 产品配置解析器
# ---------------------------------------------------------------------------

# 默认产品配置（当注册中心没有时 fallback）
DEFAULT_PRODUCT_CONFIGS: dict[str, dict[str, Any]] = {
    "one-sim": {
        "base_url": "http://192.168.31.144:5100",
        "auth_endpoint": None,
        "auth_payload": None,
        "connect_timeout": 3.0,
        "read_timeout": 30.0,
    },
    "ai-planning-5130": {
        "base_url": os.getenv("AI_PLANNING_BASE_URL", "http://192.168.31.144:5130"),
        "auth_endpoint": "/api/auth/login",
        "auth_payload": {
            "username": os.getenv("AI_PLANNING_USERNAME", "admin"),
            "password": os.getenv("AI_PLANNING_PASSWORD", "admin123"),
        },
        "connect_timeout": 3.0,
        "read_timeout": 20.0,
    },
    "openclaw-3021": {
        "base_url": "http://127.0.0.1:3021",
        "auth_endpoint": None,
        "auth_payload": None,
        "connect_timeout": 2.0,
        "read_timeout": 15.0,
    },
}


def _resolve_product_config(product_id: str) -> dict[str, Any]:
    """从产品注册中心 + 默认配置解析产品连接信息。"""
    product = product_registry_service.get_product(product_id)
    if product:
        deployment = product.get("deployment", {}) if isinstance(product.get("deployment"), dict) else {}
        auth_config = product.get("auth_config", {}) if isinstance(product.get("auth_config"), dict) else {}
        return {
            "base_url": deployment.get("public_url") or deployment.get("base_url") or DEFAULT_PRODUCT_CONFIGS.get(product_id, {}).get("base_url", ""),
            "auth_endpoint": auth_config.get("endpoint"),
            "auth_payload": auth_config.get("payload"),
            "connect_timeout": float(deployment.get("connect_timeout", 5.0)),
            "read_timeout": float(deployment.get("read_timeout", 30.0)),
        }
    # fallback 到默认配置
    fallback = DEFAULT_PRODUCT_CONFIGS.get(product_id, {})
    if not fallback:
        raise ProductInvocationError(f"产品 {product_id} 未注册且无默认配置", code="product_not_found")
    return fallback


# ---------------------------------------------------------------------------
# 预定义动作模板
# ---------------------------------------------------------------------------

ACTION_TEMPLATES: dict[str, dict[str, Any]] = {
    # one-sim 动作
    "one-sim.health": {"method": "GET", "endpoint": "/health", "requires_auth": False},
    "one-sim.state": {"method": "GET", "endpoint": "/api/planning/situation/state", "requires_auth": True},
    "one-sim.scenarios": {"method": "GET", "endpoint": "/api/scenarios", "requires_auth": False},

    # ai-planning-5130 动作
    "planning.health": {"method": "GET", "endpoint": "/api/health", "requires_auth": True},
    "planning.scenarios": {"method": "GET", "endpoint": "/api/scenarios", "requires_auth": True},
    "planning.supervisor-status": {"method": "GET", "endpoint": "/api/planning/supervisor/status", "requires_auth": True},
    "planning.supervisor-start": {"method": "POST", "endpoint": "/api/planning/supervisor/start", "requires_auth": True},
    "planning.supervisor-stop": {"method": "POST", "endpoint": "/api/planning/supervisor/stop", "requires_auth": True},
    "planning.replan": {"method": "POST", "endpoint": "/api/planning/supervisor/replan", "requires_auth": True},
    "planning.generate-plan": {"method": "POST", "endpoint": "/api/planning/situation/generate-plan", "requires_auth": True},

    # openclaw-3021 动作（本地）
    "3021.health": {"method": "GET", "endpoint": "/health", "requires_auth": False},
    "3021.products": {"method": "GET", "endpoint": "/api/v2/products", "requires_auth": False},
    "3021.tasks": {"method": "GET", "endpoint": "/api/v2/tasks", "requires_auth": False},
}


# ---------------------------------------------------------------------------
# 桥接服务主类
# ---------------------------------------------------------------------------

class ProductInvocationBridge:
    """产品调用桥接服务。

    使用方式：
        bridge = ProductInvocationBridge()
        result = await bridge.invoke(
            product_id="one-sim",
            action="one-sim.health",
            invoked_by="optimus",
        )
    """

    def __init__(self):
        self._clients: dict[str, ProductHttpClient] = {}

    def _get_client(self, product_id: str) -> ProductHttpClient:
        """懒创建 HTTP 客户端（每个产品一个实例）。"""
        if product_id not in self._clients:
            config = _resolve_product_config(product_id)
            self._clients[product_id] = ProductHttpClient(
                base_url=config["base_url"],
                auth_endpoint=config.get("auth_endpoint"),
                auth_payload=config.get("auth_payload"),
                connect_timeout=config.get("connect_timeout", 5.0),
                read_timeout=config.get("read_timeout", 30.0),
            )
        return self._clients[product_id]

    async def invoke(
        self,
        product_id: str,
        action: str,
        *,
        endpoint: str | None = None,
        method: str | None = None,
        payload: dict | None = None,
        params: dict | None = None,
        invoked_by: str = "optimus",
        custom_headers: dict | None = None,
    ) -> dict[str, Any]:
        """执行一次产品调用。

        Args:
            product_id: 产品 ID（如 "one-sim", "ai-planning-5130"）
            action: 动作名称（如 "one-sim.health"），用于查找预定义模板
            endpoint: 自定义端点路径（覆盖模板）
            method: 自定义 HTTP 方法（覆盖模板）
            payload: POST/PUT 请求体
            params: URL 查询参数
            invoked_by: 调用者标识
            custom_headers: 额外请求头

        Returns:
            调用记录字典
        """
        # 解析动作
        template = ACTION_TEMPLATES.get(action, {})
        final_method = method or template.get("method", "GET")
        final_endpoint = endpoint or template.get("endpoint")

        if not final_endpoint:
            record = InvocationRecord(product_id, action, "N/A", final_method, invoked_by)
            record.request_payload = payload
            result = record.mark_error(f"未知动作: {action}，且未提供自定义 endpoint")
            _append_log(result)
            return result

        record = InvocationRecord(product_id, action, final_endpoint, final_method, invoked_by)
        record.request_payload = payload
        started = time.monotonic()

        try:
            client = self._get_client(product_id)
            resp = await client.request(
                method=final_method,
                path=final_endpoint,
                json=payload,
                params=params,
                headers=custom_headers,
            )
            latency_ms = round((time.monotonic() - started) * 1000)

            if resp.status_code >= 400:
                error_text = ""
                try:
                    error_text = resp.json().get("detail", resp.text[:200])
                except Exception:
                    error_text = resp.text[:200]
                result = record.mark_error(
                    f"HTTP {resp.status_code}: {error_text}",
                    status_code=resp.status_code,
                )
            else:
                try:
                    data = resp.json()
                except ValueError:
                    data = resp.text[:2000]
                result = record.mark_success(resp.status_code, data, latency_ms)

        except ProductInvocationTimeoutError as exc:
            latency_ms = round((time.monotonic() - started) * 1000)
            record.latency_ms = latency_ms
            result = record.mark_timeout(str(exc))
        except ProductInvocationError as exc:
            latency_ms = round((time.monotonic() - started) * 1000)
            record.latency_ms = latency_ms
            result = record.mark_error(str(exc))
        except Exception as exc:
            latency_ms = round((time.monotonic() - started) * 1000)
            record.latency_ms = latency_ms
            result = record.mark_error(f"未知错误: {type(exc).__name__}: {exc}")

        _append_log(result)
        return result

    async def batch_invoke(
        self,
        calls: list[dict[str, Any]],
        invoked_by: str = "optimus",
        concurrency: int = 3,
    ) -> list[dict[str, Any]]:
        """批量调用多个产品动作。

        Args:
            calls: 调用列表，每项包含 product_id, action, endpoint, method, payload 等
            invoked_by: 调用者标识
            concurrency: 并发数

        Returns:
            调用结果列表
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _one(call: dict) -> dict:
            async with semaphore:
                return await self.invoke(
                    product_id=call["product_id"],
                    action=call.get("action", "custom"),
                    endpoint=call.get("endpoint"),
                    method=call.get("method"),
                    payload=call.get("payload"),
                    params=call.get("params"),
                    invoked_by=invoked_by,
                )

        tasks = [_one(c) for c in calls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_invoke_log(self, limit: int = 50, product_id: str | None = None) -> list[dict[str, Any]]:
        """读取调用日志。"""
        logs = []
        try:
            with open(INVOKE_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if product_id and entry.get("product_id") != product_id:
                            continue
                        logs.append(entry)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return []
        return logs[-limit:]

    def get_available_actions(self, product_id: str | None = None) -> list[dict[str, Any]]:
        """列出可用的动作模板。"""
        actions = []
        for key, tpl in ACTION_TEMPLATES.items():
            if product_id and not key.startswith(product_id.split("-")[0]):
                continue
            actions.append({
                "action": key,
                "method": tpl["method"],
                "endpoint": tpl["endpoint"],
                "requires_auth": tpl.get("requires_auth", False),
            })
        return actions


product_invocation_bridge = ProductInvocationBridge()
