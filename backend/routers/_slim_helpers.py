"""
Slim main.py helpers — security, frontend, lifecycle
Extracted to keep main.py under 100 lines.

@task task-005-P3-5
@author 🟥 拉斐尔
"""
import os
import ipaddress
from fastapi import Request, HTTPException, Response
from fastapi.responses import JSONResponse

# ─── Security ───
RFC1918_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))

LEGACY_ADMIN_WRITE_PREFIXES = (
    "/api/tasks", "/api/scheduled-tasks", "/api/customers",
    "/api/development-plans", "/api/bar", "/api/community",
    "/api/chat", "/api/forum", "/api/news", "/api/plans",
    "/api/auto", "/api/loop", "/api/v3", "/api/admin",
)


def _is_legacy_admin_write(request: Request) -> bool:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    path = request.url.path
    return any(path == p or path.startswith(p + "/") for p in LEGACY_ADMIN_WRITE_PREFIXES)


def _configured_admin_api_keys() -> set:
    raw = os.getenv("ADMIN_API_KEYS") or os.getenv("API_KEYS") or ""
    return {k.strip() for k in raw.split(",") if k.strip()}


def _extract_api_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key", "").strip()
    if api_key:
        return api_key
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


def _is_local_request(request: Request) -> bool:
    return (request.client.host if request.client else "") in {"127.0.0.1", "::1", "localhost", "testclient"}


def require_admin_request(request: Request) -> None:
    if _is_local_request(request):
        return
    api_keys = _configured_admin_api_keys()
    if not api_keys:
        raise HTTPException(403, "Admin API key not configured")
    if _extract_api_key(request) not in api_keys:
        raise HTTPException(401, "Admin API key required")


def validate_discovery_range(ip_range: str) -> str:
    try:
        network = ipaddress.ip_network((ip_range or "").strip(), strict=False)
    except ValueError:
        raise HTTPException(400, "Invalid ip_range")
    if network.version != 4:
        raise HTTPException(400, "Only IPv4 discovery is supported")
    if not any(network.subnet_of(base) for base in RFC1918_NETWORKS):
        raise HTTPException(400, "Discovery limited to RFC1918 private networks")
    if network.prefixlen < 24:
        raise HTTPException(400, "Discovery limited to /24 or smaller")
    return str(network)
