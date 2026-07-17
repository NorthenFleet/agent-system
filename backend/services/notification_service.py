from __future__ import annotations
"""
Notification Service — 通知业务逻辑层

提供通知 CRUD + 标记已读 + 未读计数 + WebSocket 推送。
"""
from typing import Optional, Sequence, Tuple
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.v2_models import Notification


class NotificationService:
    """通知业务逻辑服务"""

    def __init__(self, db: Session):
        self.db = db

    # ── CRUD ──

    def create_notification(
        self,
        user_id: int,
        type: str,
        title: str,
        content: str = "",
        source_id: Optional[str] = None,
        link: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Notification:
        """创建通知"""
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            content=content,
            source_id=source_id,
            link=link,
            is_read=False,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def get_user_notifications(
        self,
        user_id: int,
        type: Optional[str] = None,
        is_read: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[Sequence[Notification], int]:
        """获取用户通知列表，支持类型/已读状态筛选 + 分页"""
        skip = (page - 1) * page_size
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id
        )
        if type:
            query = query.filter(Notification.type == type)
        if is_read is not None:
            query = query.filter(Notification.is_read == is_read)
        query = query.order_by(Notification.created_at.desc())
        total = query.count()
        notifications = query.offset(skip).limit(page_size).all()
        return notifications, total

    def get_notification(
        self, notification_id: int, user_id: int
    ) -> Optional[Notification]:
        """获取指定用户的单条通知（防止越权）"""
        return self.db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        ).first()

    def mark_read(
        self, notification_id: int, user_id: int
    ) -> Optional[Notification]:
        """标记单条已读（校验 user_id 防止越权）"""
        notification = self.get_notification(notification_id, user_id)
        if not notification:
            return None
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def mark_all_read(self, user_id: int) -> int:
        """标记用户所有通知已读，返回更新数量"""
        count = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
            )
            .update(
                {
                    "is_read": True,
                    "read_at": datetime.now(timezone.utc),
                }
            )
        )
        self.db.commit()
        return count

    def get_unread_count(self, user_id: int) -> int:
        """获取未读通知数量"""
        return (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
            )
            .count()
        )

    def delete_notification(
        self, notification_id: int, user_id: int
    ) -> bool:
        """删除通知（校验 user_id）"""
        notification = self.get_notification(notification_id, user_id)
        if not notification:
            return False
        self.db.delete(notification)
        self.db.commit()
        return True
