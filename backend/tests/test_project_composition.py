import json

from project_manager import ProjectManager


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
