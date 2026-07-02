"""
BaseRepository — 通用 CRUD 封装

所有 Repository 继承此类，提供基础数据库操作。

@task task-005-P3-1
@author 🟥 拉斐尔
"""
from typing import Type, TypeVar, Generic, List, Optional, Dict, Any
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, asc

# Generic model type
ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """通用 CRUD Repository"""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    # ─── 查询 ───

    def get_by_id(self, db: Session, record_id: int) -> Optional[ModelType]:
        """根据 ID 获取单条记录"""
        return db.query(self.model).filter(self.model.id == record_id).first()

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ModelType]:
        """获取分页列表，支持排序和筛选"""
        query = db.query(self.model)

        # 动态筛选
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.filter(getattr(self.model, field) == value)

        # 排序
        if order_by and hasattr(self.model, order_by):
            col = getattr(self.model, order_by)
            query = query.order_by(desc(col) if order_desc else asc(col))

        return query.offset(skip).limit(limit).all()

    def count(
        self,
        db: Session,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """计数"""
        query = db.query(func.count(self.model.id))
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.filter(getattr(self.model, field) == value)
        return query.scalar()

    def search(
        self,
        db: Session,
        search_field: str,
        search_value: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ModelType]:
        """模糊搜索"""
        if not hasattr(self.model, search_field):
            return []
        col = getattr(self.model, search_field)
        return (
            db.query(self.model)
            .filter(col.ilike(f"%{search_value}%"))
            .offset(skip)
            .limit(limit)
            .all()
        )

    # ─── 写入 ───

    def create(self, db: Session, obj_data: Dict[str, Any]) -> ModelType:
        """创建记录"""
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        db.flush()
        return db_obj

    def update(self, db: Session, record_id: int, update_data: Dict[str, Any]) -> Optional[ModelType]:
        """更新记录"""
        obj = self.get_by_id(db, record_id)
        if not obj:
            return None
        for key, value in update_data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        db.flush()
        return obj

    def delete(self, db: Session, record_id: int) -> bool:
        """删除记录"""
        obj = self.get_by_id(db, record_id)
        if not obj:
            return False
        db.delete(obj)
        db.flush()
        return True

    def bulk_create(self, db: Session, objects_data: List[Dict[str, Any]]) -> List[ModelType]:
        """批量创建"""
        objs = [self.model(**data) for data in objects_data]
        db.add_all(objs)
        db.flush()
        return objs

    def bulk_delete(self, db: Session, ids: List[int]) -> int:
        """批量删除，返回删除数量"""
        count = db.query(self.model).filter(self.model.id.in_(ids)).delete(synchronize_session=False)
        db.flush()
        return count

    # ─── 事务 ───

    def transaction(self, db: Session):
        """事务上下文管理器"""
        return db.begin()
