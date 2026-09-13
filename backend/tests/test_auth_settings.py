from types import SimpleNamespace

import pytest

from models.v2_models import SystemSetting
from routers.auth_router import _is_trusted_development_request


@pytest.mark.parametrize(
    ("host", "trusted"),
    [
        ("192.168.31.144", True),
        ("100.100.20.30", True),
        ("fd7a:115c:a1e0::12", True),
        ("192.168.32.10", False),
        ("203.0.113.20", False),
    ],
)
def test_development_session_network_allowlist(host, trusted):
    request = SimpleNamespace(client=SimpleNamespace(host=host))
    assert _is_trusted_development_request(request) is trusted


def test_login_switch_uses_trusted_network_development_session(test_client, db_session, admin_user):
    db_session.query(SystemSetting).filter(SystemSetting.key == "auth.login_enabled").delete()
    db_session.commit()

    try:
        settings = test_client.get("/api/v2/auth/settings")
        assert settings.status_code == 200
        assert settings.json() == {"login_enabled": False, "mode": "development"}

        assert test_client.get("/api/v2/users").status_code == 401

        development = test_client.post("/api/v2/auth/development-session")
        assert development.status_code == 200
        body = development.json()
        assert body["auth_mode"] == "development"
        assert body["user"]["username"] == admin_user.username
        development_headers = {"Authorization": f"Bearer {body['access_token']}"}

        assert test_client.get("/api/v2/users", headers=development_headers).status_code == 200

        enabled = test_client.put(
            "/api/v2/auth/settings",
            json={"login_enabled": True},
            headers=development_headers,
        )
        assert enabled.status_code == 200
        assert enabled.json()["login_enabled"] is True
        assert test_client.get("/api/v2/users", headers=development_headers).status_code == 401

        login = test_client.post(
            "/api/v2/auth/login",
            json={"username": admin_user.username, "password": "test123"},
        )
        assert login.status_code == 200
        login_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        disabled = test_client.put(
            "/api/v2/auth/settings",
            json={"login_enabled": False},
            headers=login_headers,
        )
        assert disabled.status_code == 200
        assert disabled.json()["login_enabled"] is False
    finally:
        db_session.query(SystemSetting).filter(SystemSetting.key == "auth.login_enabled").delete()
        db_session.commit()
