import json

from services.memory_runtime_config import (
    memory_runtime_configuration,
    public_memory_runtime_configuration,
)


def _set_memory_environment(monkeypatch, *, password: str = "secret"):
    monkeypatch.setenv("AGENT_SYSTEM_RUNTIME_KIND", "test-runtime")
    monkeypatch.setenv("AGENT_SYSTEM_ENV_FILE", "/tmp/agent-system-test.env")
    monkeypatch.setenv("MEMORY_VECTOR_ENABLED", "true")
    monkeypatch.setenv("MEMORY_VECTOR_PREFLIGHT_REQUIRED", "false")
    monkeypatch.setenv(
        "MEMORY_VECTOR_DATABASE_URL",
        f"postgresql+psycopg2://memory:{password}@db.internal:5432/team_dashboard",
    )
    monkeypatch.setenv("MEMORY_EMBEDDING_HOST", "http://ollama.internal:11434")
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "nomic-embed-text:v1.5")
    monkeypatch.setenv("MEMORY_EMBEDDING_DIM", "768")
    monkeypatch.setenv("MEMORY_HYBRID_FUSION_MODE", "shadow")
    monkeypatch.setenv("GRAPH_MEMORY_CONTEXT_ENABLED", "true")
    monkeypatch.setenv(
        "GRAPH_MEMORY_CONTEXT_GATEWAY_URL",
        "http://graph-user:graph-secret@graph.internal:18789",
    )
    monkeypatch.setenv("GRAPH_MEMORY_DEFAULT_MODE", "rerank")


def test_runtime_configuration_is_sanitized_and_stable(monkeypatch):
    _set_memory_environment(monkeypatch, password="first-password")
    first = memory_runtime_configuration(captured_at="2026-09-20T00:00:00+00:00")
    rendered = json.dumps(first, ensure_ascii=False)

    assert "first-password" not in rendered
    assert "graph-secret" not in rendered
    assert first["runtime"]["kind"] == "test-runtime"
    assert first["memory"]["vector"]["database"] == {
        "scheme": "postgresql",
        "host": "db.internal",
        "port": 5432,
        "database": "team_dashboard",
        "user": "memory",
    }
    assert first["memory"]["graph"]["gateway"]["host"] == "graph.internal"

    _set_memory_environment(monkeypatch, password="different-password")
    second = memory_runtime_configuration(captured_at="2026-09-21T00:00:00+00:00")
    assert first["configuration_fingerprint"] == second["configuration_fingerprint"]


def test_runtime_fingerprint_changes_for_effective_non_secret_setting(monkeypatch):
    _set_memory_environment(monkeypatch)
    shadow = memory_runtime_configuration()
    monkeypatch.setenv("MEMORY_HYBRID_FUSION_MODE", "weighted_rrf")
    weighted = memory_runtime_configuration()

    assert shadow["configuration_fingerprint"] != weighted["configuration_fingerprint"]


def test_public_runtime_configuration_omits_local_paths_and_targets(monkeypatch):
    _set_memory_environment(monkeypatch)
    public = public_memory_runtime_configuration()
    rendered = json.dumps(public, ensure_ascii=False)

    assert "working_directory" not in rendered
    assert "db.internal" not in rendered
    assert "graph.internal" not in rendered
    assert public["fusion_mode"] == "shadow"
    assert public["vector_enabled"] is True
