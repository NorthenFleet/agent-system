from __future__ import annotations
"""
V2 任务模板 API 路由 — 通过 TemplateService 层
集成 Redis 缓存（Sprint 5 P4）。

GET    /api/v2/templates              模板列表（分页/分类筛选）
POST   /api/v2/templates              创建模板（Admin）
GET    /api/v2/templates/{id}         模板详情
PUT    /api/v2/templates/{id}         更新模板（Admin）
DELETE /api/v2/templates/{id}         删除模板（Admin）
POST   /api/v2/templates/{id}/create-task  从模板创建任务
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from services.template_service import TemplateService
from services.auth_service import require_role
from services.cache_service import cache_service
from database import get_db

router = APIRouter(prefix="/api/v2/templates", tags=["v2-templates"])


def get_template_service(db=Depends(get_db)) -> TemplateService:
    """依赖注入：创建 TemplateService"""
    return TemplateService(db)


@router.get("")
def list_templates(
    category: Optional[str] = Query(
        None, description="模板分类筛选"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: TemplateService = Depends(get_template_service),
):
    """模板列表，支持 category 筛选和分页"""
    cache_key = f"v2:templates:list:{category}:{page}:{page_size}"
    cached = cache_service.get(cache_key)
    if cached is not None:
        return cached

    templates, total = service.list_templates(
        category=category, page=page, page_size=page_size
    )
    result = {
        "templates": [t.to_dict() for t in templates],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }
    cache_service.set(cache_key, result, ttl=300)
    return result


@router.post("", status_code=201)
def create_template(
    body: dict,
    user: dict = Depends(require_role("admin")),
    service: TemplateService = Depends(get_template_service),
):
    """创建新模板，需 Admin 角色"""
    if not body.get("name"):
        raise HTTPException(400, "name 字段必填")
    if not body.get("template_data"):
        raise HTTPException(400, "template_data 字段必填")

    template = service.create_template(
        name=body["name"],
        template_data=body["template_data"],
        description=body.get("description", ""),
        category=body.get("category", ""),
        is_system=body.get("is_system", False),
        created_by=user.get("id"),
    )
    cache_service.invalidate_pattern("v2:templates:*")
    return template.to_dict()


@router.get("/{template_id}")
def get_template(
    template_id: int,
    service: TemplateService = Depends(get_template_service),
):
    """获取模板详情"""
    template = service.get_template(template_id)
    if not template:
        raise HTTPException(404, "模板不存在")
    return template.to_dict()


@router.put("/{template_id}")
def update_template(
    template_id: int,
    body: dict,
    user: dict = Depends(require_role("admin")),
    service: TemplateService = Depends(get_template_service),
):
    """更新模板，需 Admin 角色"""
    allowed = {
        "name", "description", "template_data",
        "category", "is_system",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "无可更新字段")

    template = service.update_template(template_id, updates)
    if not template:
        raise HTTPException(404, "模板不存在")
    cache_service.invalidate_pattern("v2:templates:*")
    return template.to_dict()


@router.delete("/{template_id}")
def delete_template(
    template_id: int,
    user: dict = Depends(require_role("admin")),
    service: TemplateService = Depends(get_template_service),
):
    """删除模板（系统模板不可删），需 Admin 角色"""
    success, message = service.delete_template(template_id)
    if not success:
        if template_id and service.get_template(template_id) is None:
            raise HTTPException(404, message)
        raise HTTPException(403, message)
    cache_service.invalidate_pattern("v2:templates:*")
    return {"message": message, "template_id": template_id}


@router.post("/{template_id}/create-task", status_code=201)
def create_task_from_template(
    template_id: int,
    body: Optional[dict] = None,
    service: TemplateService = Depends(get_template_service),
):
    """从模板创建任务：读取 template_data 作为默认值 + overrides 覆盖"""
    overrides = body.get("overrides", {}) if body else {}
    task = service.create_task_from_template(
        template_id, overrides=overrides or None
    )
    if not task:
        raise HTTPException(404, "模板不存在")
    return task
