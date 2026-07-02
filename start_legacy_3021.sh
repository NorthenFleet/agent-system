#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
PORT=3021
PID_FILE="/tmp/team-dashboard-legacy-3021.pid"
LOG_FILE="$BACKEND_DIR/backend-legacy-3021.log"
DISABLE_SCHEDULER="${DISABLE_SCHEDULER:-true}"

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
  kill -9 $(lsof -Pi :$PORT -sTCP:LISTEN -t) 2>/dev/null || true
fi

cd "$BACKEND_DIR"
USE_FRONTEND_V2=false FRONTEND_ENTRY=index-old.html API_PORT=$PORT DISABLE_SCHEDULER="$DISABLE_SCHEDULER" \
  nohup ./venv/bin/uvicorn main_slim_v2:app --host 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
sleep 2
curl -fsS "http://localhost:$PORT/health"
