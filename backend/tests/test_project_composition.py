import json

import project_manager as project_manager_module
from project_manager import ProjectManager
from services.project_composition import normalize_project_composition, upsert_product_binding
from services.product_service import ProductRegistryService
from unified_data_manager import UnifiedDataManager


def test_project_supports_composable_modules(tmp_path):
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "name": "复合交付项目",
        "project_type": "software",
        "enabled_modules": ["development", "writing", "knowledge", "products"],
    })

    assert project["enabled_modules"] == ["development", "writing", "knowledge", "products"]
    assert project["context"]["enabled_modules"] == project["enabled_modules"]


def test_legacy_mission_binding_migrates_to_products(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text(json.dumps({
        "version": 2,
        "projects": [{
            "id": "proj-legacy",
            "name": "旧仿真项目",
            "project_type": "software",
            "context": {
                "mission_planning": {
                    "scenario_id": "naval_uav_attack",
                    "side": "red",
                    "bound_at": "2026-07-13T00:00:00+00:00",
                }
            },
            "tasks": [],
        }],
        "logs": [],
    }, ensure_ascii=False), encoding="utf-8")
    manager = ProjectManager(str(path))

    assert manager.migrate_composition_model() == 1
    project = manager.get_project("proj-legacy")
    product_ids = {row["product_id"] for row in project["product_bindings"]}

    assert {"ai-planning-5130", "one-sim"}.issubset(product_ids)
    assert "mission-planning" in project["enabled_modules"]
    assert manager.migrate_composition_model() == 0


def test_invalid_modules_are_removed(tmp_path):
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "name": "模块校验",
        "enabled_modules": ["development", "not-a-module", "finance"],
    })

    assert project["enabled_modules"] == ["development", "finance"]


def test_product_bindings_survive_unified_sqlite_roundtrip(tmp_path):
    manager = UnifiedDataManager(str(tmp_path / "dashboard.db"))
    project = {
        "id": "proj-products",
        "name": "产品持久化项目",
        "project_type": "software",
        "status": "in_progress",
        "tasks": [],
        "context": {},
    }
    upsert_product_binding(project, "openclaw-3021", role="primary")
    normalize_project_composition(project)

    manager.save_projects_document({"projects": [project], "logs": []})
    restored = manager.load_projects_document()["projects"][0]

    assert restored["enabled_modules"] == project["enabled_modules"]
    assert restored["product_bindings"] == project["product_bindings"]
    assert restored["context"]["product_bindings"] == project["product_bindings"]


def test_iteration_context_includes_bound_product_delivery_and_runtime_actions(tmp_path, monkeypatch):
    registry = ProductRegistryService(str(tmp_path / "product-registry.json"))
    monkeypatch.setattr(project_manager_module, "product_registry_service", registry)
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({"name": "产品闭环项目", "project_type": "software"})
    upsert_product_binding(project, "openclaw-3021", role="primary")
    project = manager.update_project(project["id"], {"product_bindings": project["product_bindings"]})

    draft = registry.submit_deliverable("openclaw-3021", {"project_id": project["id"], "title": "待验收成果"})
    accepted = registry.submit_deliverable("openclaw-3021", {"project_id": project["id"], "title": "待发布成果"})
    registry.review_deliverable("openclaw-3021", accepted["id"], accepted=True, reviewed_by_agent_id="bumblebee")
    registry.create_runtime_instance("openclaw-3021", {"name": "Mini", "state": "offline"})

    context = manager.get_iteration_context(project["id"])
    assert context["product_context"]["summary"]["pending_deliverable_reviews"] == 1
    assert context["product_context"]["summary"]["accepted_unreleased_deliverables"] == 1
    assert context["product_context"]["summary"]["runtime_issues"] == 1
    actions = {row["action"] for row in context["suggested_next_actions"]}
    assert {"review_product_deliverables", "create_product_release", "investigate_product_runtime"}.issubset(actions)
    assert draft["status"] == "draft"
