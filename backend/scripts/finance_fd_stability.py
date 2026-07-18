#!/usr/bin/env python3
"""Refresh a URL repeatedly and assert the serving process does not leak FDs."""
from __future__ import annotations

import argparse
import subprocess
import time
import urllib.request


def pid_for_port(port: int) -> int:
    output = subprocess.check_output(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], text=True).strip().splitlines()
    if not output:
        raise RuntimeError(f"port {port} has no listener")
    return int(output[0])


def fd_count(pid: int) -> int:
    output = subprocess.check_output(["lsof", "-n", "-p", str(pid)], text=True)
    return max(0, len(output.splitlines()) - 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:3021/finance")
    parser.add_argument("--ready-url", default="http://127.0.0.1:3021/health/live")
    parser.add_argument("--port", type=int, default=3021)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--max-growth", type=int, default=10)
    args = parser.parse_args()

    pid = pid_for_port(args.port)
    before = fd_count(pid)
    failures = 0
    started = time.monotonic()
    for _ in range(args.requests):
        try:
            with urllib.request.urlopen(args.url, timeout=5) as response:
                if response.status >= 500:
                    failures += 1
                response.read()
            with urllib.request.urlopen(args.ready_url, timeout=5) as response:
                if response.status >= 500:
                    failures += 1
                response.read()
        except Exception:
            failures += 1
    after = fd_count(pid)
    growth = after - before
    elapsed = time.monotonic() - started
    print(f"pid={pid} requests={args.requests} failures={failures} fd_before={before} fd_after={after} growth={growth} elapsed={elapsed:.2f}s")
    if failures or growth > args.max_growth:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
