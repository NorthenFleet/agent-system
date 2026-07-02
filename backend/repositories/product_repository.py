"""
Product Repository — 产品表数据访问
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import Product


class ProductRepository(BaseRepository[Product]):
    def __init__(self):
        super().__init__(Product)

    def get_by_name(self, db: Session, name: str) -> Optional[Product]:
        return db.query(Product).filter(Product.name == name).first()

    def get_by_status(self, db: Session, status: str, skip: int = 0, limit: int = 100) -> List[Product]:
        return db.query(Product).filter(Product.status == status).offset(skip).limit(limit).all()

    def get_in_progress(self, db: Session) -> List[Product]:
        return db.query(Product).filter(Product.status == "in-progress").all()

    def get_by_owner(self, db: Session, owner: str, skip: int = 0, limit: int = 100) -> List[Product]:
        return db.query(Product).filter(Product.owner == owner).offset(skip).limit(limit).all()
