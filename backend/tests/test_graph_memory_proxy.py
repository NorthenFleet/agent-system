import hashlib
import hmac
import json
import stat
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException

from services import graph_memory_proxy as module


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size: int):
        return self.body


def test_proxy_signs_server_side_request_without_exposing_secret(tmp_path, monkeypatch):
    secret_path = tmp_path / "bridge.key"
    secret_path.write_bytes(b"x" * 48)
    secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"agentId": "perceptor", "totalNodes": 5})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    proxy = module.GraphMemoryProxy(secret_path=str(secret_path))
    result = proxy.get(
        "/graph-memory/v1/agents/perceptor/summary",
        {"sub": "1", "role": "admin"},
        ("memory.read.private",),
    )
    assert result["totalNodes"] == 5
    request = captured["request"]
    parts = urlsplit(request.full_url)
    raw_url = parts.path + (f"?{parts.query}" if parts.query else "")
    headers = {key.lower(): value for key, value in request.header_items()}
    canonical = module._canonical_request(
        "GET",
        raw_url,
        headers["x-gm-timestamp"],
        headers["x-gm-nonce"],
        headers["x-gm-request-id"],
        headers["x-gm-actor-id"],
        headers["x-gm-actor-role"],
        headers["x-gm-permissions"],
    )
    expected = hmac.new(b"x" * 48, canonical.encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(headers["x-gm-signature"], expected)
    assert "bridge.key" not in request.full_url
    assert b"x" * 16 not in request.full_url.encode()


def test_proxy_rejects_non_admin_and_unsafe_secret_permissions(tmp_path):
    secret_path = tmp_path / "bridge.key"
    secret_path.write_bytes(b"x" * 48)
    secret_path.chmod(0o644)
    proxy = module.GraphMemoryProxy(secret_path=str(secret_path))
    with pytest.raises(HTTPException) as non_admin:
        proxy.get("/graph-memory/v1/agents/a/summary", {"sub": "2", "role": "viewer"}, ("memory.read.private",))
    assert non_admin.value.status_code == 403
    with pytest.raises(HTTPException) as unsafe:
        proxy.get("/graph-memory/v1/agents/a/summary", {"sub": "1", "role": "admin"}, ("memory.read.private",))
    assert unsafe.value.status_code == 503


def test_summary_projects_metadata_and_never_marks_pending_backlog_ready(tmp_path, monkeypatch):
    secret_path = tmp_path / "bridge.key"
    secret_path.write_bytes(b"x" * 48)
    secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def fake_urlopen(_request, timeout):
        assert timeout == 5.0
        return FakeResponse({
            "agentId": "wheeljack",
            "initialized": True,
            "state": "ready",
            "totalNodes": 3,
            "totalEdges": 0,
            "communities": 0,
            "byType": {"TASK": 3},
            "byEdgeType": {},
            "pendingMessages": 8,
            "pendingSessions": 2,
            "oldestPendingAt": 1_725_000_000_000,
            "nextRetryAt": 1_725_000_300_000,
            "queueState": "retrying",
            "vectorCount": 0,
            "retrievalMode": "fts5",
            "lastExtraction": {
                "outcome": "succeeded",
                "messageCount": 4,
                "nodeCount": 3,
                "edgeCount": 0,
                "createdAt": 1_725_000_100_000,
                "sourceSession": "must-not-cross-proxy",
            },
            "rawMessages": [{"content": "must-not-cross-proxy"}],
            "query": "must-not-cross-proxy",
            "snapshots": [{"content": "must-not-cross-proxy"}],
        })

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    proxy = module.GraphMemoryProxy(secret_path=str(secret_path))
    result = proxy.get_summary(
        "/graph-memory/v1/agents/wheeljack/summary",
        {"sub": "1", "role": "admin"},
        ("memory.read.private",),
    )

    assert result["state"] == "backlog"
    assert result["pendingMessages"] == 8
    assert result["pendingSessions"] == 2
    assert result["nextRetryAt"] == 1_725_000_300_000
    assert result["retrievalMode"] == "fts5"
    assert "rawMessages" not in result
    assert "query" not in result
    assert "snapshots" not in result
    assert "sourceSession" not in result["lastExtraction"]


def test_summary_rejects_non_numeric_retry_metadata():
    result = module.GraphMemoryProxy._summary({
        "initialized": True,
        "totalNodes": 1,
        "pendingMessages": 1,
        "nextRetryAt": "raw retry error must not cross proxy",
        "lastSuccessfulExtraction": {"content": "must-not-cross-proxy"},
    })

    assert result["state"] == "backlog"
    assert result["nextRetryAt"] is None
    assert result["lastSuccessfulExtraction"] is None


def test_summary_attention_wins_over_backlog_and_empty_is_truthful():
    attention = module.GraphMemoryProxy._summary({
        "initialized": True,
        "state": "attention",
        "totalNodes": 3,
        "pendingMessages": 8,
        "queueState": "dead_letter",
        "deadLetterCount": 1,
    })
    empty = module.GraphMemoryProxy._summary({
        "initialized": True,
        "state": "ready",
        "totalNodes": 0,
        "pendingMessages": 0,
        "pendingSessions": 0,
        "queueState": "idle",
    })

    assert attention["state"] == "attention"
    assert empty["state"] == "empty"


def test_summary_remains_compatible_when_new_queue_metadata_is_missing():
    result = module.GraphMemoryProxy._summary({
        "agentId": "perceptor",
        "initialized": True,
        "state": "ready",
        "totalNodes": 5,
        "totalEdges": 1,
        "communities": 0,
        "byType": {"TASK": 2, "SKILL": 2, "EVENT": 1},
        "byEdgeType": {"USED_SKILL": 1},
        "pendingMessages": 0,
        "lastUpdatedAt": 1_725_000_000_000,
        "lastExtraction": None,
    })

    assert result["state"] == "ready"
    assert "nextRetryAt" not in result
    assert "queueState" not in result
    assert "pendingSessions" not in result
