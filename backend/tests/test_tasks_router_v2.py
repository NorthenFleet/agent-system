"""
tasks_router_v2 集成测试

验证 /api/v2/tasks 端点行为正确，包括认证、CRUD、筛选、分页等功能。
"""
import pytest


class TestTasksRouterV2:
    """任务管理 API 集成测试"""

    def test_create_task_success(self, test_client, auth_headers):
        response = test_client.post(
            "/api/v2/tasks",
            json={
                "title": "测试创建任务",
                "description": "测试任务描述",
                "type": "backend",
                "priority": "high",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "测试创建任务"
        assert data["status"] == "pending"

    def test_create_task_missing_title_422(self, test_client, auth_headers):
        response = test_client.post(
            "/api/v2/tasks",
            json={
                "description": "缺少标题",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_task_unauthorized_401(self, test_client):
        response = test_client.post(
            "/api/v2/tasks",
            json={
                "title": "无权限创建",
            },
        )
        assert response.status_code == 401

    def test_list_tasks_pagination(self, test_client, auth_headers):
        for i in range(5):
            test_client.post(
                "/api/v2/tasks",
                json={"title": f"分页测试任务 {i}"},
                headers=auth_headers,
            )

        response = test_client.get(
            "/api/v2/tasks?page=1&page_size=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_get_task_stats(self, test_client, auth_headers):
        response = test_client.get(
            "/api/v2/tasks/stats",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_get_gantt_data(self, test_client, auth_headers):
        response = test_client.get(
            "/api/v2/tasks/gantt",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data