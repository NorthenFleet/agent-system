"""
ProductDependency Repository — 产品依赖表数据访问
"""
from typing import List
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import ProductDependency


class ProductDependencyRepository(BaseRepository[ProductDependency]):
    def __init__(self):
        super().__init__(ProductDependency)

    def get_by_product(self, db: Session, product_id: int) -> List[ProductDependency]:
        return (
            db.query(ProductDependency)
            .filter(
                (ProductDependency.from_product_id == product_id) |
                (ProductDependency.to_product_id == product_id)
            )
            .all()
        )

    def get_dependencies(self, db: Session) -> List[ProductDependency]:
        return db.query(ProductDependency).all()

    def get_by_from_product(self, db: Session, from_product_id: int) -> List[ProductDependency]:
        return (
            db.query(ProductDependency)
            .filter(ProductDependency.from_product_id == from_product_id)
            .all()
        )

    def get_by_to_product(self, db: Session, to_product_id: int) -> List[ProductDependency]:
        return (
            db.query(ProductDependency)
            .filter(ProductDependency.to_product_id == to_product_id)
            .all()
        )
