"""Add physical cluster inventory and latest observation tables.

Revision ID: 20260925_cluster_inventory
Revises: 20260923_agent_team_hardening
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260925_cluster_inventory"
down_revision = "20260923_agent_team_hardening"
branch_labels = None
depends_on = None


_TABLE_COLUMNS = {
    "cluster_nodes": {
        "node_id", "tailscale_id", "hostname", "dns_name", "addresses", "os",
        "role", "managed", "identity_status", "legacy_device_id", "domain_refs",
        "maintenance", "network_state", "network_observed_at", "network_expired",
        "created_at", "updated_at",
    },
    "cluster_discovery": {
        "singleton_key", "observed_at", "error_code", "error_at", "updated_at",
    },
    "cluster_telemetry": {
        "node_id", "metrics", "services", "observed_at", "source", "error_code",
        "error_at", "updated_at",
    },
}
_NULLABLE = {
    "cluster_nodes": {"legacy_device_id", "network_observed_at"},
    "cluster_discovery": {"observed_at", "error_code", "error_at"},
    "cluster_telemetry": {"observed_at", "source", "error_code", "error_at"},
}
_PRIMARY_KEYS = {
    "cluster_nodes": ["node_id"],
    "cluster_discovery": ["singleton_key"],
    "cluster_telemetry": ["node_id"],
}
_TYPE_FAMILIES = {
    "cluster_nodes": {
        "node_id": sa.String, "tailscale_id": sa.String, "hostname": sa.String,
        "dns_name": sa.String, "addresses": sa.JSON, "os": sa.String,
        "role": sa.String, "managed": sa.Boolean, "identity_status": sa.String,
        "legacy_device_id": sa.String, "domain_refs": sa.JSON,
        "maintenance": sa.Boolean, "network_state": sa.String,
        "network_observed_at": sa.DateTime, "network_expired": sa.Boolean,
        "created_at": sa.DateTime, "updated_at": sa.DateTime,
    },
    "cluster_discovery": {
        "singleton_key": sa.String, "observed_at": sa.DateTime,
        "error_code": sa.String, "error_at": sa.DateTime, "updated_at": sa.DateTime,
    },
    "cluster_telemetry": {
        "node_id": sa.String, "metrics": sa.JSON, "services": sa.JSON,
        "observed_at": sa.DateTime, "source": sa.String, "error_code": sa.String,
        "error_at": sa.DateTime, "updated_at": sa.DateTime,
    },
}


def _validate_existing_schema(inspector: sa.Inspector) -> None:
    for table_name, expected_names in _TABLE_COLUMNS.items():
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        if set(columns) != expected_names:
            raise RuntimeError(
                f"incompatible {table_name} columns: expected {sorted(expected_names)}, "
                f"found {sorted(columns)}"
            )
        for column_name, column in columns.items():
            expected_nullable = column_name in _NULLABLE[table_name]
            if bool(column["nullable"]) != expected_nullable:
                raise RuntimeError(
                    f"incompatible {table_name}.{column_name} nullability"
                )
            expected_type = _TYPE_FAMILIES[table_name][column_name]
            if not isinstance(column["type"], expected_type):
                raise RuntimeError(
                    f"incompatible {table_name}.{column_name} type: {column['type']}"
                )
        primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
        if primary_key != _PRIMARY_KEYS[table_name]:
            raise RuntimeError(f"incompatible {table_name} primary key")

    indexes = {item["name"]: item for item in inspector.get_indexes("cluster_nodes")}
    tailscale_index = indexes.get("ix_cluster_nodes_tailscale_id")
    if (
        tailscale_index is None
        or not tailscale_index.get("unique")
        or tailscale_index.get("column_names") != ["tailscale_id"]
    ):
        raise RuntimeError("incompatible cluster_nodes Tailscale identity index")

    check_names = {
        item.get("name") for item in inspector.get_check_constraints("cluster_nodes")
    }
    if not {
        "ck_cluster_node_identity_status",
        "ck_cluster_node_network_state",
    }.issubset(check_names):
        raise RuntimeError("incompatible cluster_nodes check constraints")

    foreign_keys = inspector.get_foreign_keys("cluster_telemetry")
    matching_fk = [
        item for item in foreign_keys
        if item.get("constrained_columns") == ["node_id"]
        and item.get("referred_table") == "cluster_nodes"
        and item.get("referred_columns") == ["node_id"]
    ]
    if len(matching_fk) != 1:
        raise RuntimeError("incompatible cluster_telemetry node foreign key")
    ondelete = (matching_fk[0].get("options") or {}).get("ondelete")
    if str(ondelete or "").upper() != "CASCADE":
        raise RuntimeError("cluster_telemetry foreign key must cascade on delete")


def _existing_schema_state() -> tuple[sa.Inspector, set[str]]:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names()) & set(_TABLE_COLUMNS)
    if existing and existing != set(_TABLE_COLUMNS):
        raise RuntimeError(
            "partial cluster inventory schema exists; manual inspection is required"
        )
    if existing:
        _validate_existing_schema(inspector)
    return inspector, existing


def upgrade() -> None:
    inspector, existing = _existing_schema_state()
    if existing:
        return
    op.create_table(
        "cluster_nodes",
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("tailscale_id", sa.String(length=255), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("dns_name", sa.String(length=500), nullable=False),
        sa.Column("addresses", sa.JSON(), nullable=False),
        sa.Column("os", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("managed", sa.Boolean(), nullable=False),
        sa.Column("identity_status", sa.String(length=32), nullable=False),
        sa.Column("legacy_device_id", sa.String(length=64), nullable=True),
        sa.Column("domain_refs", sa.JSON(), nullable=False),
        sa.Column("maintenance", sa.Boolean(), nullable=False),
        sa.Column("network_state", sa.String(length=16), nullable=False),
        sa.Column("network_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("network_expired", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "identity_status IN ('confirmed', 'unconfirmed')",
            name="ck_cluster_node_identity_status",
        ),
        sa.CheckConstraint(
            "network_state IN ('online', 'offline', 'unknown')",
            name="ck_cluster_node_network_state",
        ),
        sa.PrimaryKeyConstraint("node_id"),
    )
    op.create_index(
        "ix_cluster_nodes_tailscale_id",
        "cluster_nodes",
        ["tailscale_id"],
        unique=True,
    )
    op.create_table(
        "cluster_discovery",
        sa.Column("singleton_key", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("singleton_key"),
    )
    op.create_table(
        "cluster_telemetry",
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["cluster_nodes.node_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if "cluster_telemetry" in existing:
        op.drop_table("cluster_telemetry")
    if "cluster_discovery" in existing:
        op.drop_table("cluster_discovery")
    if "cluster_nodes" in existing:
        indexes = {item["name"] for item in inspector.get_indexes("cluster_nodes")}
        if "ix_cluster_nodes_tailscale_id" in indexes:
            op.drop_index("ix_cluster_nodes_tailscale_id", table_name="cluster_nodes")
        op.drop_table("cluster_nodes")
