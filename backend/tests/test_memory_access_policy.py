from main_slim_v2 import _module_for_path, app


def test_legacy_memory_routes_are_in_agents_module():
    assert _module_for_path("/api/v2/memory/agents") == "agents"
    assert _module_for_path("/api/v2/memory/search") == "agents"


def test_legacy_memory_router_requires_admin_dependency():
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v2/memory/agents")
    dependencies = route.dependant.dependencies
    assert dependencies, "legacy memory routes must carry an explicit authorization dependency"
