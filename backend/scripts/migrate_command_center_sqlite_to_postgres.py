#!/usr/bin/env python3
"""Safely copy Command Center facts from SQLite to PostgreSQL.

The command is dry-run by default. ``--apply`` requires an empty PostgreSQL
target, copies all tables in dependency order inside one transaction, and
verifies row counts plus primary-key checksums before committing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repositories.command_center_repository import _postgres_dsn  # noqa: E402


TABLE_ORDER = (
    "command_conversations",
    "command_messages",
    "command_external_user_bindings",
    "orchestration_missions",
    "mission_runs",
    "mission_plan_versions",
    "mission_steps",
    "mission_step_approvals",
    "mission_effects",
    "mission_compensations",
    "mission_approvals",
    "mission_events",
    "mission_context_bindings",
    "workflow_runs",
    "mission_artifacts",
    "mission_evidence",
    "mission_acceptance_gates",
    "notification_outbox",
    "notification_deliveries",
)

SUPPORTED_TARGET_REVISIONS = {
    "20260918_command_center_pg",
    "20260919_work_run_pg",
    "20260920_langgraph_pg",
    "20260921_worker_registry",
}


def _checksum(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for value in sorted(str(row.get("id") or "") for row in rows):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _sqlite_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _sqlite_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def _postgres_columns(cursor: Any, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [str(row["column_name"]) for row in cursor.fetchall()]


def _target_summary(cursor: Any, table: str) -> dict[str, Any]:
    cursor.execute(f'SELECT id FROM "{table}"')
    rows = list(cursor.fetchall())
    return {"count": len(rows), "id_checksum": _checksum(rows)}


def migrate(sqlite_path: str, postgres_url: str, *, apply: bool) -> dict[str, Any]:
    source_path = os.path.abspath(os.path.expanduser(sqlite_path))
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"SQLite source does not exist: {source_path}")

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    target = psycopg2.connect(
        _postgres_dsn(postgres_url),
        application_name="agent-system-command-center-migration",
    )
    target.autocommit = False
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "source": source_path,
        "tables": {},
    }
    try:
        source_tables = _sqlite_tables(source)
        with target.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            version = cursor.fetchone()
            report["target_revision"] = version["version_num"] if version else ""
            if report["target_revision"] not in SUPPORTED_TARGET_REVISIONS:
                raise RuntimeError(
                    "PostgreSQL target must include revision "
                    "20260918_command_center_pg before data migration"
                )

            source_data: dict[str, list[dict[str, Any]]] = {}
            for table in TABLE_ORDER:
                rows = _sqlite_rows(source, table) if table in source_tables else []
                source_data[table] = rows
                target_before = _target_summary(cursor, table)
                report["tables"][table] = {
                    "source_count": len(rows),
                    "source_id_checksum": _checksum(rows),
                    "target_before": target_before,
                    "target_matches_source": (
                        len(rows) == target_before["count"]
                        and _checksum(rows) == target_before["id_checksum"]
                    ),
                }
                if apply and target_before["count"]:
                    raise RuntimeError(
                        f"PostgreSQL target table {table} is not empty; refusing to merge"
                    )

            if not apply:
                target.rollback()
                report["verified"] = all(
                    item["target_matches_source"]
                    for item in report["tables"].values()
                )
                return report

            for table in TABLE_ORDER:
                rows = source_data[table]
                if not rows:
                    continue
                target_columns = _postgres_columns(cursor, table)
                columns = [column for column in target_columns if column in rows[0]]
                values = [tuple(row.get(column) for column in columns) for row in rows]
                column_sql = ", ".join(f'"{column}"' for column in columns)
                execute_values(
                    cursor,
                    f'INSERT INTO "{table}" ({column_sql}) VALUES %s',
                    values,
                    page_size=500,
                )

            verified = True
            for table in TABLE_ORDER:
                target_after = _target_summary(cursor, table)
                item = report["tables"][table]
                item["target_after"] = target_after
                item["verified"] = (
                    item["source_count"] == target_after["count"]
                    and item["source_id_checksum"] == target_after["id_checksum"]
                )
                verified = verified and item["verified"]
            if not verified:
                raise RuntimeError("PostgreSQL verification failed; transaction rolled back")
            target.commit()
            report["verified"] = True
            return report
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("COMMAND_CENTER_DATABASE_URL", ""),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if not args.postgres_url:
        parser.error("--postgres-url or COMMAND_CENTER_DATABASE_URL is required")

    report = migrate(args.sqlite_path, args.postgres_url, apply=args.apply)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
