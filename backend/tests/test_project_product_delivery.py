from project_manager import ProjectManager
from services.product_delivery_service import ProductDeliveryService
from services.product_service import ProductRegistryService


def test_completed_task_creates_one_candidate_product_deliverable(tmp_path, monkeypatch):
    registry = ProductRegistryService(str(tmp_path / "product-registry.json"))
    delivery_service = ProductDeliveryService(registry)
    import project_manager as manager_module

    monkeypatch.setattr(manager_module, "product_delivery_service", delivery_service)
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "name": "产品交付自动化",
        "product_bindings": [{"product_id": "openclaw-3021", "role": "primary"}],
    })
    task = manager.add_task(project["id"], {
        "title": "实现产品交付接口",
        "assignee_agent": "raphael",
        "status": "todo",
    })

    manager.update_task(task["id"], {
        "status": "done",
        "result_summary": "接口与验收记录已提交",
        "context": {"delivery": {"uri": "https://example.test/commit/abc", "version": "v1.2.0"}},
    })
    manager.update_task(task["id"], {"status": "done"})

    deliverables = registry.list_deliverables("openclaw-3021")
    assert len(deliverables) == 1
    assert deliverables[0]["task_id"] == task["id"]
    assert deliverables[0]["kind"] == "source_code"
    assert deliverables[0]["uri"] == "https://example.test/commit/abc"
    assert deliverables[0]["status"] == "draft"


def test_final_development_point_creates_candidate_deliverable(tmp_path, monkeypatch):
    registry = ProductRegistryService(str(tmp_path / "product-registry.json"))
    import project_manager as manager_module

    monkeypatch.setattr(manager_module, "product_delivery_service", ProductDeliveryService(registry))
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "name": "开发要点交付",
        "product_bindings": [{"product_id": "openclaw-3021", "role": "primary"}],
    })
    task = manager.add_task(project["id"], {
        "title": "完成后端接口",
        "assignee_agent": "raphael",
        "development_points": [{"title": "实现接口", "status": "todo"}],
    })

    point_id = task["development_points"][0]["id"]
    manager.complete_point(point_id, "raphael", "已通过接口测试", "实现完成")

    deliverables = registry.list_deliverables("openclaw-3021")
    assert len(deliverables) == 1
    assert deliverables[0]["task_id"] == task["id"]
    assert deliverables[0]["metadata"]["completed_point_count"] == 1
