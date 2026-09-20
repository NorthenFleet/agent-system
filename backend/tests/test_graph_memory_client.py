import hashlib
import hmac
import json
import stat

from services import graph_memory_client as module


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size: int):
        return self.body


def test_context_client_signs_body_and_only_returns_approved_owner_scoped_items(
    tmp_path, monkeypatch
):
    secret_path = tmp_path / "bridge.key"
    secret = b"x" * 48
    secret_path.write_bytes(secret)
    secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "retrieval_mode": "hybrid",
                "items": [
                    {
                        "node_id": "node-approved",
                        "source_ref": "project-memory:approved-1",
                        "title": "审批约束",
                        "content": "计划批准后才能执行。",
                        "authority": "approved_projection",
                        "visibility": "project",
                        "owner_user_id": "user-1",
                        "project_id": "project-1",
                        "score": 0.92,
                        "confidence": 0.95,
                        "freshness_score": 0.8,
                        "relation_relevance": 0.9,
                        "memory_key": "decision.approval_gate",
                        "version": 3,
                        "valid_until": "2099-01-01T00:00:00Z",
                        "relations": [{"type": "APPLIES_TO", "label": "任务规划"}],
                    },
                    {
                        "node_id": "node-unreviewed",
                        "source_ref": "session:raw-1",
                        "content": "不应进入上下文。",
                        "authority": "unreviewed_session",
                        "visibility": "project",
                        "owner_user_id": "user-1",
                        "project_id": "project-1",
                    },
                    {
                        "node_id": "node-other-user",
                        "source_ref": "project-memory:other-user",
                        "content": "不应跨用户召回。",
                        "authority": "approved_memory",
                        "visibility": "private",
                        "owner_user_id": "user-2",
                    },
                ],
            }
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    client = module.GraphMemoryClient(secret_path=str(secret_path), timeout=0.9)

    result = client.retrieve_context(
        user_id="user-1",
        project_id="project-1",
        agent_id="optimus",
        mission_id="mission-1",
        query="审批约束",
    )

    assert result["health"]["status"] == "ready"
    assert result["health"]["results"] == 1
    assert result["health"]["filtered"] == 2
    assert result["items"][0]["source_ref"] == "project-memory:approved-1"
    assert result["items"][0]["memory_key"] == "decision.approval_gate"
    assert result["items"][0]["relations"][0]["weight"] == 0.95

    request = captured["request"]
    headers = {key.lower(): value for key, value in request.header_items()}
    body = request.data
    assert captured["timeout"] == 0.9
    assert json.loads(body) == {
        "user_id": "user-1",
        "project_id": "project-1",
        "agent_id": "optimus",
        "mission_id": "mission-1",
        "query": "审批约束",
        "limit": 8,
        "include_neighbors": True,
        "max_hops": 1,
        "relation_types": [
            "CONSTRAINS", "APPLIES_TO", "SUPPORTED_BY", "DERIVED_FROM", "SUPERSEDES", "RELATED_TO"
        ],
        "allowed_scopes": ["profile", "project", "agent"],
        "include_unreviewed": False,
    }
    body_hash = hashlib.sha256(body).hexdigest()
    assert headers["x-gm-body-sha256"] == body_hash
    canonical = module._canonical_request(
        "POST",
        client.retrieval_path,
        headers["x-gm-timestamp"],
        headers["x-gm-nonce"],
        headers["x-gm-request-id"],
        headers["x-gm-actor-id"],
        headers["x-gm-actor-role"],
        headers["x-gm-permissions"],
        body_hash,
    )
    assert hmac.compare_digest(
        headers["x-gm-signature"],
        hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest(),
    )


def test_context_client_can_be_disabled_without_reading_a_credential(tmp_path):
    client = module.GraphMemoryClient(
        secret_path=str(tmp_path / "missing.key"),
        enabled=False,
    )

    result = client.retrieve_context(user_id="user-1", query="测试")

    assert result["items"] == []
    assert result["health"]["status"] == "disabled"
    assert client.health()["credential_available"] is False


def test_context_client_rejects_expired_or_invalid_validity_windows(tmp_path, monkeypatch):
    secret_path = tmp_path / "bridge.key"
    secret_path.write_bytes(b"x" * 48)
    secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def fake_urlopen(_request, timeout):
        assert timeout > 0
        return FakeResponse(
            {
                "items": [
                    {
                        "source_ref": "fact:expired",
                        "content": "过期约束",
                        "authority": "approved_memory",
                        "visibility": "profile",
                        "owner_user_id": "1",
                        "valid_until": "2020-01-01T00:00:00Z",
                    },
                    {
                        "source_ref": "fact:invalid-date",
                        "content": "非法日期",
                        "authority": "approved_memory",
                        "visibility": "profile",
                        "owner_user_id": "1",
                        "valid_until": "not-a-date",
                    },
                ]
            }
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    client = module.GraphMemoryClient(secret_path=str(secret_path))
    result = client.retrieve_context(user_id="1", query="审批")

    assert result["items"] == []
    assert result["health"]["filtered"] == 2


def test_projection_upsert_uses_a_distinct_permission_and_accepts_idempotent_result(
    tmp_path, monkeypatch
):
    secret_path = tmp_path / "bridge.key"
    secret_path.write_bytes(b"p" * 48)
    secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse({"status": "already_applied", "projection_id": "node-1"})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    client = module.GraphMemoryClient(secret_path=str(secret_path))
    result = client.upsert_projection(
        {
            "event_id": "graph-event-1",
            "event_type": "memory.published",
            "aggregate_type": "project_memory",
            "aggregate_id": "project-memory-1",
            "source_ref": "project-memory:project-memory-1",
            "user_id": "1",
            "project_id": "project-1",
            "title": "项目决策",
            "content": "审批后执行。",
            "status": "active",
        }
    )

    headers = {key.lower(): value for key, value in captured["request"].header_items()}
    assert captured["request"].full_url.endswith(client.projection_path)
    assert headers["x-gm-permissions"] == "memory.write.projection"
    assert result == {"status": "already_applied", "projection_id": "node-1"}


def test_projection_inventory_is_metadata_only_and_uses_read_permission(tmp_path, monkeypatch):
    secret_path = tmp_path / "bridge.key"
    secret_path.write_bytes(b"i" * 48)
    secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse(
            {
                "items": [
                    {
                        "source_ref": "project-memory:memory-1",
                        "owner_user_id": "user-1",
                        "project_id": "project-1",
                        "agent_id": "",
                        "visibility": "project",
                        "content_hash": "hash-1",
                        "status": "active",
                    }
                ],
                "count": 1,
            }
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    client = module.GraphMemoryClient(secret_path=str(secret_path))
    inventory = client.projection_inventory(user_id="user-1")

    headers = {key.lower(): value for key, value in captured["request"].header_items()}
    assert captured["request"].full_url.endswith(client.inventory_path)
    assert headers["x-gm-permissions"] == "memory.read.projection"
    assert inventory[0]["content_hash"] == "hash-1"
