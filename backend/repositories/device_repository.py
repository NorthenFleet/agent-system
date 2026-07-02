"""
Device Repository — 设备表数据访问
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import Device


class DeviceRepository(BaseRepository[Device]):
    def __init__(self):
        super().__init__(Device)

    def get_by_name(self, db: Session, name: str) -> Optional[Device]:
        return db.query(Device).filter(Device.name == name).first()

    def get_online_devices(self, db: Session) -> List[Device]:
        return db.query(Device).filter(Device.status == "online").all()

    def get_offline_devices(self, db: Session) -> List[Device]:
        return db.query(Device).filter(Device.status == "offline").all()

    def get_by_type(self, db: Session, device_type: str, skip: int = 0, limit: int = 100) -> List[Device]:
        return db.query(Device).filter(Device.device_type == device_type).offset(skip).limit(limit).all()
