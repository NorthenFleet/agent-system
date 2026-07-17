from __future__ import annotations
"""
V2 通知中心 API 路由 — 通过 NotificationService 层 + WebSocket 推送

⚠️ 静态路径必须在动态路径 {notification_id} 之前注册，
  否则 FastAPI 会将 "unread-count"/"read-all" 解析为 int 参数 → 422。

GET    /api/v2/notifications              通知列表（分页/筛选）
POST   /api/v2/notifications              创建通知（Admin/System）
GET    /api/v2/notifications/unread-count  未读计数
PUT    /api/v2/notifications/read-all     全部已读
GET    /api/v2/notifications/{id}         通知详情
PUT    /api/v2/notifications/{id}/read    标记已读
DELETE /api/v2/notifications/{id}         删除通知
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime

from services.notification_service import NotificationService
from services.auth_service import require_role, get_current_user
from database import get_db

router = APIRouter(prefix="/api/v2/notifications", tags=["v2-notifications"])


def get_notification_service(db=Depends(get_db)) -> NotificationService:
    """依赖注入：创建 NotificationService"""
    return NotificationService(db)


# ── 静态路径（必须在动态路径之前注册） ──

@router.get("")
def list_notifications(
    type: Optional[str] = Query(
        None, description="筛选通知类型: system/task/alert/mention"
    ),
    is_read: Optional[bool] = Query(
        None, description="筛选已读状态"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """当前用户通知列表，支持类型/已读状态筛选 + 分页"""
    user_id = user.get("id")
    notifications, total = service.get_user_notifications(
        user_id=user_id,
        type=type,
        is_read=is_read,
        page=page,
        page_size=page_size,
    )
    return {
        "notifications": [n.to_dict() for n in notifications],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("", status_code=201)
def create_notification(
    body: dict,
    user: dict = Depends(require_role("admin")),
    service: NotificationService = Depends(get_notification_service),
):
    """创建通知（系统/管理员），需 Admin 角色"""
    if not body.get("user_id"):
        raise HTTPException(400, "user_id 字段必填")
    if not body.get("type"):
        raise HTTPException(400, "type 字段必填")
    if not body.get("title"):
        raise HTTPException(400, "title 字段必填")

    expires_at = None
    if body.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(body["expires_at"])
        except (ValueError, TypeError):
            raise HTTPException(400, "expires_at 格式错误，需 ISO-8601")

    notification = service.create_notification(
        user_id=body["user_id"],
        type=body["type"],
        title=body["title"],
        content=body.get("content", ""),
        source_id=body.get("source_id"),
        link=body.get("link"),
        expires_at=expires_at,
    )
    return notification.to_dict()


@router.get("/unread-count")
def get_unread_count(
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """当前用户未读通知数量"""
    count = service.get_unread_count(user.get("id"))
    return {"unread_count": count}


@router.put("/read-all")
def mark_all_read(
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """标记当前用户所有通知已读"""
    count = service.mark_all_read(user.get("id"))
    return {"message": "全部已读", "updated_count": count}


# ── 动态路径 {notification_id} ──

@router.get("/{notification_id}")
def get_notification(
    notification_id: int,
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """通知详情（只能查看自己的）"""
    notification = service.get_notification(
        notification_id, user.get("id")
    )
    if not notification:
        raise HTTPException(404, "通知不存在或无权查看")
    return notification.to_dict()


@router.put("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """标记通知已读（只能操作自己的）"""
    notification = service.mark_read(notification_id, user.get("id"))
    if not notification:
        raise HTTPException(404, "通知不存在或无权操作")
    return notification.to_dict()


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """删除通知（只能操作自己的）"""
    success = service.delete_notification(notification_id, user.get("id"))
    if not success:
        raise HTTPException(404, "通知不存在或无权操作")
    return {"message": "通知已删除", "notification_id": notification_id}
