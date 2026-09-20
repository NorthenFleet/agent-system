#!/usr/bin/env python3
"""Run a dedicated Command Center worker without starting another HTTP app."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(WORKSPACE_ROOT / ".env", override=False)

from services.command_center_worker import (  # noqa: E402
    command_center_worker,
    stop_command_center_worker,
)


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signame, stop_event.set)
    command_center_worker.start()
    try:
        await stop_event.wait()
    finally:
        await stop_command_center_worker()


if __name__ == "__main__":
    asyncio.run(main())
