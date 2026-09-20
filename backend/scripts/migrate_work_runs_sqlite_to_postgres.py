#!/usr/bin/env python3
"""Copy canonical Work Run facts from SQLite to an empty PostgreSQL target."""

from __future__ import annotations

import argparse
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
from scripts.migrate_command_center_sqlite_to_postgres import _checksum  # noqa: E402


TABLE_ORDER = ("work_runs", "work_run_events", "work_artifacts")
SUPPORTED_TARGET_REVISIONS = {
    "20260919_work_run_pg",
    "20260920_langgraph_pg",
    "20260921_worker_registry",
}


def _source_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def _target_rows(cursor: Any, table: str) -> list[dict[str, Any]]:
    cursor.execute(f'SELECT id FROM "{table}"')
    return list(cursor.fetchall())


def migrate(sqlite_path: str, postgres_url: str, *, apply: bool) -> dict[str, Any]:
    source_path = os.path.abspath(os.path.expanduser(sqlite_path))
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    target = psycopg2.connect(
        _postgres_dsn(postgres_url),
        application_name="agent-system-work-run-migration",
    )
    target.autocommit = False
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "source": source_path,
        "tables": {},
    }
    try:
        with target.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            version = cursor.fetchone()
            report["target_revision"] = version["version_num"] if version else ""
            if report["target_revision"] not in SUPPORTED_TARGET_REVISIONS:
                raise RuntimeError(
                    "PostgreSQL target must include revision 20260919_work_run_pg"
                )

            source_data: dict[str, list[dict[str, Any]]] = {}
            for table in TABLE_ORDER:
                rows = _source_rows(source, table)
                target_rows = _target_rows(cursor, table)
                item = {
                    "source_count": len(rows),
                    "source_id_checksum": _checksum(rows),
                    "target_before": {
                        "count": len(target_rows),
                        "id_checksum": _checksum(target_rows),
                    },
                }
                item["target_matches_source"] = (
                    item["source_count"] == item["target_before"]["count"]
                    and item["source_id_checksum"]
                    == item["target_before"]["id_checksum"]
                )
                report["tables"][table] = item
                source_data[table] = rows
                if apply and target_rows:
                    raise RuntimeError(f"Target table {table} is not empty; refusing to merge")

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
                cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema=current_schema() AND table_name=%s
                    ORDER BY ordinal_position
                    """,
                    (table,),
                )
                target_columns = [row["column_name"] for row in cursor.fetchall()]
                columns = [column for column in target_columns if column in rows[0]]
                column_sql = ", ".join(f'"{column}"' for column in columns)
                execute_values(
                    cursor,
                    f'INSERT INTO "{table}" ({column_sql}) VALUES %s',
                    [tuple(row.get(column) for column in columns) for row in rows],
                    page_size=500,
                )

            verified = True
            for table in TABLE_ORDER:
                target_rows = _target_rows(cursor, table)
                item = report["tables"][table]
                item["target_after"] = {
                    "count": len(target_rows),
                    "id_checksum": _checksum(target_rows),
                }
                item["verified"] = (
                    item["source_count"] == item["target_after"]["count"]
                    and item["source_id_checksum"]
                    == item["target_after"]["id_checksum"]
                )
                verified = verified and item["verified"]
            if not verified:
                raise RuntimeError("Work Run verification failed; transaction rolled back")
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
    parser.add_argument("--postgres-url", default=os.getenv("WORK_RUN_DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if not args.postgres_url:
        parser.error("--postgres-url or WORK_RUN_DATABASE_URL is required")
    report = migrate(args.sqlite_path, args.postgres_url, apply=args.apply)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
