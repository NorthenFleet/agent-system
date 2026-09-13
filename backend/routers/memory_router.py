"""智能体记忆库 — 只读 API 路由（5 个端点）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from services.auth_service import require_role

from services.memory_service import (
    list_agents,
    get_file_tree,
    read_file,
    search_memory,
    get_stats,
)

router = APIRouter(
    prefix="/api/v2/memory",
    tags=["memory-library"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/agents")
def api_list_agents():
    """列出所有智能体及其记忆统计。"""
    return list_agents()


@router.get("/files")
def api_get_file_tree(
    agent_id: str = Query(..., min_length=1, description="智能体 ID"),
    path: str = Query("", description="子目录路径，默认根目录"),
):
    """列出指定智能体的记忆文件树。"""
    return get_file_tree(agent_id=agent_id, rel_path=path)


@router.get("/file")
def api_read_file(
    agent_id: str = Query(..., min_length=1, description="智能体 ID"),
    path: str = Query(..., min_length=1, description="文件相对路径（相对于 memory/）"),
):
    """读取指定智能体的指定记忆文件内容。"""
    return read_file(agent_id=agent_id, rel_path=path)


@router.get("/search")
def api_search_memory(
    q: str = Query(..., min_length=2, description="搜索关键词（≥2字符）"),
    agent_id: str | None = Query(None, description="限定单个智能体，默认全部"),
    limit: int = Query(50, ge=1, le=200, description="结果数量上限"),
):
    """跨智能体搜索记忆内容。"""
    return search_memory(q=q, agent_id=agent_id, limit=limit)


@router.get("/stats")
def api_get_stats():
    """获取记忆库统计信息。"""
    return get_stats()
