"""Operator-only private logical backup/verification; never restores live data."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['capture', 'verify', 'revocations'])
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    from services.knowledge import backup
    if args.operation == 'verify':
        manifest, _ = backup.verify(args.destination)
        report = {'verified': True, 'captured_at': manifest['captured_at'], 'bytes': manifest['bytes']}
    else:
        from services.knowledge.runtime import require_enabled, get_service
        require_enabled()
        result = getattr(backup, args.operation)(get_service(), args.destination)
        report = {'completed': True, 'captured_at': result['captured_at']}
    print(json.dumps(report))


if __name__ == '__main__':
    main()
