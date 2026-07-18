from services.product_delivery_service import product_id_for_project, register_document_export
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
