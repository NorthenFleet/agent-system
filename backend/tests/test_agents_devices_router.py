"""
task-005-P5-2 — agents_router + devices_router 测试骨架 (P3-4)

目标：验证 Agent 和 Device 路由端点行为正确
状态：骨架就绪
"""
import pytest


class TestAgentsRouter:
    """GET /api/v2/agents"""

    def test_list_agents(self):
        pytest.skip("待 Router 实现后启用")

    """GET /api/v2/agents/{id}"""

    def test_get_agent_success(self):
        pytest.skip("待 Router 实现后启用")

    def test_get_agent_not_found_404(self):
        pytest.skip("待 Router 实现后启用")

    """POST /api/v2/agents/{id}/heartbeat"""

    def test_heartbeat_report(self):
        pytest.skip("待 Router 实现后启用")

    """GET /api/v2/agents/{id}/heartbeat/live"""

    def test_heartbeat_live(self):
        pytest.skip("待 Router 实现后启用")

    """GET /api/v2/agents/{id}/heartbeat/history"""

    def test_heartbeat_history(self):
        pytest.skip("待 Router 实现后启用")

    """GET /api/v2/agents/stats"""

    def test_agents_stats(self):
        pytest.skip("待 Router 实现后启用")

    """GET /api/v2/agents/{id}/status-history"""

    def test_status_history(self):
        pytest.skip("待 Router 实现后启用")


class TestDevicesRouter:
    """GET /api/v2/devices"""

    def test_list_devices(self):
        pytest.skip("待 Router 实现后启用")

    """POST /api/v2/devices"""

    def test_create_device(self):
        pytest.skip("待 Router 实现后启用")

    """PUT /api/v2/devices/{id}"""

    def test_update_device(self):
        pytest.skip("待 Router 实现后启用")

    """DELETE /api/v2/devices/{id}"""

    def test_delete_device(self):
        pytest.skip("待 Router 实现后启用")

    """GET /api/v2/devices/stats"""

    def test_devices_stats(self):
        pytest.skip("待 Router 实现后启用")


class TestTeamStatus:
    """GET /api/v2/team/status"""

    def test_team_status_aggregate(self):
        """团队状态聚合（Agent + Device + Task 统计）"""
        pytest.skip("待 Router 实现后启用")
