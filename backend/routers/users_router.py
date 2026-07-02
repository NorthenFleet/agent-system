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

from models.v2_models import get_session, User
from services.auth_service import hash_password, verify_password
from routers.auth_router import get_current_user, require_role

router = APIRouter(prefix="/api/v2/users", tags=["v2-users"])


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
def list_users(_admin: dict = Depends(require_role("admin"))):
    """获取用户列表（仅 admin）"""
    db = get_session()
    try:
        users = db.query(User).all()
        return {"users": [u.to_dict() for u in users], "total": len(users)}
    finally:
        db.close()


@router.post("")
@router.post("/")
def create_user(req: UserCreateRequest, _admin: dict = Depends(require_role("admin"))):
    """创建用户（仅 admin）"""
    db = get_session()
    try:
        existing = db.query(User).filter(User.username == req.username).first()
        if existing:
            raise HTTPException(400, "用户名已存在")

        valid_roles = {"admin", "viewer", "agent"}
        if req.role not in valid_roles:
            raise HTTPException(400, f"无效角色，允许值: {', '.join(sorted(valid_roles))}")

        user = User(
            username=req.username,
            password_hash=hash_password(req.password),
            display_name=req.display_name,
            role=req.role,
            email=req.email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"success": True, "user": user.to_dict()}
    finally:
        db.close()


@router.get("/{user_id}")
def get_user(user_id: int, _admin: dict = Depends(require_role("admin"))):
    """获取用户详情（仅 admin）"""
    db = get_session()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")
        return user.to_dict()
    finally:
        db.close()


@router.put("/{user_id}")
def update_user(user_id: int, req: UserUpdateRequest, _admin: dict = Depends(require_role("admin"))):
    """更新用户信息（仅 admin）"""
    db = get_session()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")

        if req.display_name is not None:
            user.display_name = req.display_name
        if req.role is not None:
            valid_roles = {"admin", "viewer", "agent"}
            if req.role not in valid_roles:
                raise HTTPException(400, f"无效角色，允许值: {', '.join(sorted(valid_roles))}")
            user.role = req.role
        if req.email is not None:
            user.email = req.email
        if req.password is not None:
            user.password_hash = hash_password(req.password)
        if req.is_active is not None:
            user.is_active = req.is_active

        db.commit()
        db.refresh(user)
        return {"success": True, "user": user.to_dict()}
    finally:
        db.close()


@router.delete("/{user_id}")
def delete_user(user_id: int, _admin: dict = Depends(require_role("admin"))):
    """删除用户（仅 admin）"""
    db = get_session()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")

        # 不允许删除自己
        current = _admin
        if current.get("sub") == str(user_id):
            raise HTTPException(400, "不能删除自己")

        db.delete(user)
        db.commit()
        return {"success": True, "message": f"用户 {user.username} 已删除"}
    finally:
        db.close()
