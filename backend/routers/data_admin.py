from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from unified_data_manager import unified_data_manager


router = APIRouter(prefix="/api/admin/data", tags=["data-admin"])


class PageUpdate(BaseModel):
    title: Optional[str] = None
    nav_label: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class BackupRequest(BaseModel):
    source_id: str = "unified-sqlite"


class OptimizeRequest(BaseModel):
    source_id: str = "unified-sqlite"
    vacuum: bool = False


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    agent_type: Optional[str] = None
    role: Optional[str] = None
    team: Optional[str] = None
    category: Optional[str] = None
    emoji: Optional[str] = None
    enabled: Optional[bool] = None
    visible: Optional[bool] = None
    visible_in_org: Optional[bool] = None
    is_clone: Optional[bool] = None
    clone_of_agent_id: Optional[str] = None
    responsibilities: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class AgentOrgSave(BaseModel):
    root: dict[str, Any]
    nodes: list[dict[str, Any]]


@router.get("/overview")
def get_overview():
    return unified_data_manager.overview()


@router.post("/sync")
def sync_data():
    result = unified_data_manager.sync_all()
    unified_data_manager.record_audit("sync_data", "admin", "data", actor="admin-api", after_state=result.get("totals", {}))
    return result


@router.post("/discover")
def discover_storage_assets():
    result = unified_data_manager.discover_storage_assets()
    unified_data_manager.record_audit("discover_storage_assets", "admin", "data_sources", actor="admin-api", after_state={"total": result.get("total")})
    return result


@router.get("/health")
def get_storage_health():
    return unified_data_manager.health_check()


@router.get("/sources")
def list_sources():
    sources = unified_data_manager.list_sources()
    return {"sources": sources, "total": len(sources)}


@router.get("/sources/{source_id}")
def get_source(source_id: str):
    source = unified_data_manager.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("/backups")
def create_backup(payload: BackupRequest):
    result = unified_data_manager.create_backup(payload.source_id)
    if result.get("status") == "missing":
        raise HTTPException(status_code=404, detail=result.get("error", "Source not found"))
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Backup failed"))
    unified_data_manager.record_audit("create_backup", "data_source", payload.source_id, actor="admin-api", after_state=result)
    return result


@router.get("/backups")
def list_backups(limit: int = 50):
    backups = unified_data_manager.list_backups(limit)
    return {"backups": backups, "total": len(backups)}


@router.post("/optimize")
def optimize_storage(payload: OptimizeRequest):
    result = unified_data_manager.optimize_sqlite(payload.source_id, payload.vacuum)
    if result.get("status") == "missing":
        raise HTTPException(status_code=404, detail=result.get("error", "Source not found"))
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Optimize failed"))
    unified_data_manager.record_audit("optimize_sqlite", "data_source", payload.source_id, actor="admin-api", after_state=result)
    return result


@router.get("/pages")
def list_pages():
    pages = unified_data_manager.list_pages()
    return {"pages": pages, "total": len(pages)}


@router.put("/pages/{page_id}")
def update_page(page_id: str, payload: PageUpdate):
    before = unified_data_manager.get_page(page_id)
    page = unified_data_manager.update_page(page_id, payload.dict(exclude_unset=True))
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    unified_data_manager.record_audit("update_page", "frontend_page", page_id, actor="admin-api", before_state=before, after_state=page)
    return page


@router.get("/projects")
def list_projects():
    projects = unified_data_manager.list_projects()
    return {"projects": projects, "total": len(projects)}


@router.get("/agents")
def list_agents():
    agents = unified_data_manager.list_agents()
    return {"agents": agents, "total": len(agents)}


@router.put("/agents/{agent_id}")
def update_agent(agent_id: str, payload: AgentUpdate):
    agent = unified_data_manager.update_agent(agent_id, payload.dict(exclude_unset=True), actor="admin-api")
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/agents/import")
def import_agents():
    result = unified_data_manager.import_agents_from_json()
    return result


@router.get("/agent-org")
def get_agent_org(include_hidden: bool = False):
    return unified_data_manager.get_agent_organization_document(include_hidden=include_hidden)


@router.put("/agent-org")
def save_agent_org(payload: AgentOrgSave):
    return unified_data_manager.save_agent_org_nodes(payload.root, payload.nodes, actor="admin-api")


@router.post("/agent-org/import")
def import_agent_org():
    return unified_data_manager.import_agent_organization_from_json()


@router.get("/devices")
def list_devices():
    devices = unified_data_manager.list_devices()
    return {"devices": devices, "total": len(devices)}


@router.post("/import-operational")
def import_operational_data():
    result = unified_data_manager.ensure_operational_data_imported()
    unified_data_manager.record_audit("import_operational_data", "admin", "operational_data", actor="admin-api", after_state=result)
    return result


@router.get("/migrations")
def list_migrations():
    migrations = unified_data_manager.list_migrations()
    return {"migrations": migrations, "total": len(migrations)}


@router.get("/audit")
def list_audit_logs(limit: int = 100, target_type: Optional[str] = None):
    logs = unified_data_manager.list_audit_logs(limit=limit, target_type=target_type)
    return {"logs": logs, "total": len(logs)}


@router.get("/schema")
def get_schema():
    return {
        "database": unified_data_manager.db_path,
        "tables": unified_data_manager.schema_summary(),
    }
