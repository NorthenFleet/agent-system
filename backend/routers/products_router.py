"""Product registry, runtime health and project-product binding API."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from project_manager import project_manager
from services.auth_service import get_current_user, require_role
from services.mission_planning_adapter import MissionPlanningError, mission_planning_adapter
from services.product_service import product_registry_service
from services.product_delivery_service import product_delivery_service, product_id_for_project
from services.project_composition import remove_product_binding, upsert_product_binding


router = APIRouter(prefix="/api/v2/products", tags=["products"])

# Existing registries predate the delivery ledger. This is idempotent and only
# persists a schema upgrade when an old registry is encountered.
product_registry_service.ensure_ledger_schema()


class ProductUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    category: str | None = None
    description: str | None = None
    version: str | None = None
    status: str | None = None
    owner: str | None = None
    repository: str | None = None
    deployment: dict[str, Any] | None = None
    capabilities: list[str] | None = None
    dependencies: list[dict[str, Any]] | None = None
    tags: list[str] | None = None


class ProductBindingUpdate(BaseModel):
    role: str = "uses"
    status: str = "bound"
    config: dict[str, Any] = Field(default_factory=dict)


class ProductCreate(ProductUpdate):
    id: str = Field(min_length=2, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)


class DeliverableCreate(BaseModel):
    project_id: str = ""
    task_id: str = ""
    development_point_id: str = ""
    kind: str = Field(default="document", pattern=r"^(source_code|service|document|model|dataset|scenario|report)$")
    title: str = Field(min_length=1, max_length=240)
    uri: str = ""
    content_hash: str = ""
    version: str = ""
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    produced_by_agent_id: str = ""


class DeliverableReview(BaseModel):
    accepted: bool
    reviewed_by_agent_id: str = Field(min_length=1, max_length=96)
    review_note: str = ""


class ReleaseCreate(BaseModel):
    version: str = Field(min_length=1, max_length=96)
    environment: str = Field(default="internal", max_length=96)
    status: str = Field(default="pending", pattern=r"^(pending|deploying|active|failed|rolled_back)$")
    deployment_url: str = ""
    source_deliverable_id: str = ""
    released_by_agent_id: str = ""
    release_note: str = ""


class CompletedTaskBackfillRequest(BaseModel):
    dry_run: bool = True


def _model_dict(model: BaseModel, *, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _project_references(product_id: str) -> list[dict[str, Any]]:
    references = []
    for project in project_manager.list_projects():
        binding = next(
            (
                row for row in project.get("product_bindings", [])
                if isinstance(row, dict) and row.get("product_id") == product_id
            ),
            None,
        )
        if binding:
            references.append({
                "project_id": project.get("id"),
                "project_name": project.get("name"),
                "role": binding.get("role"),
                "status": binding.get("status"),
            })
    return references


async def _runtime_health(product: dict[str, Any]) -> dict[str, Any]:
    product_id = product.get("id")
    if product_id == "openclaw-3021":
        return {"state": "online", "online": True, "summary": "3021统一服务运行中"}
    if product_id == "ai-planning-5130":
        try:
            health = await mission_planning_adapter.health()
            return {
                "state": "online" if health.get("online") else "offline",
                "online": bool(health.get("online")),
                "summary": f"监督器 {health.get('supervisor_state') or 'unknown'}",
                "details": health,
            }
        except MissionPlanningError as exc:
            return {"state": "offline", "online": False, "summary": str(exc), "error_code": exc.code}
    if product_id == "one-sim":
        try:
            snapshot = await mission_planning_adapter.simulation_snapshot()
            return {
                "state": "online",
                "online": True,
                "summary": f"帧 {snapshot.get('frame', 0)} · {snapshot.get('unit_count', 0)} 个实体",
                "details": snapshot,
            }
        except MissionPlanningError as exc:
            return {"state": "offline", "online": False, "summary": str(exc), "error_code": exc.code}
    return {
        "state": "managed",
        "online": None,
        "summary": "非在线服务产品",
    }


async def _enrich_product(product: dict[str, Any]) -> dict[str, Any]:
    references = _project_references(str(product.get("id") or ""))
    deliverables = product_registry_service.list_deliverables(str(product.get("id") or ""), limit=500)
    releases = product_registry_service.list_releases(str(product.get("id") or ""), limit=1)
    return {
        **product,
        "runtime": await _runtime_health(product),
        "project_references": references,
        "usage_count": len(references),
        "delivery_summary": {
            "total": len(deliverables),
            "accepted": sum(1 for row in deliverables if row.get("status") == "accepted"),
            "pending_review": sum(1 for row in deliverables if row.get("status") == "draft"),
            "latest": deliverables[0] if deliverables else None,
        },
        "current_release": releases[0] if releases else None,
    }


@router.get("")
async def get_products(_user: dict = Depends(get_current_user)):
    registry = product_registry_service.get_registry()
    products = await asyncio.gather(*[_enrich_product(row) for row in registry["products"]])
    dependencies = [
        {"from": row.get("id"), **dependency}
        for row in registry["products"]
        for dependency in row.get("dependencies", [])
        if isinstance(dependency, dict) and dependency.get("product_id")
    ]
    return {
        **{key: value for key, value in registry.items() if key != "products"},
        "products": products,
        "dependencies": dependencies,
        "summary": {
            "total": len(products),
            "online": sum(1 for row in products if (row.get("runtime") or {}).get("online") is True),
            "offline": sum(1 for row in products if (row.get("runtime") or {}).get("online") is False),
            "project_bindings": sum(int(row.get("usage_count") or 0) for row in products),
        },
    }


@router.post("", status_code=201)
def create_product(
    req: ProductCreate,
    _user: dict = Depends(require_role("admin")),
):
    if product_registry_service.get_product(req.id):
        raise HTTPException(status_code=409, detail="Product already exists")
    payload = _model_dict(req, exclude_unset=True)
    product_id = payload.pop("id")
    return product_registry_service.upsert_product(product_id, payload)


@router.put("/projects/{project_id}/bindings/{product_id}")
def bind_product_to_project(
    project_id: str,
    product_id: str,
    req: ProductBindingUpdate,
    _user: dict = Depends(require_role("admin")),
):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not product_registry_service.get_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    binding = upsert_product_binding(
        project,
        product_id,
        role=req.role,
        status=req.status,
        config=req.config,
    )
    updated = project_manager.update_project(project_id, {
        "enabled_modules": project["enabled_modules"],
        "product_bindings": project["product_bindings"],
    })
    return {"project": updated, "binding": binding}


@router.delete("/projects/{project_id}/bindings/{product_id}")
def unbind_product_from_project(
    project_id: str,
    product_id: str,
    _user: dict = Depends(require_role("admin")),
):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not remove_product_binding(project, product_id):
        raise HTTPException(status_code=404, detail="Product binding not found")
    updated = project_manager.update_project(project_id, {"product_bindings": project["product_bindings"]})
    return {"project": updated, "removed": product_id}


@router.post("/projects/{project_id}/backfill-completed-tasks")
def backfill_completed_tasks(
    project_id: str,
    req: CompletedTaskBackfillRequest,
    _user: dict = Depends(require_role("admin")),
):
    """Migrate only completed tasks of an explicitly primary-bound project."""
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    product_id = product_id_for_project(project)
    if not product_id:
        raise HTTPException(status_code=409, detail="Project has no primary product binding")
    completed = [
        task for task in project.get("tasks", [])
        if isinstance(task, dict) and str(task.get("status") or "") in {"done", "completed"}
    ]
    if req.dry_run:
        return {
            "project_id": project_id,
            "product_id": product_id,
            "dry_run": True,
            "completed_task_count": len(completed),
            "tasks": [{"id": task.get("id"), "title": task.get("title")} for task in completed],
        }
    deliverables = product_delivery_service.backfill_completed_tasks(project)
    return {
        "project_id": project_id,
        "product_id": product_id,
        "dry_run": False,
        "deliverables": deliverables,
        "count": len(deliverables),
    }


def _ensure_project_reference(project_id: str) -> None:
    if project_id and not project_manager.get_project(project_id):
        raise HTTPException(status_code=400, detail="Referenced project not found")


@router.get("/{product_id}/deliverables")
def list_deliverables(
    product_id: str,
    project_id: str | None = None,
    limit: int = 100,
    _user: dict = Depends(get_current_user),
):
    if not product_registry_service.get_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return {"deliverables": product_registry_service.list_deliverables(product_id, project_id=project_id, limit=limit)}


@router.post("/{product_id}/deliverables", status_code=201)
def submit_deliverable(
    product_id: str,
    req: DeliverableCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _user: dict = Depends(require_role("admin")),
):
    if not product_registry_service.get_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    _ensure_project_reference(req.project_id)
    return product_registry_service.submit_deliverable(
        product_id, _model_dict(req), idempotency_key=idempotency_key
    )


@router.post("/{product_id}/deliverables/{deliverable_id}/review")
def review_deliverable(
    product_id: str,
    deliverable_id: str,
    req: DeliverableReview,
    _user: dict = Depends(require_role("admin")),
):
    result = product_registry_service.review_deliverable(
        product_id,
        deliverable_id,
        accepted=req.accepted,
        reviewed_by_agent_id=req.reviewed_by_agent_id,
        review_note=req.review_note,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return result


@router.get("/{product_id}/releases")
def list_releases(product_id: str, limit: int = 100, _user: dict = Depends(get_current_user)):
    if not product_registry_service.get_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return {"releases": product_registry_service.list_releases(product_id, limit=limit)}


@router.post("/{product_id}/releases", status_code=201)
def create_release(
    product_id: str,
    req: ReleaseCreate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return product_registry_service.create_release(product_id, _model_dict(req))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{product_id}/timeline")
def product_timeline(product_id: str, limit: int = 100, _user: dict = Depends(get_current_user)):
    if not product_registry_service.get_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return {"events": product_registry_service.timeline(product_id, limit=limit)}


@router.get("/{product_id}")
async def get_product(product_id: str, _user: dict = Depends(get_current_user)):
    product = product_registry_service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return await _enrich_product(product)


@router.get("/{product_id}/health")
async def get_product_health(product_id: str, _user: dict = Depends(get_current_user)):
    product = product_registry_service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return await _runtime_health(product)


@router.put("/{product_id}")
def update_product(
    product_id: str,
    req: ProductUpdate,
    _user: dict = Depends(require_role("admin")),
):
    payload = _model_dict(req, exclude_unset=True)
    if not payload and not product_registry_service.get_product(product_id):
        raise HTTPException(status_code=400, detail="Product payload is required")
    return product_registry_service.upsert_product(product_id, payload)


@router.delete("/{product_id}")
def delete_product(product_id: str, _user: dict = Depends(require_role("admin"))):
    if product_id in {"openclaw-3021", "ai-planning-5130", "one-sim"}:
        raise HTTPException(status_code=400, detail="Core product cannot be deleted")
    if not product_registry_service.delete_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return {"deleted": True, "product_id": product_id}
