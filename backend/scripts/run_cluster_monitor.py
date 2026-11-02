"""Run the separate, single-owner read-only collector; never in an HTTP request."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import threading

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(BACKEND / "config/cluster_nodes.json"))
    parser.add_argument("--register", action="store_true", help="Explicitly enroll/update declared identities then exit")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    from database import SessionLocal
    from services.cluster_collector import collect_cycle, validate_config
    from services.cluster_inventory_service import ClusterInventoryService

    config = validate_config(json.loads(Path(args.config).read_text()))
    # A stable lock inode, not PID-file cleanup; second workers exit safely.
    lock_path = Path(os.getenv("CLUSTER_MONITOR_LOCK_PATH", str(BACKEND / "data/cluster-monitor.lock")))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("cluster_monitor_already_running")
        if args.register:
            with SessionLocal() as db:
                service = ClusterInventoryService(db)
                for node in config["nodes"]:
                    service.register_node({key: value for key, value in node.items() if key not in {"collector", "services"}})
                db.commit()
            print(json.dumps({"registered": len(config["nodes"])}))
            return
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        binary = os.getenv("CLUSTER_TAILSCALE_BINARY", "/Applications/Tailscale.app/Contents/MacOS/Tailscale")
        while not stop.is_set():
            try:
                receipt = collect_cycle(config, tailscale_binary=binary, session_factory=SessionLocal)
                print(json.dumps(receipt), flush=True)
            except Exception as exc:
                print(json.dumps({"state": "error", "error_type": type(exc).__name__}), flush=True)
                if args.once:
                    raise SystemExit(1)
            if args.once:
                break
            stop.wait(max(15, args.interval))


if __name__ == "__main__":
    main()
