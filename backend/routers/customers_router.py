"""
客户管理 API Router — 完整 CRUD + 采购记录管理 + 统计
Dev Spec: customer-management v1.0

API 端点:
  GET    /api/customers                    客户列表（支持筛选）
  GET    /api/customers/stats               统计信息（必须在 /{id} 之前）
  GET    /api/customers/{id}                客户详情
  POST   /api/customers                     创建客户
  PUT    /api/customers/{id}                更新客户
  DELETE /api/customers/{id}                删除客户
  POST   /api/customers/{id}/purchases      添加采购记录
  PUT    /api/customers/{id}/purchases/{pid} 更新采购记录
  DELETE /api/customers/{id}/purchases/{pid} 删除采购记录
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
import uuid
import json
import os
import fcntl

from models.customer import (
    Customer, ContactInfo, PurchaseRecord, CustomerStatus, CustomerType,
    CreateCustomerRequest, UpdateCustomerRequest,
    CreatePurchaseRequest, UpdatePurchaseRequest,
    CustomerStats,
)

router = APIRouter(prefix="/api", tags=["customers"])

# ── 数据文件路径 ──
BASE_DIR = os.path.expanduser("~/WorkSpace/team-dashboard")
CUSTOMERS_FILE = os.path.join(BASE_DIR, "data", "customers.json")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _generate_customer_id() -> str:
    """生成 CUST-XXX 格式 ID"""
    data = _load_data()
    existing_ids = [c["id"] for c in data.get("customers", [])]
    max_num = 0
    for cid in existing_ids:
        try:
            num = int(cid.split("-")[-1])
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            pass
    return f"CUST-{max_num + 1:03d}"


def _generate_purchase_id(customer_purchases: list[dict]) -> str:
    """生成 PUR-XXX 格式 ID"""
    max_num = 0
    for p in customer_purchases:
        try:
            num = int(p["id"].split("-")[-1])
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            pass
    return f"PUR-{max_num + 1:03d}"


# ── 文件锁保护 ──

def _load_data() -> dict:
    """带文件锁的 JSON 加载"""
    if not os.path.exists(CUSTOMERS_FILE):
        return {"customers": [], "last_updated": _now_iso()}
    try:
        with open(CUSTOMERS_FILE, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
                return data
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return {"customers": [], "last_updated": _now_iso()}


def _save_data(data: dict):
    """带文件锁的 JSON 保存（原子写入）"""
    os.makedirs(os.path.dirname(CUSTOMERS_FILE), exist_ok=True)
    tmp_path = CUSTOMERS_FILE + ".tmp"
    data["last_updated"] = _now_iso()
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(tmp_path, CUSTOMERS_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _handle_value_error(e: ValueError) -> HTTPException:
    """将 ValueError 转为 400 HTTPException"""
    return HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════
# ⚠️ 静态路由必须在动态路由之前定义！
# ═══════════════════════════════════════════

# ── 统计（静态路由，必须在 CRUD 之前） ──

@router.get("/customers/stats")
def get_customer_stats(
    period: str = Query(default="all", description="统计周期：all/month/week")
):
    """获取客户统计信息"""
    data = _load_data()
    customers = data.get("customers", [])

    now = datetime.now().astimezone()
    this_month = now.month
    this_year = now.year

    stats = CustomerStats()
    stats.total_customers = len(customers)

    # 按状态分类
    status_counts = {}
    type_counts = {}
    tag_counter = {}
    total_revenue = 0.0
    potential_count = 0
    negotiating_count = 0
    closed_count = 0
    lost_count = 0
    this_month_new = 0
    this_month_revenue = 0.0

    for c in customers:
        status = c.get("status", "potential")
        ctype = c.get("type", "enterprise")

        # 状态计数
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "potential":
            potential_count += 1
        elif status == "negotiating":
            negotiating_count += 1
        elif status == "closed":
            closed_count += 1
        elif status == "lost":
            lost_count += 1

        # 类型计数
        type_counts[ctype] = type_counts.get(ctype, 0) + 1

        # 标签统计
        for tag in c.get("tags", []):
            tag_counter[tag] = tag_counter.get(tag, 0) + 1

        # 采购金额
        for p in c.get("purchases", []):
            total_revenue += p.get("amount", 0)
            # 本月收入
            try:
                p_date = datetime.strptime(p.get("date", ""), "%Y-%m-%d")
                if p_date.month == this_month and p_date.year == this_year:
                    this_month_revenue += p.get("amount", 0)
            except (ValueError, TypeError):
                pass

        # 本月新增
        try:
            created = c.get("created_at", "")
            if created:
                created_dt = datetime.fromisoformat(created)
                if created_dt.month == this_month and created_dt.year == this_year:
                    this_month_new += 1
        except (ValueError, TypeError):
            pass

    stats.total_revenue = round(total_revenue, 2)
    stats.potential_count = potential_count
    stats.negotiating_count = negotiating_count
    stats.closed_count = closed_count
    stats.lost_count = lost_count
    stats.this_month_new = this_month_new
    stats.this_month_revenue = round(this_month_revenue, 2)
    stats.by_status = status_counts
    stats.by_type = type_counts
    stats.top_tags = sorted(
        [{"tag": k, "count": v} for k, v in tag_counter.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    return stats.to_dict()


# ── CRUD ──

@router.get("/customers")
def list_customers(
    status: Optional[str] = Query(default=None, description="状态筛选"),
    type: Optional[str] = Query(default=None, description="类型筛选"),
    tags: Optional[str] = Query(default=None, description="标签筛选，逗号分隔"),
    search: Optional[str] = Query(default=None, description="名称/行业搜索"),
):
    """获取客户列表，支持筛选"""
    data = _load_data()
    customers = data.get("customers", [])

    # 状态筛选
    if status:
        customers = [c for c in customers if c.get("status") == status]

    # 类型筛选
    if type:
        customers = [c for c in customers if c.get("type") == type]

    # 标签筛选
    if tags:
        filter_tags = [t.strip() for t in tags.split(",") if t.strip()]
        customers = [
            c for c in customers
            if any(tag in c.get("tags", []) for tag in filter_tags)
        ]

    # 搜索
    if search:
        search_lower = search.lower()
        customers = [
            c for c in customers
            if search_lower in c.get("name", "").lower()
            or search_lower in c.get("industry", "").lower()
        ]

    return {
        "customers": customers,
        "total": len(customers),
    }


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str):
    """获取客户详情"""
    data = _load_data()
    for c in data.get("customers", []):
        if c["id"] == customer_id:
            return c
    raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")


@router.post("/customers", status_code=201)
def create_customer(req: CreateCustomerRequest):
    """创建新客户"""
    data = _load_data()
    now = _now_iso()

    contact_dict = req.contact.model_dump() if req.contact else ContactInfo().model_dump()

    customer = Customer(
        id=_generate_customer_id(),
        name=req.name,
        type=req.type,
        contact=ContactInfo(**contact_dict),
        industry=req.industry,
        tags=req.tags,
        status=req.status,
        source=req.source,
        avatar_url=req.avatar_url,
        purchases=[],
        notes=req.notes,
        created_at=now,
        updated_at=now,
    )

    customer_dict = customer.to_dict()
    data.setdefault("customers", []).append(customer_dict)
    _save_data(data)

    return customer_dict


@router.put("/customers/{customer_id}")
def update_customer(customer_id: str, req: UpdateCustomerRequest):
    """更新客户信息"""
    data = _load_data()
    now = _now_iso()

    for i, c in enumerate(data.get("customers", [])):
        if c["id"] == customer_id:
            update_fields = req.model_dump(exclude_unset=True)
            for key, value in update_fields.items():
                if value is not None:
                    if key == "contact" and isinstance(value, dict):
                        c["contact"] = value
                    elif key == "tags":
                        c["tags"] = value
                    else:
                        c[key] = value
            c["updated_at"] = now
            data["customers"][i] = c
            _save_data(data)
            return c

    raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str):
    """删除客户"""
    data = _load_data()
    customers = data.get("customers", [])

    for i, c in enumerate(customers):
        if c["id"] == customer_id:
            deleted = customers.pop(i)
            _save_data(data)
            return {
                "ok": True,
                "message": f"客户 {customer_id} 已删除",
                "deleted": deleted,
            }

    raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")


# ── 采购记录 ──

@router.post("/customers/{customer_id}/purchases", status_code=201)
def add_purchase(customer_id: str, req: CreatePurchaseRequest):
    """添加采购记录"""
    data = _load_data()
    now = _now_iso()

    for i, c in enumerate(data.get("customers", [])):
        if c["id"] == customer_id:
            purchases = c.get("purchases", [])
            purchase = {
                "id": _generate_purchase_id(purchases),
                "product_service": req.product_service,
                "amount": req.amount,
                "date": req.date,
                "notes": req.notes,
            }
            purchases.append(purchase)
            c["purchases"] = purchases
            c["updated_at"] = now
            data["customers"][i] = c
            _save_data(data)
            return purchase

    raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")


@router.put("/customers/{customer_id}/purchases/{purchase_id}")
def update_purchase(customer_id: str, purchase_id: str, req: UpdatePurchaseRequest):
    """更新采购记录"""
    data = _load_data()
    now = _now_iso()

    for i, c in enumerate(data.get("customers", [])):
        if c["id"] == customer_id:
            purchases = c.get("purchases", [])
            for j, p in enumerate(purchases):
                if p["id"] == purchase_id:
                    update_fields = req.model_dump(exclude_unset=True)
                    for key, value in update_fields.items():
                        if value is not None:
                            p[key] = value
                    purchases[j] = p
                    c["purchases"] = purchases
                    c["updated_at"] = now
                    data["customers"][i] = c
                    _save_data(data)
                    return p

            raise HTTPException(
                status_code=404,
                detail=f"采购记录 {purchase_id} 不存在",
            )

    raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")


@router.delete("/customers/{customer_id}/purchases/{purchase_id}")
def delete_purchase(customer_id: str, purchase_id: str):
    """删除采购记录"""
    data = _load_data()
    now = _now_iso()

    for i, c in enumerate(data.get("customers", [])):
        if c["id"] == customer_id:
            purchases = c.get("purchases", [])
            for j, p in enumerate(purchases):
                if p["id"] == purchase_id:
                    deleted = purchases.pop(j)
                    c["purchases"] = purchases
                    c["updated_at"] = now
                    data["customers"][i] = c
                    _save_data(data)
                    return {
                        "ok": True,
                        "message": f"采购记录 {purchase_id} 已删除",
                        "deleted": deleted,
                    }

            raise HTTPException(
                status_code=404,
                detail=f"采购记录 {purchase_id} 不存在",
            )

    raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")


# Note: ValueError handling is done inline via try/except where needed.
# exception_handler is only available on FastAPI app, not APIRouter.
