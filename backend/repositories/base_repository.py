from __future__ import annotations
"""
通用基础 Repository — 泛型 CRUD

提供: get_by_id, list, create, update, delete, count, exists
"""
from typing import Generic, TypeVar, Type, Optional, Any, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """泛型基础 Repository"""

    model: Type[T]

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id: Any) -> Optional[T]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def list(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[Any] = None,
        desc: bool = True,
        filters: Optional[dict] = None,
    ) -> Sequence[T]:
        query = self.db.query(self.model)
        if filters:
            for key, value in filters.items():
                if value is not None:
                    query = query.filter(getattr(self.model, key) == value)
        if order_by:
            col = getattr(self.model, order_by, None)
            if col is not None:
                query = query.order_by(col.desc() if desc else col.asc())
        return query.offset(skip).limit(limit).all()

    def create(self, entity: T) -> T:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, entity: T, updates: dict) -> T:
        for key, value in updates.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity: T) -> bool:
        self.db.delete(entity)
        self.db.commit()
        return True

    def count(self, filters: Optional[dict] = None) -> int:
        query = self.db.query(func.count(self.model.id))
        if filters:
            for key, value in filters.items():
                if value is not None:
                    query = query.filter(getattr(self.model, key) == value)
        return query.scalar()

    def exists(self, **filters: Any) -> bool:
        return self.count(filters) > 0
