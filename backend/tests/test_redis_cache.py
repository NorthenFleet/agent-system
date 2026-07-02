"""
task-005-P5-2 — Redis 缓存测试骨架 (P4-1)

目标：验证 Redis 缓存封装和心跳缓存
状态：骨架就绪
"""
import pytest


class TestRedisCache:
    """基础 Redis 操作"""

    def test_redis_connect(self):
        """Redis 连接成功"""
        pytest.skip("待 Redis 实现后启用")

    def test_set_and_get(self):
        """set + get 值匹配"""
        pytest.skip("待 Redis 实现后启用")

    def test_get_nonexistent_key(self):
        """不存在的 key → None"""
        pytest.skip("待 Redis 实现后启用")

    def test_delete(self):
        """正常删除"""
        pytest.skip("待 Redis 实现后启用")

    def test_expire_ttl(self):
        """TTL 过期后返回 None"""
        pytest.skip("待 Redis 实现后启用")


class TestHeartbeatCache:
    """心跳缓存"""

    def test_heartbeat_cache_write(self):
        """心跳写入缓存"""
        pytest.skip("待 Redis 实现后启用")

    def test_heartbeat_cache_read(self):
        """心跳读取缓存"""
        pytest.skip("待 Redis 实现后启用")

    def test_query_cache_hit_count(self):
        """查询缓存命中计数增加"""
        pytest.skip("待 Redis 实现后启用")
