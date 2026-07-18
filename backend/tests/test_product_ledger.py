from services.product_service import ProductRegistryService


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
