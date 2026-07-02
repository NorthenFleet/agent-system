"""
DeviceService — 设备业务逻辑
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.device_repository import DeviceRepository
from models.v2_models import Device


class DeviceService(BaseService[Device, DeviceRepository]):
    repository: DeviceRepository
    cache_prefix: str = "device"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = DeviceRepository()

    def get_by_name(self, name: str) -> Optional[Device]:
        return self.repository.get_by_name(self.db, name)

    def get_online_devices(self) -> List[Device]:
        return self.repository.get_online_devices(self.db)

    def get_offline_devices(self) -> List[Device]:
        return self.repository.get_offline_devices(self.db)

    def get_by_type(self, device_type: str, skip: int = 0, limit: int = 100) -> List[Device]:
        return self.repository.get_by_type(self.db, device_type, skip, limit)

    def register_device(self, device_data: Dict[str, Any]) -> Device:
        obj = self.repository.create(self.db, device_data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def update_status(self, device_id: int, new_status: str) -> Optional[Device]:
        obj = self.repository.update(self.db, device_id, {
            "status": new_status,
            "last_seen_at": datetime.now(timezone.utc),
        })
        if obj:
            self.db.commit()
            self._cache_invalidate(str(device_id))
            self._cache_invalidate_prefix("status")
        return obj

    def heartbeat(self, device_id: int) -> Optional[Device]:
        return self.update_status(device_id, "online")

    def mark_offline(self, device_id: int) -> Optional[Device]:
        return self.update_status(device_id, "offline")
