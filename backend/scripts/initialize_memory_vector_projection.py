#!/usr/bin/env python3
"""Validate the migrated projection table (or initialize in legacy DDL mode)."""

from __future__ import annotations

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

from services.memory_vector_service import ApprovedMemoryVectorService  # noqa: E402


def main() -> int:
    service = ApprovedMemoryVectorService()
    result = service.initialize_projection()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("initialized") else 2


if __name__ == "__main__":
    sys.exit(main())
