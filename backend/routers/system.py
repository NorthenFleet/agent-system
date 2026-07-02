from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
import platform
import subprocess
import time
import sys

router = APIRouter(prefix="/api/system", tags=["system"])

# 启动时间戳（秒级 Unix 时间戳）
START_TIME = time.time()


class SystemInfo(BaseModel):
    python_version: str
    git_commit: str
    server_start_time: str
    current_time: str
    os_info: str
    uptime_seconds: float


def _get_git_commit() -> str:
    """获取项目最近一次 Git commit hash"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=".",
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _format_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


@router.get("/info", response_model=SystemInfo)
def get_system_info():
    return SystemInfo(
        python_version=platform.python_version(),
        git_commit=_get_git_commit(),
        server_start_time=_format_timestamp(START_TIME),
        current_time=_format_timestamp(time.time()),
        os_info=f"{platform.system()} {platform.release()} ({platform.machine()})",
        uptime_seconds=round(time.time() - START_TIME, 2),
    )
