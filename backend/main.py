"""Compatibility entrypoint for tests and legacy commands.

The production 3021 service is implemented in main_slim_v2.py. Keep this file
as a thin alias so imports such as `from main import app` exercise the current
application instead of a stale 3020 implementation.
"""
from __future__ import annotations

import os

from main_slim_v2 import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", os.getenv("PORT", "3021"))),
    )
