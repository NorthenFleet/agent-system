"""Read-only cluster inventory projection backed by explicit collector writes."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from models.cluster_inventory import ClusterDiscovery, ClusterNode, ClusterTelemetry


SCHEMA_VERSION = "cluster-monitoring.v1"
DISCOVERY_KEY = "tailscale"
DEFAULT_FRESHNESS_SECONDS = 90
METRIC_KEYS = (
    "cpu_percent",
    "cpu_logical_count",
    "memory_total_bytes",
    "memory_available_bytes",
    "memory_percent",
    "disk_total_bytes",
    "disk_free_bytes",
    "os_version",
    "architecture",
    "hardware_model",
    "hostname",
    "memory_unused_bytes",
    "gpu_probe_state",
    "docker_state",
    "docker_version",
)
SAFE_ERROR_CODES = {
    "collection_failed",
    "collector_not_configured",
    "command_failed",
    "discovery_failed",
    "discovery_not_ready",
    "discovery_timeout",
    "discovery_unavailable",
    "local_identity_mismatch",
    "node_unreachable",
    "parse_failed",
    "probe_failed",
    "probe_timeout",
    "probe_unavailable",
    "ssh_failed",
    "ssh_timeout",
    "ssh_unavailable",
    "tailscale_failed",
    "unsupported_os",
}
GPU_PROBE_STATES = {"available", "unavailable", "error", "inventory_only"}
DOCKER_STATES = {"ready", "unknown", "unavailable", "error"}
MAX_GPUS = 16


class ClusterInventoryConflict(ValueError):
    """A stable node identity conflicts with an existing record."""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _error_code(value: Any) -> str | None:
    if value is None:
        return None
    first_token = str(value).strip().split(maxsplit=1)[0]
    sanitized = re.sub(r"[^a-z0-9_]", "_", first_token.lower())[:80]
    return sanitized if sanitized in SAFE_ERROR_CODES else "collection_failed"


def _safe_label(value: Any, fallback: str = "unknown") -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(value or ""))[:32]
    return sanitized or fallback


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item)[:500] for item in value if item is not None]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _finite_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def _percent(value: Any) -> float | int | None:
    number = _finite_number(value)
    return number if number is not None and 0 <= number <= 100 else None


def _nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _bounded_string(value: Any, limit: int = 255) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


class ClusterInventoryService:
    def __init__(self, db: Session, *, freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS):
        self.db = db
        self.freshness_seconds = max(1, int(freshness_seconds))

    def register_node(self, mapping: Mapping[str, Any]) -> ClusterNode:
        node_id = str(mapping.get("node_id") or "").strip()
        tailscale_id = str(mapping.get("tailscale_id") or "").strip()
        if not node_id:
            raise ValueError("node_id is required")
        if not tailscale_id:
            raise ValueError("tailscale_id is required")

        by_node = self.db.get(ClusterNode, node_id)
        by_tail = (
            self.db.query(ClusterNode)
            .filter(ClusterNode.tailscale_id == tailscale_id)
            .one_or_none()
        )
        if by_node is not None and by_node.tailscale_id != tailscale_id:
            raise ClusterInventoryConflict("node_id is already bound to another tailscale_id")
        if by_tail is not None and by_tail.node_id != node_id:
            raise ClusterInventoryConflict("tailscale_id is already bound to another node_id")

        node = by_node or by_tail
        if node is None:
            node = ClusterNode(node_id=node_id, tailscale_id=tailscale_id)
            self.db.add(node)

        node.hostname = str(mapping.get("hostname") or node.hostname or "")
        node.dns_name = str(mapping.get("dns_name") or node.dns_name or "")
        if "addresses" in mapping:
            node.addresses = _string_list(mapping.get("addresses"))
        node.os = str(mapping.get("os") or node.os or "unknown")
        node.role = str(mapping.get("role") or node.role or "unassigned")
        if "managed" in mapping:
            node.managed = bool(mapping.get("managed"))
        identity_status = str(mapping.get("identity_status") or node.identity_status or "unconfirmed")
        if identity_status not in {"confirmed", "unconfirmed"}:
            raise ValueError("identity_status must be confirmed or unconfirmed")
        node.identity_status = identity_status
        if "legacy_device_id" in mapping:
            legacy_id = mapping.get("legacy_device_id")
            node.legacy_device_id = str(legacy_id) if legacy_id is not None else None
        if "domain_refs" in mapping:
            refs = mapping.get("domain_refs")
            node.domain_refs = dict(refs) if isinstance(refs, Mapping) else {}
        if "maintenance" in mapping:
            node.maintenance = bool(mapping.get("maintenance"))
        self.db.flush()
        return node

    def record_discovery(self, status_json: Mapping[str, Any], observed_at: datetime) -> None:
        observed = _as_utc(observed_at)
        if observed is None:
            raise ValueError("observed_at is required")
        nodes = list(self._discovered_nodes(status_json))

        for existing in self.db.query(ClusterNode).all():
            # A node may be hidden by Tailscale grants or omitted from this
            # observer's peer map. Absence is therefore unknown, not offline.
            existing.network_state = "unknown"
            existing.network_expired = False
            existing.network_observed_at = observed

        for discovered in nodes:
            tailscale_id = str(
                discovered.get("tailscale_id")
                or discovered.get("ID")
                or discovered.get("id")
                or ""
            ).strip()
            if not tailscale_id:
                continue
            node = (
                self.db.query(ClusterNode)
                .filter(ClusterNode.tailscale_id == tailscale_id)
                .one_or_none()
            )
            if node is None:
                node = self.register_node(
                    {
                        "node_id": self._automatic_node_id(tailscale_id),
                        "tailscale_id": tailscale_id,
                        "hostname": discovered.get("hostname") or discovered.get("HostName") or "",
                        "dns_name": discovered.get("dns_name") or discovered.get("DNSName") or "",
                        "addresses": discovered.get("addresses") or discovered.get("TailscaleIPs") or [],
                        "os": discovered.get("os") or discovered.get("OS") or "unknown",
                        "role": "unassigned",
                        "managed": False,
                        "identity_status": "unconfirmed",
                    }
                )
            else:
                if discovered.get("hostname") or discovered.get("HostName"):
                    node.hostname = str(discovered.get("hostname") or discovered.get("HostName"))
                if discovered.get("dns_name") or discovered.get("DNSName"):
                    node.dns_name = str(discovered.get("dns_name") or discovered.get("DNSName"))
                addresses = discovered.get("addresses") or discovered.get("TailscaleIPs")
                if addresses is not None:
                    node.addresses = _string_list(addresses)
                if discovered.get("os") or discovered.get("OS"):
                    node.os = str(discovered.get("os") or discovered.get("OS"))

            expired = bool(discovered.get("expired", discovered.get("Expired", False)))
            online_value = discovered.get("online", discovered.get("Online"))
            if expired:
                state = "offline"
            elif online_value is True:
                state = "online"
            elif online_value is False:
                state = "offline"
            else:
                state = "unknown"
            node.network_state = state
            node.network_expired = expired
            node.network_observed_at = observed

        discovery = self.db.get(ClusterDiscovery, DISCOVERY_KEY)
        if discovery is None:
            discovery = ClusterDiscovery(singleton_key=DISCOVERY_KEY)
            self.db.add(discovery)
        discovery.observed_at = observed
        discovery.error_code = None
        discovery.error_at = None
        self.db.flush()

    def record_discovery_error(self, code: str) -> None:
        discovery = self.db.get(ClusterDiscovery, DISCOVERY_KEY)
        if discovery is None:
            discovery = ClusterDiscovery(singleton_key=DISCOVERY_KEY)
            self.db.add(discovery)
        discovery.error_code = _error_code(code)
        discovery.error_at = datetime.now(timezone.utc)
        self.db.flush()

    def record_telemetry(
        self,
        node_id: str,
        metrics: Mapping[str, Any],
        observed_at: datetime,
        *,
        source: str = "ssh",
        error: str | None = None,
        services: list[Mapping[str, Any]] | None = None,
    ) -> None:
        node = self.db.get(ClusterNode, node_id)
        if node is None:
            raise KeyError(f"unknown cluster node: {node_id}")
        observed = _as_utc(observed_at)
        if observed is None:
            raise ValueError("observed_at is required")
        telemetry = self.db.get(ClusterTelemetry, node_id)
        if telemetry is None:
            telemetry = ClusterTelemetry(node_id=node_id)
            self.db.add(telemetry)

        if error is not None:
            telemetry.error_code = _error_code(error)
            telemetry.error_at = observed
            if services is not None:
                telemetry.services = self._normalize_services(services, observed)
            self.db.flush()
            return

        telemetry.metrics = self._normalize_metrics(metrics)
        telemetry.services = self._normalize_services(services or [], observed)
        telemetry.observed_at = observed
        telemetry.source = _safe_label(source)
        telemetry.error_code = None
        telemetry.error_at = None
        self.db.flush()

    def snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        generated_at = _as_utc(now) or datetime.now(timezone.utc)
        discovery = self.db.get(ClusterDiscovery, DISCOVERY_KEY)
        discovery_projection = self._discovery_projection(discovery, generated_at)
        telemetry_by_node = {
            row.node_id: row for row in self.db.query(ClusterTelemetry).all()
        }
        nodes = [
            self._node_projection(
                node,
                telemetry_by_node.get(node.node_id),
                generated_at,
                discovery_projection["state"],
            )
            for node in self.db.query(ClusterNode).order_by(ClusterNode.node_id.asc()).all()
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at.isoformat(),
            "mode": "read_only",
            "discovery": discovery_projection,
            "nodes": nodes,
        }

    def _discovery_projection(
        self,
        discovery: ClusterDiscovery | None,
        now: datetime,
    ) -> dict[str, Any]:
        if discovery is None:
            return {"state": "missing", "observed_at": None, "error": None}
        if discovery.error_code:
            state = "error"
        elif discovery.observed_at is None:
            state = "missing"
        elif self._is_fresh(discovery.observed_at, now):
            state = "fresh"
        else:
            state = "stale"
        return {
            "state": state,
            "observed_at": _iso(discovery.observed_at),
            "error": discovery.error_code,
        }

    def _node_projection(
        self,
        node: ClusterNode,
        telemetry: ClusterTelemetry | None,
        now: datetime,
        discovery_state: str,
    ) -> dict[str, Any]:
        network_state = node.network_state or "unknown"
        if network_state == "online" and (
            discovery_state != "fresh"
            or node.network_observed_at is None
            or not self._is_fresh(node.network_observed_at, now)
        ):
            network_state = "unknown"
        return {
            "node_id": node.node_id,
            "tailscale_id": node.tailscale_id,
            "hostname": node.hostname,
            "dns_name": node.dns_name,
            "addresses": list(node.addresses or []),
            "os": node.os,
            "role": node.role,
            "managed": bool(node.managed),
            "identity_status": node.identity_status,
            "legacy_device_id": node.legacy_device_id,
            "domain_refs": dict(node.domain_refs or {}),
            "maintenance": bool(node.maintenance),
            "network": {
                "state": network_state,
                "observed_at": _iso(node.network_observed_at),
                "expired": bool(node.network_expired),
            },
            "telemetry": self._telemetry_projection(telemetry, now),
            "services": self._service_projection(telemetry, now),
            "scheduling": {"eligible": False, "reason": "phase_2_read_only"},
        }

    def _telemetry_projection(
        self,
        telemetry: ClusterTelemetry | None,
        now: datetime,
    ) -> dict[str, Any]:
        if telemetry is None:
            return {
                "state": "missing",
                "observed_at": None,
                "source": None,
                "error": None,
                "metrics": self._normalize_metrics({}),
            }
        success_at = _as_utc(telemetry.observed_at)
        error_at = _as_utc(telemetry.error_at)
        if telemetry.error_code and (success_at is None or (error_at and error_at >= success_at)):
            state = "error"
        elif success_at is None:
            state = "missing"
        elif self._is_fresh(success_at, now):
            state = "fresh"
        else:
            state = "stale"
        return {
            "state": state,
            "observed_at": _iso(telemetry.observed_at),
            "source": telemetry.source,
            "error": telemetry.error_code,
            "metrics": self._normalize_metrics(telemetry.metrics or {}),
        }

    def _is_fresh(self, observed_at: datetime, now: datetime) -> bool:
        age = (now - (_as_utc(observed_at) or now)).total_seconds()
        return 0 <= age <= self.freshness_seconds

    @staticmethod
    def _automatic_node_id(tailscale_id: str) -> str:
        digest = hashlib.sha256(tailscale_id.encode("utf-8")).hexdigest()[:16]
        return f"ts-auto-{digest}"

    @staticmethod
    def _discovered_nodes(status_json: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        normalized = status_json.get("nodes")
        if isinstance(normalized, list):
            return [item for item in normalized if isinstance(item, Mapping)]
        result: list[Mapping[str, Any]] = []
        self_node = status_json.get("Self")
        if isinstance(self_node, Mapping):
            result.append(self_node)
        peers = status_json.get("Peer")
        if isinstance(peers, Mapping):
            result.extend(item for item in peers.values() if isinstance(item, Mapping))
        elif isinstance(peers, list):
            result.extend(item for item in peers if isinstance(item, Mapping))
        return result

    @staticmethod
    def _normalize_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
        normalized = {key: None for key in METRIC_KEYS}
        for key in ("cpu_percent", "memory_percent"):
            normalized[key] = _percent(metrics.get(key))
        for key in (
            "cpu_logical_count",
            "memory_total_bytes",
            "memory_available_bytes",
            "memory_unused_bytes",
            "disk_total_bytes",
            "disk_free_bytes",
        ):
            normalized[key] = _nonnegative_integer(metrics.get(key))
        for key in (
            "os_version",
            "architecture",
            "hardware_model",
            "hostname",
            "docker_version",
        ):
            normalized[key] = _bounded_string(metrics.get(key))
        gpu_probe_state = _bounded_string(metrics.get("gpu_probe_state"), 32)
        normalized["gpu_probe_state"] = (
            gpu_probe_state if gpu_probe_state in GPU_PROBE_STATES else None
        )
        docker_state = _bounded_string(metrics.get("docker_state"), 32)
        normalized["docker_state"] = (
            docker_state if docker_state in DOCKER_STATES else None
        )

        for available_key, total_key in (
            ("memory_available_bytes", "memory_total_bytes"),
            ("memory_unused_bytes", "memory_total_bytes"),
            ("disk_free_bytes", "disk_total_bytes"),
        ):
            available = normalized[available_key]
            total = normalized[total_key]
            if available is not None and total is not None and available > total:
                normalized[available_key] = None
        gpus = metrics.get("gpus")
        normalized["gpus"] = []
        if isinstance(gpus, list):
            for gpu in gpus[:MAX_GPUS]:
                if not isinstance(gpu, Mapping):
                    continue
                total_bytes = _nonnegative_integer(gpu.get("memory_total_bytes"))
                used_bytes = _nonnegative_integer(gpu.get("memory_used_bytes"))
                if total_bytes is not None and used_bytes is not None and used_bytes > total_bytes:
                    used_bytes = None
                normalized["gpus"].append(
                    {
                        "name": _bounded_string(gpu.get("name"), 160),
                        "memory_total_bytes": total_bytes,
                        "memory_used_bytes": used_bytes,
                        "utilization_percent": _percent(gpu.get("utilization_percent")),
                    }
                )
        return normalized

    @staticmethod
    def _normalize_services(
        services: list[Mapping[str, Any]],
        fallback_observed_at: datetime,
    ) -> list[dict[str, Any]]:
        normalized = []
        for service in services:
            if not isinstance(service, Mapping):
                continue
            name = str(service.get("name") or "").strip()
            if not name:
                continue
            state = str(service.get("state") or "unknown")
            if state not in {"healthy", "unhealthy", "unknown"}:
                state = "unknown"
            raw_observed_at = service.get("observed_at")
            observed_at = (
                fallback_observed_at
                if raw_observed_at is None
                else _parse_datetime(raw_observed_at)
            )
            if observed_at is None:
                state = "unknown"
            item = {
                "name": name[:160],
                "state": state,
                "observed_at": _iso(observed_at),
            }
            if service.get("detail") is not None:
                item["detail"] = str(service.get("detail"))[:500]
            normalized.append(item)
        return normalized

    def _service_projection(
        self,
        telemetry: ClusterTelemetry | None,
        now: datetime,
    ) -> list[dict[str, Any]]:
        if telemetry is None:
            return []
        projected = []
        for service in telemetry.services or []:
            if not isinstance(service, Mapping):
                continue
            item = dict(service)
            observed_at = _parse_datetime(item.get("observed_at"))
            if observed_at is None or not self._is_fresh(observed_at, now):
                item["state"] = "unknown"
            item["observed_at"] = _iso(observed_at)
            projected.append(item)
        return projected
