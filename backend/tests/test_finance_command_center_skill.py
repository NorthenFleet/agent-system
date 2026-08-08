import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "integrations"
    / "openclaw"
    / "skills"
    / "finance-command-center"
    / "scripts"
    / "finance_command_center.py"
)
REVIEWER_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "integrations"
    / "openclaw"
    / "skills"
    / "finance-reviewer"
    / "scripts"
    / "finance_reviewer.py"
)


def _load_skill_module(path=SCRIPT_PATH, name="finance_command_center_skill"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_context_uses_latest_session_and_normalizes_open_id(tmp_path, monkeypatch):
    module = _load_skill_module()
    session_index = tmp_path / "sessions.json"
    session_index.write_text(
        json.dumps(
            {
                "agent:soundwave:older": {
                    "updatedAt": 1,
                    "deliveryContext": {"to": "chat:oc_old"},
                    "origin": {"from": "feishu:ou_old"},
                },
                "agent:soundwave:newer": {
                    "updatedAt": 2,
                    "deliveryContext": {"to": "user:ou_current"},
                    "origin": {"from": "feishu:ou_current"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "SESSION_INDEX", session_index)

    assert module._session_context() == {
        "target": "user:ou_current",
        "user_id": "ou_current",
    }


def test_external_id_removes_only_transport_prefixes():
    module = _load_skill_module()

    assert module._external_id("user:ou_123") == "ou_123"
    assert module._external_id("feishu:ou_456") == "ou_456"
    assert module._external_id("ou_789") == "ou_789"


def test_route_requires_shadow_job_contract(monkeypatch):
    module = _load_skill_module()
    monkeypatch.setattr(
        module,
        "_session_context",
        lambda: {"target": "user:ou_current", "user_id": "ou_current"},
    )
    monkeypatch.setattr(
        module,
        "_request",
        lambda *_args, **_kwargs: {
            "action": "finance_intake",
            "finance_job": {"mode": "shadow", "status": "shadow_read"},
        },
    )

    assert module.route("测试报销")["finance_job"]["mode"] == "shadow"


def test_route_rejects_missing_shadow_job(monkeypatch):
    module = _load_skill_module()
    monkeypatch.setattr(
        module,
        "_session_context",
        lambda: {"target": "user:ou_current", "user_id": "ou_current"},
    )
    monkeypatch.setattr(
        module,
        "_request",
        lambda *_args, **_kwargs: {"action": "finance_intake"},
    )

    try:
        module.route("测试报销")
    except RuntimeError as exc:
        assert "shadow intake contract" in str(exc)
    else:
        raise AssertionError("missing shadow job must be rejected")


def test_soundwave_extraction_uses_soundwave_service_identity(monkeypatch):
    module = _load_skill_module()
    captured = {}
    monkeypatch.setattr(
        module,
        "_request",
        lambda method, path, payload=None: captured.update(
            {"method": method, "path": path, "payload": payload}
        ) or {"ok": True},
    )

    module.extract("job-1", {"amount": 10}, ["message"], 0.9, 1)

    assert captured["payload"]["agent_id"] == "soundwave"
    assert captured["payload"]["expected_version"] == 1


def test_reviewer_uses_independent_inspector_identity(monkeypatch):
    module = _load_skill_module(REVIEWER_SCRIPT_PATH, "finance_reviewer_skill")
    captured = {}
    monkeypatch.setattr(
        module,
        "_request",
        lambda method, path, payload=None: captured.update(
            {"method": method, "path": path, "payload": payload}
        ) or {"ok": True},
    )

    module.review("job-1", "approve", "通过", [], 0.95, 2)

    assert captured["payload"]["reviewer_agent_id"] == "inspector"
    assert captured["payload"]["expected_version"] == 2
