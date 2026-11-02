"""Apply ONLY the additive cluster revision to an older SQLite deployment.

The canonical migration is reused via Alembic Operations. We intentionally do not
stamp alembic_version or apply unrelated historical migrations. A normal future
Alembic upgrade can run the same idempotent revision. No ORM initialization runs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

REVISION_PATH = Path(__file__).resolve().parents[1] / "alembic/versions/20260925_cluster_inventory.py"
CLUSTER_TABLES = {"cluster_nodes", "cluster_discovery", "cluster_telemetry"}


def _backup_locked_database(database: Path, backup: Path) -> None:
    """Caller holds BEGIN IMMEDIATE; another read connection can back up safely.

    Using the write connection's backup API while it owns an open write
    transaction can wait on itself. A separate reader sees the committed state,
    and the caller's reserved lock prevents competing writers until validation.
    """
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as source:
        with sqlite3.connect(backup) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("backup_integrity_failed")


def apply_additive(database: Path, backup: Path, expected_revision: str) -> dict:
    database = database.resolve(strict=True)
    if backup.exists() or backup.resolve() == database:
        raise ValueError("backup_must_be_a_new_path")
    with sqlite3.connect(f"{database.as_uri()}?mode=rw", uri=True) as source:
        actual = [row[0] for row in source.execute("SELECT version_num FROM alembic_version")]
        if actual != [expected_revision]:
            raise ValueError("unexpected_alembic_revision")
    spec = importlib.util.spec_from_file_location("cluster_additive_revision", REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                actual = [row[0] for row in connection.exec_driver_sql("SELECT version_num FROM alembic_version")]
                if actual != [expected_revision]:
                    raise ValueError("revision_changed_during_preflight")
                _backup_locked_database(database, backup)
                before = {tuple(row) for row in connection.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master") if row[2] not in CLUSTER_TABLES}
                with Operations.context(MigrationContext.configure(connection)):
                    module.upgrade()
                    # Also validate the structure in the initial creation case.
                    module.upgrade()
                after = {tuple(row) for row in connection.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master") if row[2] not in CLUSTER_TABLES}
                if before != after:
                    raise RuntimeError("unrelated_schema_changed")
                if [row[0] for row in connection.exec_driver_sql("SELECT version_num FROM alembic_version")] != actual:
                    raise RuntimeError("global_revision_changed")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    finally:
        engine.dispose()
    return {"applied_revision": module.revision, "global_revision_unchanged": expected_revision,
            "backup": str(backup), "tables": sorted(CLUSTER_TABLES)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("explicit --apply is required; validate on an isolated database first")
    print(json.dumps(apply_additive(args.database, args.backup, args.expected_revision)))


if __name__ == "__main__":
    main()
