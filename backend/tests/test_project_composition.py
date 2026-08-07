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


def test_document_projects_cannot_enable_development_modules(tmp_path):
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "name": "课程项目",
        "project_type": "document",
        "enabled_modules": ["development", "writing", "mission-planning", "products"],
    })

    assert project["enabled_modules"] == ["writing", "products"]
    assert "development" not in project["context"]["enabled_modules"]


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


def test_project_relations_are_bidirectional_and_enter_agent_context(tmp_path):
    manager = ProjectManager(str(tmp_path / "projects.json"))
    course = manager.create_project({
        "id": "course-1",
        "name": "水面舰艇作战软件与兵棋推演课程",
        "project_type": "document",
        "description": "形成教学计划、教案和实作指导书",
        "document_spec": {
            "document_type": "课程建设项目",
            "writing_goal": "形成软件与兵棋推演一体化课程",
            "target_audience": "任课教员和参训学员",
        },
    })
    software = manager.create_project({
        "id": "software-1",
        "name": "one-sim 仿真",
        "project_type": "software",
        "description": "实现水面舰艇作战软件与兵棋推演引擎",
    })
    manual = manager.create_project({
        "id": "manual-1",
        "name": "谋战·水面舰艇编队战术手工兵棋",
        "project_type": "document",
        "description": "课程兵棋规则和想定基线",
    })

    relation = manager.link_projects(
        course["id"],
        software["id"],
        purpose="课程提供需求和验收依据，one-sim 提供软件实作环境",
        context_contract={"implementation_repo": "/workspace/one-sim"},
    )
    reference_relation = manager.link_projects(
        course["id"],
        manual["id"],
        relation_type="reference_document",
        purpose="课程专业内容基线",
    )

    assert relation["relation_type"] == "course_implementation"
    assert {item["id"] for item in manager.get_project(course["id"])["project_relations"]} == {
        relation["id"],
        reference_relation["id"],
    }
    assert manager.get_project(software["id"])["project_relations"][0]["id"] == relation["id"]

    course_context = manager.build_project_chat_context(course["id"])
    software_context = manager.get_iteration_context(software["id"])
    assert course_context["relationship_context"]["implementation_project"]["id"] == software["id"]
    assert software_context["relationship_context"]["source_documents"][0]["id"] == course["id"]
    assert "文档任务不得直接" in " ".join(software_context["background_context"]["boundaries"])
    assert software_context["project_manager_input"]["relationship_context"]["relations"][0]["id"] == relation["id"]

    manager.update_project(course["id"], {
        "project_relations": [],
        "context": {"project_relations": [], "goal": "保留关系，仅更新目标"},
    })
    assert {item["id"] for item in manager.get_project(course["id"])["project_relations"]} == {
        relation["id"],
        reference_relation["id"],
    }
    assert manager.get_project(software["id"])["project_relations"][0]["id"] == relation["id"]


def test_project_relations_survive_unified_sqlite_roundtrip(tmp_path):
    manager = UnifiedDataManager(str(tmp_path / "dashboard.db"))
    relation = {
        "id": "relation-course-software",
        "source_project_id": "course-1",
        "target_project_id": "software-1",
        "relation_type": "course_implementation",
        "status": "active",
        "purpose": "共享课程与软件背景",
    }
    project = {
        "id": "software-1",
        "name": "one-sim",
        "project_type": "software",
        "status": "active",
        "tasks": [],
        "context": {"project_relations": [relation]},
        "project_relations": [relation],
    }
    normalize_project_composition(project)

    manager.save_projects_document({"projects": [project], "logs": []})
    restored = manager.load_projects_document()["projects"][0]

    assert restored["context"]["project_relations"][0]["source_project_id"] == "course-1"
    normalize_project_composition(restored)
    assert restored["context"]["project_relations"] == restored["project_relations"]


def test_software_spec_update_persists_all_typed_fields(tmp_path):
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "id": "software-spec-1",
        "name": "one-sim",
        "project_type": "software",
    })

    result = manager.update_software_spec(project["id"], {
        "requirements": [{"title": "支持编队战术推演"}],
        "architecture": {"components": ["裁决引擎"]},
        "database_design": {"entities": ["舰艇"]},
        "api_design": [{"path": "/simulation"}],
        "frontend_design": {"views": ["态势图"]},
        "test_plan": [{"name": "编队协同回归"}],
        "deployment_plan": [{"target": "Mac Pro"}],
    }, "wheeljack")

    assert result["design_doc"]["version"] == 2
    restored = manager.get_project(project["id"])["design_doc"]
    assert restored["usage_requirements"][0]["title"] == "支持编队战术推演"
    assert restored["system_architecture"]["components"] == ["裁决引擎"]
    assert restored["data_structure"]["entities"] == ["舰艇"]
    assert restored["api_interfaces"][0]["path"] == "/simulation"
    assert restored["frontend_design"]["views"] == ["态势图"]
    assert restored["test_plan"][0]["name"] == "编队协同回归"
    assert restored["deployment_plan"][0]["target"] == "Mac Pro"


def test_document_section_and_asset_crud_is_persisted(tmp_path):
    manager = ProjectManager(str(tmp_path / "projects.json"))
    project = manager.create_project({
        "id": "course-doc-1",
        "name": "水面舰艇作战软件与兵棋推演课程",
        "project_type": "document",
    })

    created_section = manager.add_document_section(project["id"], {
        "title": "课程教学计划",
        "main_content": "明确课程目标与学时分配",
    }, "ultramagnus")
    section_id = created_section["section"]["id"]
    updated_section = manager.update_document_section(
        project["id"],
        section_id,
        {"content_brief": "补充考核方式", "status": "writing"},
        "ultramagnus",
    )
    created_asset = manager.add_document_asset(project["id"], {
        "section_id": section_id,
        "type": "diagram",
        "title": "课程能力结构图",
    }, "ultramagnus")
    asset_id = created_asset["asset"]["id"]
    updated_asset = manager.update_document_asset(
        project["id"],
        asset_id,
        {"description": "课程、兵棋与软件实作的关系"},
        "ultramagnus",
    )

    assert updated_section["section"]["main_content"] == "补充考核方式"
    assert updated_asset["asset"]["chapter_id"] == section_id
    restored = manager.get_project(project["id"])["document_spec"]
    assert restored["chapters"][0]["status"] == "writing"
    assert restored["assets"][0]["description"] == "课程、兵棋与软件实作的关系"

    assert manager.delete_document_section(project["id"], section_id, "ultramagnus")
    after_delete = manager.get_project(project["id"])["document_spec"]
    assert after_delete["chapters"] == []
    assert after_delete["assets"] == []


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
