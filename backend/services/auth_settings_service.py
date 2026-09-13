"""Database-backed authentication policy for the dashboard."""
from __future__ import annotations

import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.v2_models import SystemSetting, User


LOGIN_ENABLED_KEY = "auth.login_enabled"


def _environment_default() -> bool:
    value = os.getenv("DASHBOARD_LOGIN_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def is_login_enabled(db: Session) -> bool:
    setting = db.query(SystemSetting).filter(SystemSetting.key == LOGIN_ENABLED_KEY).first()
    if not setting:
        return _environment_default()
    value = setting.value or {}
    return bool(value.get("enabled", False))


def set_login_enabled(db: Session, enabled: bool, updated_by: int | None = None) -> bool:
    setting = db.query(SystemSetting).filter(SystemSetting.key == LOGIN_ENABLED_KEY).first()
    if not setting:
        setting = SystemSetting(
            key=LOGIN_ENABLED_KEY,
            value={"enabled": bool(enabled)},
            description="Whether dashboard users must authenticate before accessing modules",
            updated_by=updated_by,
        )
        db.add(setting)
    else:
        setting.value = {"enabled": bool(enabled)}
        setting.updated_by = updated_by
    db.commit()
    return bool(enabled)


def development_admin_payload(db: Session) -> dict:
    username = os.getenv("DASHBOARD_DEVELOPMENT_USER", "admin")
    user = (
        db.query(User)
        .filter(User.username == username, User.role == "admin", User.is_active == True)
        .first()
    )
    if not user:
        user = (
            db.query(User)
            .filter(User.role == "admin", User.is_active == True)
            .order_by(User.id.asc())
            .first()
        )
    if not user:
        raise HTTPException(503, "免登录模式需要至少一个启用的管理员账号")
    return {
        "sub": str(user.id),
        "username": user.username,
        "role": "admin",
        "auth_mode": "development",
    }


def public_auth_settings(db: Session) -> dict:
    enabled = is_login_enabled(db)
    return {
        "login_enabled": enabled,
        "mode": "login_required" if enabled else "development",
    }
