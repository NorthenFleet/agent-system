"""
ProductService — 产品业务逻辑
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from services.base import BaseService, Cache
from repositories.product_repository import ProductRepository
from repositories.product_dependency_repository import ProductDependencyRepository
from models.v2_models import Product


class ProductService(BaseService[Product, ProductRepository]):
    repository: ProductRepository
    cache_prefix: str = "product"

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        super().__init__(db, cache)
        self.repository = ProductRepository()
        self._dep_repo = ProductDependencyRepository()

    def get_by_name(self, name: str) -> Optional[Product]:
        return self.repository.get_by_name(self.db, name)

    def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Product]:
        return self.repository.get_by_status(self.db, status, skip, limit)

    def get_in_progress(self) -> List[Product]:
        return self.repository.get_in_progress(self.db)

    def get_by_owner(self, owner: str, skip: int = 0, limit: int = 100) -> List[Product]:
        return self.repository.get_by_owner(self.db, owner, skip, limit)

    def create_product(self, product_data: Dict[str, Any]) -> Product:
        obj = self.repository.create(self.db, product_data)
        self.db.commit()
        self._cache_invalidate_prefix()
        return obj

    def update_progress(self, product_id: int, progress: int) -> Optional[Product]:
        return self.update(product_id, {"progress": progress})

    # ─── 依赖关系 ───

    def get_dependencies(self, product_id: int) -> List[Any]:
        return self._dep_repo.get_by_product(self.db, product_id)

    def add_dependency(self, from_product_id: int, to_product_id: int,
                       dependency_type: str = "blocks", description: str = "") -> Any:
        dep = self._dep_repo.create(self.db, {
            "from_product_id": from_product_id,
            "to_product_id": to_product_id,
            "dependency_type": dependency_type,
            "description": description,
        })
        self.db.commit()
        return dep

    def remove_dependency(self, dep_id: int) -> bool:
        result = self._dep_repo.delete(self.db, dep_id)
        if result:
            self.db.commit()
        return result

    def get_all_dependencies(self) -> List[Any]:
        return self._dep_repo.get_dependencies(self.db)
