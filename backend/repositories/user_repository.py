"""
User Repository — 用户表数据访问
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import User


class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get_by_role(self, db: Session, role: str, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).filter(User.role == role).offset(skip).limit(limit).all()

    def get_active_users(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).filter(User.is_active == True).offset(skip).limit(limit).all()

    def get_inactive_users(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).filter(User.is_active == False).offset(skip).limit(limit).all()

    def search_by_display_name(self, db: Session, keyword: str, skip: int = 0, limit: int = 50) -> List[User]:
        return (
            db.query(User)
            .filter(User.display_name.ilike(f"%{keyword}%"))
            .offset(skip)
            .limit(limit)
            .all()
        )
