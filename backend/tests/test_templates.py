from __future__ import annotations
"""
Task Template API 单元测试 — TemplateService + Router 端点

覆盖: Repository 行为, Service 层 CRUD, create_task_from_template,
权限校验, 系统模板保护, 边界情况
"""
import os
import tempfile
import pytest
import time
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── 1. TemplateService 测试 ──


class TestTemplateService:
    """TemplateService 单元测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from database import Base
        from models.v2_models import TaskTemplate  # noqa: F401

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        yield
        self.db.close()

    def _make_template(self, name="Test", category=None, is_system=False):
        from models.v2_models import TaskTemplate
        t = TaskTemplate(
            name=name,
            description=f"Desc for {name}",
            template_data={"title": name, "type": "general", "priority": "medium"},
            category=category,
            is_system=is_system,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        return t

    # ── CRUD 测试 ──

    def test_create_template(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = svc.create_template(
            name="API Template",
            template_data={"title": "API", "type": "backend"},
            description="Test",
            category="dev",
        )
        assert t.id is not None
        assert t.name == "API Template"
        assert t.category == "dev"
        assert t.usage_count == 0

    def test_get_template(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("Get Me")
        result = svc.get_template(t.id)
        assert result is not None and result.name == "Get Me"

    def test_get_template_not_found(self):
        from services.template_service import TemplateService
        assert TemplateService(self.db).get_template(999) is None

    def test_update_template(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("Before")
        result = svc.update_template(t.id, {"name": "After", "description": "Updated"})
        assert result is not None
        assert result.name == "After"
        assert result.description == "Updated"

    def test_update_template_not_found(self):
        from services.template_service import TemplateService
        assert TemplateService(self.db).update_template(999, {"name": "x"}) is None

    def test_delete_template(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("ToDelete")
        success, msg = svc.delete_template(t.id)
        assert success is True
        assert svc.get_template(t.id) is None

    def test_delete_system_template_forbidden(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("System", is_system=True)
        success, msg = svc.delete_template(t.id)
        assert success is False
        assert "系统模板" in msg

    def test_delete_nonexistent_template(self):
        from services.template_service import TemplateService
        success, msg = TemplateService(self.db).delete_template(999)
        assert success is False
        assert "不存在" in msg

    # ── 列表 + 分页 + 筛选 ──

    def test_list_templates_empty(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        templates, total = svc.list_templates()
        assert total == 0 and len(templates) == 0

    def test_list_templates_pagination(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        for i in range(5):
            self._make_template(f"T-{i}")
        templates, total = svc.list_templates(page=1, page_size=2)
        assert total == 5
        assert len(templates) == 2

    def test_list_templates_category_filter(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        self._make_template("Dev1", category="dev")
        self._make_template("Dev2", category="dev")
        self._make_template("Ops1", category="ops")
        templates, total = svc.list_templates(category="dev")
        assert total == 2
        assert all(t.category == "dev" for t in templates)

    def test_list_templates_ordering(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        self._make_template("Old")
        time.sleep(0.01)
        self._make_template("New")
        templates, _ = svc.list_templates()
        assert templates[0].name == "New"

    # ── create_task_from_template ──

    def test_create_task_from_template(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("Task Template", category="dev")
        result = svc.create_task_from_template(t.id)
        assert result is not None
        assert result["title"] == "Task Template"
        assert result["source"] == "template"
        assert result["task_id"].startswith("tmpl-")

    def test_create_task_from_template_with_overrides(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("Backend API", category="dev")
        result = svc.create_task_from_template(
            t.id, overrides={"title": "Override Title", "priority": "high"}
        )
        assert result is not None
        assert result["title"] == "Override Title"
        assert result["priority"] == "high"

    def test_create_task_from_template_not_found(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        result = svc.create_task_from_template(999)
        assert result is None

    def test_create_task_from_template_increments_usage_count(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = self._make_template("Counter Template")
        assert t.usage_count == 0
        svc.create_task_from_template(t.id)
        self.db.refresh(t)
        assert t.usage_count == 1
        svc.create_task_from_template(t.id)
        self.db.refresh(t)
        assert t.usage_count == 2

    def test_create_task_from_template_preserves_tags(self):
        from services.template_service import TemplateService
        from models.v2_models import TaskTemplate as _TT
        svc = TemplateService(self.db)
        t = _TT(
            name="Tagged",
            description="Has tags",
            template_data={
                "title": "Tagged Task",
                "type": "backend",
                "tags": ["api", "backend"],
                "priority": "low",
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        result = svc.create_task_from_template(t.id)
        assert result["tags"] == ["api", "backend"]

    def test_to_dict_includes_new_fields(self):
        from services.template_service import TemplateService
        svc = TemplateService(self.db)
        t = svc.create_template(
            name="Dict Test",
            template_data={"title": "x"},
            category="test",
            is_system=True,
        )
        d = t.to_dict()
        assert d["category"] == "test"
        assert d["is_system"] is True
        assert d["usage_count"] == 0


# ── 2. Templates Router 端点测试 ──


class TestTemplatesRouter:
    """Templates Router API 端点测试 (FastAPI TestClient + SQLite 文件 DB)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from database import Base, get_db
        from routers.templates_router import router as templates_router
        from services.auth_service import get_current_user

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()

        self._engine = create_engine(f"sqlite:///{self._db_path}")
        Base.metadata.create_all(self._engine)
        TestSession = sessionmaker(bind=self._engine)

        app = FastAPI()
        app.include_router(templates_router)

        def _override_get_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: {"id": 1, "role": "admin"}

        self.client = TestClient(app)
        yield
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def test_list_templates_empty(self):
        resp = self.client.get("/api/v2/templates")
        assert resp.status_code == 200
        d = resp.json()
        assert d["templates"] == [] and d["total"] == 0

    def test_create_template(self):
        resp = self.client.post("/api/v2/templates", json={
            "name": "API Test Template",
            "template_data": {"title": "Test", "type": "backend"},
            "description": "API 测试",
            "category": "dev",
        })
        assert resp.status_code == 201
        d = resp.json()
        assert d["name"] == "API Test Template"
        assert d["category"] == "dev"

    def test_create_template_missing_name(self):
        resp = self.client.post("/api/v2/templates", json={
            "template_data": {"title": "x"},
        })
        assert resp.status_code == 400

    def test_create_template_missing_template_data(self):
        resp = self.client.post("/api/v2/templates", json={"name": "No Data"})
        assert resp.status_code == 400

    def test_get_template_by_id(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "Detail Template",
            "template_data": {"title": "D"},
        })
        tid = cr.json()["id"]
        resp = self.client.get(f"/api/v2/templates/{tid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Detail Template"

    def test_get_template_not_found(self):
        resp = self.client.get("/api/v2/templates/999")
        assert resp.status_code == 404

    def test_update_template(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "Before",
            "template_data": {"title": "B"},
        })
        tid = cr.json()["id"]
        resp = self.client.put(f"/api/v2/templates/{tid}", json={
            "name": "After",
            "description": "Updated",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    def test_update_template_no_fields(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "No Fields",
            "template_data": {"title": "N"},
        })
        tid = cr.json()["id"]
        resp = self.client.put(f"/api/v2/templates/{tid}", json={"unknown": "x"})
        assert resp.status_code == 400

    def test_update_template_not_found(self):
        resp = self.client.put("/api/v2/templates/999", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_template(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "ToDelete",
            "template_data": {"title": "D"},
        })
        tid = cr.json()["id"]
        resp = self.client.delete(f"/api/v2/templates/{tid}")
        assert resp.status_code == 200

    def test_delete_system_template_forbidden(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "System Template",
            "template_data": {"title": "S"},
            "is_system": True,
        })
        tid = cr.json()["id"]
        resp = self.client.delete(f"/api/v2/templates/{tid}")
        assert resp.status_code == 403

    def test_delete_template_not_found(self):
        resp = self.client.delete("/api/v2/templates/999")
        assert resp.status_code == 404

    def test_create_task_from_template(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "Task Creator",
            "template_data": {
                "title": "Template Task",
                "type": "backend",
                "priority": "high",
            },
        })
        tid = cr.json()["id"]
        resp = self.client.post(f"/api/v2/templates/{tid}/create-task", json={
            "overrides": {"priority": "critical"},
        })
        assert resp.status_code == 201
        d = resp.json()
        assert d["title"] == "Template Task"
        assert d["priority"] == "critical"
        assert d["source"] == "template"

    def test_create_task_from_template_no_overrides(self):
        cr = self.client.post("/api/v2/templates", json={
            "name": "No Override",
            "template_data": {"title": "Default Task", "type": "general"},
        })
        tid = cr.json()["id"]
        resp = self.client.post(f"/api/v2/templates/{tid}/create-task")
        assert resp.status_code == 201
        assert resp.json()["title"] == "Default Task"

    def test_create_task_from_template_not_found(self):
        resp = self.client.post("/api/v2/templates/999/create-task")
        assert resp.status_code == 404

    def test_list_templates_with_category_filter(self):
        self.client.post("/api/v2/templates", json={
            "name": "Dev Tpl", "template_data": {"title": "D"}, "category": "dev"})
        self.client.post("/api/v2/templates", json={
            "name": "Ops Tpl", "template_data": {"title": "O"}, "category": "ops"})
        resp = self.client.get("/api/v2/templates?category=dev")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["templates"]]
        assert "Dev Tpl" in names and "Ops Tpl" not in names

    def test_create_template_with_is_system(self):
        resp = self.client.post("/api/v2/templates", json={
            "name": "System",
            "template_data": {"title": "S"},
            "is_system": True,
            "category": "system",
        })
        assert resp.status_code == 201
        d = resp.json()
        assert d["is_system"] is True
        assert d["category"] == "system"

    def test_pagination_total_pages(self):
        for i in range(25):
            self.client.post("/api/v2/templates", json={
                "name": f"Pag-{i}", "template_data": {"title": f"P-{i}"}})
        resp = self.client.get("/api/v2/templates?page=1&page_size=10")
        d = resp.json()
        assert d["total"] == 25
        assert d["total_pages"] == 3
