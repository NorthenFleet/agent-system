"""One explicitly enabled projection step, usable by the existing scheduler."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', required=True)
    parser.parse_args()
    from services.knowledge.runtime import get_projection, require_enabled
    require_enabled(write=True)
    print({'processed': get_projection().run_once()})


if __name__ == '__main__':
    main()
