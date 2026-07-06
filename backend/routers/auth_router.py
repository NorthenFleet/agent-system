"""
V2 认证 API 路由
POST /api/v2/auth/login
POST /api/v2/auth/refresh
POST /api/v2/auth/logout
GET  /api/v2/auth/me
POST /api/v2/auth/init-admin
"""
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os
from sqlalchemy.orm import Session

from models.v2_models import get_session
from services.user_service import UserService
from services.auth_service import (
    verify_password, hash_password, create_access_token, create_refresh_token,
    decode_access_token, revoke_token, generate_default_admin_password
)
from services.module_permission_service import get_user_module_keys, modules_for_user

router = APIRouter(prefix="/api/v2/auth", tags=["v2-auth"])


def get_user_service(db: Session = Depends(get_session)) -> UserService:
    return UserService(db)


def _is_local_setup_request(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    return client_host in {"127.0.0.1", "::1", "localhost", "testclient"}


def require_init_admin_allowed(request: Request) -> None:
    setup_token = os.getenv("DASHBOARD_INIT_ADMIN_TOKEN")
    if setup_token:
        if request.headers.get("x-init-token", "") == setup_token:
            return
    elif _is_local_setup_request(request):
        return
    raise HTTPException(403, "init-admin 仅允许本机调用，或提供 X-Init-Token")


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "Token 无效或已过期")
    return payload


def require_role(*roles):
    def check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(403, "权限不足")
        return user
    return check


def user_payload_with_modules(db: Session, user_obj) -> dict:
    data = user_obj.to_dict()
    data["module_keys"] = get_user_module_keys(db, user_obj)
    data["modules"] = [m for m in modules_for_user(db, user_obj) if m["granted"]]
    return data


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: dict


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "viewer"


@router.post("/login")
def login(
    req: LoginRequest,
    svc: UserService = Depends(get_user_service),
):
    user = svc.get_active_user_by_username(req.username)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")

    svc.update_last_login(user.id)

    access_token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })
    refresh_token = create_refresh_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": 86400,
        "user": user_payload_with_modules(svc.db, user),
    }


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        revoke_token(authorization[7:])
    return {"message": "已登出"}


@router.get("/me")
def get_me(
    user: dict = Depends(get_current_user),
    svc: UserService = Depends(get_user_service),
):
    u = svc.get_user_by_id(int(user["sub"]))
    if not u:
        raise HTTPException(404, "用户不存在")
    return user_payload_with_modules(svc.db, u)


@router.post("/init-admin")
def init_admin(
    request: Request,
    svc: UserService = Depends(get_user_service),
):
    require_init_admin_allowed(request)

    existing = svc.get_by_username("admin")
    if existing:
        return {"message": "admin 用户已存在"}

    initial_password = generate_default_admin_password()
    admin = svc.create_user({
        "username": "admin",
        "password_hash": hash_password(initial_password),
        "display_name": "管理员",
        "role": "admin",
    })
    return {"message": "admin 用户已创建", "user": admin.to_dict(), "initial_password": initial_password}


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
def refresh_token(
    req: RefreshRequest,
    svc: UserService = Depends(get_user_service),
):
    payload = decode_access_token(req.refresh_token)
    if not payload:
        raise HTTPException(401, "Refresh token 无效或已过期")
    if payload.get("type") != "refresh":
        raise HTTPException(401, "请使用 refresh token")

    user = svc.get_active_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(401, "用户不存在或已禁用")

    new_access = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })
    new_refresh = create_refresh_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "Bearer",
        "expires_in": 86400,
    }
