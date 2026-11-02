"""Persistent identity and latest read-only observations for physical cluster nodes."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, JSON, String

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ClusterNode(Base):
    __tablename__ = "cluster_nodes"

    node_id = Column(String(128), primary_key=True)
    tailscale_id = Column(String(255), nullable=False, unique=True, index=True)
    hostname = Column(String(255), nullable=False, default="")
    dns_name = Column(String(500), nullable=False, default="")
    addresses = Column(JSON, nullable=False, default=list)
    os = Column(String(64), nullable=False, default="unknown")
    role = Column(String(64), nullable=False, default="unassigned")
    managed = Column(Boolean, nullable=False, default=False)
    identity_status = Column(String(32), nullable=False, default="unconfirmed")
    legacy_device_id = Column(String(64), nullable=True)
    domain_refs = Column(JSON, nullable=False, default=dict)
    maintenance = Column(Boolean, nullable=False, default=False)
    network_state = Column(String(16), nullable=False, default="unknown")
    network_observed_at = Column(DateTime(timezone=True), nullable=True)
    network_expired = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint(
            "identity_status IN ('confirmed', 'unconfirmed')",
            name="ck_cluster_node_identity_status",
        ),
        CheckConstraint(
            "network_state IN ('online', 'offline', 'unknown')",
            name="ck_cluster_node_network_state",
        ),
    )


class ClusterDiscovery(Base):
    __tablename__ = "cluster_discovery"

    singleton_key = Column(String(32), primary_key=True, default="tailscale")
    observed_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(80), nullable=True)
    error_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ClusterTelemetry(Base):
    __tablename__ = "cluster_telemetry"

    node_id = Column(
        String(128),
        ForeignKey("cluster_nodes.node_id", ondelete="CASCADE"),
        primary_key=True,
    )
    metrics = Column(JSON, nullable=False, default=dict)
    services = Column(JSON, nullable=False, default=list)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(32), nullable=True)
    error_code = Column(String(80), nullable=True)
    error_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
