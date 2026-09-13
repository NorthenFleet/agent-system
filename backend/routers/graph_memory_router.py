"""Authenticated graph-memory views for the 3021 agent dashboard."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query

from services.auth_service import require_role
from services.graph_memory_proxy import graph_memory_proxy
from unified_data_manager import unified_data_manager


router = APIRouter(prefix="/api/v3/agents", tags=["agent-graph-memory"])
require_memory_admin = require_role("admin")


def _agent_path(agent_id: str, suffix: str) -> str:
    try:
        document = unified_data_manager.get_agent_organization_document()
        known = {
            str(node.get("agent_id"))
            for node in document.get("nodes", [])
            if node.get("visible", True)
            and node.get("node_type") in {"agent", "assistant"}
            and node.get("agent_id")
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="智能体组织数据不可用") from exc
    if agent_id not in known:
        raise HTTPException(status_code=404, detail="未找到记忆数据")
    return f"/graph-memory/v1/agents/{quote(agent_id, safe='')}/{suffix}"


@router.get("/{agent_id}/graph-memory/summary")
def get_graph_memory_summary(agent_id: str, user: dict = Depends(require_memory_admin)):
    return graph_memory_proxy.get_summary(
        _agent_path(agent_id, "summary"), user, ("memory.read.private",),
    )


@router.get("/{agent_id}/graph-memory/nodes")
def list_graph_memory_nodes(
    agent_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    type: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
    user: dict = Depends(require_memory_admin),
):
    return graph_memory_proxy.get(
        _agent_path(agent_id, "nodes"),
        user,
        ("memory.read.private",),
        {"limit": limit, "offset": offset, "type": type, "q": q},
    )


@router.get("/{agent_id}/graph-memory/nodes/{node_id}")
def get_graph_memory_node(agent_id: str, node_id: str, user: dict = Depends(require_memory_admin)):
    return graph_memory_proxy.get(
        _agent_path(agent_id, f"nodes/{quote(node_id, safe='')}"),
        user,
        ("memory.read.private", "memory.read.content"),
    )


@router.get("/{agent_id}/graph-memory/graph")
def get_graph_memory_graph(
    agent_id: str,
    limit: int = Query(60, ge=1, le=100),
    user: dict = Depends(require_memory_admin),
):
    return graph_memory_proxy.get(
        _agent_path(agent_id, "graph"), user, ("memory.read.private",), {"limit": limit},
    )


@router.get("/{agent_id}/graph-memory/health")
def get_graph_memory_health(agent_id: str, user: dict = Depends(require_memory_admin)):
    return graph_memory_proxy.get(
        _agent_path(agent_id, "health"), user, ("memory.read.private",),
    )


@router.get("/{agent_id}/graph-memory/shares")
def list_graph_memory_shares(
    agent_id: str,
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_memory_admin),
):
    return graph_memory_proxy.get(
        _agent_path(agent_id, "shares"),
        user,
        ("memory.read.private", "memory.read.shares"),
        {"limit": limit},
    )
