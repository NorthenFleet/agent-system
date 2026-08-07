"""Resolve the OpenClaw CLI without depending on an interactive shell PATH."""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path


DEFAULT_NODE = Path("/opt/homebrew/opt/node@22/bin/node")
DEFAULT_OPENCLAW_SCRIPT = Path(
    "/opt/homebrew/opt/node/lib/node_modules/@qingchencloud/openclaw-zh/dist/index.js"
)


def openclaw_command(*args: str) -> list[str]:
    configured = os.getenv("OPENCLAW_BIN", "").strip()
    if configured:
        prefix = shlex.split(configured)
    elif DEFAULT_NODE.is_file() and DEFAULT_OPENCLAW_SCRIPT.is_file():
        prefix = [str(DEFAULT_NODE), str(DEFAULT_OPENCLAW_SCRIPT)]
    else:
        executable = shutil.which("openclaw")
        if executable:
            prefix = [executable]
        else:
            prefix = ["openclaw"]
    return [*prefix, *args]
