#!/usr/bin/env python3
"""Inspector client for independent finance-intake review."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = os.getenv("COMMAND_CENTER_URL", "http://127.0.0.1:3021").rstrip("/")


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("COMMAND_CENTER_INGRESS_TOKEN", "").strip()
    if token:
        headers["X-Command-Center-Token"] = token
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=(json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"3021 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"3021 unavailable: {exc}") from exc


def list_pending() -> dict[str, Any]:
    return _request(
        "GET",
        "/api/v3/command-center/agent/finance-jobs?agent_id=inspector&status=needs_review",
    )


def show(job_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/v3/command-center/agent/finance-jobs/{urllib.parse.quote(job_id)}?agent_id=inspector",
    )


def review(
    job_id: str,
    decision: str,
    summary: str,
    findings: list[dict[str, Any]],
    confidence: float,
    expected_version: int,
) -> dict[str, Any]:
    return _request(
        "POST",
        f"/api/v3/command-center/agent/finance-jobs/{urllib.parse.quote(job_id)}/review",
        {
            "reviewer_agent_id": "inspector",
            "decision": decision,
            "summary": summary,
            "findings": findings,
            "confidence": confidence,
            "expected_version": expected_version,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show_parser = commands.add_parser("show")
    show_parser.add_argument("--job-id", required=True)
    review_parser = commands.add_parser("review")
    review_parser.add_argument("--job-id", required=True)
    review_parser.add_argument("--decision", choices=("approve", "reject"), required=True)
    review_parser.add_argument("--summary", required=True)
    review_parser.add_argument("--findings-json", default="[]")
    review_parser.add_argument("--confidence", type=float, required=True)
    review_parser.add_argument("--expected-version", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "list":
            result = list_pending()
        elif args.command == "show":
            result = show(args.job_id)
        else:
            findings = json.loads(args.findings_json)
            if not isinstance(findings, list):
                raise TypeError("findings must be a JSON array")
            result = review(
                args.job_id,
                args.decision,
                args.summary,
                findings,
                args.confidence,
                args.expected_version,
            )
    except (RuntimeError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"success": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
