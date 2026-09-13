#!/usr/bin/env python3
"""Create a disposable DOCX candidate that auto-opens a registered Word add-in."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.word_addin_ooxml_embedder import embed_word_addin  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--addin-id", required=True)
    parser.add_argument("--addin-version", required=True)
    args = parser.parse_args()
    report = embed_word_addin(
        args.source,
        args.output,
        expected_source_sha256=args.expected_source_sha256,
        addin_id=args.addin_id,
        version=args.addin_version,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
