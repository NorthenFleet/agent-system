import json
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import routers.monitoring_router as monitoring_router_module
from routers.auth_router import get_current_user
from models.v2_models import Base, Notification, User
from services.memory_system_health_status import (
    publish_memory_health_notification,
    read_memory_system_health,
    read_memory_system_matrix,
)


def _write(path, *, healthy=True, checked_at=None):
    path.write_text(
        json.dumps(
            {
                "schema_version": "memory-system-health.v1",
                "checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
                "healthy": healthy,
                "case_id": "optimus-memory-inventory-system-gate",
                "failures": [] if healthy else [{"check": "identity.bound"}],
                "summary": {"channels": {"approved_graph_projection": "ready"}},
            }
        ),
        encoding="utf-8",
    )


def test_status_reader_marks_fresh_health_and_stale_state(tmp_path):
    path = tmp_path / "health.json"
    now = datetime.now(timezone.utc)
    _write(path, checked_at=now.isoformat())

    healthy = read_memory_system_health(path, now=now)
    assert healthy["status"] == "healthy"
    assert healthy["healthy"] is True

    stale = read_memory_system_health(
        path,
        stale_after_seconds=60,
        now=now + timedelta(seconds=61),
    )
    assert stale["status"] == "stale"
    assert stale["healthy"] is False
    assert stale["failures"][-1]["check"] == "freshness"


def test_status_reader_fails_closed_for_missing_file(tmp_path):
    result = read_memory_system_health(tmp_path / "missing.json")

    assert result["status"] == "missing"
    assert result["healthy"] is False

    matrix = read_memory_system_matrix(tmp_path / "missing-matrix.json")
    assert matrix["status"] == "missing"
    assert matrix["healthy"] is False


def test_notifications_are_emitted_only_on_state_transitions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        User(
            username="admin",
            password_hash="not-used",
            display_name="管理员",
            role="admin",
            is_active=True,
        )
    )
    session.commit()

    baseline = publish_memory_health_notification(
        session,
        {"healthy": True, "checked_at": "2026-09-17T00:00:00+00:00", "failures": []},
    )
    assert baseline["status"] == "unchanged"

    alert = publish_memory_health_notification(
        session,
        {
            "healthy": False,
            "checked_at": "2026-09-17T00:01:00+00:00",
            "failures": [{"check": "channels.approved_graph_projection.status"}],
        },
    )
    assert alert["notifications_created"] == 1
    assert session.query(Notification).count() == 1
    assert session.query(Notification).first().type == "alert"
    assert session.query(Notification).first().source_id.startswith("memory-system:primary:unhealthy:")

    duplicate_state = publish_memory_health_notification(
        session,
        {"healthy": False, "checked_at": "2026-09-17T00:02:00+00:00", "failures": []},
    )
    assert duplicate_state["status"] == "unchanged"
    assert session.query(Notification).count() == 1

    recovered = publish_memory_health_notification(
        session,
        {"healthy": True, "checked_at": "2026-09-17T00:03:00+00:00", "failures": []},
    )
    assert recovered["notifications_created"] == 1
    assert session.query(Notification).count() == 2
    assert session.query(Notification).order_by(Notification.id.desc()).first().type == "system"

    matrix_alert = publish_memory_health_notification(
        session,
        {
            "monitor_key": "matrix",
            "healthy": False,
            "checked_at": "2026-09-17T00:04:00+00:00",
            "failures": [{"check": "case.inspector"}],
        },
    )
    assert matrix_alert["notifications_created"] == 1
    assert session.query(Notification).count() == 3
    session.close()


def test_monitoring_route_exposes_authenticated_memory_health(monkeypatch):
    approval_updates = []
    recorded_decisions = []
    release_state = {
        "status": "awaiting_approval",
        "technical_ready": True,
        "promotion_ready": False,
        "candidate_digest": "a" * 64,
        "release_completed": False,
    }
    monkeypatch.setattr(
        monitoring_router_module,
        "read_memory_system_health",
        lambda: {"status": "healthy", "healthy": True, "summary": {}},
    )
    monkeypatch.setattr(
        monitoring_router_module,
        "read_memory_system_matrix",
        lambda: {"status": "healthy", "healthy": True, "summary": {"passed_cases": 5}},
    )
    monkeypatch.setattr(
        monitoring_router_module,
        "calculate_memory_slo",
        lambda days=7: {"status": "healthy", "window_days": days, "monitors": {}},
    )
    monkeypatch.setattr(
        monitoring_router_module,
        "read_memory_system_drill",
        lambda: {"status": "healthy", "healthy": True, "summary": {"passed_scenarios": 4}},
    )
    monkeypatch.setattr(
        monitoring_router_module,
        "current_release_gate",
        lambda: dict(release_state),
    )
    monkeypatch.setattr(monitoring_router_module, "read_latest_release_execution", lambda: None)
    monkeypatch.setattr(
        monitoring_router_module,
        "read_release_audit",
        lambda limit=20: [{"schema_version": "memory-release-decision.v1", "status": "awaiting_approval"}][:limit],
    )
    monkeypatch.setattr(
        monitoring_router_module,
        "update_release_candidate_approval",
        lambda **kwargs: approval_updates.append(kwargs) or {"approval": {"status": "approved"}},
    )
    monkeypatch.setattr(
        monitoring_router_module,
        "record_release_decision",
        lambda decision: recorded_decisions.append(decision),
    )
    app = FastAPI()
    app.include_router(monitoring_router_module.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "role": "admin"}

    response = TestClient(app).get("/api/v2/monitoring/memory-system")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["matrix"]["summary"]["passed_cases"] == 5
    assert response.json()["slo"]["window_days"] == 7
    assert response.json()["drill"]["summary"]["passed_scenarios"] == 4
    assert response.json()["release"]["technical_ready"] is True

    slo = TestClient(app).get("/api/v2/monitoring/memory-system/slo?days=30")
    assert slo.status_code == 200
    assert slo.json()["window_days"] == 30

    monkeypatch.setattr(
        monitoring_router_module,
        "memory_runtime_configuration",
        lambda: {
            "configuration_fingerprint": "sha256:test",
            "memory": {"retrieval": {"fusion_mode": "shadow"}},
        },
    )
    configuration = TestClient(app).get(
        "/api/v2/monitoring/memory-system/configuration"
    )
    assert configuration.status_code == 200
    assert configuration.json()["configuration_fingerprint"] == "sha256:test"
    assert configuration.json()["memory"]["retrieval"]["fusion_mode"] == "shadow"

    release = TestClient(app).get("/api/v2/monitoring/memory-system/release")
    assert release.status_code == 200
    assert release.json()["status"] == "awaiting_approval"

    audit = TestClient(app).get("/api/v2/monitoring/memory-system/release/audit?limit=5")
    assert audit.status_code == 200
    assert audit.json()["total"] == 1

    approval = TestClient(app).post(
        "/api/v2/monitoring/memory-system/release/approve",
        json={"expected_digest": "a" * 64},
    )
    assert approval.status_code == 200
    assert approval_updates[-1] == {
        "actor": "1",
        "expected_digest": "a" * 64,
        "approve": True,
    }
    assert recorded_decisions[-1]["status"] == "awaiting_approval"

    revoke = TestClient(app).post(
        "/api/v2/monitoring/memory-system/release/revoke",
        json={"expected_digest": "a" * 64},
    )
    assert revoke.status_code == 200
    assert approval_updates[-1]["approve"] is False

    release_state.update(
        {"status": "completed", "promotion_ready": True, "release_completed": True}
    )
    immutable = TestClient(app).post(
        "/api/v2/monitoring/memory-system/release/revoke",
        json={"expected_digest": "a" * 64},
    )
    assert immutable.status_code == 409
    assert immutable.json()["detail"] == "completed release approval is immutable"

    app.dependency_overrides[get_current_user] = lambda: {"sub": "2", "role": "viewer"}
    forbidden = TestClient(app).post(
        "/api/v2/monitoring/memory-system/release/approve",
        json={"expected_digest": "a" * 64},
    )
    assert forbidden.status_code == 403
