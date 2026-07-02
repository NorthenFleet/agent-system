"""
task-005-P5-2 — JWT 中间件测试骨架 (P3-6)

目标：验证 JWT 中间件覆盖所有受保护端点
状态：骨架就绪
"""
import pytest


class TestJWTAuth:
    """无/无效 token 拒绝"""

    def test_no_token_401(self):
        """无 token → 401"""
        pytest.skip("待 JWT 实现后启用")

    def test_invalid_token_401(self):
        """无效 token → 401"""
        pytest.skip("待 JWT 实现后启用")

    def test_expired_token_401(self):
        """过期 token → 401"""
        pytest.skip("待 JWT 实现后启用")

    def test_valid_token_200(self):
        """有效 token → 200"""
        pytest.skip("待 JWT 实现后启用")


class TestLoginFlow:
    """登录流程"""

    def test_login_returns_access_token(self):
        """登录成功 → access_token"""
        pytest.skip("待 JWT 实现后启用")

    def test_login_returns_refresh_token(self):
        """登录成功 → refresh_token"""
        pytest.skip("待 JWT 实现后启用")

    def test_refresh_token_gets_new_access_token(self):
        """refresh_token → 新 access_token"""
        pytest.skip("待 JWT 实现后启用")

    def test_expired_refresh_token_401(self):
        """过期 refresh_token → 401"""
        pytest.skip("待 JWT 实现后启用")


class TestRoleBasedAccess:
    """角色权限"""

    def test_admin_access_restricted_endpoint(self):
        """admin 角色可访问受保护端点"""
        pytest.skip("待 JWT 实现后启用")

    def test_viewer_blocked_from_admin_endpoint(self):
        """viewer 角色不可访问 admin 端点"""
        pytest.skip("待 JWT 实现后启用")


class TestPublicEndpoints:
    """公开端点"""

    def test_health_no_auth_required(self):
        """/health 无需 token"""
        pytest.skip("待 JWT 实现后启用")
