"""Fixed, read-only probes for the operator-enrolled cluster.

Discovery never authorizes a probe: only configured stable identities are polled.
The UI has no command endpoint, SSH is key-only with host-key checking, and probe
failures never fabricate hardware metrics or refresh the last successful sample.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BACKEND = Path(__file__).resolve().parents[1]
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def timestamp() -> datetime:
    return datetime.now(timezone.utc)


def validate_config(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("invalid_cluster_config")
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or len(nodes) > 100:
        raise ValueError("invalid_cluster_nodes")
    ids, tail_ids = set(), set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("invalid_node")
        node_id, tail_id = node.get("node_id"), node.get("tailscale_id")
        if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", node_id):
            raise ValueError("invalid_node_id")
        if not isinstance(tail_id, str) or not re.fullmatch(r"n[A-Za-z0-9]{1,254}", tail_id):
            raise ValueError("invalid_tailscale_id")
        if node_id in ids or tail_id in tail_ids:
            raise ValueError("duplicate_or_missing_identity")
        if type(node.get("managed", False)) is not bool or type(node.get("maintenance", False)) is not bool:
            raise ValueError("invalid_boolean")
        ids.add(node_id)
        tail_ids.add(tail_id)
        collector = node.get("collector", {})
        if not isinstance(collector, dict):
            raise ValueError("invalid_collector")
        if collector.get("transport", "disabled") not in {"local", "ssh", "disabled"}:
            raise ValueError("unsupported_transport")
        if collector.get("transport") == "ssh" and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", collector.get("user", "")):
            raise ValueError("invalid_ssh_user")
        if set(collector) - {"transport", "user"}:
            raise ValueError("unsupported_collector_option")
        services = node.get("services", [])
        if not isinstance(services, list) or len(services) > 3:
            raise ValueError("invalid_services")
        for service in services:
            _validate_service(service)
    return value


def discover(binary: str, *, runner=subprocess.run) -> dict:
    try:
        result = runner([binary, "status", "--json"], capture_output=True, text=True, timeout=10)
        if result.returncode or len(result.stdout) > 2_000_000:
            raise RuntimeError("discovery_failed")
        value = json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("discovery_timeout") from exc
    except (OSError, ValueError) as exc:
        raise RuntimeError("discovery_unavailable") from exc
    if not isinstance(value, dict) or value.get("BackendState") != "Running" or not (value.get("Self") or {}).get("ID") or not isinstance(value.get("Peer", {}), dict):
        raise RuntimeError("discovery_not_ready")
    return value


def collection_target(node: dict, status: dict) -> str | None:
    peers = [status.get("Self", {}), *status.get("Peer", {}).values()]
    for peer in peers:
        if peer.get("ID") != node["tailscale_id"] or not peer.get("Online") or peer.get("Expired"):
            continue
        for address in peer.get("TailscaleIPs", []):
            try:
                if ipaddress.ip_address(address) in TAILNET:
                    return address
            except ValueError:
                continue
    return None


def collect_node(node: dict, address: str, *, runner=subprocess.run) -> dict:
    validate_config({"nodes": [node]})
    if ipaddress.ip_address(address) not in TAILNET:
        raise ValueError("not_a_tailnet_address")
    transport = node.get("collector", {}).get("transport", "disabled")
    if transport == "disabled":
        return {"metrics": {}, "error": "collector_not_configured", "source": None}
    windows = str(node.get("os", "")).lower().startswith("win")
    source = (BACKEND / "scripts" / ("collect_host_metrics.ps1" if windows else "collect_host_metrics.py")).read_text()
    if transport == "local":
        import sys
        argv, stdin = [sys.executable, "-"], source
    else:
        command = "python3 -"
        stdin = source
        if windows:
            encoded = base64.b64encode(source.encode("utf-16-le")).decode("ascii")
            command, stdin = f"powershell.exe -NoProfile -NonInteractive -EncodedCommand {encoded}", None
        known_hosts = Path(os.getenv("CLUSTER_KNOWN_HOSTS", str(BACKEND / "data/cluster_known_hosts")))
        if not known_hosts.is_absolute():
            raise ValueError("known_hosts_must_be_absolute")
        argv = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "IdentitiesOnly=yes", "-o", f"UserKnownHostsFile={known_hosts}", "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=4", "-o", "ConnectionAttempts=1", "-o", "ClearAllForwardings=yes",
                "-o", "ForwardAgent=no", "-o", "ProxyCommand=none", "-o", "ProxyJump=none",
                f"{node['collector']['user']}@{address}", command]
    try:
        result = runner(argv, input=stdin, capture_output=True, text=True, timeout=18)
        if result.returncode:
            return {"metrics": {}, "source": transport, "error": "ssh_unavailable" if transport == "ssh" else "probe_failed"}
        if len(result.stdout) > 64_000:
            raise ValueError("output_limit")
        metrics = json.loads(result.stdout.lstrip("\ufeff"))
        if not isinstance(metrics, dict) or type(metrics.get("cpu_logical_count")) is not int or not 1 <= metrics["cpu_logical_count"] <= 65536:
            raise ValueError("invalid_metrics")
        return {"metrics": metrics, "source": transport, "error": None, "observed_at": timestamp()}
    except subprocess.TimeoutExpired:
        return {"metrics": {}, "source": transport, "error": "probe_timeout"}
    except (ValueError, OSError):
        return {"metrics": {}, "source": transport, "error": "probe_unavailable"}


def _validate_service(service: dict) -> None:
    if not isinstance(service, dict):
        raise ValueError("invalid_service")
    if type(service.get("port")) is not int or not 1 <= service["port"] <= 65535:
        raise ValueError("invalid_service_port")
    path = service.get("path", "")
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or any(c in path for c in ("\r", "\n", "#", "?", "\\")):
        raise ValueError("invalid_health_path")
    if not isinstance(service.get("name"), str) or not service["name"]:
        raise ValueError("invalid_service_name")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_service(address: str, service: dict) -> dict:
    if ipaddress.ip_address(address) not in TAILNET:
        raise ValueError("not_a_tailnet_address")
    _validate_service(service)
    result = {"name": service["name"], "state": "unknown", "observed_at": timestamp().isoformat()}
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        request = Request(f"http://{address}:{service['port']}{service['path']}", headers={"User-Agent": "cluster-readonly-monitor/1"})
        with opener.open(request, timeout=3) as response:
            # Only explicit JSON health semantics can claim health. An HTTP 200
            # login page or a redirect is not a healthy service receipt.
            payload = json.loads(response.read(16_384))
            if isinstance(payload, dict) and payload.get("status") in {"ok", "healthy"}:
                result.update(state="healthy", detail="health_ok")
            else:
                result.update(state="unknown", detail="unrecognized_health_contract")
    except HTTPError as exc:
        result.update(state="unknown" if exc.code in {401, 403} else "unhealthy", detail=f"http_{exc.code}")
    except (URLError, OSError, ValueError):
        result.update(state="unhealthy", detail="health_probe_failed")
    return result


def collect_cycle(config: dict, *, tailscale_binary: str, session_factory) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from services.cluster_inventory_service import ClusterInventoryService

    config = validate_config(config)
    try:
        status = discover(tailscale_binary)
    except RuntimeError as exc:
        with session_factory() as db:
            ClusterInventoryService(db).record_discovery_error(str(exc))
            db.commit()
        return {"discovery": "error", "collected": 0}
    with session_factory() as db:
        ClusterInventoryService(db).record_discovery(status, timestamp())
        db.commit()

    def probe(node):
        address = collection_target(node, status)
        if not address:
            return node, {"metrics": {}, "error": "node_unreachable", "source": None}, []
        if node.get("collector", {}).get("transport") == "local" and node["tailscale_id"] != status["Self"]["ID"]:
            return node, {"metrics": {}, "error": "local_identity_mismatch", "source": None}, []
        result = collect_node(node, address)
        services = [probe_service(address, item) for item in node.get("services", [])]
        return node, result, services

    collected = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(probe, node): node for node in config["nodes"] if node.get("managed") is True}
        for future in as_completed(futures):
            try:
                node, result, services = future.result()
            except Exception:
                node, result, services = futures[future], {"metrics": {}, "source": None, "error": "probe_failed"}, []
            with session_factory() as db:
                ClusterInventoryService(db).record_telemetry(
                    node["node_id"], result["metrics"], result.get("observed_at") or timestamp(),
                    source=result["source"], error=result["error"], services=services,
                )
                db.commit()
            collected += result["error"] is None
    return {"discovery": "fresh", "collected": collected}
