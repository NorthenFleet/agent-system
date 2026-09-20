#!/usr/bin/env python3
"""Build and execute the phase-1 real-memory effectiveness baseline."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.context_retrieval_service import ContextRetrievalService
from services.memory_effectiveness_service import (
    build_provisional_dataset,
    evaluate_effectiveness_dataset,
    load_dataset,
    save_json,
)
from unified_data_manager import UNIFIED_DB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a reproducible, non-promoting memory-effectiveness baseline."
    )
    parser.add_argument("--db", default=UNIFIED_DB_PATH)
    parser.add_argument("--owner-user-id", default="1")
    parser.add_argument("--target-cases", type=int, default=80)
    parser.add_argument("--dataset", default="")
    parser.add_argument("--dataset-output", default="")
    parser.add_argument("--report-output", default="")
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = str(Path(args.db).expanduser().resolve())
    if args.dataset:
        dataset = load_dataset(args.dataset)
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            dataset = build_provisional_dataset(
                conn,
                owner_user_id=str(args.owner_user_id),
                target_cases=max(1, min(int(args.target_cases), 1000)),
            )
        finally:
            conn.close()
    if args.dataset_output:
        save_json(args.dataset_output, dataset)
    service = ContextRetrievalService(db_path)
    report = evaluate_effectiveness_dataset(service, dataset)
    if args.report_output:
        save_json(args.report_output, report)
    printable = report
    if args.summary_only:
        printable = {
            key: report[key]
            for key in (
                "version",
                "dataset_id",
                "dataset_hash",
                "metrics",
                "by_scenario",
                "quality_checks",
                "data_quality",
                "effectiveness_gate",
                "error_attribution",
                "failure_breakdown",
            )
        }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0 if report["effectiveness_gate"]["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
