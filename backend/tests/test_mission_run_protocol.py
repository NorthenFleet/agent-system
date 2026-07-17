from services.mission_run_protocol import (
    create_run,
    current_run,
    ensure_mission_protocol,
    protocol_summary,
    record_artifact,
    record_command,
    record_event,
    transition_run,
    update_binding,
)


def _project():
    return {
        "id": "proj-demo",
        "name": "联合任务",
        "description": "验证统一运行协议",
    }


def test_protocol_owns_dual_product_bindings():
    integration = {"scenario_id": "scenario-1", "side": "red", "bound_at": "now"}

    changed = ensure_mission_protocol(_project(), integration, product_url="http://5130")
    update_binding(integration)

    assert changed is True
    assert integration["mission"]["project_id"] == "proj-demo"
    assert integration["mission"]["bindings"]["planning"]["product"] == "ai-planning"
    assert integration["mission"]["bindings"]["simulation"]["product"] == "one-sim"
    assert integration["mission"]["bindings"]["simulation"]["mode"] == "embedded-planning-situation"


def test_run_correlates_commands_events_and_artifacts():
    integration = {"scenario_id": "scenario-1", "side": "blue"}
    ensure_mission_protocol(_project(), integration, product_url="http://5130")
    run = create_run(integration, actor="human:test")

    command = record_command(integration, "generate_plan", target="ai-planning")
    event = record_event(
        integration,
        "simulation.snapshot",
        source="one-sim",
        summary="frame 10",
        data={"frame": 10},
    )
    artifact = record_artifact(
        integration,
        "simulation-state-summary",
        source="one-sim",
        title="frame 10",
        metadata={"frame": 10},
    )
    transition_run(integration, "running")

    assert current_run(integration)["id"] == run["id"]
    assert command["correlation_id"] == run["correlation_id"]
    assert event["correlation_id"] == run["correlation_id"]
    assert artifact["correlation_id"] == run["correlation_id"]
    assert protocol_summary(integration)["current_run"]["status"] == "running"


def test_identical_consecutive_event_is_compacted():
    integration = {"scenario_id": "scenario-1"}
    ensure_mission_protocol(_project(), integration, product_url="http://5130")
    create_run(integration, actor="system:test")

    first = record_event(
        integration,
        "planning.status",
        source="ai-planning",
        summary="idle",
        data={"tick": 1},
    )
    second = record_event(
        integration,
        "planning.status",
        source="ai-planning",
        summary="idle",
        data={"tick": 1},
    )

    assert first["id"] == second["id"]
    assert current_run(integration)["events"][0]["observations"] == 2
