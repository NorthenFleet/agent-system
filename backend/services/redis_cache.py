"""
Redis 缓存服务 — V3 架构

提供统一的 Redis 缓存封装，支持：
- 心跳缓存（agent 最新状态，TTL 60s）
- 查询缓存（任务列表/统计，TTL 30s）
- 通用 key-value 缓存

@task task-005-P4-1
@author 🟥 拉斐尔
"""
import json
import os
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone

import redis

# ─── 配置 ───

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_TTL_HEARTBEAT = int(os.getenv("REDIS_TTL_HEARTBEAT", "60"))    # 心跳缓存 60s
REDIS_TTL_QUERY = int(os.getenv("REDIS_TTL_QUERY", "30"))             # 查询缓存 30s
REDIS_TTL_DEFAULT = int(os.getenv("REDIS_TTL_DEFAULT", "300"))        # 默认 5min

# ─── Key 命名规范 ───
# hb:<agent_id>          单个 agent 最新心跳
# hb:all                 全部 agent 状态快照
# q:tasks:<hash>         任务列表查询结果（hash 为筛选参数）
# q:stats                统计数据
# meta:<key>             通用元数据


class RedisCache:
    """Redis 缓存封装"""

    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._enabled = False

    def init(self) -> bool:
        """初始化 Redis 连接，失败时静默降级为无缓存"""
        try:
            self._client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            self._client.ping()
            self._enabled = True
            print(f"[Redis] ✅ 已连接 {REDIS_URL}")
            return True
        except Exception as e:
            print(f"[Redis] ⚠️ 连接失败，缓存已禁用: {e}")
            self._enabled = False
            self._client = None
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def client(self) -> Optional[redis.Redis]:
        return self._client

    # ─── 通用操作 ───

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值（自动反序列化 JSON）"""
        if not self._enabled or not self._client:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int = REDIS_TTL_DEFAULT) -> bool:
        """设置缓存值（自动序列化 JSON）"""
        if not self._enabled or not self._client:
            return False
        try:
            self._client.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
            return True
        except Exception:
            return False

    def delete(self, *keys: str) -> int:
        """删除缓存，返回实际删除数量"""
        if not self._enabled or not self._client:
            return 0
        try:
            return self._client.delete(*keys)
        except Exception:
            return 0

    def exists(self, key: str) -> bool:
        if not self._enabled or not self._client:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """按模式批量失效（SCAN + DELETE）"""
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

    # ─── 心跳缓存 ───

    def cache_heartbeat(self, agent_id: str, data: Dict[str, Any]) -> bool:
        """缓存单个 agent 最新心跳"""
        return self.set(f"hb:{agent_id}", data, ttl=REDIS_TTL_HEARTBEAT)

    def get_heartbeat(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存的 agent 心跳"""
        return self.get(f"hb:{agent_id}")

    def cache_all_heartbeats(self, agents: List[Dict[str, Any]]) -> bool:
        """缓存全部 agent 状态快照"""
        return self.set("hb:all", agents, ttl=REDIS_TTL_HEARTBEAT)

    def get_all_heartbeats(self) -> Optional[List[Dict[str, Any]]]:
        return self.get("hb:all")

    def invalidate_heartbeat(self, agent_id: str) -> int:
        """失效单个 agent + 全局心跳缓存"""
        return self.delete(f"hb:{agent_id}", "hb:all")

    # ─── 查询缓存 ───

    def cache_query(self, name: str, params: Dict[str, Any], data: Any, ttl: int = REDIS_TTL_QUERY) -> bool:
        """缓存查询结果，key 含参数 hash"""
        import hashlib
        param_str = json.dumps(params, sort_keys=True, default=str)
        key_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        key = f"q:{name}:{key_hash}"
        return self.set(key, data, ttl=ttl)

    def get_query(self, name: str, params: Dict[str, Any]) -> Optional[Any]:
        import hashlib
        param_str = json.dumps(params, sort_keys=True, default=str)
        key_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        key = f"q:{name}:{key_hash}"
        return self.get(key)

    def invalidate_query(self, name: str) -> int:
        """失效某类查询的所有缓存"""
        return self.invalidate_pattern(f"q:{name}:*")

    def invalidate_all_queries(self) -> int:
        return self.invalidate_pattern("q:*")

    # ─── 统计 ───

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        if not self._enabled or not self._client:
            return {"enabled": False}
        try:
            info = self._client.info("memory")
            db_size = self._client.dbsize()
            return {
                "enabled": True,
                "url": REDIS_URL,
                "keys_count": db_size,
                "used_memory_human": info.get("used_memory_human", "N/A"),
            }
        except Exception as e:
            return {"enabled": True, "error": str(e)}


# ─── 全局单例 ───

redis_cache = RedisCache()
