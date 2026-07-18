from __future__ import annotations

import uuid

from models.finance_models import FinanceAuditEvent


def idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


def test_finance_requires_authentication(test_client):
    response = test_client.get("/api/finance/dashboard")
    assert response.status_code == 401


def test_project_create_requires_idempotency_key(test_client, auth_headers):
    response = test_client.post(
        "/api/finance/projects",
        headers=auth_headers,
        json={"project_key": f"missing-idem-{uuid.uuid4().hex[:8]}", "name": "缺少幂等键"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "idempotency_key_required"


def test_project_create_replays_same_idempotent_response(test_client, auth_headers):
    key = str(uuid.uuid4())
    headers = {**auth_headers, "Idempotency-Key": key}
    payload = {"project_key": f"api-project-{uuid.uuid4().hex[:8]}", "name": "API 项目"}
    first = test_client.post("/api/finance/projects", headers=headers, json=payload)
    second = test_client.post("/api/finance/projects", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.headers["Idempotency-Replayed"] == "false"
    assert second.headers["Idempotency-Replayed"] == "true"


def test_dashboard_get_does_not_create_audit_events(test_client, auth_headers, db_session):
    before = db_session.query(FinanceAuditEvent).count()
    response = test_client.get("/api/finance/dashboard", headers=auth_headers)
    after = db_session.query(FinanceAuditEvent).count()
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"
    assert before == after


def test_legacy_sync_is_read_only_and_removed(test_client, auth_headers):
    response = test_client.get("/api/finance/sync", headers=auth_headers)
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "sync_moved"


def test_health_live_is_public(test_client):
    response = test_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
