#!/usr/bin/env python3
"""Audit pinned DOCX gold documents without opening a 3021 workspace."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.docx_gold_baseline import audit_manifest  # noqa: E402


def _write_atomically(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true", help="Exit non-zero when any gold document fails")
    args = parser.parse_args()

    report = audit_manifest(args.manifest)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.verify and report["status"] != "passed":
        for document in report["documents"]:
            if document["status"] != "passed":
                sys.stderr.write(f"{document['id']}: {', '.join(document['errors'])}\n")
        if args.output:
            sys.stderr.write(f"verification failed; baseline not replaced: {args.output}\n")
        else:
            sys.stdout.write(payload)
        return 1
    if args.output:
        _write_atomically(args.output, payload)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
