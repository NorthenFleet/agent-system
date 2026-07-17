"""
V2 用户管理 API 路由
GET    /api/v2/users       — 用户列表 (admin)
POST   /api/v2/users       — 创建用户 (admin)
GET    /api/v2/users/{id}  — 用户详情 (admin)
PUT    /api/v2/users/{id}  — 更新用户 (admin)
DELETE /api/v2/users/{id}  — 删除用户 (admin)
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from database import get_db
from services.user_service import UserService
from services.auth_service import hash_password, verify_password
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/users", tags=["v2-users"])


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "viewer"
    email: Optional[str] = None


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
@router.get("/")
def list_users(
    _admin: dict = Depends(require_role("admin")),
    svc: UserService = Depends(get_user_service),
):
    users = svc.list_users()
    return {"users": [u.to_dict() for u in users], "total": len(users)}


@router.post("")
@router.post("/")
def create_user(
    req: UserCreateRequest,
    _admin: dict = Depends(require_role("admin")),
    svc: UserService = Depends(get_user_service),
):
    existing = svc.get_by_username(req.username)
    if existing:
        raise HTTPException(400, "用户名已存在")

    valid_roles = {"admin", "viewer", "agent"}
    if req.role not in valid_roles:
        raise HTTPException(400, f"无效角色，允许值: {', '.join(sorted(valid_roles))}")

    user = svc.create_user({
        "username": req.username,
        "password_hash": hash_password(req.password),
        "display_name": req.display_name,
        "role": req.role,
        "email": req.email,
    })
    return {"success": True, "user": user.to_dict()}


@router.get("/{user_id}")
def get_user(
    user_id: int,
    _admin: dict = Depends(require_role("admin")),
    svc: UserService = Depends(get_user_service),
):
    user = svc.get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return user.to_dict()


@router.put("/{user_id}")
def update_user(
    user_id: int,
    req: UserUpdateRequest,
    _admin: dict = Depends(require_role("admin")),
    svc: UserService = Depends(get_user_service),
):
    user = svc.get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")

    update_data = {}
    if req.display_name is not None:
        update_data["display_name"] = req.display_name
    if req.role is not None:
        valid_roles = {"admin", "viewer", "agent"}
        if req.role not in valid_roles:
            raise HTTPException(400, f"无效角色，允许值: {', '.join(sorted(valid_roles))}")
        update_data["role"] = req.role
    if req.email is not None:
        update_data["email"] = req.email
    if req.password is not None:
        update_data["password_hash"] = hash_password(req.password)
    if req.is_active is not None:
        update_data["is_active"] = req.is_active

    updated_user = svc.update(user_id, update_data)
    return {"success": True, "user": updated_user.to_dict()}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    _admin: dict = Depends(require_role("admin")),
    svc: UserService = Depends(get_user_service),
):
    user = svc.get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")

    if _admin.get("sub") == str(user_id):
        raise HTTPException(400, "不能删除自己")

    svc.delete(user_id)
    return {"success": True, "message": f"用户 {user.username} 已删除"}
