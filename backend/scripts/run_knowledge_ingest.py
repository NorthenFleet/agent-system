"""Run one durable knowledge job; invoke with the existing scheduler.

Usage: python scripts/run_knowledge_ingest.py --once
No environment file is silently loaded and no schema is created here.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args()
    from services.knowledge.runtime import require_enabled, get_service
    from services.knowledge.worker import run_once
    require_enabled(write=True)
    service = get_service()
    from services.work_run_service import work_run_service
    print({"processed": run_once(service, work_run_service)})


if __name__ == "__main__":
    main()
