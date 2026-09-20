#!/usr/bin/env python3
"""Validate and attach AI suggestions to a human memory-review batch."""

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

from services.context_retrieval_service import context_retrieval_service  # noqa: E402
from services.memory_retrieval_evaluation_service import (  # noqa: E402
    MemoryRetrievalEvaluationService,
)


DEFAULT_FILE = BACKEND_DIR / "evals" / "memory_retrieval_review_proposals_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--owner-user-id", default="1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.file.read_text(encoding="utf-8"))
    proposals = payload.get("proposals") or []
    case_ids = [str(item.get("case_id") or "") for item in proposals]
    if payload.get("version") != "memory-review-proposals.v1":
        raise SystemExit("unsupported proposal artifact version")
    if not payload.get("batch_id"):
        raise SystemExit("batch_id is required")
    if len(proposals) != 30 or len(set(case_ids)) != len(case_ids):
        raise SystemExit("proposal artifact must contain 30 unique case IDs")

    evaluator = MemoryRetrievalEvaluationService(context_retrieval_service)
    batch = evaluator.latest_review_batch(str(args.owner_user_id))
    if not batch or batch["id"] != payload["batch_id"]:
        raise SystemExit("proposal artifact does not match the current review batch")
    if set(case_ids) != set(batch["case_ids"]):
        raise SystemExit("proposal artifact must cover every selected batch case exactly once")

    before = {
        case["id"]: (case["query"], case["status"], case["version"], case["review_checks"])
        for case in evaluator.list_cases(str(args.owner_user_id), limit=1000)
        if case["id"] in set(case_ids)
    }
    result = batch
    if not args.dry_run:
        result = evaluator.set_review_proposals(
            owner_user_id=str(args.owner_user_id),
            batch_id=str(payload["batch_id"]),
            proposed_by=str(payload.get("proposed_by") or "assistant"),
            proposals=proposals,
        )
    after = {
        case["id"]: (case["query"], case["status"], case["version"], case["review_checks"])
        for case in evaluator.list_cases(str(args.owner_user_id), limit=1000)
        if case["id"] in set(case_ids)
    }
    unchanged = before == after
    report = {
        "success": bool(args.dry_run or result.get("proposal_count") == 30) and unchanged,
        "dry_run": args.dry_run,
        "batch_id": result["id"],
        "proposal_count": 30 if args.dry_run else result.get("proposal_count"),
        "selected_cases": result.get("selected_cases"),
        "active_cases": result.get("active_cases"),
        "cases_unchanged": unchanged,
        "automatic_review": result.get("automatic_review"),
        "automatic_activation": result.get("automatic_activation"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 2


if __name__ == "__main__":
    sys.exit(main())
