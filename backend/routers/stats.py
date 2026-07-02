"""
统计汇总 API
GET /api/stats/summary — 返回任务总数、在线设备数、智能体总数
"""
from fastapi import APIRouter
from pydantic import BaseModel
from data_manager import data_manager
from device_manager import device_manager

router = APIRouter(prefix="/api/stats", tags=["stats"])


class SummaryResponse(BaseModel):
    """统计汇总响应"""
    task_count: int
    online_devices: int
    total_agents: int


@router.get("/summary", response_model=SummaryResponse)
def get_stats_summary():
    """统计汇总：任务总数 + 在线设备数 + 智能体总数"""
    # 任务总数（来自 data_manager 的合并任务列表）
    tasks = data_manager.get_merged_tasks()
    task_count = len(tasks)

    # 在线设备数（来自 device_manager）
    devices = device_manager.get_devices()
    online_devices = sum(1 for d in devices if d.get("status") == "online")

    # 智能体总数（来自 data_manager）
    agents = data_manager.get_agents()
    total_agents = len(agents)

    return SummaryResponse(
        task_count=task_count,
        online_devices=online_devices,
        total_agents=total_agents,
    )
