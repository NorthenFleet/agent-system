from scripts import memory_vector_preflight as preflight
from urllib.error import URLError


def _config(**overrides):
    values = {
        "vector_enabled": True,
        "database_url": "postgresql://user:secret@db.internal:5432/memory",
        "ollama_host": "http://ollama.internal:11434",
        "embedding_model": "nomic-embed-text:v1.5",
        "embedding_dimension": 768,
        "fusion_mode": "shadow",
        "unified_db_path": "/tmp/unified.db",
    }
    values.update(overrides)
    return preflight.PreflightConfig(**values)


def test_database_target_never_contains_password():
    target = preflight.safe_database_target(
        "postgresql+psycopg2://memory_user:super-secret@db.internal:5432/memory"
    )

    assert target == {
        "scheme": "postgresql",
        "host": "db.internal",
        "port": "5432",
        "database": "memory",
        "user": "memory_user",
    }
    assert "super-secret" not in str(target)


def test_preflight_reports_ready_without_mutating_dependencies(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "check_postgres",
        lambda _config: {
            "status": "ready",
            "extension_available": True,
            "extension_installed": True,
            "projection_table": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_ollama",
        lambda _config, probe_embedding: {
            "status": "ready",
            "model_available": True,
            "dimension_matches": probe_embedding,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_queue",
        lambda _config: {"status": "ready", "total": 0},
    )

    report = preflight.run_preflight(_config(), probe_embedding=True)

    assert report["infrastructure_ready"] is True
    assert report["ready_for_vector_rollout"] is True
    assert report["blockers"] == []


def test_preflight_separates_infrastructure_from_disabled_rollout(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "check_postgres",
        lambda _config: {
            "status": "ready",
            "extension_available": True,
            "extension_installed": True,
            "projection_table": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_ollama",
        lambda _config, probe_embedding: {
            "status": "ready",
            "model_available": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_queue",
        lambda _config: {"status": "ready", "total": 4},
    )

    report = preflight.run_preflight(
        _config(vector_enabled=False), probe_embedding=False
    )

    assert report["infrastructure_ready"] is True
    assert report["ready_for_vector_rollout"] is False
    assert report["blockers"] == ["vector_enabled"]


def test_preflight_blocks_when_projection_migration_is_missing(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "check_postgres",
        lambda _config: {
            "status": "ready",
            "extension_available": True,
            "extension_installed": True,
            "projection_table": False,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_ollama",
        lambda _config, probe_embedding: {
            "status": "ready",
            "model_available": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_queue",
        lambda _config: {"status": "ready", "total": 0},
    )

    report = preflight.run_preflight(_config(), probe_embedding=False)

    assert report["infrastructure_ready"] is False
    assert "projection_table_ready" in report["blockers"]


def test_preflight_reports_configuration_source_and_fingerprint(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "check_postgres",
        lambda _config: {
            "status": "ready",
            "extension_available": True,
            "extension_installed": True,
            "projection_table": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_ollama",
        lambda _config, probe_embedding: {
            "status": "ready",
            "model_available": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_queue",
        lambda _config: {"status": "ready", "total": 0},
    )

    report = preflight.run_preflight(
        _config(),
        probe_embedding=False,
        environment={
            "status": "loaded",
            "env_file": "/tmp/runtime.env",
            "source_valid": True,
        },
    )

    assert report["configuration"]["source"]["status"] == "loaded"
    assert report["configuration"]["fingerprint"].startswith("sha256:")
    assert report["checks"]["configuration"]["configuration_source_valid"] is True


def test_preflight_blocks_missing_configuration_source(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "check_postgres",
        lambda _config: {
            "status": "ready",
            "extension_available": True,
            "extension_installed": True,
            "projection_table": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_ollama",
        lambda _config, probe_embedding: {
            "status": "ready",
            "model_available": True,
        },
    )
    monkeypatch.setattr(
        preflight,
        "check_queue",
        lambda _config: {"status": "ready", "total": 0},
    )

    report = preflight.run_preflight(
        _config(),
        probe_embedding=False,
        environment={
            "status": "missing",
            "env_file": "/missing/runtime.env",
            "source_valid": False,
        },
    )

    assert report["infrastructure_ready"] is True
    assert report["ready_for_vector_rollout"] is False
    assert "configuration_source_valid" in report["blockers"]


def test_dependency_error_distinguishes_sandbox_restriction():
    restricted = URLError(PermissionError(1, "Operation not permitted"))
    unavailable = URLError(ConnectionRefusedError(61, "Connection refused"))

    assert preflight.classify_dependency_error(restricted) == "environment_restricted"
    assert preflight.classify_dependency_error(unavailable) == "dependency_unavailable"


def test_process_environment_requires_complete_memory_configuration(
    monkeypatch, tmp_path
):
    for group in preflight.MEMORY_CONFIG_GROUPS:
        for key in group:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MEMORY_VECTOR_ENABLED", "true")

    result = preflight.load_environment(str(tmp_path / "missing.env"))

    assert result["status"] == "process_environment"
    assert result["source_valid"] is False
