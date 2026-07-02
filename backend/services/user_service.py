"""
UserService — 用户业务逻辑
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.user_repository import UserRepository
from models.v2_models import User


class UserService(BaseService[User, UserRepository]):
    repository: UserRepository
    cache_prefix: str = "user"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = UserRepository()

    def get_by_username(self, username: str) -> Optional[User]:
        cached = self._cache_get("by_username", username)
        if cached is not None:
            return cached
        obj = self.repository.get_by_username(self.db, username)
        if obj:
            self._cache_set(obj.to_dict(), "by_username", username, ttl=300)
        return obj

    def get_by_role(self, role: str, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.get_by_role(self.db, role, skip, limit)

    def get_active_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.get_active_users(self.db, skip, limit)

    def search_by_display_name(self, keyword: str, skip: int = 0, limit: int = 50) -> List[User]:
        return self.repository.search_by_display_name(self.db, keyword, skip, limit)

    def create_user(self, user_data: dict) -> User:
        obj = self.repository.create(self.db, user_data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def deactivate_user(self, user_id: int) -> Optional[User]:
        return self.update(user_id, {"is_active": False})

    def activate_user(self, user_id: int) -> Optional[User]:
        return self.update(user_id, {"is_active": True})
