import json
from datetime import datetime, timedelta, timezone

from services.memory_system_slo import (
    append_sample_classification,
    append_health_sample,
    build_health_sample,
    calculate_memory_slo,
    read_memory_system_drill,
)
import services.memory_system_slo as slo_module


def _status(checked_at, healthy=True, failures=None):
    return {
        "checked_at": checked_at,
        "healthy": healthy,
        "failures": failures or [],
        "summary": {
            "authority": "3021-unified-memory",
            "identity_bound": True,
            "channels": {"local_markdown": "ready"},
            "bridge_deployment": {"ready": True},
        },
        "remembered_items": [{"content": "must never enter history"}],
    }


def test_history_sample_is_sanitized_and_slo_tracks_incident_recovery(tmp_path):
    history = tmp_path / "history.jsonl"
    now = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
    append_health_sample(_status((now - timedelta(minutes=45)).isoformat()), monitor_key="primary", duration_ms=100, path=history)
    append_health_sample(
        _status(
            (now - timedelta(minutes=30)).isoformat(),
            healthy=False,
            failures=[{"check": "identity.bound", "actual": "private detail"}],
        ),
        monitor_key="primary",
        duration_ms=800,
        path=history,
    )
    append_health_sample(_status((now - timedelta(minutes=15)).isoformat()), monitor_key="primary", duration_ms=300, path=history)
    matrix_status = {
        **_status((now - timedelta(hours=1)).isoformat()),
        "summary": {"total_cases": 5, "passed_cases": 5},
        "cases": [
            {
                "summary": {
                    "authority": "3021-unified-memory",
                    "identity_bound": True,
                    "channels": {"local_markdown": "ready"},
                }
            },
            {
                "summary": {
                    "authority": "3021-unified-memory",
                    "identity_bound": True,
                    "channels": {"local_markdown": "ready"},
                }
            },
        ],
    }
    matrix_sample = append_health_sample(
        matrix_status,
        monitor_key="matrix",
        duration_ms=1200,
        path=history,
    )
    assert matrix_sample["authority"] == "3021-unified-memory"
    assert matrix_sample["identity_bound"] is True
    assert matrix_sample["channels"] == {"local_markdown": "ready"}

    raw = history.read_text(encoding="utf-8")
    assert "must never enter history" not in raw
    assert "private detail" not in raw
    assert "identity.bound" in raw

    result = calculate_memory_slo(history, days=7, now=now)
    primary = result["monitors"]["primary"]
    assert primary["status"] == "breached"
    assert primary["sample_count"] == 3
    assert primary["incident_count"] == 1
    assert primary["open_incident"] is False
    assert primary["mean_recovery_seconds"] == 900.0
    assert primary["p95_duration_ms"] == 800.0
    assert primary["top_failure_checks"] == [{"check": "identity.bound", "count": 1}]
    assert result["monitors"]["matrix"]["success_rate_percent"] == 100.0


def test_build_health_sample_rejects_unknown_monitor():
    try:
        build_health_sample(_status("2026-09-17T00:00:00+00:00"), monitor_key="unknown")
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unknown monitor key should fail")


def test_append_only_classification_excludes_invalid_environment_sample_from_slo(tmp_path):
    history = tmp_path / "history.jsonl"
    now = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
    append_health_sample(
        _status((now - timedelta(minutes=10)).isoformat()),
        monitor_key="primary",
        duration_ms=100,
        path=history,
    )
    invalid = append_health_sample(
        _status(
            (now - timedelta(minutes=5)).isoformat(),
            healthy=False,
            failures=[{"check": "gate_execution"}],
        ),
        monitor_key="primary",
        duration_ms=10_000,
        path=history,
    )

    classification = append_sample_classification(
        invalid["sample_id"],
        reason="execution_environment_invalid",
        classified_by="release-operator",
        detail="local loopback was denied by the execution sandbox",
        path=history,
    )
    duplicate = append_sample_classification(
        invalid["sample_id"],
        reason="execution_environment_invalid",
        classified_by="release-operator",
        path=history,
    )
    result = calculate_memory_slo(history, days=7, now=now)

    assert classification["status"] == "recorded"
    assert duplicate["status"] == "duplicate"
    assert result["monitors"]["primary"]["status"] == "healthy"
    assert result["monitors"]["primary"]["sample_count"] == 1
    assert result["excluded_sample_count"] == 1
    assert result["data_quality"]["excluded_samples"] == 1
    assert result["data_quality"]["exclusion_reasons"] == {
        "execution_environment_invalid": 1
    }
    raw = history.read_text(encoding="utf-8")
    assert "memory-system-sample-classification.v1" in raw
    assert raw.count(invalid["sample_id"]) == 2


def test_history_compaction_retains_recent_complete_samples(tmp_path, monkeypatch):
    history = tmp_path / "history.jsonl"
    now = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
    first = build_health_sample(_status(now.isoformat()), monitor_key="primary", duration_ms=10)
    history.write_text("\n".join(json.dumps(first) for _ in range(4)) + "\n", encoding="utf-8")
    monkeypatch.setattr(slo_module, "COMPACT_HISTORY_AT_BYTES", 1)
    monkeypatch.setattr(slo_module, "RETAIN_HISTORY_LINES", 2)

    append_health_sample(_status(now.isoformat()), monitor_key="primary", duration_ms=20, path=history)

    lines = history.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[-1])["duration_ms"] == 20.0


def test_drill_reader_marks_old_result_stale(tmp_path):
    path = tmp_path / "drill.json"
    checked = datetime(2026, 9, 1, tzinfo=timezone.utc)
    path.write_text(
        json.dumps(
            {
                "checked_at": checked.isoformat(),
                "healthy": True,
                "summary": {"total_scenarios": 4, "passed_scenarios": 4},
                "failures": [],
                "scenarios": [],
            }
        ),
        encoding="utf-8",
    )
    result = read_memory_system_drill(path, now=checked + timedelta(days=9))
    assert result["status"] == "stale"
    assert result["healthy"] is False
    assert result["failures"][-1]["check"] == "drill_freshness"
