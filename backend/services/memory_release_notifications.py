"""Deduplicated administrator alerts for terminal memory-release failures."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from models.v2_models import Notification, User
from services.notification_service import NotificationService


FAILURE_STATUSES = {
    "rolled_back",
    "rollback_failed",
    "verification_failed_no_change",
    "failed_before_backup",
}
SOURCE_PREFIX = "memory-release:"


class MemoryReleaseNotificationError(RuntimeError):
    pass


def publish_memory_release_notification(
    db: Session,
    execution: dict[str, Any],
) -> dict[str, Any]:
    """Fan out one alert per release terminal failure state to active admins."""
    status = str(execution.get("status") or "").strip()
    release_id = str(execution.get("release_id") or "").strip()
    if status not in FAILURE_STATUSES:
        return {"status": "not_applicable", "notifications_created": 0}
    if not release_id:
        raise MemoryReleaseNotificationError("release failure notification requires release_id")

    fingerprint = hashlib.sha256(
        json.dumps(
            {"release_id": release_id, "status": status},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    source_id = f"{SOURCE_PREFIX}{release_id[:64]}:{status}:{fingerprint}"
    if db.query(Notification).filter(Notification.source_id == source_id).first():
        return {
            "status": "duplicate",
            "release_status": status,
            "notifications_created": 0,
            "source_id": source_id,
        }

    admins = (
        db.query(User)
        .filter(User.role == "admin", User.is_active == True)  # noqa: E712
        .order_by(User.id.asc())
        .all()
    )
    if not admins:
        raise MemoryReleaseNotificationError(
            "no active administrator can receive memory release notifications"
        )

    labels = {
        "rolled_back": ("记忆系统发布已自动回滚", "灰度验证失败，已恢复发布前版本。"),
        "rollback_failed": ("记忆系统发布回滚失败", "发布与自动回滚均失败，需要立即人工介入。"),
        "verification_failed_no_change": ("记忆系统发布验证失败", "产物未变更，但灰度或多 Agent 矩阵验证未通过。"),
        "failed_before_backup": ("记忆系统发布失败", "发布在建立可恢复备份前失败。"),
    }
    title, detail = labels[status]
    version = str(execution.get("version") or "未知版本")
    completed_at = str(execution.get("completed_at") or "未知时间")
    service = NotificationService(db)
    for admin in admins:
        service.create_notification(
            user_id=admin.id,
            type="alert",
            title=title,
            content=(
                f"{detail}\n版本：{version}\n发布 ID：{release_id}\n完成时间：{completed_at}"
            ),
            source_id=source_id,
            link="/monitoring",
        )
    return {
        "status": "published",
        "release_status": status,
        "notifications_created": len(admins),
        "source_id": source_id,
    }
