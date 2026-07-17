"""
通用 Redis 缓存服务 — Sprint 5 性能优化

提供：
- get / set / invalidate 通用缓存操作
- cache_or 装饰器：命中返回缓存，miss 执行函数并缓存
- 优雅降级：Redis 不可用时降级为 no-op，不阻断服务

@task task-S5-P4-B-001
@author 🟥 拉斐尔
"""
from __future__ import annotations

import json
import hashlib
import functools
from typing import Any, Callable, Optional

import redis


def _get_redis_url() -> str:
    import os
    return os.getenv("REDIS_URL", "redis://localhost:6379/1")


def _get_default_ttl() -> int:
    import os
    return int(os.getenv("CACHE_DEFAULT_TTL", "300"))


def _get_cache_enabled() -> bool:
    import os
    return os.getenv("CACHE_ENABLED", "true").lower() == "true"


class CacheService:
    """Redis 缓存服务 — 优雅降级，Redis 不可用时静默 no-op"""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: Optional[int] = None,
        enabled: Optional[bool] = None,
    ):
        self._client: Optional[redis.Redis] = None
        self._enabled = enabled if enabled is not None else _get_cache_enabled()
        self._default_ttl = default_ttl if default_ttl is not None else _get_default_ttl()
        self._redis_url = redis_url or _get_redis_url()

    # ─── 初始化 ───

    def init(self) -> bool:
        """
        初始化 Redis 连接。连接失败时静默降级为 no-op 模式。
        返回 True 表示连接成功，False 表示已降级。
        """
        if not self._enabled:
            print("[Cache] ⚠️ 缓存已禁用 (CACHE_ENABLED=false)")
            return False
        try:
            self._client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            self._client.ping()
            self._enabled = True
            print(f"[Cache] ✅ Redis 已连接 {self._redis_url}")
            return True
        except Exception as e:
            print(f"[Cache] ⚠️ Redis 连接失败，缓存降级为 no-op: {e}")
            self._enabled = False
            self._client = None
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def client(self) -> Optional[redis.Redis]:
        return self._client

    # ─── CRUD ───

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值（自动反序列化 JSON），未命中或降级时返回 None"""
        if not self._enabled or not self._client:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值（自动序列化 JSON），降级时返回 False"""
        if not self._enabled or not self._client:
            return False
        try:
            effective_ttl = ttl if ttl is not None else self._default_ttl
            self._client.setex(
                key,
                effective_ttl,
                json.dumps(value, ensure_ascii=False, default=str),
            )
            return True
        except Exception:
            return False

    def delete(self, *keys: str) -> int:
        """删除缓存键，返回实际删除数量"""
        if not self._enabled or not self._client:
            return 0
        try:
            return self._client.delete(*keys)
        except Exception:
            return 0

    def invalidate(self, pattern: str) -> int:
        """
        按模式批量失效缓存（SCAN + DELETE），避免使用 KEYS 阻塞 Redis。
        返回实际删除的键数量。
        """
        if not self._enabled or not self._client:
            return 0
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    deleted += self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass
        return deleted

    def invalidate_pattern(self, pattern: str) -> int:
        """Backward-compatible alias for invalidate()."""
        return self.invalidate(pattern)

    def exists(self, key: str) -> bool:
        """检查缓存键是否存在"""
        if not self._enabled or not self._client:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    # ─── 装饰器 ───

    def cache_or(
        self,
        key_prefix: str,
        ttl: Optional[int] = None,
        key_builder: Optional[Callable[..., str]] = None,
    ) -> Callable:
        """
        缓存装饰器：
        - 先尝试从 Redis 获取缓存
        - 命中则直接返回
        - Miss 则执行原函数，并将结果写入缓存后返回

        用法:
            @cache_service.cache_or("v2:tasks", ttl=60)
            def get_tasks(page: int, limit: int):
                return db.query(...)

        key_builder 可选：自定义缓存键生成函数，接收原函数所有参数。
        默认使用参数的 MD5 hash。
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                if key_builder is not None:
                    cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
                else:
                    param_str = json.dumps({"args": args, "kwargs": kwargs}, default=str, sort_keys=True)
                    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:10]
                    cache_key = f"{key_prefix}:{fn.__name__}:{param_hash}"

                # 尝试命中
                cached = self.get(cache_key)
                if cached is not None:
                    return cached

                # Miss: 执行原函数
                result = fn(*args, **kwargs)

                # 写入缓存
                self.set(cache_key, result, ttl=effective_ttl)

                return result

            return wrapper

        return decorator

    # ─── 统计 ───

    def get_stats(self) -> dict:
        """获取 Redis 连接统计"""
        if not self._enabled or not self._client:
            return {"enabled": False, "status": "disconnected"}
        try:
            info = self._client.info("memory")
            db_size = self._client.dbsize()
            return {
                "enabled": True,
                "status": "connected",
                "url": self._redis_url,
                "keys_count": db_size,
                "used_memory_human": info.get("used_memory_human", "N/A"),
            }
        except Exception as e:
            return {"enabled": True, "status": "error", "error": str(e)}


# ─── 全局单例 ───

cache_service = CacheService()
