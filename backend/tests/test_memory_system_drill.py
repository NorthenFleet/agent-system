import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "memory_system_drill.py"


def _module():
    spec = importlib.util.spec_from_file_location("memory_system_drill_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_non_destructive_drill_covers_all_expected_failure_paths():
    result = _module().run_drills()

    assert result["healthy"] is True
    assert result["summary"] == {
        "mode": "synthetic-non-destructive",
        "total_scenarios": 4,
        "passed_scenarios": 4,
        "failed_scenarios": [],
    }
    assert {item["name"] for item in result["scenarios"]} == {
        "3021_unavailable",
        "identity_unbound",
        "bridge_version_mismatch",
        "notification_recovery_dedupe",
    }
    assert all(item["passed"] for item in result["scenarios"])
