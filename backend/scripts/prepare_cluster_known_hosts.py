"""Copy only ALREADY trusted enrolled host entries, never learn a new SSH key."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from services.cluster_collector import collection_target, discover, validate_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=BACKEND / "config/cluster_nodes.json")
    args = parser.parse_args()
    config = validate_config(json.loads(args.config.read_text()))
    status = discover(os.getenv("CLUSTER_TAILSCALE_BINARY", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"))
    source = Path.home() / ".ssh/known_hosts"
    lines, receipts = [], []
    for node in config["nodes"]:
        if node.get("collector", {}).get("transport") != "ssh":
            continue
        address = collection_target(node, status)
        if not address:
            continue
        result = subprocess.run(["/usr/bin/ssh-keygen", "-F", address, "-f", str(source)],
                                capture_output=True, text=True, timeout=5)
        entries = [line for line in result.stdout.splitlines() if line and not line.startswith("#")]
        lines.extend(entries)
        receipts.append({"node_id": node["node_id"], "existing_trusted_entries": len(entries)})
    if not lines:
        raise SystemExit("no_existing_trusted_entries")
    # Exclusive creation: changing trust later requires an explicit reviewed action.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write("\n".join(dict.fromkeys(lines)) + "\n")
    print(json.dumps({"known_hosts": str(args.output), "nodes": receipts}))


if __name__ == "__main__":
    main()
