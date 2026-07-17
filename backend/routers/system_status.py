"""
系统状态聚合 API
GET /api/system/status — 返回运行时间、节点在线状态、内存/磁盘用量、智能体在线统计
"""
from fastapi import APIRouter
from pydantic import BaseModel
import time
import shutil

from data_manager import data_manager
from device_manager import device_manager

router = APIRouter(prefix="/api/system", tags=["system"])
START_TIME = time.time()


class NodeStatus(BaseModel):
    """单个节点/设备状态"""
    id: str
    name: str
    status: str  # online / offline
    ip: str


class MemoryInfo(BaseModel):
    """内存用量信息"""
    total_mb: float
    used_mb: float
    available_mb: float
    usage_percent: float


class DiskInfo(BaseModel):
    """磁盘用量信息"""
    total_gb: float
    used_gb: float
    free_gb: float
    usage_percent: float


class AgentSummary(BaseModel):
    """智能体在线统计"""
    total: int
    online: int
    busy: int
    idle: int
    offline: int
    unknown: int = 0


class SystemStatusResponse(BaseModel):
    """系统状态聚合响应"""
    uptime_seconds: float
    nodes: list[NodeStatus]
    online_nodes: int
    total_nodes: int
    memory: MemoryInfo
    disk: DiskInfo
    agents: AgentSummary


def _get_memory_info() -> MemoryInfo:
    """获取内存使用信息（macOS / Linux）"""
    try:
        import platform
        system = platform.system()
        if system == "Darwin":
            import subprocess
            # macOS: vm_stat gives pages, page size = 4096
            result = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=5
            )
            page_size = 4096
            pages = {}
            for line in result.stdout.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip().rstrip(".")
                    try:
                        pages[key.strip()] = int(val)
                    except ValueError:
                        pass

            total_pages = (
                pages.get("Pages active", 0)
                + pages.get("Pages inactive", 0)
                + pages.get("Pages speculative", 0)
                + pages.get("Pages wired down", 0)
                + pages.get("Pages purgeable", 0)
                + pages.get("Pages free", 0)
            )
            total_mb = round(total_pages * page_size / (1024 * 1024), 1)
            used_pages = pages.get("Pages active", 0) + pages.get("Pages wired down", 0)
            used_mb = round(used_pages * page_size / (1024 * 1024), 1)
            available_mb = round((total_pages - used_pages) * page_size / (1024 * 1024), 1)
            usage_percent = round((used_pages / total_pages) * 100, 1) if total_pages else 0
        else:
            # Linux: /proc/meminfo
            meminfo = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            used_kb = total_kb - avail_kb
            total_mb = round(total_kb / 1024, 1)
            used_mb = round(used_kb / 1024, 1)
            available_mb = round(avail_kb / 1024, 1)
            usage_percent = round((used_kb / total_kb) * 100, 1) if total_kb else 0
        return MemoryInfo(
            total_mb=total_mb,
            used_mb=used_mb,
            available_mb=available_mb,
            usage_percent=usage_percent,
        )
    except Exception:
        return MemoryInfo(total_mb=0, used_mb=0, available_mb=0, usage_percent=0)


def _get_disk_info(path: str = "/") -> DiskInfo:
    """获取磁盘使用信息"""
    try:
        usage = shutil.disk_usage(path)
        total_gb = round(usage.total / (1024 ** 3), 1)
        used_gb = round(usage.used / (1024 ** 3), 1)
        free_gb = round(usage.free / (1024 ** 3), 1)
        usage_percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0
        return DiskInfo(
            total_gb=total_gb,
            used_gb=used_gb,
            free_gb=free_gb,
            usage_percent=usage_percent,
        )
    except Exception:
        return DiskInfo(total_gb=0, used_gb=0, free_gb=0, usage_percent=0)


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status() -> SystemStatusResponse:
    """聚合系统状态：运行时间、节点在线数、内存/磁盘用量、智能体在线统计"""
    # 运行时间
    uptime_seconds = round(time.time() - START_TIME, 2)

    # 节点/设备状态
    devices = device_manager.get_devices()
    nodes = []
    online_count = 0
    for d in devices:
        status = d.get("status", "offline")
        if status == "online":
            online_count += 1
        nodes.append(NodeStatus(
            id=d.get("id", ""),
            name=d.get("name", ""),
            status=status,
            ip=d.get("ip", ""),
        ))

    # 智能体统计
    agents = data_manager.get_agents()
    agent_statuses = [a.get("status") for a in agents]
    total_agents = len(agents)
    online_agents = agent_statuses.count("online")
    busy_agents = agent_statuses.count("busy")
    idle_agents = agent_statuses.count("idle")
    offline_agents = agent_statuses.count("offline")
    unknown_agents = total_agents - online_agents - busy_agents - idle_agents - offline_agents

    return SystemStatusResponse(
        uptime_seconds=uptime_seconds,
        nodes=nodes,
        online_nodes=online_count,
        total_nodes=len(devices),
        memory=_get_memory_info(),
        disk=_get_disk_info(),
        agents=AgentSummary(
            total=total_agents,
            online=online_agents,
            busy=busy_agents,
            idle=idle_agents,
            offline=offline_agents,
            unknown=unknown_agents,
        ),
    )
