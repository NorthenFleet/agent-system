#!/usr/bin/env python3
"""Rebuild dirty OpenClaw memory indexes with the working local runtime."""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

from openclaw_memory_extract import MemoryExtractor


def _run(command: list[str], *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*command, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _status(command: list[str]) -> list[dict[str, Any]]:
    result = _run(command, "memory", "status", "--json", timeout=60)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "memory status failed")[-2000:])
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    command = MemoryExtractor.find_openclaw_command()
    if not command:
        raise SystemExit("working OpenClaw runtime not found")

    before = _status(command)
    requested = set(args.agent)
    selected = []
    for item in before:
        agent_id = item.get("agentId")
        status = item.get("status") or {}
        identity = (status.get("custom") or {}).get("indexIdentity") or {}
        needs_rebuild = bool(status.get("dirty")) or identity.get("status") != "valid"
        if requested and agent_id not in requested:
            continue
        if args.all or needs_rebuild:
            selected.append(str(agent_id))

    results = []
    for agent_id in selected:
        run = _run(
            command,
            "memory",
            "index",
            "--force",
            "--agent",
            agent_id,
        )
        results.append(
            {
                "agent_id": agent_id,
                "success": run.returncode == 0,
                "returncode": run.returncode,
                "output": (run.stdout or "")[-500:],
                "error": (run.stderr or "")[-500:],
            }
        )

    after = _status(command)
    remaining = [
        {
            "agent_id": item.get("agentId"),
            "dirty": bool((item.get("status") or {}).get("dirty")),
            "identity": (
                ((item.get("status") or {}).get("custom") or {}).get("indexIdentity") or {}
            ).get("status"),
        }
        for item in after
        if bool((item.get("status") or {}).get("dirty"))
        or (
            ((item.get("status") or {}).get("custom") or {}).get("indexIdentity") or {}
        ).get("status")
        != "valid"
    ]
    payload = {
        "runtime": command,
        "selected": selected,
        "results": results,
        "remaining": remaining,
        "success": all(item["success"] for item in results) and not remaining,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
