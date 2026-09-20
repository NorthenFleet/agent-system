import importlib.util
import json
from pathlib import Path

from services.memory_system_gate import evaluate_memory_report


SCRIPT = Path(__file__).parents[1] / "scripts" / "memory_system_gate.py"


def _script_module():
    spec = importlib.util.spec_from_file_location("memory_system_gate_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _report():
    return {
        "schema_version": "memory-introspection.v1",
        "status": "ready",
        "authority": {"system": "3021-unified-memory"},
        "scope": {"agent_id": "optimus", "user_scoped": True},
        "identity": {"channel": "feishu", "bound": True, "display_name": "孙总"},
        "counts": {
            "profile": 1,
            "profile_facts": 10,
            "project_memories": 3,
            "agent_memories": 2,
        },
        "remembered_items": [{"scope": "profile"}],
        "retrieval": {"citations": ["fact:one"]},
        "channels": {
            "local_markdown": {"status": "ready"},
            "openclaw_lexical_index": {"status": "ready"},
            "approved_graph_projection": {"status": "ready"},
            "native_private_graph": {"status": "ready"},
        },
        "degraded_channels": [],
        "interpretation": {
            "fixed_layer_count": False,
            "private_graph_empty_means_system_empty": False,
            "sandbox_error_means_file_missing": False,
        },
    }


def _contract():
    return {
        "minimum_counts": {
            "profile": 1,
            "profile_facts": 1,
            "project_memories": 1,
            "agent_memories": 1,
        },
        "minimum_remembered_items": 1,
        "required_channels": {
            "local_markdown": ["ready"],
            "openclaw_lexical_index": ["ready"],
            "approved_graph_projection": ["ready"],
            "native_private_graph": ["ready"],
        },
        "max_degraded_channels": 0,
        "interpretation_must_be_false": [
            "fixed_layer_count",
            "private_graph_empty_means_system_empty",
            "sandbox_error_means_file_missing",
        ],
    }


def test_memory_system_gate_accepts_complete_end_to_end_report():
    result = evaluate_memory_report(_report(), _contract())

    assert result["healthy"] is True
    assert result["failures"] == []
    assert result["summary"]["channels"]["approved_graph_projection"] == "ready"


def test_memory_system_gate_reports_identity_and_channel_regressions():
    report = _report()
    report["identity"]["bound"] = False
    report["channels"]["approved_graph_projection"]["status"] = "degraded"
    report["degraded_channels"] = [{"channel": "approved_graph_projection"}]

    result = evaluate_memory_report(report, _contract())

    assert result["healthy"] is False
    checks = {failure["check"] for failure in result["failures"]}
    assert "identity.bound" in checks
    assert "channels.approved_graph_projection.status" in checks
    assert "degraded_channels" in checks


def test_memory_system_gate_enforces_agent_memory_isolation_counts():
    report = _report()
    report["counts"]["agent_memories"] = 1
    contract = _contract()
    contract["exact_counts"] = {"agent_memories": 0}

    result = evaluate_memory_report(report, contract)

    assert result["healthy"] is False
    assert any(
        failure["check"] == "counts.agent_memories"
        and failure["expected"] == 0
        for failure in result["failures"]
    )


def test_gate_publishes_only_sanitized_health_payload(monkeypatch):
    module = _script_module()
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status":"unchanged","notifications_created":0}'

    def urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    result = module.publish_health(
        "http://127.0.0.1:3021/api/v3/command-center/agent/memory-health",
        {
            "schema_version": "memory-system-health.v1",
            "checked_at": "2026-09-17T00:00:00+00:00",
            "healthy": True,
            "case_id": "case-1",
            "failures": [],
            "summary": {"channels": {"local_markdown": "ready"}},
            "remembered_items": [{"content": "private content"}],
        },
        3,
    )

    assert result["status"] == "unchanged"
    assert "remembered_items" not in captured["payload"]
    assert captured["payload"]["monitor_key"] == "primary"
    assert captured["payload"]["summary"]["channels"]["local_markdown"] == "ready"
