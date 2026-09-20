"""Internal, read-only client for graph-memory context retrieval.

This client is deliberately separate from ``GraphMemoryProxy``: the proxy
serves an administrator-facing dashboard, while this client retrieves a
strictly scoped, citation-ready subset for an agent context pack.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GATEWAY_URL = "http://127.0.0.1:18789"
DEFAULT_SECRET_PATH = "~/.openclaw/graph-memory-bridge.key"
DEFAULT_RETRIEVAL_PATH = "/graph-memory/v1/retrieve-context"
DEFAULT_PROJECTION_PATH = "/graph-memory/v1/upsert-projection"
DEFAULT_INVENTORY_PATH = "/graph-memory/v1/projection-inventory"
MAX_RESPONSE_BYTES = 1_000_000
MAX_ITEM_CONTENT_CHARS = 4_000
ALLOWED_AUTHORITIES = {"approved_memory", "approved_projection"}
ALLOWED_VISIBILITIES = {"private", "profile", "project", "agent"}
RELATION_WEIGHTS = {
    "CONSTRAINS": 1.0,
    "APPLIES_TO": 0.95,
    "SUPPORTED_BY": 0.90,
    "DERIVED_FROM": 0.85,
    "SUPERSEDES": 0.80,
    "RELATED_TO": 0.65,
}


class GraphMemoryClientError(RuntimeError):
    """A safe-to-display operational error from graph-memory retrieval."""


def _canonical_request(
    method: str,
    raw_path: str,
    timestamp: str,
    nonce: str,
    request_id: str,
    actor_id: str,
    actor_role: str,
    permissions: str,
    body_sha256: str,
) -> str:
    return "\n".join(
        (
            method.upper(), raw_path, timestamp, nonce, request_id,
            actor_id, actor_role, permissions, body_sha256,
        )
    )


class GraphMemoryClient:
    """Retrieve approved graph-memory projections for a single user scope."""

    def __init__(
        self,
        gateway_url: str | None = None,
        secret_path: str | None = None,
        retrieval_path: str | None = None,
        projection_path: str | None = None,
        inventory_path: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ):
        self.gateway_url = (
            gateway_url
            or os.getenv("GRAPH_MEMORY_CONTEXT_GATEWAY_URL")
            or os.getenv("GRAPH_MEMORY_GATEWAY_URL")
            or DEFAULT_GATEWAY_URL
        ).rstrip("/")
        self.secret_path = Path(
            secret_path
            or os.getenv("GRAPH_MEMORY_CONTEXT_SECRET_PATH")
            or os.getenv("GRAPH_MEMORY_BRIDGE_SECRET_PATH")
            or DEFAULT_SECRET_PATH
        ).expanduser()
        self.retrieval_path = retrieval_path or os.getenv(
            "GRAPH_MEMORY_CONTEXT_RETRIEVAL_PATH", DEFAULT_RETRIEVAL_PATH
        )
        self.projection_path = projection_path or os.getenv(
            "GRAPH_MEMORY_PROJECTION_PATH", DEFAULT_PROJECTION_PATH
        )
        self.inventory_path = inventory_path or os.getenv(
            "GRAPH_MEMORY_INVENTORY_PATH", DEFAULT_INVENTORY_PATH
        )
        self.timeout = max(
            0.2,
            min(float(timeout or os.getenv("GRAPH_MEMORY_CONTEXT_TIMEOUT", "1.2")), 5.0),
        )
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("GRAPH_MEMORY_CONTEXT_ENABLED", "true").lower()
            not in {"0", "false", "no", "off"}
        )
        self.actor_id = os.getenv("GRAPH_MEMORY_CONTEXT_ACTOR_ID", "3021-context")[:160]
        self.actor_role = os.getenv("GRAPH_MEMORY_CONTEXT_ACTOR_ROLE", "service")[:80]

    def health(self) -> dict[str, Any]:
        """Return local configuration state without probing the remote service."""
        return {
            "status": "disabled" if not self.enabled else "configured",
            "engine": "graph-memory",
            "enabled": self.enabled,
            "gateway_configured": bool(self.gateway_url),
            "credential_available": self._credential_available(),
            "retrieval_path": self.retrieval_path,
            "projection_path": self.projection_path,
            "inventory_path": self.inventory_path,
        }

    def retrieve_context(
        self,
        *,
        user_id: str,
        query: str,
        project_id: str = "",
        agent_id: str = "",
        mission_id: str = "",
        limit: int = 8,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "items": [],
                "health": {
                    "status": "disabled",
                    "engine": "graph-memory",
                    "results": 0,
                },
            }
        clean_user_id = str(user_id or "").strip()
        clean_query = str(query or "").strip()
        if not clean_user_id or not clean_query:
            raise GraphMemoryClientError("graph-memory retrieval requires user_id and query")

        payload = {
            "user_id": clean_user_id,
            "project_id": str(project_id or "").strip(),
            "agent_id": str(agent_id or "").strip(),
            "mission_id": str(mission_id or "").strip(),
            "query": clean_query[:20_000],
            "limit": max(1, min(int(limit), 20)),
            "include_neighbors": True,
            "max_hops": 1,
            "relation_types": list(RELATION_WEIGHTS),
            "allowed_scopes": ["profile", "project", "agent"],
            "include_unreviewed": False,
        }
        response = self._post(
            self.retrieval_path,
            payload,
            permission="memory.retrieve.context",
        )
        items = self._normalize_items(response.get("items"), payload)
        return {
            "items": items,
            "health": {
                "status": "ready",
                "engine": "graph-memory",
                "mode": str(response.get("retrieval_mode") or "hybrid")[:80],
                "results": len(items),
                "returned": len(response.get("items") or []),
                "filtered": max(0, len(response.get("items") or []) - len(items)),
            },
        }

    def upsert_projection(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Idempotently project one approved canonical memory into the graph."""
        if not self.enabled:
            raise GraphMemoryClientError("graph-memory projection is disabled")
        if not isinstance(payload, dict):
            raise GraphMemoryClientError("graph-memory projection payload is invalid")
        required = {
            "event_id", "event_type", "aggregate_type", "aggregate_id",
            "source_ref", "user_id", "title", "content", "status",
        }
        if any(not str(payload.get(key) or "").strip() for key in required):
            raise GraphMemoryClientError("graph-memory projection payload is incomplete")
        if str(payload.get("event_type")) not in {
            "memory.published", "memory.superseded", "memory.archived",
        }:
            raise GraphMemoryClientError("graph-memory projection event type is invalid")
        response = self._post(
            self.projection_path,
            payload,
            permission="memory.write.projection",
        )
        status = str(response.get("status") or "").lower()
        if status not in {"accepted", "upserted", "already_applied"}:
            raise GraphMemoryClientError("graph-memory projection was not accepted")
        return {
            "status": status,
            "projection_id": str(response.get("projection_id") or "")[:200],
        }

    def projection_inventory(
        self,
        *,
        user_id: str = "",
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Return metadata-only projection inventory for reconciliation."""
        if not self.enabled:
            raise GraphMemoryClientError("graph-memory projection is disabled")
        response = self._post(
            self.inventory_path,
            {"user_id": str(user_id or "").strip(), "limit": max(1, min(int(limit), 5000))},
            permission="memory.read.projection",
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise GraphMemoryClientError("graph-memory inventory is invalid")
        return [dict(item) for item in items if isinstance(item, dict)]

    def _credential_available(self) -> bool:
        try:
            mode = stat.S_IMODE(self.secret_path.stat().st_mode)
            return not bool(mode & 0o077) and self.secret_path.stat().st_size >= 32
        except OSError:
            return False

    def _secret(self) -> bytes:
        try:
            mode = stat.S_IMODE(self.secret_path.stat().st_mode)
            if mode & 0o077:
                raise GraphMemoryClientError("graph-memory credential permissions are unsafe")
            secret = self.secret_path.read_bytes()
        except GraphMemoryClientError:
            raise
        except OSError as exc:
            raise GraphMemoryClientError("graph-memory credential is unavailable") from exc
        if len(secret) < 32:
            raise GraphMemoryClientError("graph-memory credential is unavailable")
        return secret

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        permission: str,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        body_sha256 = hashlib.sha256(body).hexdigest()
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        request_id = uuid.uuid4().hex
        permissions = permission
        signature = hmac.new(
            self._secret(),
            _canonical_request(
                "POST", path, timestamp, nonce, request_id,
                self.actor_id, self.actor_role, permissions, body_sha256,
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = urllib.request.Request(
            f"{self.gateway_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-GM-Timestamp": timestamp,
                "X-GM-Nonce": nonce,
                "X-GM-Request-Id": request_id,
                "X-GM-Actor-Id": self.actor_id,
                "X-GM-Actor-Role": self.actor_role,
                "X-GM-Permissions": permissions,
                "X-GM-Body-SHA256": body_sha256,
                "X-GM-Signature": signature,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310 - configured internal gateway
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise GraphMemoryClientError(f"graph-memory request failed ({exc.code})") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GraphMemoryClientError("graph-memory service is unavailable") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GraphMemoryClientError("graph-memory response exceeds the safety limit")
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GraphMemoryClientError("graph-memory returned invalid data") from exc
        if not isinstance(parsed, dict):
            raise GraphMemoryClientError("graph-memory returned invalid data")
        if not isinstance(parsed.get("items", []), list):
            raise GraphMemoryClientError("graph-memory returned invalid items")
        return parsed

    @staticmethod
    def _normalize_items(raw_items: Any, scope: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []
        normalized: list[dict[str, Any]] = []
        for raw in raw_items[:40]:
            if not isinstance(raw, dict):
                continue
            authority = str(raw.get("authority") or "").strip().lower()
            visibility = str(raw.get("visibility") or "").strip().lower()
            source_ref = str(raw.get("source_ref") or "").strip()[:500]
            content = str(raw.get("content") or "").strip()[:MAX_ITEM_CONTENT_CHARS]
            owner_user_id = str(raw.get("owner_user_id") or "").strip()
            item_project_id = str(raw.get("project_id") or "").strip()
            valid_until = str(raw.get("valid_until") or "").strip()
            if (
                authority not in ALLOWED_AUTHORITIES
                or visibility not in ALLOWED_VISIBILITIES
                or not source_ref
                or not content
                or owner_user_id != scope["user_id"]
                or (visibility == "project" and item_project_id != scope["project_id"])
                or GraphMemoryClient._expired(valid_until)
            ):
                continue
            try:
                semantic_score = float(raw.get("score") or 0)
                confidence = float(raw.get("confidence") or 0.8)
                freshness = float(raw.get("freshness_score") or 0.5)
                relation_relevance = float(raw.get("relation_relevance") or 0.5)
            except (TypeError, ValueError):
                continue
            relations = []
            for relation in raw.get("relations") or []:
                if not isinstance(relation, dict):
                    continue
                relation_type = str(relation.get("type") or "").strip().upper()[:80]
                label = str(relation.get("label") or relation.get("target_label") or "").strip()[:200]
                if relation_type in RELATION_WEIGHTS and label:
                    relations.append(
                        {
                            "type": relation_type,
                            "label": label,
                            "weight": RELATION_WEIGHTS[relation_type],
                        }
                    )
                if len(relations) >= 4:
                    break
            relation_relevance = max(
                max(0.0, min(relation_relevance, 1.0)),
                max((relation["weight"] for relation in relations), default=0.0) * 0.8,
            )
            normalized.append(
                {
                    "node_id": str(raw.get("node_id") or raw.get("id") or "")[:200],
                    "source_ref": source_ref,
                    "title": str(raw.get("title") or source_ref).strip()[:300],
                    "content": content,
                    "authority": authority,
                    "visibility": visibility,
                    "score": max(0.0, min(semantic_score, 1.0)),
                    "confidence": max(0.0, min(confidence, 1.0)),
                    "freshness_score": max(0.0, min(freshness, 1.0)),
                    "relation_relevance": max(0.0, min(relation_relevance, 1.0)),
                    "freshness_at": raw.get("freshness_at"),
                    "valid_until": valid_until or None,
                    "memory_key": str(raw.get("memory_key") or "").strip()[:200],
                    "version": GraphMemoryClient._version(raw.get("version")),
                    "supersedes_ref": str(raw.get("supersedes_ref") or "").strip()[:500] or None,
                    "evidence_refs": [
                        str(value).strip()[:300]
                        for value in (raw.get("evidence_refs") or [])
                        if str(value).strip()
                    ][:12],
                    "relations": relations,
                }
            )
        return normalized[: int(scope["limit"])]

    @staticmethod
    def _expired(value: str) -> bool:
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return True
            return parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    @staticmethod
    def _version(value: Any) -> int | None:
        try:
            parsed = int(value)
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError):
            return None


graph_memory_client = GraphMemoryClient()
