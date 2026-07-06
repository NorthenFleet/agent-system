"""Feature module permission APIs."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.v2_models import get_session
from routers.auth_router import get_current_user, require_role
from services.user_service import UserService
from services.module_permission_service import (
    ensure_default_modules,
    get_user_module_keys,
    list_modules,
    modules_for_user,
    replace_user_modules,
)

router = APIRouter(prefix="/api/v2/modules", tags=["v2-modules"])


class UserModuleUpdateRequest(BaseModel):
    module_keys: List[str]


def _load_user(db: Session, user_id: int):
    user = UserService(db).get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return user


@router.get("")
@router.get("/")
def get_modules(
    _admin: dict = Depends(require_role("admin")),
    db: Session = Depends(get_session),
):
    ensure_default_modules(db)
    modules = [module.to_dict() for module in list_modules(db)]
    return {"modules": modules, "total": len(modules)}


@router.get("/me")
def get_my_modules(
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    user = _load_user(db, int(current["sub"]))
    modules = modules_for_user(db, user)
    granted = [module for module in modules if module["granted"]]
    return {
        "modules": granted,
        "module_keys": get_user_module_keys(db, user),
        "total": len(granted),
    }


@router.get("/users/{user_id}")
def get_user_modules(
    user_id: int,
    _admin: dict = Depends(require_role("admin")),
    db: Session = Depends(get_session),
):
    user = _load_user(db, user_id)
    modules = modules_for_user(db, user)
    return {
        "user": user.to_dict(),
        "modules": modules,
        "module_keys": get_user_module_keys(db, user),
    }


@router.put("/users/{user_id}")
def update_user_modules(
    user_id: int,
    req: UserModuleUpdateRequest,
    admin: dict = Depends(require_role("admin")),
    db: Session = Depends(get_session),
):
    user = _load_user(db, user_id)
    keys = replace_user_modules(db, user, req.module_keys, granted_by=int(admin["sub"]))
    return {
        "success": True,
        "user": user.to_dict(),
        "module_keys": keys,
        "modules": modules_for_user(db, user),
    }
