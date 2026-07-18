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


class ProductDeliveryService:
    """Converts real project output events into product-ledger entries."""

    def __init__(self, registry: ProductRegistryService = product_registry_service) -> None:
        self.registry = registry

    def register_document_export(
        self,
        project: dict[str, Any],
        output_path: Path,
        output_format: str,
        *,
        produced_by_agent_id: str = "",
        product_id: str = "",
    ) -> dict[str, Any] | None:
        """Record an exported document as a draft product deliverable when bound."""
        target_product_id = product_id_for_project(project, product_id)
        if not target_product_id or not self.registry.get_product(target_product_id):
            return None
        stat = output_path.stat()
        return self.registry.submit_deliverable(
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

    def register_task_completion(
        self,
        project: dict[str, Any],
        task: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Create one candidate deliverable from a completed project task.

        Task context can supply a precise artifact URI, version, or kind under
        ``context.delivery``. Without it, the result remains a truthful task
        completion record rather than claiming that a service was deployed.
        """
        target_product_id = product_id_for_project(project)
        if not target_product_id or not self.registry.get_product(target_product_id):
            return None
        context = task.get("context") if isinstance(task.get("context"), dict) else {}
        delivery = context.get("delivery") if isinstance(context.get("delivery"), dict) else {}
        project_type = str(project.get("project_type") or project.get("type") or "software")
        task_type = str(task.get("type") or "development").lower()
        kind = str(delivery.get("kind") or "")
        if not kind:
            if project_type == "document" or task_type in {"writing", "document"}:
                kind = "document"
            elif task_type in {"test", "testing", "qa", "verification"}:
                kind = "report"
            else:
                kind = "source_code"
        revision = str(delivery.get("revision") or context.get("delivery_revision") or "1")
        points = task.get("development_points") if isinstance(task.get("development_points"), list) else []
        return self.registry.submit_deliverable(
            target_product_id,
            {
                "project_id": str(project.get("id") or ""),
                "task_id": str(task.get("id") or ""),
                "kind": kind,
                "title": str(delivery.get("title") or f"{project.get('name') or '项目'}：{task.get('title') or '已完成任务'}"),
                "uri": str(delivery.get("uri") or context.get("artifact_uri") or ""),
                "content_hash": str(delivery.get("content_hash") or ""),
                "version": str(delivery.get("version") or ""),
                "summary": str(task.get("result_summary") or delivery.get("summary") or "任务已完成，等待验收"),
                "metadata": {
                    "source": "project-task-completion",
                    "task_type": task_type,
                    "task_status": task.get("status"),
                    "task_progress": task.get("progress"),
                    "completed_at": task.get("completed_at") or task.get("updated_at"),
                    "development_point_count": len(points),
                    "completed_point_count": sum(
                        1 for point in points if str(point.get("status") or "") in {"done", "completed"}
                    ),
                },
                "produced_by_agent_id": str(task.get("assignee_agent_id") or task.get("assignee_agent") or project.get("owner_agent") or ""),
            },
            idempotency_key=f"task-completion:{task.get('id')}:{revision}",
        )

    def backfill_completed_tasks(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        """Create idempotent draft records for completed tasks of a bound project."""
        results = []
        for task in project.get("tasks", []):
            if not isinstance(task, dict) or str(task.get("status") or "") not in {"done", "completed"}:
                continue
            deliverable = self.register_task_completion(project, task)
            if deliverable:
                results.append(deliverable)
        return results


product_delivery_service = ProductDeliveryService()


def register_document_export(
    project: dict[str, Any],
    output_path: Path,
    output_format: str,
    *,
    produced_by_agent_id: str = "",
    product_id: str = "",
    registry: ProductRegistryService = product_registry_service,
) -> dict[str, Any] | None:
    """Backward-compatible function used by the writing workspace."""
    return ProductDeliveryService(registry).register_document_export(
        project,
        output_path,
        output_format,
        produced_by_agent_id=produced_by_agent_id,
        product_id=product_id,
    )
