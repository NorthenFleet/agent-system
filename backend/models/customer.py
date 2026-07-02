"""
客户管理数据模型 (CRM)
Dev Spec: customer-management v1.0
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class CustomerType(str, Enum):
    enterprise = "enterprise"
    individual = "individual"
    research = "research"
    commercial = "commercial"


class CustomerStatus(str, Enum):
    potential = "potential"
    negotiating = "negotiating"
    closed = "closed"
    lost = "lost"


class ContactInfo(BaseModel):
    """联系人信息"""
    name: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=200)
    wechat: str = Field(default="", max_length=100)


class PurchaseRecord(BaseModel):
    """采购记录"""
    id: str
    product_service: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., ge=0, description="金额，不可为负")
    date: str = Field(..., description="日期，格式 YYYY-MM-DD")
    notes: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        return v

    @field_validator("product_service")
    @classmethod
    def product_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("商品/服务名称不能为空")
        return v.strip()


class Customer(BaseModel):
    """客户完整定义"""
    id: str
    name: str = Field(..., min_length=1, max_length=200)
    type: CustomerType
    contact: ContactInfo = Field(default_factory=ContactInfo)
    industry: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list)
    status: CustomerStatus = CustomerStatus.potential
    source: str = Field(default="", max_length=100)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    purchases: list[PurchaseRecord] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)
    created_at: str = Field(default="")
    updated_at: str = Field(default="")

    model_config = {"use_enum_values": True}

    def to_dict(self) -> dict:
        return self.model_dump()

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("客户名称不能为空")
        return v.strip()

    @property
    def total_purchase_amount(self) -> float:
        """累计采购金额"""
        return sum(p.amount for p in self.purchases)

    @property
    def tags_display(self) -> str:
        """标签显示用字符串"""
        return ", ".join(self.tags) if self.tags else ""


# ── Request Models ──

class CreateCustomerRequest(BaseModel):
    """创建客户请求"""
    name: str = Field(..., min_length=1, max_length=200, description="客户名称")
    type: CustomerType
    contact: Optional[ContactInfo] = None
    industry: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list)
    status: CustomerStatus = CustomerStatus.potential
    source: str = Field(default="", max_length=100)
    avatar_url: Optional[str] = None
    notes: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("客户名称不能为空")
        return v.strip()


class UpdateCustomerRequest(BaseModel):
    """更新客户请求"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[CustomerType] = None
    contact: Optional[ContactInfo] = None
    industry: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[list[str]] = None
    status: Optional[CustomerStatus] = None
    source: Optional[str] = Field(default=None, max_length=100)
    avatar_url: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class CreatePurchaseRequest(BaseModel):
    """添加采购记录请求"""
    product_service: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., ge=0, description="金额，不可为负")
    date: str = Field(..., description="日期，格式 YYYY-MM-DD")
    notes: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        return v

    @field_validator("product_service")
    @classmethod
    def product_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("商品/服务名称不能为空")
        return v.strip()


class UpdatePurchaseRequest(BaseModel):
    """更新采购记录请求"""
    product_service: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[float] = Field(default=None, ge=0)
    date: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class CustomerStats(BaseModel):
    """客户统计信息"""
    total_customers: int = 0
    total_revenue: float = 0.0
    potential_count: int = 0
    negotiating_count: int = 0
    closed_count: int = 0
    lost_count: int = 0
    this_month_new: int = 0
    this_month_revenue: float = 0.0
    by_type: dict = Field(default_factory=dict)
    by_status: dict = Field(default_factory=dict)
    top_tags: list[dict] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()
