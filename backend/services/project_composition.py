"""Composable project modules and normalized product bindings."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


PROJECT_MODULES = {
    "development",
    "writing",
    "finance",
    "knowledge",
    "products",
    "mission-planning",
}

PROJECT_TYPE_MODULES = {
    "software": PROJECT_MODULES,
    "document": {"writing", "finance", "knowledge", "products"},
}

PROJECT_RELATION_TYPES = {
    "course_implementation",
    "reference_document",
    "supporting_software",
}

DEFAULT_MODULES = {
    "software": ["development", "finance", "knowledge", "products"],
    "document": ["writing", "finance", "knowledge", "products"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _binding_id(project_id: str, product_id: str) -> str:
    digest = hashlib.sha256(f"{project_id}:{product_id}".encode("utf-8")).hexdigest()[:12]
    return f"binding-{digest}"


def project_relation_id(source_project_id: str, target_project_id: str, relation_type: str) -> str:
    digest = hashlib.sha256(
        f"{source_project_id}:{target_project_id}:{relation_type}".encode("utf-8")
    ).hexdigest()[:12]
    return f"relation-{digest}"


def normalize_enabled_modules(project: dict[str, Any]) -> list[str]:
    project_type = str(project.get("project_type") or project.get("type") or "software").lower()
    if project_type not in PROJECT_TYPE_MODULES:
        project_type = "software"
    context = project.get("context") if isinstance(project.get("context"), dict) else {}
    requested = project.get("enabled_modules")
    if not isinstance(requested, list):
        requested = context.get("enabled_modules")
    allowed_modules = PROJECT_TYPE_MODULES[project_type]
    values = [str(value) for value in requested if str(value) in allowed_modules] if isinstance(requested, list) else []
    if not values:
        values = list(DEFAULT_MODULES.get(project_type, DEFAULT_MODULES["software"]))
    if project_type == "software" and isinstance(context.get("mission_planning"), dict) and context["mission_planning"].get("scenario_id"):
        values.extend(["products", "mission-planning"])
    if project_type == "document" and "writing" not in values:
        values.append("writing")
    return list(dict.fromkeys(value for value in values if value in PROJECT_MODULES))


def normalize_product_bindings(project: dict[str, Any]) -> list[dict[str, Any]]:
    project_id = str(project.get("id") or "")
    source = project.get("product_bindings")
    context = project.get("context") if isinstance(project.get("context"), dict) else {}
    if not isinstance(source, list):
        source = context.get("product_bindings")
    bindings: list[dict[str, Any]] = []
    if isinstance(source, list):
        for value in source:
            if not isinstance(value, dict) or not value.get("product_id"):
                continue
            row = dict(value)
            row.setdefault("id", _binding_id(project_id, str(row["product_id"])))
            row.setdefault("project_id", project_id)
            row.setdefault("role", "uses")
            row.setdefault("status", "bound")
            row.setdefault("config", {})
            bindings.append(row)

    mission = context.get("mission_planning") if isinstance(context.get("mission_planning"), dict) else {}
    if mission.get("scenario_id"):
        for product_id, role in (("ai-planning-5130", "planner"), ("one-sim", "simulator")):
            if any(row.get("product_id") == product_id for row in bindings):
                continue
            bindings.append({
                "id": _binding_id(project_id, product_id),
                "project_id": project_id,
                "product_id": product_id,
                "role": role,
                "status": "bound",
                "source": "mission-planning-migration",
                "bound_at": mission.get("bound_at") or _now(),
                "config": {
                    "scenario_id": mission.get("scenario_id"),
                    "side": mission.get("side") if product_id == "ai-planning-5130" else None,
                },
            })
    return bindings


def normalize_project_relations(project: dict[str, Any]) -> list[dict[str, Any]]:
    context = project.get("context") if isinstance(project.get("context"), dict) else {}
    source = project.get("project_relations")
    if not isinstance(source, list):
        source = context.get("project_relations")
    relations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in source if isinstance(source, list) else []:
        if not isinstance(value, dict):
            continue
        source_id = str(value.get("source_project_id") or "").strip()
        target_id = str(value.get("target_project_id") or "").strip()
        relation_type = str(value.get("relation_type") or "course_implementation").strip()
        if not source_id or not target_id or source_id == target_id:
            continue
        if relation_type not in PROJECT_RELATION_TYPES:
            relation_type = "course_implementation"
        relation_id = str(value.get("id") or project_relation_id(source_id, target_id, relation_type))
        if relation_id in seen:
            continue
        seen.add(relation_id)
        relations.append({
            "id": relation_id,
            "source_project_id": source_id,
            "target_project_id": target_id,
            "relation_type": relation_type,
            "status": str(value.get("status") or "active"),
            "purpose": str(value.get("purpose") or ""),
            "source_role": str(value.get("source_role") or "course_documentation"),
            "target_role": str(value.get("target_role") or "software_implementation"),
            "context_policy": str(value.get("context_policy") or "bidirectional_summary"),
            "context_contract": value.get("context_contract") if isinstance(value.get("context_contract"), dict) else {},
            "created_by": str(value.get("created_by") or "project-manager"),
            "created_at": value.get("created_at") or _now(),
            "updated_at": value.get("updated_at") or _now(),
        })
    return relations


def normalize_project_composition(project: dict[str, Any]) -> bool:
    before_modules = project.get("enabled_modules")
    before_bindings = project.get("product_bindings")
    before_relations = project.get("project_relations")
    modules = normalize_enabled_modules(project)
    bindings = normalize_product_bindings(project)
    relations = normalize_project_relations(project)
    project["enabled_modules"] = modules
    project["product_bindings"] = bindings
    project["project_relations"] = relations
    context = project.get("context") if isinstance(project.get("context"), dict) else {}
    context["enabled_modules"] = modules
    # The unified SQLite project table persists the context JSON. Keep the
    # top-level compatibility fields and the persisted representation aligned.
    context["product_bindings"] = bindings
    context["project_relations"] = relations
    project["context"] = context
    return before_modules != modules or before_bindings != bindings or before_relations != relations


def upsert_product_binding(
    project: dict[str, Any],
    product_id: str,
    *,
    role: str = "uses",
    status: str = "bound",
    config: dict[str, Any] | None = None,
    source: str = "project-console",
) -> dict[str, Any]:
    normalize_project_composition(project)
    bindings = project["product_bindings"]
    row = next((item for item in bindings if item.get("product_id") == product_id), None)
    if row is None:
        row = {
            "id": _binding_id(str(project.get("id") or ""), product_id),
            "project_id": project.get("id"),
            "product_id": product_id,
            "bound_at": _now(),
        }
        bindings.append(row)
    merged_config = dict(row.get("config") or {})
    merged_config.update(config or {})
    row.update({
        "role": str(role or "uses")[:64],
        "status": status,
        "config": merged_config,
        "source": source,
        "updated_at": _now(),
    })
    modules = project["enabled_modules"]
    if "products" not in modules:
        modules.append("products")
    if product_id in {"ai-planning-5130", "one-sim"} and "mission-planning" not in modules:
        modules.append("mission-planning")
    project["context"]["enabled_modules"] = modules
    return row


def remove_product_binding(project: dict[str, Any], product_id: str) -> bool:
    normalize_project_composition(project)
    before = len(project["product_bindings"])
    project["product_bindings"] = [
        row for row in project["product_bindings"] if row.get("product_id") != product_id
    ]
    return len(project["product_bindings"]) != before
