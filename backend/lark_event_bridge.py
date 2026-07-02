#!/usr/bin/env python3
"""Bridge lark-cli event subscription output into the dashboard inbox."""

import argparse
import json
import subprocess
import sys
import urllib.request


def post_event(endpoint: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward Feishu/Lark events to 3021.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:3021/api/v2/lark/events")
    parser.add_argument("--event-types", default="")
    parser.add_argument("--filter", default="")
    args = parser.parse_args()

    cmd = ["lark-cli", "event", "+subscribe", "--compact", "--quiet"]
    if args.event_types:
        cmd.extend(["--event-types", args.event_types])
    if args.filter:
        cmd.extend(["--filter", args.filter])

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            post_event(args.endpoint, json.loads(line))
        except Exception as exc:
            print(f"[lark_event_bridge] forward failed: {exc}; line={line[:500]}", file=sys.stderr)
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
