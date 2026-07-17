"""Product registry, runtime health and project-product binding API."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from project_manager import project_manager
from services.auth_service import get_current_user, require_role
from services.mission_planning_adapter import MissionPlanningError, mission_planning_adapter
from services.product_service import product_registry_service
from services.project_composition import remove_product_binding, upsert_product_binding


router = APIRouter(prefix="/api/v2/products", tags=["products"])


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
    return {
        **product,
        "runtime": await _runtime_health(product),
        "project_references": references,
        "usage_count": len(references),
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
