#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[WARN] start_legacy_3021.sh is deprecated; delegating to ./start.sh on port 3021."
API_PORT="${API_PORT:-3021}" USE_FRONTEND_V2="${USE_FRONTEND_V2:-true}" DISABLE_SCHEDULER="${DISABLE_SCHEDULER:-false}" \
  "$SCRIPT_DIR/start.sh" "${1:-start}"
