"""Bridge project outputs into the durable product delivery ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.product_service import ProductRegistryService, product_registry_service


PRIMARY_PRODUCT_ROLES = {"primary", "produces", "owns", "upgrade", "maintenance"}


def product_id_for_project(project: dict[str, Any], requested_product_id: str = "") -> str | None:
    """Return the explicit or primary product binding for a project.

    A project may consume several platforms but should publish a document or
    software artifact only to its declared primary product.
    """
    bindings = [row for row in project.get("product_bindings", []) if isinstance(row, dict)]
    bound_ids = {str(row.get("product_id") or "") for row in bindings}
    if requested_product_id:
        return requested_product_id if requested_product_id in bound_ids else None
    primary = next(
        (row.get("product_id") for row in bindings if str(row.get("role") or "") in PRIMARY_PRODUCT_ROLES),
        None,
    )
    if primary:
        return str(primary)
    return str(bindings[0].get("product_id")) if len(bindings) == 1 else None


def register_document_export(
    project: dict[str, Any],
    output_path: Path,
    output_format: str,
    *,
    produced_by_agent_id: str = "",
    product_id: str = "",
    registry: ProductRegistryService = product_registry_service,
) -> dict[str, Any] | None:
    """Record an exported document as a draft product deliverable when bound."""
    target_product_id = product_id_for_project(project, product_id)
    if not target_product_id or not registry.get_product(target_product_id):
        return None
    stat = output_path.stat()
    return registry.submit_deliverable(
        target_product_id,
        {
            "project_id": str(project.get("id") or ""),
            "kind": "document",
            "title": output_path.name,
            "uri": output_path.resolve().as_uri(),
            "version": str((project.get("document_spec") or {}).get("edition") or ""),
            "summary": f"{output_format.upper()} 导出：{project.get('name') or output_path.stem}",
            "metadata": {
                "format": output_format.lower(),
                "filename": output_path.name,
                "size_bytes": stat.st_size,
                "source": "writing-workspace-export",
            },
            "produced_by_agent_id": produced_by_agent_id or str(project.get("owner_agent") or ""),
        },
        idempotency_key=f"document-export:{project.get('id')}:{stat.st_mtime_ns}:{stat.st_size}",
    )
