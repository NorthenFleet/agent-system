#!/usr/bin/env python3
"""Read-only canonical/lifecycle/pgvector/graph-memory reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_DIR / ".env", override=False)
except ImportError:
    pass

from services.memory_projection_reconciliation_service import (  # noqa: E402
    MemoryProjectionReconciliationService,
)
from unified_data_manager import UNIFIED_DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=UNIFIED_DB_PATH)
    parser.add_argument("--user-id", default="")
    args = parser.parse_args()
    try:
        result = MemoryProjectionReconciliationService(args.db_path).reconcile(
            user_id=str(args.user_id or "")
        )
    except Exception as exc:
        result = {"status": "error", "consistent": False, "error": str(exc)[:1000]}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("consistent") else 3


if __name__ == "__main__":
    raise SystemExit(main())
