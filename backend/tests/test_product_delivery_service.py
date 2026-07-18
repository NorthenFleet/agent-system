from services.product_delivery_service import ProductDeliveryService, product_id_for_project, register_document_export
from services.product_service import ProductRegistryService


def test_primary_product_binding_is_selected(tmp_path):
    project = {
        "product_bindings": [
            {"product_id": "openclaw-3021", "role": "uses"},
            {"product_id": "one-sim", "role": "primary"},
        ]
    }
    assert product_id_for_project(project) == "one-sim"
    assert product_id_for_project(project, "openclaw-3021") == "openclaw-3021"
    assert product_id_for_project(project, "unknown") is None


def test_document_export_becomes_product_deliverable(tmp_path):
    registry = ProductRegistryService(str(tmp_path / "product-registry.json"))
    export = tmp_path / "product-design.docx"
    export.write_bytes(b"product design")
    project = {
        "id": "proj-design",
        "name": "产品设计项目",
        "owner_agent": "donatello",
        "product_bindings": [{"product_id": "openclaw-3021", "role": "primary"}],
    }

    deliverable = register_document_export(project, export, "docx", registry=registry)

    assert deliverable and deliverable["kind"] == "document"
    assert deliverable["product_id"] == "openclaw-3021"
    assert deliverable["metadata"]["format"] == "docx"


def test_completed_task_backfill_is_idempotent(tmp_path):
    registry = ProductRegistryService(str(tmp_path / "product-registry.json"))
    service = ProductDeliveryService(registry)
    project = {
        "id": "proj-historical",
        "name": "历史看板项目",
        "product_bindings": [{"product_id": "openclaw-3021", "role": "primary"}],
        "tasks": [{"id": "task-done", "title": "已完成接口", "status": "done"}],
    }

    first = service.backfill_completed_tasks(project)
    second = service.backfill_completed_tasks(project)

    assert len(first) == len(second) == 1
    assert len(registry.list_deliverables("openclaw-3021")) == 1
