import importlib.util
import json
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[2]
    / "integrations"
    / "openclaw"
    / "skills"
    / "memory-context"
    / "scripts"
    / "memory_context.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("memory_context_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_session_identity_uses_newest_valid_backup(tmp_path):
    module = _module()
    module.SESSION_DIR = tmp_path
    module.AGENT_STATE_DB = tmp_path / "missing-agent-state.sqlite"
    older = tmp_path / "sessions.json.bak.1"
    newer = tmp_path / "sessions.json.bak.2"
    older.write_text("{}", encoding="utf-8")
    newer.write_text(
        json.dumps(
            {
                "agent:optimus:main": {
                    "updatedAt": 10,
                    "deliveryContext": {
                        "channel": "feishu",
                        "to": "user:ou_bound",
                    },
                    "origin": {
                        "provider": "feishu",
                        "from": "feishu:ou_bound",
                    },
                },
                "agent:optimus:cron:test": {"updatedAt": 20},
            }
        ),
        encoding="utf-8",
    )

    assert module._session_context() == {
        "channel": "feishu",
        "external_user_id": "ou_bound",
    }


def test_current_agent_state_identity_wins_over_stale_legacy_backup(tmp_path):
    module = _module()
    module.SESSION_DIR = tmp_path
    (tmp_path / "sessions.json.bak.1").write_text(
        json.dumps(
            {
                "agent:optimus:main": {
                    "updatedAt": 1,
                    "deliveryContext": {"channel": "feishu", "to": "user:ou_stale"},
                }
            }
        ),
        encoding="utf-8",
    )
    module.AGENT_STATE_DB = tmp_path / "openclaw-agent.sqlite"
    import sqlite3

    conn = sqlite3.connect(module.AGENT_STATE_DB)
    conn.execute(
        """
        CREATE TABLE session_participants (
            session_key TEXT, identity_namespace TEXT, actor_id TEXT,
            contribution_count INTEGER, first_prompted_at INTEGER,
            last_prompted_at INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO session_participants VALUES (
            'agent:optimus:main',
            '{"pluginId":"feishu","senderKind":"human"}',
            'ou_current',1,10,20
        )
        """
    )
    conn.commit()
    conn.close()

    assert module._session_context() == {
        "channel": "feishu",
        "external_user_id": "ou_current",
    }


def test_inspect_sends_scoped_contract(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_session_context",
        lambda: {"channel": "feishu", "external_user_id": "ou_bound"},
    )
    captured = {}

    def fake_request(payload):
        captured.update(payload)
        return {"status": "ready"}

    monkeypatch.setattr(module, "_request", fake_request)

    result = module.inspect("你记住了什么", project_id="project-1", persist=False)

    assert result == {"status": "ready"}
    assert captured == {
        "channel": "feishu",
        "external_user_id": "ou_bound",
        "query": "你记住了什么",
        "agent_id": "optimus",
        "project_id": "project-1",
        "limit": 12,
        "persist": False,
    }
