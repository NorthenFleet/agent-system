"""Knowledge graph API backed by the Obsidian graph index."""

from fastapi import APIRouter, HTTPException, Query

from knowledge_manager import knowledge_manager


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/stats")
def get_knowledge_stats():
    return knowledge_manager.get_stats()


@router.get("/graph")
def get_knowledge_graph(
    limit_edges: int = Query(500, ge=1, le=5000),
    node_type: str | None = None,
    mode: str = Query("concept_backbone", description="Graph mode: concept_backbone or full"),
):
    return knowledge_manager.graph(limit_edges=limit_edges, node_type=node_type, mode=mode)


@router.get("/nodes")
def list_knowledge_nodes(
    type: str | None = Query(None, description="Filter by knowledge node type"),
    q: str | None = Query(None, description="Substring search"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return knowledge_manager.list_nodes(node_type=type, q=q, limit=limit, offset=offset)


@router.get("/tree")
def get_knowledge_tree(
    max_depth: int = Query(4, ge=1, le=8),
    include_files: bool = Query(True),
    max_entries: int = Query(1200, ge=100, le=5000),
):
    return knowledge_manager.directory_tree(
        max_depth=max_depth,
        include_files=include_files,
        max_entries=max_entries,
    )


@router.get("/search")
def search_knowledge(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    type: str | None = Query(None, description="Filter by knowledge node type"),
):
    return knowledge_manager.search(q=q, limit=limit, node_type=type)


@router.get("/nodes/{node_id:path}/content")
def get_knowledge_node_content(
    node_id: str,
    max_chars: int = Query(6000, ge=200, le=20000),
):
    return knowledge_manager.node_content(node_id=node_id, max_chars=max_chars)


@router.get("/nodes/{node_id:path}")
def get_knowledge_node(node_id: str):
    node = knowledge_manager.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found")
    return node


@router.get("/neighbors/{node_id:path}")
def get_knowledge_neighbors(node_id: str, limit: int = Query(50, ge=1, le=500)):
    return knowledge_manager.neighbors(node_id=node_id, limit=limit)
