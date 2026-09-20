"""Sanitized runtime configuration diagnostics for the memory system.

This module deliberately exposes only non-secret configuration.  Database
passwords, graph-memory credentials, JWT secrets, and raw environment values
must never be included in the summary or its fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "memory-runtime-config.v1"
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_DIR / ".env"
DEFAULT_VECTOR_DATABASE_URL = "postgresql+psycopg2:///team_dashboard"
DEFAULT_EMBEDDING_HOST = "http://192.168.1.5:11434"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:v1.5"
DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_GRAPH_GATEWAY_URL = "http://127.0.0.1:18789"
DEFAULT_GRAPH_RETRIEVAL_PATH = "/graph-memory/v1/retrieve-context"
DEFAULT_GRAPH_PROJECTION_PATH = "/graph-memory/v1/upsert-projection"


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_postgres_dsn(value: str) -> str:
    clean = str(value or "").strip()
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if clean.startswith(prefix):
            return "postgresql://" + clean[len(prefix) :]
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[len("postgres://") :]
    return clean


def _safe_url_target(value: str, *, default_port: int) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(str(value or ""))
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "local-socket",
        "port": int(parsed.port or default_port),
        "path": parsed.path or "",
    }


def safe_database_target(value: str) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(_normalize_postgres_dsn(value))
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "local-socket",
        "port": int(parsed.port or 5432),
        "database": (parsed.path or "").lstrip("/") or "default",
        "user": parsed.username or "current-user",
    }


def runtime_kind() -> str:
    explicit = str(os.getenv("AGENT_SYSTEM_RUNTIME_KIND") or "").strip().lower()
    if explicit:
        return explicit[:40]
    if os.getenv("PYTEST_CURRENT_TEST"):
        return "test"
    if os.getenv("KUBERNETES_SERVICE_HOST") or Path("/.dockerenv").exists():
        return "container"
    return "direct"


def _environment_source(env_file: str | None = None) -> dict[str, Any]:
    declared = str(
        env_file
        or os.getenv("AGENT_SYSTEM_ENV_FILE")
        or DEFAULT_ENV_FILE
    ).strip()
    path = Path(declared).expanduser()
    source_kind = (
        "declared_env_file"
        if os.getenv("AGENT_SYSTEM_ENV_FILE") or env_file
        else "default_env_file"
    )
    if not path.exists():
        source_kind = "process_environment"
    return {
        "kind": source_kind,
        "env_file": str(path),
        "env_file_status": "present" if path.is_file() else "missing",
    }


def _effective_memory_config() -> dict[str, Any]:
    database_url = os.getenv("MEMORY_VECTOR_DATABASE_URL") or os.getenv(
        "DATABASE_URL", DEFAULT_VECTOR_DATABASE_URL
    )
    embedding_host = (
        os.getenv("MEMORY_EMBEDDING_HOST")
        or os.getenv("EMBEDDING_BINDING_HOST")
        or os.getenv("OLLAMA_HOST")
        or DEFAULT_EMBEDDING_HOST
    ).rstrip("/")
    graph_gateway = (
        os.getenv("GRAPH_MEMORY_CONTEXT_GATEWAY_URL")
        or os.getenv("GRAPH_MEMORY_GATEWAY_URL")
        or DEFAULT_GRAPH_GATEWAY_URL
    ).rstrip("/")
    return {
        "vector": {
            "enabled": _enabled(os.getenv("MEMORY_VECTOR_ENABLED")),
            "preflight_required": _enabled(
                os.getenv("MEMORY_VECTOR_PREFLIGHT_REQUIRED")
            ),
            "database": safe_database_target(database_url),
            "embedding": {
                "provider": "ollama",
                "target": _safe_url_target(embedding_host, default_port=11434),
                "model": str(
                    os.getenv("MEMORY_EMBEDDING_MODEL")
                    or os.getenv("LIGHTRAG_EMBEDDING_MODEL")
                    or os.getenv("EMBEDDING_MODEL")
                    or DEFAULT_EMBEDDING_MODEL
                ),
                "dimension": int(
                    os.getenv("MEMORY_EMBEDDING_DIM")
                    or os.getenv("EMBEDDING_DIM")
                    or DEFAULT_EMBEDDING_DIMENSION
                ),
            },
        },
        "retrieval": {
            "fusion_mode": str(
                os.getenv("MEMORY_HYBRID_FUSION_MODE") or "weighted_rrf"
            ).strip().lower(),
        },
        "graph": {
            "enabled": _enabled(
                os.getenv("GRAPH_MEMORY_CONTEXT_ENABLED"), default=True
            ),
            "gateway": _safe_url_target(graph_gateway, default_port=18789),
            "default_mode": str(
                os.getenv("GRAPH_MEMORY_DEFAULT_MODE") or "rerank"
            ).strip().lower(),
            "retrieval_path": str(
                os.getenv(
                    "GRAPH_MEMORY_CONTEXT_RETRIEVAL_PATH",
                    DEFAULT_GRAPH_RETRIEVAL_PATH,
                )
            ),
            "projection_path": str(
                os.getenv(
                    "GRAPH_MEMORY_PROJECTION_PATH",
                    DEFAULT_GRAPH_PROJECTION_PATH,
                )
            ),
        },
    }


def _fingerprint_payload(memory: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"schema_version": SCHEMA_VERSION, "memory": memory},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def memory_runtime_configuration(
    *,
    env_file: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Return a detailed but secret-free runtime configuration summary."""
    memory = _effective_memory_config()
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "kind": runtime_kind(),
            "platform": platform.system().lower(),
            "working_directory": str(Path.cwd()),
        },
        "configuration_source": _environment_source(env_file),
        "configuration_fingerprint": _fingerprint_payload(memory),
        "memory": memory,
    }


def public_memory_runtime_configuration() -> dict[str, Any]:
    """Return the reduced summary safe for the unauthenticated health route."""
    summary = memory_runtime_configuration()
    memory = summary["memory"]
    source = summary["configuration_source"]
    return {
        "schema_version": summary["schema_version"],
        "runtime_kind": summary["runtime"]["kind"],
        "configuration_source": source["kind"],
        "env_file_status": source["env_file_status"],
        "configuration_fingerprint": summary["configuration_fingerprint"],
        "vector_enabled": memory["vector"]["enabled"],
        "embedding_model": memory["vector"]["embedding"]["model"],
        "embedding_dimension": memory["vector"]["embedding"]["dimension"],
        "fusion_mode": memory["retrieval"]["fusion_mode"],
        "graph_enabled": memory["graph"]["enabled"],
        "graph_default_mode": memory["graph"]["default_mode"],
    }
