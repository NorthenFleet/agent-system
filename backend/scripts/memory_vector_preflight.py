#!/usr/bin/env python3
"""Read-only production preflight for approved-memory vector retrieval."""

from __future__ import annotations

import argparse
import errno
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.memory_runtime_config import memory_runtime_configuration

DEFAULT_UNIFIED_DB = BACKEND_DIR / "data" / "unified_dashboard.db"
DEFAULT_DATABASE_URL = "postgresql+psycopg2:///team_dashboard"
DEFAULT_OLLAMA_HOST = "http://192.168.1.5:11434"
DEFAULT_MODEL = "nomic-embed-text:v1.5"
DEFAULT_DIMENSION = 768
VALID_FUSION_MODES = {"baseline", "shadow", "weighted_rrf"}
MEMORY_CONFIG_GROUPS = (
    ("MEMORY_VECTOR_ENABLED",),
    ("MEMORY_VECTOR_DATABASE_URL", "DATABASE_URL"),
    ("MEMORY_EMBEDDING_HOST", "EMBEDDING_BINDING_HOST", "OLLAMA_HOST"),
    ("MEMORY_EMBEDDING_MODEL", "LIGHTRAG_EMBEDDING_MODEL", "EMBEDDING_MODEL"),
    ("MEMORY_EMBEDDING_DIM", "EMBEDDING_DIM"),
    ("MEMORY_HYBRID_FUSION_MODE",),
)


def configuration_source_valid() -> bool:
    return all(
        any(os.getenv(key) is not None for key in group)
        for group in MEMORY_CONFIG_GROUPS
    )


def normalize_postgres_dsn(value: str) -> str:
    clean = str(value or "").strip()
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if clean.startswith(prefix):
            return "postgresql://" + clean[len(prefix) :]
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[len("postgres://") :]
    return clean


def enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def safe_error(exc: Exception, secrets: list[str] | None = None) -> str:
    message = f"{type(exc).__name__}: {exc}"
    for secret in secrets or []:
        if secret:
            message = message.replace(secret, "***")
    return message[:500]


def safe_database_target(database_url: str) -> dict[str, str]:
    normalized = normalize_postgres_dsn(database_url)
    parsed = urllib.parse.urlsplit(normalized)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "local-socket",
        "port": str(parsed.port or 5432),
        "database": (parsed.path or "").lstrip("/") or "default",
        "user": parsed.username or "current-user",
    }


@dataclass(frozen=True)
class PreflightConfig:
    vector_enabled: bool
    database_url: str
    ollama_host: str
    embedding_model: str
    embedding_dimension: int
    fusion_mode: str
    unified_db_path: str


def load_environment(env_file: str) -> dict[str, Any]:
    path = Path(env_file)
    if not path.exists():
        configured_keys = sorted(
            key
            for group in MEMORY_CONFIG_GROUPS
            for key in group
            if os.getenv(key) is not None
        )
        return {
            "status": "process_environment" if configured_keys else "missing",
            "env_file": str(path),
            "loaded": False,
            "configured_keys": configured_keys,
            "source_valid": configuration_source_valid(),
        }
    try:
        from dotenv import dotenv_values, load_dotenv

        declared_keys = sorted(str(key) for key in dotenv_values(path) if key)
        before = {key for key in declared_keys if os.getenv(key) is not None}
        load_dotenv(path, override=False)
        after = {key for key in declared_keys if os.getenv(key) is not None}
        return {
            "status": "loaded" if after - before else "present_no_change",
            "env_file": str(path.resolve()),
            "loaded": bool(after - before),
            "declared_key_count": len(declared_keys),
            "effective_key_count": len(after),
            "source_valid": configuration_source_valid(),
        }
    except ImportError:
        return {
            "status": "dotenv_unavailable",
            "env_file": str(path.resolve()),
            "loaded": False,
            "source_valid": False,
        }


def classify_dependency_error(exc: Exception) -> str:
    """Separate execution-environment restrictions from dependency outages."""
    reason = getattr(exc, "reason", None)
    candidate = reason if isinstance(reason, BaseException) else exc
    error_number = getattr(candidate, "errno", None)
    message = str(exc).lower()
    if isinstance(candidate, PermissionError) or error_number in {errno.EPERM, errno.EACCES}:
        return "environment_restricted"
    if "operation not permitted" in message or "permission denied" in message:
        return "environment_restricted"
    return "dependency_unavailable"


def resolve_config() -> PreflightConfig:
    database_url = os.getenv("MEMORY_VECTOR_DATABASE_URL") or os.getenv(
        "DATABASE_URL", DEFAULT_DATABASE_URL
    )
    return PreflightConfig(
        vector_enabled=enabled(os.getenv("MEMORY_VECTOR_ENABLED")),
        database_url=normalize_postgres_dsn(database_url),
        ollama_host=(
            os.getenv("MEMORY_EMBEDDING_HOST")
            or os.getenv("EMBEDDING_BINDING_HOST")
            or os.getenv("OLLAMA_HOST")
            or DEFAULT_OLLAMA_HOST
        ).rstrip("/"),
        embedding_model=(
            os.getenv("MEMORY_EMBEDDING_MODEL")
            or os.getenv("LIGHTRAG_EMBEDDING_MODEL")
            or os.getenv("EMBEDDING_MODEL")
            or DEFAULT_MODEL
        ),
        embedding_dimension=int(
            os.getenv("MEMORY_EMBEDDING_DIM")
            or os.getenv("EMBEDDING_DIM")
            or DEFAULT_DIMENSION
        ),
        fusion_mode=str(
            os.getenv("MEMORY_HYBRID_FUSION_MODE") or "weighted_rrf"
        ).strip().lower(),
        unified_db_path=os.getenv("UNIFIED_DB_PATH") or str(DEFAULT_UNIFIED_DB),
    )


def check_postgres(config: PreflightConfig) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unavailable",
        "target": safe_database_target(config.database_url),
        "extension_available": False,
        "extension_installed": False,
        "projection_table": False,
    }
    parsed = urllib.parse.urlsplit(config.database_url)
    secrets = [parsed.password or ""]
    try:
        import psycopg2

        connection = psycopg2.connect(config.database_url, connect_timeout=3)
        try:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version')"
                )
                database, user, version = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT default_version, installed_version
                    FROM pg_available_extensions WHERE name='vector'
                    """
                )
                extension = cursor.fetchone()
                cursor.execute(
                    "SELECT to_regclass('public.approved_memory_vectors') IS NOT NULL"
                )
                table_exists = bool(cursor.fetchone()[0])
                result.update(
                    {
                        "status": "ready",
                        "database": database,
                        "user": user,
                        "server_version": version,
                        "extension_available": extension is not None,
                        "extension_installed": bool(extension and extension[1]),
                        "extension_default_version": extension[0] if extension else None,
                        "extension_installed_version": extension[1] if extension else None,
                        "projection_table": table_exists,
                    }
                )
                if table_exists:
                    cursor.execute("SELECT COUNT(*) FROM approved_memory_vectors")
                    result["projection_rows"] = int(cursor.fetchone()[0])
        finally:
            connection.close()
    except Exception as exc:
        result["error"] = safe_error(exc, secrets)
        result["reason_code"] = classify_dependency_error(exc)
    return result


def check_ollama(config: PreflightConfig, *, probe_embedding: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unavailable",
        "host": config.ollama_host,
        "model": config.embedding_model,
        "model_available": False,
        "expected_dimension": config.embedding_dimension,
        "probe_performed": probe_embedding,
    }
    try:
        with urllib.request.urlopen(
            config.ollama_host + "/api/tags", timeout=3
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [
            str(model.get("name") or "")
            for model in payload.get("models") or []
            if model.get("name")
        ]
        result.update(
            {
                "status": "ready",
                "model_available": config.embedding_model in models,
                "installed_model_count": len(models),
            }
        )
        if probe_embedding and result["model_available"]:
            request = urllib.request.Request(
                config.ollama_host + "/api/embed",
                data=json.dumps(
                    {
                        "model": config.embedding_model,
                        "input": ["memory vector preflight"],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                embedding_payload = json.loads(response.read().decode("utf-8"))
            embeddings = embedding_payload.get("embeddings") or []
            actual_dimension = len(embeddings[0]) if embeddings else 0
            result["actual_dimension"] = actual_dimension
            result["dimension_matches"] = actual_dimension == config.embedding_dimension
    except Exception as exc:
        result["error"] = safe_error(exc)
        result["reason_code"] = classify_dependency_error(exc)
    return result


def check_queue(config: PreflightConfig) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unavailable",
        "database": config.unified_db_path,
        "table_exists": False,
        "total": 0,
        "by_status": {},
    }
    try:
        database_uri = Path(config.unified_db_path).resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True, timeout=3)
        connection.row_factory = sqlite3.Row
        try:
            table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='memory_vector_index_jobs'
                """
            ).fetchone()
            if not table:
                return {**result, "status": "ready"}
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM memory_vector_index_jobs GROUP BY status
                """
            ).fetchall()
            by_status = {str(row["status"]): int(row["count"]) for row in rows}
            return {
                **result,
                "status": "ready",
                "table_exists": True,
                "total": sum(by_status.values()),
                "by_status": by_status,
            }
        finally:
            connection.close()
    except Exception as exc:
        result["error"] = safe_error(exc)
        result["reason_code"] = classify_dependency_error(exc)
        return result


def run_preflight(
    config: PreflightConfig,
    *,
    probe_embedding: bool,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    postgres = check_postgres(config)
    ollama = check_ollama(config, probe_embedding=probe_embedding)
    queue = check_queue(config)
    fusion_valid = config.fusion_mode in VALID_FUSION_MODES
    embedding_ready = bool(
        ollama.get("status") == "ready" and ollama.get("model_available")
    )
    if probe_embedding:
        embedding_ready = embedding_ready and bool(ollama.get("dimension_matches"))
    infrastructure_checks = {
        "postgres_reachable": postgres.get("status") == "ready",
        "vector_extension_available": bool(postgres.get("extension_available")),
        "vector_extension_installed": bool(postgres.get("extension_installed")),
        "projection_table_ready": bool(postgres.get("projection_table")),
        "embedding_ready": embedding_ready,
        "queue_readable": queue.get("status") == "ready",
    }
    configuration_checks = {
        "vector_enabled": config.vector_enabled,
        "fusion_mode_valid": fusion_valid,
        "configuration_source_valid": bool(
            (environment or {}).get("source_valid", True)
        ),
    }
    infrastructure_ready = all(infrastructure_checks.values())
    ready = infrastructure_ready and all(configuration_checks.values())
    blockers = [
        name
        for name, passed in {**infrastructure_checks, **configuration_checks}.items()
        if not passed
    ]
    runtime_configuration = memory_runtime_configuration(
        env_file=(environment or {}).get("env_file")
    )
    dependency_reasons = {
        "postgres": postgres.get("reason_code", "ready"),
        "embedding": ollama.get("reason_code", "ready"),
        "queue": queue.get("reason_code", "ready"),
    }
    return {
        "status": "ready" if ready else "blocked",
        "infrastructure_ready": infrastructure_ready,
        "ready_for_vector_rollout": ready,
        "blockers": blockers,
        "configuration": {
            "vector_enabled": config.vector_enabled,
            "fusion_mode": config.fusion_mode,
            "embedding_model": config.embedding_model,
            "embedding_dimension": config.embedding_dimension,
            "source": environment or {"status": "not_reported", "source_valid": True},
            "fingerprint": runtime_configuration["configuration_fingerprint"],
        },
        "runtime": runtime_configuration["runtime"],
        "dependency_reasons": dependency_reasons,
        "checks": {
            "infrastructure": infrastructure_checks,
            "configuration": configuration_checks,
        },
        "postgres": postgres,
        "ollama": ollama,
        "queue": queue,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", default=str(PROJECT_DIR / ".env"), help="Environment file"
    )
    parser.add_argument(
        "--probe-embedding",
        action="store_true",
        help="Generate one test embedding and verify its dimension",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit non-zero unless configuration and infrastructure are ready",
    )
    parser.add_argument(
        "--require-infrastructure",
        action="store_true",
        help="Exit non-zero unless PostgreSQL, pgvector, Ollama and the queue are ready",
    )
    parser.add_argument(
        "--require-config-source",
        action="store_true",
        help="Exit non-zero unless an env file was found or memory settings were supplied by the process environment",
    )
    args = parser.parse_args()
    environment = load_environment(args.env_file)
    report = run_preflight(
        resolve_config(),
        probe_embedding=args.probe_embedding,
        environment=environment,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if args.require_ready and not report["ready_for_vector_rollout"]:
        return 2
    if args.require_infrastructure and not report["infrastructure_ready"]:
        return 3
    if args.require_config_source and not environment.get("source_valid"):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
