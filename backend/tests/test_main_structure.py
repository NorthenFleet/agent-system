"""
task-005-P5-2 — main.py 精简测试骨架 (P3-5)

目标：验证 main.py ≤ 100 行且路由注册完整
状态：骨架就绪
"""
import pytest
import os


class TestMainStructure:
    """main.py 行数限制"""

    def test_main_lines_under_100(self):
        """main.py 行数 ≤ 100"""
        pytest.skip("待重构完成后启用")
        main_path = os.path.join(os.path.dirname(__file__), '..', 'main.py')
        with open(main_path) as f:
            lines = f.readlines()
        assert len(lines) <= 100, f"main.py 有 {len(lines)} 行，应 ≤ 100"

    def test_all_routers_registered(self):
        """所有 router 已 include_router"""
        pytest.skip("待重构完成后启用")
        # 检查 main.py 中 include_router 调用数量

    def test_cors_config_present(self):
        """CORS 配置存在"""
        pytest.skip("待重构完成后启用")

    def test_health_endpoint(self):
        """/health 返回 {"status": "ok"}"""
        pytest.skip("待重构完成后启用")
