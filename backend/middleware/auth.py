"""
API Key 认证中间件
支持多种认证方式：
1. Header: X-API-Key
2. Query Param: api_key
3. Bearer Token: Authorization: Bearer <token>
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Optional, Set
import os
import hashlib
from datetime import datetime, timedelta


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    API Key 认证中间件
    支持配置需要认证的路径前缀
    """

    def __init__(
        self,
        app,
        api_keys: Optional[Set[str]] = None,
        exclude_paths: Optional[Set[str]] = None,
        require_auth: bool = False
    ):
        super().__init__(app)
        # 从环境变量加载 API Keys，如果没有则使用提供的
        env_api_keys = os.getenv("API_KEYS", "")
        if env_api_keys:
            self.api_keys = set(env_api_keys.split(","))
        else:
            self.api_keys = api_keys or set()

        # 不需要认证的路径
        self.exclude_paths = exclude_paths or {
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static",
            "/health",
            "/api/public"
        }

        # 是否强制要求认证
        self.require_auth = require_auth

        # 认证统计
        self.auth_stats = {
            "total_requests": 0,
            "authenticated_requests": 0,
            "failed_auth_attempts": 0,
            "invalid_keys": set()
        }

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """从请求中提取 API Key"""
        # 1. 检查 X-API-Key 头
        api_key = request.headers.get("x-api-key")
        if api_key:
            return api_key.strip()

        # 2. 检查 Authorization Bearer Token
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()

        # 3. 检查查询参数
        api_key = request.query_params.get("api_key")
        if api_key:
            return api_key.strip()

        return None

    def _is_excluded_path(self, path: str) -> bool:
        """检查路径是否排除在认证之外"""
        for exclude_path in self.exclude_paths:
            if exclude_path == "/":
                if path == "/":
                    return True
                continue
            normalized = exclude_path.rstrip("/")
            if path == normalized or path.startswith(normalized + "/"):
                return True
        return False

    def _validate_api_key(self, api_key: str) -> bool:
        """验证 API Key 是否有效"""
        return api_key in self.api_keys

    def _get_key_info(self, api_key: str) -> dict:
        """获取 API Key 的信息（用于审计）"""
        # 根据 key 的前缀判断类型
        if api_key.startswith("admin"):
            return {"type": "admin", "permissions": ["read", "write", "admin"]}
        elif api_key.startswith("dashboard"):
            return {"type": "standard", "permissions": ["read"]}
        else:
            return {"type": "unknown", "permissions": []}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        self.auth_stats["total_requests"] += 1

        # 检查是否需要认证
        if self._is_excluded_path(path):
            return await call_next(request)

        # 提取 API Key
        api_key = self._extract_api_key(request)

        # 如果没有 API Key
        if not api_key:
            self.auth_stats["failed_auth_attempts"] += 1

            if self.require_auth:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Unauthorized",
                        "detail": "API Key required. Please provide X-API-Key header or api_key query parameter."
                    },
                    headers={"WWW-Authenticate": "ApiKey"}
                )
            else:
                # 不强制认证，但记录警告
                request.state.api_key_status = "missing"
                return await call_next(request)

        # 验证 API Key
        if not self._validate_api_key(api_key):
            self.auth_stats["failed_auth_attempts"] += 1
            self.auth_stats["invalid_keys"].add(api_key[:8] + "...")  # 只记录前缀用于审计

            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Invalid API Key"
                },
                headers={"WWW-Authenticate": "ApiKey"}
            )

        # 认证成功
        self.auth_stats["authenticated_requests"] += 1
        key_info = self._get_key_info(api_key)

        # 将认证信息存入请求状态
        request.state.api_key_status = "authenticated"
        request.state.api_key_type = key_info["type"]
        request.state.api_key_permissions = key_info["permissions"]
        request.state.api_key = api_key[:8] + "..."  # 只存储前缀用于日志

        # 继续处理请求
        response = await call_next(request)

        # 添加认证信息到头（可选）
        response.headers["X-Auth-Status"] = "authenticated"
        response.headers["X-Auth-Type"] = key_info["type"]

        return response

    def get_stats(self) -> dict:
        """获取认证统计信息"""
        return {
            **self.auth_stats,
            "invalid_keys_sample": list(self.auth_stats["invalid_keys"])[:10]
        }

    def add_api_key(self, key: str) -> None:
        """添加新的 API Key"""
        self.api_keys.add(key)

    def remove_api_key(self, key: str) -> None:
        """移除 API Key"""
        self.api_keys.discard(key)

    def reset_stats(self) -> None:
        """重置统计数据"""
        self.auth_stats = {
            "total_requests": 0,
            "authenticated_requests": 0,
            "failed_auth_attempts": 0,
            "invalid_keys": set()
        }


# 全局实例
auth_instance: APIKeyAuthMiddleware = None


def get_auth_middleware() -> APIKeyAuthMiddleware:
    """获取全局认证中间件实例"""
    return auth_instance


def generate_api_key(prefix: str = "key") -> str:
    """生成新的 API Key"""
    import secrets
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = secrets.token_hex(8)
    return f"{prefix}-{timestamp}-{random_part}"
