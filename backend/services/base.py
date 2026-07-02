"""
BaseService — 业务逻辑基类 + 内存缓存

所有 Service 继承此类。提供：
1. Repository 实例管理
2. 简单内存缓存（TTL + max_size）

@task VB-008
@author 🟥 拉斐尔
"""
import time
import threading
from typing import TypeVar, Generic, Optional, Any, Dict
from functools import wraps

from sqlalchemy.orm import Session

from repositories.base import BaseRepository


# ──────────────────────────────────────────────
# 简单内存缓存（TTL + LRU 淘汰）
# ──────────────────────────────────────────────

class Cache:
    """线程安全的内存缓存，支持 TTL 和最大容量。"""

    def __init__(self, max_size: int = 512, default_ttl: int = 60):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._access_order: list = []  # 简单的 LRU 顺序
        self._lock = threading.Lock()
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                return None
            if self._expiry.get(key, 0) < time.monotonic():
                self._evict(key)
                return None
            # 更新访问顺序
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return self._store[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            if key not in self._store and len(self._store) >= self._max_size:
                self._evict_oldest()
            self._store[key] = value
            self._expiry[key] = time.monotonic() + ttl
            if key not in self._access_order:
                self._access_order.append(key)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._evict(key)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                self._evict(k)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._expiry.clear()
            self._access_order.clear()

    def _evict(self, key: str) -> None:
        self._store.pop(key, None)
        self._expiry.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)

    def _evict_oldest(self) -> None:
        if self._access_order:
            oldest = self._access_order.pop(0)
            self._evict(oldest)

    @property
    def size(self) -> int:
        return len(self._store)


# ──────────────────────────────────────────────
# BaseService
# ──────────────────────────────────────────────

ModelType = TypeVar("ModelType")
RepoType = TypeVar("RepoType", bound=BaseRepository)


class BaseService(Generic[ModelType, RepoType]):
    """
    业务逻辑基类。
    
    子类需设置：
        repository: 对应 Repository 实例
        cache_prefix: 缓存键前缀（可选）
    """

    repository: BaseRepository = None
    cache_prefix: str = ""
    cache: Cache = None  # 共享缓存实例，由外部注入

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        self.db = db
        if cache is not None:
            self.cache = cache

    # ─── 便捷缓存操作 ───

    def _cache_key(self, *parts) -> str:
        return f"{self.cache_prefix}:" + ":".join(str(p) for p in parts)

    def _cache_get(self, *parts):
        if self.cache is None:
            return None
        return self.cache.get(self._cache_key(*parts))

    def _cache_set(self, value: Any, *parts, ttl: Optional[int] = None):
        if self.cache is None:
            return
        self.cache.set(self._cache_key(*parts), value, ttl=ttl)

    def _cache_invalidate(self, *parts):
        if self.cache is None:
            return
        self.cache.invalidate(self._cache_key(*parts))

    def _cache_invalidate_prefix(self, prefix: str = ""):
        if self.cache is None:
            return
        p = f"{self.cache_prefix}:{prefix}" if prefix else self.cache_prefix
        self.cache.invalidate_prefix(p)

    # ─── CRUD 委托 ───

    def get_by_id(self, record_id: int):
        return self.repository.get_by_id(self.db, record_id)

    def list(self, skip: int = 0, limit: int = 100, order_by: Optional[str] = None,
             order_desc: bool = True, filters: Optional[Dict[str, Any]] = None):
        return self.repository.get_all(self.db, skip=skip, limit=limit,
                                       order_by=order_by, order_desc=order_desc,
                                       filters=filters)

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return self.repository.count(self.db, filters=filters)

    def create(self, obj_data: Dict[str, Any]):
        obj = self.repository.create(self.db, obj_data)
        self.db.commit()
        self._cache_invalidate_prefix()  # 清空相关缓存
        return obj

    def update(self, record_id: int, update_data: Dict[str, Any]):
        obj = self.repository.update(self.db, record_id, update_data)
        if obj:
            self.db.commit()
            self._cache_invalidate(str(record_id))
            self._cache_invalidate_prefix()
        return obj

    def delete(self, record_id: int) -> bool:
        result = self.repository.delete(self.db, record_id)
        if result:
            self.db.commit()
            self._cache_invalidate(str(record_id))
            self._cache_invalidate_prefix()
        return result
