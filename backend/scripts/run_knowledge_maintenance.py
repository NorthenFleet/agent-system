"""Explicit one-shot entry point for an operator's existing scheduler."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', required=True)
    parser.parse_args()
    from services.knowledge.runtime import get_service, require_enabled
    from services.knowledge.operations import run_scheduled_once
    from services.work_run_service import work_run_service
    require_enabled(write=True)
    print({'configured_spaces_processed': run_scheduled_once(get_service(), work_run_service)})


if __name__ == '__main__':
    main()
