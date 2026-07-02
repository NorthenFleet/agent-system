"""
工具状态与健康检查 API — 🟪 多纳泰罗
列出后端已注册的路由模块、可用端点概览和运行状态。
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import time


class ToolInfo(BaseModel):
    name: str
    path: str
    size: int
    has_router: bool


class BackendStatus(BaseModel):
    uptime_seconds: int
    start_time: str
    python_version: str
    cwd: str


class ToolsStatusResponse(BaseModel):
    backend_status: BackendStatus
    available_tools: List[ToolInfo]
    total_modules: int
    timestamp: str


# 记录后端启动时间
_start_time = datetime.now()
_boot_timestamp = _start_time.isoformat()


router = APIRouter(prefix="/api/tools", tags=["tools"])


def _scan_routers() -> List[ToolInfo]:
    """扫描 routers/ 目录，推断可用工具模块"""
    routers_dir = os.path.dirname(__file__)
    tools: List[ToolInfo] = []
    for fname in sorted(os.listdir(routers_dir)):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        fpath = os.path.join(routers_dir, fname)
        module_name = fname.replace(".py", "")
        has_router = False
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
            has_router = "APIRouter" in content or "router" in content
        tools.append(ToolInfo(
            name=module_name,
            path=fpath,
            size=os.path.getsize(fpath),
            has_router=has_router,
        ))
    return tools


@router.get("/status", response_model=ToolsStatusResponse)
def get_tools_status():
    """获取后端工具列表、运行状态和当前时间"""
    now = datetime.now()
    uptime = int((now - _start_time).total_seconds())

    try:
        import sys
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    except Exception:
        py_ver = "unknown"

    return ToolsStatusResponse(
        backend_status=BackendStatus(
            uptime_seconds=uptime,
            start_time=_boot_timestamp,
            python_version=py_ver,
            cwd=os.getcwd(),
        ),
        available_tools=_scan_routers(),
        total_modules=len(os.listdir(os.path.dirname(__file__))) - 1,  # exclude __pycache__
        timestamp=now.isoformat(),
    )
