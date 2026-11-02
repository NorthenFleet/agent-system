"""Authenticated reviewed-knowledge APIs; old Obsidian routes remain unchanged."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, File, Form
from pydantic import Field
from sqlalchemy.exc import SQLAlchemyError
from fastapi.responses import Response
from urllib.parse import quote

from routers.auth_router import get_current_user, require_role
from models import knowledge_schema_v1 as tables
from services.knowledge.contracts import Contract, MaintenanceRequest
from services.knowledge.runtime import get_service, require_enabled, flag
from services.knowledge.service import KnowledgeError

router = APIRouter(prefix="/api/v3/knowledge", tags=["v3-knowledge"])


def actor(user):
    value = str(user.get("sub") or "").strip()
    if not value:
        raise HTTPException(401, "登录身份缺少用户标识")
    return value


def service():
    try:
        require_enabled()
        return get_service()
    except KnowledgeError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)}) from exc


def invoke(operation, *, write=False):
    try:
        require_enabled(write=write)
        return operation()
    except KnowledgeError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": str(exc), "retryable": exc.status == 503}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, {"code": "authority_unavailable", "message": "知识数据库或迁移尚未就绪", "retryable": True}) from exc


class SpaceCreate(Contract):
    name: str = Field(min_length=1, max_length=240)
    project_id: str = Field(default="", max_length=160)


class Ingest(Contract):
    space_id: str
    source_version_id: str
    concept_title: str = Field(default="", max_length=240)
    target_page_id: str = ""
    base_revision: int = Field(default=0, ge=0)


class Review(Contract):
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: str = Field(pattern=r"^(approve|reject)$")
    reason: str = Field(min_length=1, max_length=2000)


class Publish(Contract):
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class QueryBody(Contract):
    space_id: str
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=10, ge=1, le=20)


@router.get("/status")
def status(user=Depends(get_current_user)):
    from services.knowledge.context import mode
    actor(user)
    return {"enabled": flag("SECOND_BRAIN_ENABLED"), "write_enabled": flag("SECOND_BRAIN_WRITE_ENABLED") and user.get("role") == "admin",
            "phase": "SB4", "projection_enabled": flag("SECOND_BRAIN_PROJECTION_ENABLED"), "compiler": "extractive-v1", "auto_publish": False,
            "worker_enabled": flag("SECOND_BRAIN_WORKER_ENABLED"), "context_mode": mode(), "knowledge_execution_enabled": False}


@router.get("/spaces")
def spaces(user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: {"items": svc.list_spaces(actor(user))})


@router.get("/projects")
def projects(user=Depends(get_current_user), svc=Depends(service)):
    from project_manager import project_manager
    return invoke(lambda: {"items": [{"id": p["id"], "name": p.get("name", p["id"])}
        for p in project_manager.list_projects() if svc.project_check(actor(user), p["id"])]})


@router.post("/spaces", status_code=201)
def create_space(body: SpaceCreate, user=Depends(require_role("admin")), svc=Depends(service),
                 key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.create_space(actor(user), body.name, body.project_id, key), write=True)


@router.post("/sources", status_code=201)
async def upload_source(space_id: str = Form(...), file: UploadFile = File(...),
                        user=Depends(require_role("admin")), svc=Depends(service),
                        key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    data = await file.read(5 * 1024 * 1024 + 1)
    return invoke(lambda: svc.upload(actor(user), space_id, file.filename or "source.txt", data, key), write=True)


@router.get("/sources/{version_id}")
def source(version_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: svc.get_source(actor(user), version_id))


@router.post("/sources/{version_id}/retract")
def retract(version_id: str, user=Depends(require_role("admin")), svc=Depends(service),
            key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.retract_source(actor(user), version_id, key), write=True)


@router.get("/sources/{version_id}/download")
def download(version_id: str, user=Depends(get_current_user), svc=Depends(service)):
    data, name = invoke(lambda: svc.download_source(actor(user), version_id))
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.post("/ingestions", status_code=202)
def ingest(body: Ingest, user=Depends(require_role("admin")), svc=Depends(service),
           key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.enqueue(actor(user), body.space_id, body.source_version_id,
        body.model_dump(exclude={"space_id", "source_version_id"}), key), write=True)


@router.get("/spaces/{space_id}/items/{kind}")
def items(space_id: str, kind: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
          user=Depends(get_current_user), svc=Depends(service)):
    table = {"sources": tables.sources, "jobs": tables.jobs, "pages": tables.pages,
             "changes": tables.changes}.get(kind)
    if table is None:
        raise HTTPException(404, "未知列表")
    result = invoke(lambda: svc.list_objects(actor(user), space_id, table, limit, offset))
    # Lists never return candidate content; detail performs evidence authorization.
    for item in result["items"]:
        item.pop("payload", None)
        item.pop("lease_until", None)
        item.pop("fence", None)
    return result


@router.get("/change-sets/{change_id}")
def change(change_id: str, user=Depends(require_role("admin")), svc=Depends(service)):
    return invoke(lambda: svc.change(actor(user), change_id))


@router.get("/jobs/{job_id}")
def job(job_id: str, user=Depends(get_current_user), svc=Depends(service)):
    result = invoke(lambda: svc.get_job(actor(user), job_id))
    result.pop("lease_until", None)
    result.pop("fence", None)
    return result


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, user=Depends(require_role("admin")), svc=Depends(service),
           key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.cancel_job(actor(user), job_id, key), write=True)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: str, user=Depends(require_role("admin")), svc=Depends(service),
          key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.retry_job(actor(user), job_id, key), write=True)


@router.get("/operations")
def operations(space_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: svc.operations(actor(user), space_id))


@router.post("/change-sets/{change_id}/review")
def review(change_id: str, body: Review, user=Depends(require_role("admin")), svc=Depends(service),
           key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.review(actor(user), change_id, body.payload_hash, body.decision, body.reason, key), write=True)


@router.post("/change-sets/{change_id}/publish")
def publish(change_id: str, body: Publish, user=Depends(require_role("admin")), svc=Depends(service),
            key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.publish(actor(user), change_id, body.payload_hash, key), write=True)


@router.get("/pages/{page_id}")
def page(page_id: str, revision: int | None = Query(None, ge=1),
         user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: svc.get_page(actor(user), page_id, revision))


@router.post("/query")
def query(body: QueryBody, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: svc.query(actor(user), body.space_id, body.query, body.limit))


class ProjectionReplay(Contract):
    regenerate: bool = False


@router.post("/spaces/{space_id}/maintenance/candidates", status_code=201)
def maintenance_candidate(space_id: str, body: MaintenanceRequest, user=Depends(require_role("admin")),
                          svc=Depends(service), key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    return invoke(lambda: svc.maintenance_candidate(actor(user), space_id, body.model_dump(), key), write=True)


@router.get("/spaces/{space_id}/maintenance")
def maintenance_report(space_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: svc.maintenance_report(actor(user), space_id))


@router.get("/pages/{page_id}/history")
def history(page_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: svc.page_history(actor(user), page_id))


@router.get("/spaces/{space_id}/projection")
def projection_health(space_id: str, user=Depends(get_current_user), svc=Depends(service)):
    def read():
        # Authorize before disclosing deployment/health information.
        with svc.engine.connect() as conn:
            svc.space(conn, actor(user), space_id)
        if not flag("SECOND_BRAIN_PROJECTION_ENABLED"):
            return {"status": "disabled", "issues": [], "events": []}
        from services.knowledge.runtime import get_projection
        return get_projection().health(actor(user), space_id)
    return invoke(read)


@router.post("/spaces/{space_id}/projection/{event_id}/replay")
def projection_replay(space_id: str, event_id: str, body: ProjectionReplay, user=Depends(require_role("admin")),
                      svc=Depends(service), key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160)):
    def replay():
        with svc.engine.connect() as conn:
            svc.space(conn, actor(user), space_id)
        from services.knowledge.runtime import get_projection
        return get_projection().replay(actor(user), space_id, event_id, key, body.regenerate)
    return invoke(replay, write=True)


class ContextPreview(Contract):
    project_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=2, max_length=2000)
    total_chars: int = Field(default=12000, ge=1000, le=30000)
    baseline_chars: int = Field(default=0, ge=0, le=100000)


class CitationResolve(Contract):
    project_id: str = Field(min_length=1, max_length=160)
    page_id: str = Field(pattern=r'^kp-[a-f0-9]{32}$')
    revision: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=80)


@router.post('/spaces/{space_id}/context/preview')
def context_preview(space_id: str, body: ContextPreview, user=Depends(get_current_user), svc=Depends(service)):
    def preview():
        from services.knowledge.context import KnowledgeContextService, require_shadow
        require_shadow()
        return KnowledgeContextService(svc).build(actor(user), space_id, body.project_id, body.query,
            total_chars=body.total_chars, baseline_chars=body.baseline_chars, persist=False)
    return invoke(preview)


@router.post('/spaces/{space_id}/context/snapshots', status_code=201)
def context_capture(space_id: str, body: ContextPreview, user=Depends(require_role('admin')), svc=Depends(service),
                    key: str = Header(..., alias='Idempotency-Key', min_length=1, max_length=160)):
    def capture():
        from services.knowledge.context import KnowledgeContextService, require_shadow
        require_shadow()
        # Snapshot IDs are deterministic for request replay, but content is created
        # only once under a common space lock by the context service.
        return KnowledgeContextService(svc).capture(actor(user), space_id, body.model_dump(), key)
    return invoke(capture, write=True)


@router.get('/context/snapshots/{snapshot_id}')
def context_snapshot(snapshot_id: str, project_id: str = Query(..., min_length=1, max_length=160),
                     user=Depends(get_current_user), svc=Depends(service)):
    def read():
        from services.knowledge.context import KnowledgeContextService, require_shadow
        require_shadow()
        return KnowledgeContextService(svc).read(actor(user), snapshot_id, project_id)
    return invoke(read)


@router.post('/spaces/{space_id}/citations/resolve')
def resolve_citation(space_id: str, body: CitationResolve, user=Depends(get_current_user), svc=Depends(service)):
    def resolve():
        from services.knowledge.context import KnowledgeContextService
        return KnowledgeContextService(svc).resolve(actor(user), space_id, body.project_id,
            body.page_id, body.revision, body.block_id)
    return invoke(resolve)


from services.knowledge.bridges import KnowledgeBridges, ExternalReference, MemoryProposal
from services.knowledge.operations import KnowledgeOperations


@router.post('/spaces/{space_id}/external-imports', status_code=201)
def import_registered(space_id: str, body: ExternalReference, user=Depends(require_role('admin')),
                      svc=Depends(service), key: str = Header(..., alias='Idempotency-Key', min_length=1, max_length=160)):
    return invoke(lambda: KnowledgeBridges(svc).import_reference(actor(user), space_id, body.model_dump(), key), write=True)


@router.post('/spaces/{space_id}/memory-proposals', status_code=201)
def memory_proposal(space_id: str, body: MemoryProposal, user=Depends(require_role('admin')),
                    svc=Depends(service), key: str = Header(..., alias='Idempotency-Key', min_length=1, max_length=160)):
    return invoke(lambda: KnowledgeBridges(svc).propose_memory(actor(user), space_id, body.model_dump(), key), write=True)


@router.get('/memory-proposals/{proposal_id}')
def read_memory_proposal(proposal_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: KnowledgeBridges(svc).read_proposal(actor(user), proposal_id))


@router.get('/spaces/{space_id}/bridges')
def bridges(space_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: KnowledgeBridges(svc).overview(actor(user), space_id))


class MaintenanceRun(Contract):
    cadence: str = Field(default='weekly', pattern=r'^(daily|weekly|monthly)$')


@router.post('/spaces/{space_id}/maintenance-runs', status_code=201)
def maintain(space_id: str, body: MaintenanceRun, user=Depends(require_role('admin')), svc=Depends(service)):
    # Server-computed period is the idempotency key; clients cannot spoof historical dates.
    return invoke(lambda: KnowledgeOperations(svc).maintain(actor(user), space_id, body.cadence), write=True)


@router.get('/spaces/{space_id}/maintenance-runs')
def maintenance_runs(space_id: str, user=Depends(get_current_user), svc=Depends(service)):
    return invoke(lambda: KnowledgeOperations(svc).history(actor(user), space_id))
