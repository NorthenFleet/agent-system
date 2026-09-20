#!/usr/bin/env python3
"""Sync explicitly reconciled cutover WorkRuns back to the SQLite fallback."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repositories.command_center_repository import _postgres_dsn  # noqa: E402


RUN_COLUMNS = (
    "status",
    "lease_expires_at",
    "failure_code",
    "failure_detail",
    "updated_at",
    "ended_at",
)
EVENT_COLUMNS = (
    "id",
    "run_id",
    "event_type",
    "from_status",
    "to_status",
    "actor",
    "detail",
    "metadata",
    "created_at",
)


def sync(sqlite_path: str, postgres_url: str) -> dict[str, Any]:
    source_path = os.path.abspath(os.path.expanduser(sqlite_path))
    postgres = psycopg2.connect(
        _postgres_dsn(postgres_url),
        application_name="agent-system-cutover-fallback-sync",
    )
    sqlite = sqlite3.connect(source_path, timeout=30)
    sqlite.row_factory = sqlite3.Row
    report: dict[str, Any] = {"sqlite_path": source_path}
    try:
        with postgres.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT * FROM work_runs
                WHERE failure_code='stale_legacy_lease'
                  AND status='blocked'
                ORDER BY id
                """
            )
            runs = list(cursor.fetchall())
            run_ids = [str(row["id"]) for row in runs]
            cursor.execute(
                """
                SELECT * FROM work_run_events
                WHERE actor='command-center-cutover'
                  AND event_type='status_changed'
                  AND to_status='blocked'
                ORDER BY id
                """
            )
            events = list(cursor.fetchall())
        if not runs or len(events) != len(runs):
            raise RuntimeError(
                "Expected one audited cutover event for every reconciled WorkRun"
            )
        if {str(row["run_id"]) for row in events} != set(run_ids):
            raise RuntimeError("Cutover event/run set mismatch")

        sqlite.execute("BEGIN IMMEDIATE")
        for row in runs:
            existing = sqlite.execute(
                "SELECT status FROM work_runs WHERE id=?",
                (row["id"],),
            ).fetchone()
            if not existing:
                raise RuntimeError(f"SQLite fallback is missing WorkRun {row['id']}")
            assignments = ", ".join(f"{column}=?" for column in RUN_COLUMNS)
            sqlite.execute(
                f"UPDATE work_runs SET {assignments} WHERE id=?",
                tuple(row[column] for column in RUN_COLUMNS) + (row["id"],),
            )
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        columns = ", ".join(EVENT_COLUMNS)
        for row in events:
            sqlite.execute(
                f"INSERT OR IGNORE INTO work_run_events ({columns}) VALUES ({placeholders})",
                tuple(row[column] for column in EVENT_COLUMNS),
            )
        sqlite.commit()

        statuses = {
            str(row["id"]): str(row["status"])
            for row in sqlite.execute(
                f"SELECT id, status FROM work_runs WHERE id IN ({','.join('?' for _ in run_ids)})",
                run_ids,
            ).fetchall()
        }
        synced_events = int(
            sqlite.execute(
                """
                SELECT COUNT(*) FROM work_run_events
                WHERE actor='command-center-cutover'
                  AND event_type='status_changed'
                  AND to_status='blocked'
                """
            ).fetchone()[0]
        )
        report.update(
            {
                "run_ids": run_ids,
                "statuses": statuses,
                "synced_events": synced_events,
                "verified": (
                    set(statuses) == set(run_ids)
                    and set(statuses.values()) == {"blocked"}
                    and synced_events == len(events)
                ),
            }
        )
        if not report["verified"]:
            raise RuntimeError("SQLite fallback verification failed")
        return report
    except Exception:
        sqlite.rollback()
        raise
    finally:
        sqlite.close()
        postgres.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("COMMAND_CENTER_DATABASE_URL", ""),
    )
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if not args.postgres_url:
        parser.error("--postgres-url or COMMAND_CENTER_DATABASE_URL is required")
    report = sync(args.sqlite_path, args.postgres_url)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
