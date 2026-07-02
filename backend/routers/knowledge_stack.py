"""Knowledge system stack API: local Obsidian index + LightRAG + KAG."""

from pydantic import BaseModel
from fastapi import APIRouter, Query

from knowledge_stack_manager import knowledge_stack_manager


router = APIRouter(prefix="/api/knowledge-stack", tags=["knowledge-stack"])


class KnowledgeStackQuery(BaseModel):
    query: str
    engine: str = "auto"
    mode: str = "mix"
    limit: int = 10


class LightRagBatchIndexRequest(BaseModel):
    source_path: str
    limit: int = 3
    max_chars_per_file: int = 12000


@router.get("/status")
def get_knowledge_stack_status():
    return knowledge_stack_manager.status()


@router.post("/query")
def query_knowledge_stack(payload: KnowledgeStackQuery):
    return knowledge_stack_manager.query(
        query=payload.query,
        engine=payload.engine,
        mode=payload.mode,
        limit=payload.limit,
    )


@router.get("/graph")
def get_knowledge_stack_graph(
    source: str = Query("local"),
    limit_edges: int = Query(260, ge=1, le=2000),
    type: str | None = Query(None),
):
    return knowledge_stack_manager.graph(source=source, limit_edges=limit_edges, node_type=type)


@router.get("/lightrag/sources")
def get_lightrag_sources():
    return knowledge_stack_manager.lightrag_sources()


@router.get("/lightrag/documents")
def get_lightrag_documents():
    return knowledge_stack_manager.lightrag_documents()


@router.post("/lightrag/index-batch")
def index_lightrag_batch(payload: LightRagBatchIndexRequest):
    return knowledge_stack_manager.index_lightrag_batch(
        source_path=payload.source_path,
        limit=payload.limit,
        max_chars_per_file=payload.max_chars_per_file,
    )


@router.post("/lightrag/scan")
def trigger_lightrag_scan():
    return knowledge_stack_manager.trigger_lightrag_scan()
