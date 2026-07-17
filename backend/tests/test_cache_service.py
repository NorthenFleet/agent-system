"""
CacheService 单元测试 — Sprint 5 P4 性能优化

测试覆盖:
1. 初始化和连接
2. get/set/delete 基本操作
3. invalidate 模式匹配
4. exists 检查
5. 优雅降级（连接失败）
6. cache_or 装饰器
7. get_stats

@author: 拉斐尔 (🟥 后端开发)
"""
import json
import time
import pytest
from unittest.mock import patch, MagicMock

from services.cache_service import CacheService


# ─── 初始化 ───

class TestCacheServiceInit:
    def test_init_defaults(self):
        """默认配置正确"""
        cs = CacheService(redis_url="redis://localhost:6379/1")
        assert cs._redis_url == "redis://localhost:6379/1"
        assert cs._default_ttl == 300
        assert cs._enabled is True  # CACHE_DEFAULT is True

    def test_init_custom_params(self):
        """自定义参数正确"""
        cs = CacheService(redis_url="redis://test:6379/2", default_ttl=60, enabled=False)
        assert cs._redis_url == "redis://test:6379/2"
        assert cs._default_ttl == 60
        assert cs._enabled is False

    def test_init_disabled(self):
        """enabled=False 时降级"""
        cs = CacheService(enabled=False)
        assert cs.init() is False
        assert cs.enabled is False

    def test_init_with_env_false(self):
        """CACHE_ENABLED=false 时降级"""
        with patch.dict("os.environ", {"CACHE_ENABLED": "false"}):
            cs = CacheService()
            assert cs._enabled is False

    def test_init_with_custom_ttl_env(self):
        """CACHE_DEFAULT_TTL 环境变量生效"""
        with patch.dict("os.environ", {"CACHE_DEFAULT_TTL": "120"}):
            cs = CacheService()
            assert cs._default_ttl == 120


# ─── 连接 ───

class TestCacheServiceConnect:
    @patch("services.cache_service.redis")
    def test_connect_success(self, mock_redis):
        """Redis 连接成功"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis.from_url.return_value = mock_client

        cs = CacheService(redis_url="redis://test:6379/0")
        result = cs.init()

        assert result is True
        assert cs.enabled is True
        assert cs.client is mock_client
        mock_redis.from_url.assert_called_once()
        mock_client.ping.assert_called_once()

    @patch("services.cache_service.redis")
    def test_connect_failure(self, mock_redis):
        """Redis 连接失败时优雅降级"""
        mock_redis.from_url.side_effect = Exception("Connection refused")

        cs = CacheService(redis_url="redis://bad:6379/0")
        result = cs.init()

        assert result is False
        assert cs.enabled is False
        assert cs.client is None


# ─── get/set/delete ───

class TestCacheServiceCRUD:
    @pytest.fixture
    def cs(self):
        cs = CacheService(redis_url="redis://test:6379/0")
        cs._enabled = True
        cs._client = MagicMock()
        return cs

    def test_set_and_get(self, cs):
        """set 和 get 操作"""
        cs._client.get.return_value = json.dumps({"key": "value", "num": 42})
        cs._client.setex.return_value = True

        result = cs.set("test:key", {"key": "value", "num": 42})
        assert result is True
        cs._client.setex.assert_called_once()

        got = cs.get("test:key")
        assert got == {"key": "value", "num": 42}

    def test_get_miss_returns_none(self, cs):
        """缓存未命中返回 None"""
        cs._client.get.return_value = None
        assert cs.get("nonexistent") is None

    def test_set_disabled_returns_false(self):
        """禁用状态下 set 返回 False"""
        cs = CacheService(enabled=False)
        assert cs.set("key", "value") is False

    def test_get_disabled_returns_none(self):
        """禁用状态下 get 返回 None"""
        cs = CacheService(enabled=False)
        assert cs.get("key") is None

    def test_delete(self, cs):
        """delete 操作"""
        cs._client.delete.return_value = 2
        result = cs.delete("key1", "key2")
        assert result == 2
        cs._client.delete.assert_called_once_with("key1", "key2")

    def test_delete_disabled(self):
        """禁用状态下 delete 返回 0"""
        cs = CacheService(enabled=False)
        assert cs.delete("key") == 0

    def test_set_default_ttl(self, cs):
        """set 使用默认 TTL"""
        cs._client.setex.return_value = True
        cs.set("key", "val")
        args = cs._client.setex.call_args
        assert args[0][1] == 300  # default_ttl

    def test_set_custom_ttl(self, cs):
        """set 使用自定义 TTL"""
        cs._client.setex.return_value = True
        cs.set("key", "val", ttl=60)
        args = cs._client.setex.call_args
        assert args[0][1] == 60

    def test_set_exception_returns_false(self, cs):
        """set 异常时返回 False"""
        cs._client.setex.side_effect = Exception("Redis error")
        assert cs.set("key", "val") is False

    def test_get_exception_returns_none(self, cs):
        """get 异常时返回 None"""
        cs._client.get.side_effect = Exception("Redis error")
        assert cs.get("key") is None


# ─── invalidate ───

class TestCacheServiceInvalidate:
    @pytest.fixture
    def cs(self):
        cs = CacheService(redis_url="redis://test:6379/0")
        cs._enabled = True
        cs._client = MagicMock()
        return cs

    def test_invalidate_pattern(self, cs):
        """按模式失效"""
        cs._client.scan.side_effect = [
            (0, ["v2:tasks:1", "v2:tasks:2"]),
        ]
        cs._client.delete.return_value = 2

        result = cs.invalidate("v2:tasks:*")
        assert result == 2

    def test_invalidate_no_match(self, cs):
        """无匹配键时返回 0"""
        cs._client.scan.return_value = (0, [])
        assert cs.invalidate("nonexistent:*") == 0

    def test_invalidate_disabled(self):
        """禁用状态下返回 0"""
        cs = CacheService(enabled=False)
        assert cs.invalidate("key:*") == 0


# ─── exists ───

class TestCacheServiceExists:
    @pytest.fixture
    def cs(self):
        cs = CacheService(redis_url="redis://test:6379/0")
        cs._enabled = True
        cs._client = MagicMock()
        return cs

    def test_exists_true(self, cs):
        cs._client.exists.return_value = 1
        assert cs.exists("key") is True

    def test_exists_false(self, cs):
        cs._client.exists.return_value = 0
        assert cs.exists("key") is False

    def test_exists_disabled(self):
        cs = CacheService(enabled=False)
        assert cs.exists("key") is False


# ─── cache_or 装饰器 ───

class TestCacheOrDecorator:
    @pytest.fixture
    def cs(self):
        cs = CacheService(redis_url="redis://test:6379/0")
        cs._enabled = True
        cs._client = MagicMock()
        return cs

    def test_cache_miss_executes_fn(self, cs):
        """缓存未命中时执行函数并缓存结果"""
        call_count = 0

        def slow_fn(x, y):
            nonlocal call_count
            call_count += 1
            return x + y

        decorated = cs.cache_or("test:fn", ttl=60)(slow_fn)

        # First call - miss
        cs._client.get.return_value = None
        result1 = decorated(1, 2)
        assert result1 == 3
        assert call_count == 1

        # Second call - hit
        cs._client.get.return_value = json.dumps(3)
        result2 = decorated(1, 2)
        assert result2 == 3
        assert call_count == 1  # 函数未被再次调用

    def test_cache_hit_returns_cached(self, cs):
        """缓存命中直接返回"""
        cs._client.get.return_value = json.dumps({"data": "cached"})

        @cs.cache_or("test:data")
        def get_data():
            return {"data": "fresh"}

        result = get_data()
        assert result == {"data": "cached"}

    def test_cache_miss_set_called(self, cs):
        """缓存未命中时 set 被调用"""
        cs._client.get.return_value = None
        cs._client.setex.return_value = True

        @cs.cache_or("test:data", ttl=120)
        def get_data():
            return {"result": 42}

        result = get_data()
        assert result == {"result": 42}
        cs._client.setex.assert_called_once()

    def test_cache_disabled_executes_fn(self, cs):
        """缓存禁用时函数正常执行"""
        cs._enabled = False

        @cs.cache_or("test:data")
        def get_data():
            return "executed"

        result = get_data()
        assert result == "executed"


# ─── get_stats ───

class TestCacheServiceStats:
    def test_stats_disabled(self):
        cs = CacheService(enabled=False)
        stats = cs.get_stats()
        assert stats["enabled"] is False

    @patch("services.cache_service.redis")
    def test_stats_connected(self, mock_redis):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = {"used_memory_human": "1.2M"}
        mock_client.dbsize.return_value = 42
        mock_redis.from_url.return_value = mock_client

        cs = CacheService(redis_url="redis://test:6379/0")
        cs.init()

        stats = cs.get_stats()
        assert stats["enabled"] is True
        assert stats["keys_count"] == 42
        assert stats["used_memory_human"] == "1.2M"
