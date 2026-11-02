from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models.cluster_inventory import ClusterDiscovery, ClusterNode, ClusterTelemetry
from models.v2_models import SystemSetting
from routers.auth_router import get_current_user
from routers.cluster_inventory_router import router
from services.cluster_inventory_service import (
    ClusterInventoryConflict,
    ClusterInventoryService,
)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            ClusterNode.__table__,
            ClusterDiscovery.__table__,
            ClusterTelemetry.__table__,
            SystemSetting.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _node(**overrides):
    payload = {
        "node_id": "mac-mini-01",
        "tailscale_id": "n-control",
        "hostname": "appledeMac-mini",
        "dns_name": "applemac-mini.tailnet.ts.net",
        "addresses": ["100.81.208.50"],
        "os": "macOS",
        "role": "control",
        "managed": True,
        "identity_status": "confirmed",
        "legacy_device_id": None,
        "domain_refs": {"service": "3021"},
        "maintenance": False,
    }
    payload.update(overrides)
    return payload


def test_service_constructor_does_not_create_schema():
    engine = create_engine("sqlite://")
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        ClusterInventoryService(db)
        assert inspect(engine).get_table_names() == []
    finally:
        db.close()
        engine.dispose()


def test_register_node_has_stable_identity_and_rejects_conflicts(session):
    service = ClusterInventoryService(session)
    created = service.register_node(_node())
    session.commit()

    updated = service.register_node(_node(hostname="mac-mini-renamed"))
    session.commit()
    assert updated.node_id == created.node_id
    assert updated.hostname == "mac-mini-renamed"

    with pytest.raises(ClusterInventoryConflict, match="node_id"):
        service.register_node(_node(tailscale_id="n-other"))
    session.rollback()

    with pytest.raises(ClusterInventoryConflict, match="tailscale_id"):
        service.register_node(_node(node_id="duplicate-node"))


def test_discovery_creates_unmanaged_peers_and_offline_is_authoritative(session):
    service = ClusterInventoryService(session)
    service.register_node(_node())
    first = datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc)
    service.record_discovery(
        {
            "nodes": [
                {
                    "tailscale_id": "n-control",
                    "hostname": "appledeMac-mini",
                    "dns_name": "applemac-mini.tailnet.ts.net",
                    "addresses": ["100.81.208.50"],
                    "os": "macOS",
                    "online": True,
                    "expired": False,
                },
                {
                    "tailscale_id": "n-unmanaged",
                    "hostname": "new-peer",
                    "addresses": ["100.64.0.9"],
                    "os": "linux",
                    "online": True,
                },
            ]
        },
        first,
    )
    session.commit()

    snapshot = service.snapshot(now=first + timedelta(seconds=30))
    unmanaged = next(node for node in snapshot["nodes"] if node["tailscale_id"] == "n-unmanaged")
    assert unmanaged["managed"] is False
    assert unmanaged["identity_status"] == "unconfirmed"
    assert unmanaged["scheduling"] == {"eligible": False, "reason": "phase_2_read_only"}

    second = first + timedelta(seconds=31)
    service.record_discovery(
        {
            "nodes": [
                {
                    "tailscale_id": "n-control",
                    "hostname": "appledeMac-mini",
                    "online": True,
                    "expired": True,
                }
            ]
        },
        second,
    )
    session.commit()
    snapshot = service.snapshot(now=second)
    control = next(node for node in snapshot["nodes"] if node["tailscale_id"] == "n-control")
    unmanaged = next(node for node in snapshot["nodes"] if node["tailscale_id"] == "n-unmanaged")
    assert control["network"]["state"] == "offline"
    assert control["network"]["expired"] is True
    assert unmanaged["network"]["state"] == "unknown"
    assert unmanaged["network"]["observed_at"] == second.isoformat()


def test_snapshot_tracks_missing_stale_error_and_preserves_last_good_metrics(session):
    service = ClusterInventoryService(session, freshness_seconds=90)
    service.register_node(_node())
    session.commit()
    now = datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc)

    missing = service.snapshot(now=now)
    assert missing["discovery"]["state"] == "missing"
    assert missing["nodes"][0]["telemetry"]["state"] == "missing"
    assert missing["nodes"][0]["telemetry"]["metrics"]["cpu_percent"] is None
    assert missing["nodes"][0]["telemetry"]["metrics"]["gpus"] == []

    service.record_discovery(
        {"nodes": [{"tailscale_id": "n-control", "online": True, "expired": False}]},
        now,
    )
    service.record_telemetry(
        "mac-mini-01",
        {"cpu_percent": 17.5, "architecture": "arm64"},
        now,
        source="ssh",
        services=[{"name": "agent-system", "state": "healthy", "observed_at": now.isoformat()}],
    )
    session.commit()
    fresh = service.snapshot(now=now + timedelta(seconds=10))
    assert fresh["discovery"]["state"] == "fresh"
    assert fresh["nodes"][0]["network"]["state"] == "online"
    assert fresh["nodes"][0]["telemetry"]["state"] == "fresh"

    service.record_telemetry(
        "mac-mini-01",
        {},
        now + timedelta(seconds=20),
        source="ssh",
        error="ssh_timeout secret-output-must-not-leak",
        services=[
            {
                "name": "agent-system",
                "state": "unhealthy",
                "observed_at": (now + timedelta(seconds=20)).isoformat(),
            }
        ],
    )
    session.commit()
    failed = service.snapshot(now=now + timedelta(seconds=21))
    assert failed["nodes"][0]["telemetry"]["state"] == "error"
    assert failed["nodes"][0]["telemetry"]["observed_at"] == now.isoformat()
    assert failed["nodes"][0]["telemetry"]["metrics"]["cpu_percent"] == 17.5
    assert failed["nodes"][0]["telemetry"]["error"] == "ssh_timeout"
    assert failed["nodes"][0]["services"][0]["state"] == "unhealthy"

    stale = service.snapshot(now=now + timedelta(seconds=111))
    assert stale["discovery"]["state"] == "stale"
    assert stale["nodes"][0]["network"]["state"] != "online"
    assert stale["nodes"][0]["services"][0]["state"] == "unknown"


def test_future_timestamps_and_malformed_metrics_fail_closed(session):
    service = ClusterInventoryService(session)
    service.register_node(_node())
    now = datetime(2026, 9, 25, 4, 0, tzinfo=timezone.utc)
    future = now + timedelta(minutes=5)
    service.record_discovery(
        {"nodes": [{"tailscale_id": "n-control", "online": True}]},
        future,
    )
    service.record_telemetry(
        "mac-mini-01",
        {
            "cpu_percent": "not-a-number",
            "memory_percent": float("nan"),
            "memory_total_bytes": 100,
            "memory_available_bytes": 101,
            "cpu_logical_count": True,
            "gpu_probe_state": "made-up",
            "docker_state": "running-ish",
            "gpus": [
                {
                    "name": "gpu",
                    "memory_total_bytes": 9,
                    "memory_used_bytes": 10,
                    "utilization_percent": 101,
                }
            ] * 20,
        },
        future,
        services=[
            {"name": "future-service", "state": "healthy", "observed_at": future.isoformat()},
            {"name": "invalid-time-service", "state": "healthy", "observed_at": "not-a-time"},
        ],
    )
    session.commit()

    snapshot = service.snapshot(now=now)
    node = snapshot["nodes"][0]
    assert snapshot["discovery"]["state"] == "stale"
    assert node["network"]["state"] == "unknown"
    assert node["telemetry"]["state"] == "stale"
    assert node["telemetry"]["metrics"]["cpu_percent"] is None
    assert node["telemetry"]["metrics"]["memory_percent"] is None
    assert node["telemetry"]["metrics"]["memory_total_bytes"] == 100
    assert node["telemetry"]["metrics"]["memory_available_bytes"] is None
    assert node["telemetry"]["metrics"]["cpu_logical_count"] is None
    assert node["telemetry"]["metrics"]["gpu_probe_state"] is None
    assert node["telemetry"]["metrics"]["docker_state"] is None
    assert len(node["telemetry"]["metrics"]["gpus"]) == 16
    assert node["telemetry"]["metrics"]["gpus"][0]["memory_total_bytes"] == 9
    assert node["telemetry"]["metrics"]["gpus"][0]["memory_used_bytes"] is None
    assert node["telemetry"]["metrics"]["gpus"][0]["utilization_percent"] is None
    assert node["services"][0]["state"] == "unknown"
    assert node["services"][1]["state"] == "unknown"
    assert node["services"][1]["observed_at"] is None


def test_discovery_error_does_not_destroy_last_success(session):
    service = ClusterInventoryService(session)
    observed = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)
    service.record_discovery({"nodes": []}, observed)
    service.record_discovery_error("tailscale_failed stderr=credential")
    session.commit()

    snapshot = service.snapshot(now=observed + timedelta(seconds=1))
    assert snapshot["discovery"]["state"] == "error"
    assert snapshot["discovery"]["observed_at"] == observed.isoformat()
    assert snapshot["discovery"]["error"] == "tailscale_failed"


def test_authenticated_cluster_endpoint_is_read_only(session):
    service = ClusterInventoryService(session)
    service.register_node(_node())
    session.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    unauthenticated = TestClient(app).get("/api/v2/monitoring/cluster")
    assert unauthenticated.status_code == 401

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "1",
        "username": "admin",
        "role": "admin",
    }
    response = TestClient(app).get("/api/v2/monitoring/cluster")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "cluster-monitoring.v1"
    assert payload["mode"] == "read_only"
    assert payload["generated_at"].endswith("+00:00")
    assert payload["nodes"][0]["scheduling"]["eligible"] is False
    assert payload["execution"]["enabled"] is False
    assert "production_login_required" in payload["execution"]["blockers"]
    assert session.query(ClusterTelemetry).count() == 0
    assert session.query(SystemSetting).count() == 0
    assert TestClient(app).post("/api/v2/monitoring/cluster", json={}).status_code == 405
    assert all(route.methods == {"GET"} for route in router.routes)


def test_additive_migration_can_be_applied_idempotently_without_version_stamp():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260925_cluster_inventory.py"
    )
    spec = importlib.util.spec_from_file_location("cluster_inventory_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                migration.upgrade()
        inspector = inspect(engine)
        assert {
            "cluster_nodes",
            "cluster_discovery",
            "cluster_telemetry",
        }.issubset(inspector.get_table_names())
        tailscale_index = next(
            item
            for item in inspector.get_indexes("cluster_nodes")
            if item["name"] == "ix_cluster_nodes_tailscale_id"
        )
        assert tailscale_index["unique"] == 1

        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            operations = Operations(context)
            operations.drop_index(
                "ix_cluster_nodes_tailscale_id",
                table_name="cluster_nodes",
            )
            operations.create_index(
                "ix_cluster_nodes_tailscale_id",
                "cluster_nodes",
                ["tailscale_id"],
                unique=False,
            )
            with Operations.context(context), pytest.raises(
                RuntimeError,
                match="Tailscale identity index",
            ):
                migration.upgrade()
    finally:
        engine.dispose()
