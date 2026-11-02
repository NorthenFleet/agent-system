#!/bin/zsh
# 3021 后端启动脚本（launchctl submit 用）
# 复刻 ai.openclaw.agent-system-3021.plist 的启动逻辑
set -e
cd "/Users/apple/工作桌面/Workspace/agent-system/backend"

export AGENT_SYSTEM_ENV_FILE="../.env"
export AGENT_SYSTEM_RUNTIME_KIND="launchd"

set -a
source "$AGENT_SYSTEM_ENV_FILE"
set +a

if [[ -r "./data/genoffice-runtime.env" && ! -L "./data/genoffice-runtime.env" ]]; then
  set -a
  source "./data/genoffice-runtime.env"
  set +a
fi

export DASHBOARD_JWT_SECRET="$(<data/.dashboard_jwt_secret)"

exec ./venv/bin/uvicorn main_slim_v2:app --host 0.0.0.0 --port 3021
