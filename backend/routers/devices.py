"""
设备管理 API 路由 (Service 层重构版)

所有端点通过 DeviceService 调用，路由层仅负责请求解析和响应构造。
API 路径和请求/响应格式保持不变（前端兼容）。

GET    /api/devices                — 设备列表
GET    /api/devices/stats          — 设备统计
GET    /api/devices/{device_id}    — 设备详情
POST   /api/devices                — 创建设备
PUT    /api/devices/{device_id}    — 更新设备
DELETE /api/devices/{device_id}    — 删除设备

@author 🟥 拉斐尔 (后端开发)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from models.v2_models import get_session, Device
from services.device_service import DeviceService

router = APIRouter(prefix="/api", tags=["devices"])


def get_device_service(db: Session = Depends(get_session)) -> DeviceService:
    """依赖注入：获取 DeviceService 实例"""
    return DeviceService(db)


# ---------- Request Models ----------

class DeviceCreateRequest(BaseModel):
    name: str
    device_type: str = "server"
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "offline"
    os_info: Optional[str] = None
    cpu_cores: Optional[int] = None
    memory_gb: Optional[float] = None
    disk_gb: Optional[float] = None
    tags: List[str] = []


class DeviceUpdateRequest(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    status: Optional[str] = None
    os_info: Optional[str] = None
    cpu_cores: Optional[int] = None
    memory_gb: Optional[float] = None
    disk_gb: Optional[float] = None
    tags: Optional[List[str]] = None


# ---------- Endpoints ----------
# ⚠️ 静态路由（/stats）必须在动态路由（/{device_id}）之前定义！

@router.get("/devices")
def list_devices(
    status: Optional[str] = Query(None, description="按状态筛选"),
    svc: DeviceService = Depends(get_device_service),
):
    """获取所有设备列表"""
    if status:
        devices = [d for d in svc.list() if d.status == status]
    else:
        devices = svc.list()
    return {"devices": [d.to_dict() for d in devices], "total": len(devices)}


@router.get("/devices/stats")
def get_device_stats(
    svc: DeviceService = Depends(get_device_service),
):
    """获取设备统计信息"""
    devices = svc.list()
    total = len(devices)
    online = sum(1 for d in devices if d.status == "online")
    by_type: Dict[str, int] = {}
    for d in devices:
        by_type[d.device_type] = by_type.get(d.device_type, 0) + 1
    return {
        "total": total,
        "online": online,
        "offline": total - online,
        "by_type": by_type,
    }


@router.get("/devices/{device_id}")
def get_device(
    device_id: str,
    svc: DeviceService = Depends(get_device_service),
):
    """获取单个设备详情"""
    # 尝试按 ID 查找
    try:
        device_id_int = int(device_id)
        device = svc.get_by_id(device_id_int)
    except (ValueError, TypeError):
        device = None

    # 如果按 ID 没找到，尝试按名称查找
    if not device:
        device = svc.get_by_name(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device.to_dict()


@router.post("/devices")
def create_device(
    req: DeviceCreateRequest,
    svc: DeviceService = Depends(get_device_service),
):
    """创建设备"""
    device_data = req.model_dump()
    new_device = svc.register_device(device_data)
    return {"message": "Device created", "device": new_device.to_dict()}


@router.put("/devices/{device_id}")
def update_device(
    device_id: str,
    req: DeviceUpdateRequest,
    svc: DeviceService = Depends(get_device_service),
):
    """更新设备信息"""
    updates = req.model_dump(exclude_unset=True)

    # 先查找设备
    try:
        device_id_int = int(device_id)
        device = svc.get_by_id(device_id_int)
    except (ValueError, TypeError):
        device = svc.get_by_name(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    result = svc.update(device.id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device updated", "device_id": device_id, "device": result.to_dict()}


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: str,
    svc: DeviceService = Depends(get_device_service),
):
    """删除设备"""
    # 先查找设备
    try:
        device_id_int = int(device_id)
        device = svc.get_by_id(device_id_int)
    except (ValueError, TypeError):
        device = svc.get_by_name(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    success = svc.delete(device.id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device deleted", "device_id": device_id}
