"""
JWT 认证中间件 — V3 架构

将所有 /api/v2/ 端点纳入 JWT 保护（登录/注册除外）。
通过 FastAPI Depends 依赖注入实现。

@task task-005-P3-6
@author 🟥 拉斐尔
"""
from fastapi import Header, HTTPException, Depends
from typing import Optional

from services.auth_service import decode_access_token
from models.v2_models import get_session, User


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """依赖注入：获取当前登录用户"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "Token 无效或已过期")
    return payload


def require_role(*roles):
    """依赖注入：检查角色"""
    def check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(403, f"权限不足，需要角色: {roles}")
        return user
    return check


def get_current_user_with_db(
    authorization: Optional[str] = Header(None),
):
    """依赖注入：获取当前用户 + 验证数据库状态"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "Token 无效或已过期")

    db = get_session()
    try:
        user = db.query(User).filter(
            User.id == int(payload["sub"]),
            User.is_active == True,
        ).first()
        if not user:
            raise HTTPException(401, "用户不存在或已禁用")
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
        }
    finally:
        db.close()
