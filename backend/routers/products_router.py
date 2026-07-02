"""
产品矩阵 API 路由
GET /api/v2/products — 返回 products.json 数据

@autor 🟥 拉斐尔
@task task-006-P1-1
"""
import json
import os
from fastapi import APIRouter

router = APIRouter(prefix="/api/v2/products", tags=["products"])

PRODUCTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "products.json")


@router.get("")
def get_products():
    """读取 products.json 并返回产品矩阵数据"""
    if not os.path.exists(PRODUCTS_FILE):
        return {"products": [], "progression": []}
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data
