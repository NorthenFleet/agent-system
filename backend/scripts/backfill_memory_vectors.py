#!/usr/bin/env python3
"""Backfill approved memories and fail unless the projection reconciles."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_DIR / ".env", override=False)
except ImportError:
    pass

from services.memory_vector_service import ApprovedMemoryVectorService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-wait-seconds", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    service = ApprovedMemoryVectorService()
    if not service.ready:
        print(json.dumps({**service.health(), "success": False}, ensure_ascii=False, indent=2))
        return 2

    before = service.operations_status()
    scanned = service.enqueue_approved_memories()
    processed: list[dict] = []
    deadline = time.monotonic() + max(1, int(args.max_wait_seconds))
    while time.monotonic() < deadline:
        processed.extend(
            service.process_pending_jobs(
                owner="memory-vector-backfill",
                limit=max(1, min(int(args.batch_size), 50)),
            )
        )
        operations = service.operations_status()
        queue = operations.get("queue") or {}
        if int(queue.get("pending") or 0) == 0 and int(queue.get("processing") or 0) == 0:
            break
        time.sleep(0.5)

    after = service.operations_status()
    reconciliation = service.reconcile_projection()
    queue = after.get("queue") or {}
    success = bool(
        reconciliation.get("consistent")
        and int(queue.get("pending") or 0) == 0
        and int(queue.get("processing") or 0) == 0
        and int(queue.get("dead_letter") or 0) == 0
    )
    report = {
        "success": success,
        "approved_records_scanned": scanned,
        "jobs_processed_by_command": len(
            [item for item in processed if item.get("status") == "completed"]
        ),
        "jobs_retried_by_command": len(
            [item for item in processed if item.get("status") == "retry"]
        ),
        "queue_before": before.get("queue"),
        "queue_after": after.get("queue"),
        "reconciliation": reconciliation,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if success else 3


if __name__ == "__main__":
    sys.exit(main())
