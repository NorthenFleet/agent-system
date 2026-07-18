from services.product_service import ProductRegistryService
import json
import sqlite3


def test_deliverable_is_idempotent_and_can_be_accepted(tmp_path):
    service = ProductRegistryService(str(tmp_path / "product-registry.json"))
    first = service.submit_deliverable(
        "openclaw-3021",
        {
            "project_id": "proj-dashboard",
            "task_id": "task-products",
            "kind": "document",
            "title": "产品设计文档",
            "uri": "knowledge://products/design",
            "produced_by_agent_id": "donatello",
        },
        idempotency_key="task-products:document:v1",
    )
    again = service.submit_deliverable(
        "openclaw-3021",
        {"kind": "document", "title": "should-not-create"},
        idempotency_key="task-products:document:v1",
    )

    assert again["id"] == first["id"]
    accepted = service.review_deliverable(
        "openclaw-3021", first["id"], accepted=True, reviewed_by_agent_id="bumblebee"
    )
    assert accepted and accepted["status"] == "accepted"
    assert service.timeline("openclaw-3021")[0]["event_type"] == "deliverable.accepted"


def test_active_release_requires_accepted_source(tmp_path):
    service = ProductRegistryService(str(tmp_path / "product-registry.json"))
    deliverable = service.submit_deliverable(
        "openclaw-3021", {"kind": "service", "title": "Dashboard API"}
    )
    try:
        service.create_release("openclaw-3021", {"source_deliverable_id": deliverable["id"]})
    except ValueError as exc:
        assert "accepted" in str(exc)
    else:
        raise AssertionError("release must reject an unaccepted deliverable")

    service.review_deliverable(
        "openclaw-3021", deliverable["id"], accepted=True, reviewed_by_agent_id="bumblebee"
    )
    release = service.create_release(
        "openclaw-3021",
        {"source_deliverable_id": deliverable["id"], "version": "v4.0.0", "status": "active"},
    )
    assert release["status"] == "active"
    assert service.get_product("openclaw-3021")["current_release_id"] == release["id"]


def test_active_release_cannot_skip_deliverable_acceptance(tmp_path):
    service = ProductRegistryService(str(tmp_path / "product-registry.json"))
    try:
        service.create_release("openclaw-3021", {"version": "v4.0.0", "status": "active"})
    except ValueError as exc:
        assert "accepted source" in str(exc)
    else:
        raise AssertionError("active release must have an accepted source deliverable")


def test_runtime_instances_are_tracked_and_validate_release_ownership(tmp_path):
    service = ProductRegistryService(str(tmp_path / "product-registry.json"))
    deliverable = service.submit_deliverable("openclaw-3021", {"kind": "service", "title": "Dashboard API"})
    service.review_deliverable(
        "openclaw-3021", deliverable["id"], accepted=True, reviewed_by_agent_id="bumblebee"
    )
    release = service.create_release(
        "openclaw-3021", {"source_deliverable_id": deliverable["id"], "version": "v4.0.0", "status": "active"}
    )
    runtime = service.create_runtime_instance(
        "openclaw-3021",
        {
            "name": "Mini production",
            "environment": "production",
            "state": "online",
            "release_id": release["id"],
            "host": "192.168.31.41",
            "port": 3021,
        },
    )
    assert service.list_runtime_instances("openclaw-3021")[0]["id"] == runtime["id"]
    updated = service.update_runtime_instance(
        "openclaw-3021", runtime["id"], {"state": "degraded", "summary": "health check timeout"}
    )
    assert updated and updated["state"] == "degraded"
    assert service.delete_runtime_instance("openclaw-3021", runtime["id"])
    assert service.list_runtime_instances("openclaw-3021") == []


def test_registry_uses_sqlite_as_authoritative_store_when_configured(tmp_path):
    legacy_path = tmp_path / "legacy-product-registry.json"
    database_path = tmp_path / "unified-dashboard.db"
    service = ProductRegistryService(str(legacy_path), db_path=str(database_path))

    created = service.upsert_product("sqlite-product", {"name": "数据库产品", "kind": "offering"})
    service.submit_deliverable("sqlite-product", {"title": "数据库交付物", "kind": "document"})

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM product_registry_products").fetchone()[0] == 7
        assert connection.execute("SELECT COUNT(*) FROM product_registry_deliverables").fetchone()[0] == 1

    reloaded = ProductRegistryService(str(legacy_path), db_path=str(database_path))
    assert reloaded.get_product(created["id"])["name"] == "数据库产品"
    assert reloaded.list_deliverables("sqlite-product")[0]["title"] == "数据库交付物"


def test_sqlite_imports_legacy_registry_only_for_first_database_initialization(tmp_path):
    legacy_path = tmp_path / "legacy-product-registry.json"
    legacy_path.write_text(json.dumps({
        "schema": "openclaw.product-registry",
        "version": 3,
        "products": [{"id": "legacy-product", "name": "历史产品", "kind": "offering"}],
        "deliverables": [{"id": "dlv-legacy", "product_id": "legacy-product", "title": "历史交付", "kind": "document", "status": "draft"}],
        "releases": [],
        "runtime_instances": [],
        "events": [],
        "idempotency": {},
    }, ensure_ascii=False), encoding="utf-8")
    database_path = tmp_path / "unified-dashboard.db"

    service = ProductRegistryService(str(legacy_path), db_path=str(database_path))
    assert service.get_product("legacy-product")["name"] == "历史产品"
    legacy_path.write_text("{}", encoding="utf-8")

    reloaded = ProductRegistryService(str(legacy_path), db_path=str(database_path))
    assert reloaded.list_deliverables("legacy-product")[0]["id"] == "dlv-legacy"
