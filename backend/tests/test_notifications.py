from __future__ import annotations
"""
Notification API 单元测试 — NotificationService + Router 端点

覆盖: CRUD, mark_read, mark_all_read, unread_count, 权限校验,
分页, 筛选, 边界情况
"""
import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ── 1. NotificationService 测试 ──


class TestNotificationService:
    """NotificationService 单元测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from database import Base
        from models.v2_models import Notification  # noqa: F401

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        yield
        self.db.close()

    def _make_notification(self, user_id=1, is_read=False, ntype="system"):
        from models.v2_models import Notification
        n = Notification(
            user_id=user_id,
            type=ntype,
            title=f"Notification for {user_id}",
            content="Test content",
            is_read=is_read,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(n)
        self.db.commit()
        self.db.refresh(n)
        return n

    # ── CRUD 测试 ──

    def test_create_notification(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = svc.create_notification(
            user_id=1, type="task", title="Task Assigned",
            content="You have a new task", source_id="task-123",
        )
        assert n.id is not None
        assert n.title == "Task Assigned"
        assert n.is_read is False
        assert n.source_id == "task-123"

    def test_create_notification_with_expires(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        n = svc.create_notification(
            user_id=1, type="alert", title="Expiring",
            expires_at=expires,
        )
        assert n.expires_at is not None

    def test_get_user_notifications_empty(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        notifications, total = svc.get_user_notifications(user_id=1)
        assert total == 0 and len(notifications) == 0

    def test_get_user_notifications_pagination(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        for i in range(5):
            self._make_notification(user_id=1)
        notifications, total = svc.get_user_notifications(
            user_id=1, page=1, page_size=2
        )
        assert total == 5
        assert len(notifications) == 2

    def test_get_user_notifications_type_filter(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        self._make_notification(user_id=1, ntype="task")
        self._make_notification(user_id=1, ntype="alert")
        self._make_notification(user_id=1, ntype="system")
        notifications, total = svc.get_user_notifications(
            user_id=1, type="task"
        )
        assert total == 1
        assert all(n.type == "task" for n in notifications)

    def test_get_user_notifications_is_read_filter(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        self._make_notification(user_id=1, is_read=False)
        self._make_notification(user_id=1, is_read=True)
        self._make_notification(user_id=1, is_read=False)
        unread, total = svc.get_user_notifications(
            user_id=1, is_read=False
        )
        assert total == 2

    def test_get_notification(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1)
        result = svc.get_notification(n.id, user_id=1)
        assert result is not None and result.id == n.id

    def test_get_notification_wrong_user(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1)
        result = svc.get_notification(n.id, user_id=2)
        assert result is None

    def test_mark_read(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1, is_read=False)
        result = svc.mark_read(n.id, user_id=1)
        assert result is not None
        assert result.is_read is True
        assert result.read_at is not None

    def test_mark_read_already_read(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1, is_read=True)
        result = svc.mark_read(n.id, user_id=1)
        assert result is not None
        assert result.is_read is True

    def test_mark_read_wrong_user(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1)
        result = svc.mark_read(n.id, user_id=2)
        assert result is None

    def test_mark_read_not_found(self):
        from services.notification_service import NotificationService
        result = NotificationService(self.db).mark_read(999, user_id=1)
        assert result is None

    def test_mark_all_read(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        self._make_notification(user_id=1, is_read=False)
        self._make_notification(user_id=1, is_read=False)
        self._make_notification(user_id=1, is_read=True)
        self._make_notification(user_id=2, is_read=False)
        count = svc.mark_all_read(user_id=1)
        assert count == 2

    def test_mark_all_read_no_unread(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        self._make_notification(user_id=1, is_read=True)
        count = svc.mark_all_read(user_id=1)
        assert count == 0

    def test_get_unread_count(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        self._make_notification(user_id=1, is_read=False)
        self._make_notification(user_id=1, is_read=False)
        self._make_notification(user_id=1, is_read=True)
        assert svc.get_unread_count(user_id=1) == 2

    def test_get_unread_count_zero(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        assert svc.get_unread_count(user_id=1) == 0

    def test_delete_notification(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1)
        assert svc.delete_notification(n.id, user_id=1) is True
        assert svc.get_notification(n.id, user_id=1) is None

    def test_delete_notification_wrong_user(self):
        from services.notification_service import NotificationService
        svc = NotificationService(self.db)
        n = self._make_notification(user_id=1)
        assert svc.delete_notification(n.id, user_id=2) is False

    def test_delete_notification_not_found(self):
        from services.notification_service import NotificationService
        assert NotificationService(self.db).delete_notification(999, 1) is False

    def test_to_dict(self):
        n = self._make_notification(user_id=1, ntype="alert")
        d = n.to_dict()
        assert d["user_id"] == 1
        assert d["type"] == "alert"
        assert d["title"] == "Notification for 1"
        assert "created_at" in d
        assert d["is_read"] is False


# ── 2. Notification Router 端点测试 ──


class TestNotificationRouter:
    """Notification Router API 端点测试 (FastAPI TestClient + SQLite 文件 DB)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from database import Base, get_db
        from routers.notification_router import router as notification_router
        from services.auth_service import get_current_user

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()

        self._engine = create_engine(f"sqlite:///{self._db_path}")
        Base.metadata.create_all(self._engine)
        TestSession = sessionmaker(bind=self._engine)

        app = FastAPI()
        app.include_router(notification_router)

        def _override_get_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: {
            "id": 1, "role": "admin"
        }

        self.client = TestClient(app)
        yield
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _create_notification_via_api(self, user_id=1):
        return self.client.post("/api/v2/notifications", json={
            "user_id": user_id,
            "type": "system",
            "title": f"Test Notif for {user_id}",
            "content": "Test content",
        })

    def test_list_notifications_empty(self):
        resp = self.client.get("/api/v2/notifications")
        assert resp.status_code == 200
        d = resp.json()
        assert d["notifications"] == [] and d["total"] == 0

    def test_create_notification(self):
        resp = self._create_notification_via_api(user_id=1)
        assert resp.status_code == 201
        d = resp.json()
        assert d["title"] == "Test Notif for 1"
        assert d["type"] == "system"

    def test_create_notification_missing_user_id(self):
        resp = self.client.post("/api/v2/notifications", json={
            "type": "system", "title": "No User",
        })
        assert resp.status_code == 400

    def test_create_notification_missing_title(self):
        resp = self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "system",
        })
        assert resp.status_code == 400

    def test_create_notification_missing_type(self):
        resp = self.client.post("/api/v2/notifications", json={
            "user_id": 1, "title": "No Type",
        })
        assert resp.status_code == 400

    def test_get_notification(self):
        cr = self._create_notification_via_api()
        nid = cr.json()["id"]
        resp = self.client.get(f"/api/v2/notifications/{nid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test Notif for 1"

    def test_get_notification_not_found(self):
        resp = self.client.get("/api/v2/notifications/999")
        assert resp.status_code == 404

    def test_get_notification_other_user(self):
        """用户不能查看别人的通知"""
        cr = self.client.post("/api/v2/notifications", json={
            "user_id": 2, "type": "system", "title": "For User 2",
        })
        nid = cr.json()["id"]
        resp = self.client.get(f"/api/v2/notifications/{nid}")
        assert resp.status_code == 404

    def test_mark_notification_read(self):
        cr = self._create_notification_via_api()
        nid = cr.json()["id"]
        resp = self.client.put(f"/api/v2/notifications/{nid}/read")
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True
        assert resp.json()["read_at"] is not None

    def test_mark_read_not_found(self):
        resp = self.client.put("/api/v2/notifications/999/read")
        assert resp.status_code == 404

    def test_mark_all_read(self):
        self._create_notification_via_api()
        self._create_notification_via_api()
        resp = self.client.put("/api/v2/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["message"] == "全部已读"
        assert resp.json()["updated_count"] == 2

    def test_get_unread_count(self):
        self._create_notification_via_api()
        self._create_notification_via_api()
        resp = self.client.get("/api/v2/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 2

    def test_get_unread_count_after_read(self):
        self._create_notification_via_api()
        self.client.put("/api/v2/notifications/read-all")
        resp = self.client.get("/api/v2/notifications/unread-count")
        assert resp.json()["unread_count"] == 0

    def test_delete_notification(self):
        cr = self._create_notification_via_api()
        nid = cr.json()["id"]
        resp = self.client.delete(f"/api/v2/notifications/{nid}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "通知已删除"

    def test_delete_notification_not_found(self):
        resp = self.client.delete("/api/v2/notifications/999")
        assert resp.status_code == 404

    def test_delete_notification_other_user(self):
        cr = self.client.post("/api/v2/notifications", json={
            "user_id": 2, "type": "system", "title": "For User 2",
        })
        nid = cr.json()["id"]
        resp = self.client.delete(f"/api/v2/notifications/{nid}")
        assert resp.status_code == 404

    def test_list_with_type_filter(self):
        self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "task", "title": "Task Notif"})
        self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "alert", "title": "Alert Notif"})
        resp = self.client.get("/api/v2/notifications?type=task")
        assert resp.status_code == 200
        names = [n["title"] for n in resp.json()["notifications"]]
        assert "Task Notif" in names and "Alert Notif" not in names

    def test_list_with_is_read_filter(self):
        self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "system", "title": "Unread"})
        cr = self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "system", "title": "Read"})
        nid = cr.json()["id"]
        self.client.put(f"/api/v2/notifications/{nid}/read")
        resp = self.client.get("/api/v2/notifications?is_read=false")
        assert resp.status_code == 200
        names = [n["title"] for n in resp.json()["notifications"]]
        assert "Unread" in names and "Read" not in names

    def test_pagination(self):
        for i in range(10):
            self.client.post("/api/v2/notifications", json={
                "user_id": 1, "type": "system", "title": f"N-{i}"})
        resp = self.client.get("/api/v2/notifications?page=1&page_size=3")
        d = resp.json()
        assert d["total"] == 10
        assert len(d["notifications"]) == 3
        assert d["total_pages"] == 4

    def test_create_notification_with_expires(self):
        expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        resp = self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "system", "title": "Expiring",
            "expires_at": expires,
        })
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    def test_create_notification_bad_expires_format(self):
        resp = self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "system", "title": "Bad Date",
            "expires_at": "not-a-date",
        })
        assert resp.status_code == 400

    def test_notification_with_source_and_link(self):
        resp = self.client.post("/api/v2/notifications", json={
            "user_id": 1, "type": "task", "title": "Linked",
            "source_id": "task-42",
            "link": "/tasks/42",
        })
        assert resp.status_code == 201
        d = resp.json()
        assert d["source_id"] == "task-42"
        assert d["link"] == "/tasks/42"
