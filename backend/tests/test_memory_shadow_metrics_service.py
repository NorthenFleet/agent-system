import sqlite3
from datetime import datetime, timezone

from services.memory_shadow_metrics_service import (
    ensure_shadow_metrics_schema,
    record_shadow_observation,
    summarize_shadow_observations,
)


def _payload(index: int) -> dict:
    return {
        "user_id": "user-1",
        "project_id": "project-1",
        "query": f"release query {index}",
        "items": [{"source_ref": "memory:1"}],
        "retrieval_health": {
            "vector_memory": {"status": "ready", "latency_ms": 100.0},
            "hybrid_fusion": {
                "rollout_mode": "shadow",
                "served_strategy": "score-sort-baseline",
                "candidate_strategy": "weighted-rrf.v1",
                "multi_channel_candidates": 1,
                "comparison": {
                    "k": 10,
                    "overlap": 8,
                    "overlap_ratio": 0.8,
                    "top1_changed": index % 4 == 0,
                    "mean_rank_displacement": 1.5,
                    "baseline_refs": ["sensitive-baseline-ref"],
                    "candidate_refs": ["sensitive-candidate-ref"],
                },
            },
        },
    }


def test_shadow_metrics_are_privacy_minimized_and_aggregated(monkeypatch):
    monkeypatch.setenv("MEMORY_SHADOW_MIN_QUERIES", "100")
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    ensure_shadow_metrics_schema(connection)

    for index in range(100):
        record_shadow_observation(
            connection,
            pack_id=f"pack-{index}",
            payload=_payload(index),
            total_latency_ms=200.0,
        )
    connection.commit()

    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(memory_retrieval_shadow_events)"
        ).fetchall()
    }
    serialized = " ".join(
        str(tuple(row))
        for row in connection.execute(
            "SELECT * FROM memory_retrieval_shadow_events"
        ).fetchall()
    )
    report = summarize_shadow_observations(
        connection,
        window_hours=24,
        now=datetime.now(timezone.utc),
    )
    connection.close()

    assert "query" not in columns
    assert "baseline_refs" not in columns
    assert "candidate_refs" not in columns
    assert "release query" not in serialized
    assert "sensitive-baseline-ref" not in serialized
    assert report["samples"]["queries"] == 100
    assert report["samples"]["distinct_query_fingerprints"] == 100
    assert report["availability"]["vector_ready_rate"] == 1.0
    assert report["latency_ms"]["vector"]["p95"] == 100.0
    assert report["latency_ms"]["total"]["p95"] == 200.0
    assert report["ranking_change"]["top1_change_rate"] == 0.25
    assert report["rollout_gate"]["online_observation_passed"] is True
    assert report["rollout_gate"]["promotion_ready"] is False
    assert report["rollout_gate"]["blockers"] == [
        "offline_labeled_evaluation"
    ]
    assert report["privacy"]["raw_query_stored"] is False


def test_non_shadow_payload_is_not_recorded():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    payload = _payload(1)
    payload["retrieval_health"]["hybrid_fusion"]["rollout_mode"] = "baseline"

    event_id = record_shadow_observation(
        connection,
        pack_id="pack-1",
        payload=payload,
        total_latency_ms=20.0,
    )

    assert event_id is None
    assert summarize_shadow_observations(connection)["samples"]["queries"] == 0
    connection.close()
