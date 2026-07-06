"""Feature module permission service.

Keeps sidebar modules as database-managed master data and maps users to the
modules they can see/use.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models.v2_models import FeatureModule, User, UserFeatureModule


DEFAULT_MODULES = [
    {"module_key": "dashboard", "name": "仪表盘", "route_path": "/", "icon": "Monitor", "sort_order": 10, "description": "系统概览与近期协作状态"},
    {"module_key": "projects", "name": "项目中枢", "route_path": "/projects", "icon": "FolderOpened", "sort_order": 20, "description": "完整项目画像与产品侧模块入口"},
    {"module_key": "development", "name": "程序开发", "route_path": "/development", "icon": "Promotion", "sort_order": 30, "description": "软件项目开发、任务拆解和执行反馈"},
    {"module_key": "writing", "name": "文档撰写", "route_path": "/writing", "icon": "EditPen", "sort_order": 40, "description": "文档类项目工作区"},
    {"module_key": "finance", "name": "财务管理", "route_path": "/finance", "icon": "Money", "sort_order": 50, "description": "预算、报销和财务信息分析"},
    {"module_key": "products", "name": "产品矩阵", "route_path": "/products", "icon": "Grid", "sort_order": 60, "description": "产品、依赖和推进状态"},
    {"module_key": "data-admin", "name": "数据管理", "route_path": "/data-admin", "icon": "Coin", "sort_order": 110, "description": "统一数据源、备份和数据健康"},
    {"module_key": "agents", "name": "智能体团队", "route_path": "/agents", "icon": "Cpu", "sort_order": 120, "description": "智能体组织、状态和能力"},
    {"module_key": "agent-dispatch", "name": "任务派发", "route_path": "/agent-dispatch", "icon": "Promotion", "sort_order": 130, "description": "智能体任务派发与执行跟踪"},
    {"module_key": "agent-chat", "name": "智能体对话", "route_path": "/agent-chat", "icon": "ChatLineRound", "sort_order": 140, "description": "与智能体进行上下文对话"},
    {"module_key": "knowledge", "name": "知识库", "route_path": "/knowledge", "icon": "Collection", "sort_order": 150, "description": "知识节点和资料上下文"},
    {"module_key": "tools", "name": "工具管理", "route_path": "/tools", "icon": "Tools", "sort_order": 160, "description": "智能体技能、工具和定时任务"},
    {"module_key": "devices", "name": "设备清单", "route_path": "/devices", "icon": "Platform", "sort_order": 170, "description": "机器设备、健康检查和在线状态"},
    {"module_key": "community", "name": "活动社区", "route_path": "/community", "icon": "ChatLineRound", "sort_order": 180, "description": "社区、论坛和互动信息"},
    {"module_key": "news-center", "name": "情报信息", "route_path": "/news-center", "icon": "MapLocation", "sort_order": 190, "description": "全球资讯、情报和 RSS"},
    {"module_key": "tasks", "name": "任务列表", "route_path": "/tasks", "icon": "List", "sort_order": 200, "description": "独立任务列表和详情"},
    {"module_key": "monitoring", "name": "系统监控", "route_path": "/monitoring", "icon": "Monitor", "sort_order": 210, "description": "系统监控和运行指标"},
    {"module_key": "user-admin", "name": "用户管理", "route_path": "/user-admin", "icon": "User", "sort_order": 900, "description": "用户、角色和模块授权"},
]

LEGACY_DISABLED_MODULE_KEYS = {"skills", "scheduled"}

ROLE_DEFAULT_MODULES = {
    "admin": [m["module_key"] for m in DEFAULT_MODULES],
    "agent": [
        "dashboard", "projects", "development", "writing", "agents", "agent-dispatch",
        "agent-chat", "knowledge", "tools", "tasks", "products", "devices",
    ],
    "viewer": ["dashboard", "projects", "development", "writing", "knowledge", "news-center", "products"],
}


def ensure_default_modules(db: Session) -> None:
    """Upsert module master data. Existing admin edits to is_enabled are kept."""
    existing = {m.module_key: m for m in db.query(FeatureModule).all()}
    changed = False
    for item in DEFAULT_MODULES:
        module = existing.get(item["module_key"])
        if not module:
            db.add(FeatureModule(**item))
            changed = True
            continue
        for field in ("name", "route_path", "icon", "description", "sort_order"):
            if getattr(module, field) != item[field]:
                setattr(module, field, item[field])
                changed = True
    for module_key in LEGACY_DISABLED_MODULE_KEYS:
        module = existing.get(module_key)
        if module and module.is_enabled:
            module.is_enabled = False
            changed = True
    if changed:
        db.commit()


def list_modules(db: Session) -> list[FeatureModule]:
    ensure_default_modules(db)
    return db.query(FeatureModule).order_by(FeatureModule.sort_order.asc(), FeatureModule.id.asc()).all()


def _default_keys_for_role(role: str) -> list[str]:
    return ROLE_DEFAULT_MODULES.get(role, ROLE_DEFAULT_MODULES["viewer"])


def ensure_user_default_grants(db: Session, user: User) -> None:
    ensure_default_modules(db)
    existing_count = db.query(UserFeatureModule).filter(UserFeatureModule.user_id == user.id).count()
    if existing_count:
        return
    default_keys = _default_keys_for_role(user.role)
    for module_key in default_keys:
        db.add(UserFeatureModule(
            user_id=user.id,
            module_key=module_key,
            can_view=True,
            can_manage=user.role == "admin",
        ))
    db.commit()


def get_user_module_keys(db: Session, user: Optional[User]) -> list[str]:
    if not user or not user.is_active:
        return []
    ensure_user_default_grants(db, user)
    if user.role == "admin":
        return [
            module.module_key
            for module in list_modules(db)
            if module.is_enabled
        ]
    rows = (
        db.query(UserFeatureModule.module_key)
        .join(FeatureModule, FeatureModule.module_key == UserFeatureModule.module_key)
        .filter(
            UserFeatureModule.user_id == user.id,
            UserFeatureModule.can_view == True,
            FeatureModule.is_enabled == True,
        )
        .all()
    )
    return [row[0] for row in rows]


def user_has_module(db: Session, user: Optional[User], module_key: str) -> bool:
    if not user or not user.is_active:
        return False
    if user.role == "admin":
        return True
    return module_key in set(get_user_module_keys(db, user))


def modules_for_user(db: Session, user: User) -> list[dict]:
    keys = set(get_user_module_keys(db, user))
    modules = []
    for module in list_modules(db):
        item = module.to_dict()
        item["granted"] = module.module_key in keys
        modules.append(item)
    return modules


def replace_user_modules(
    db: Session,
    user: User,
    module_keys: Iterable[str],
    granted_by: Optional[int] = None,
) -> list[str]:
    ensure_default_modules(db)
    valid = {m.module_key for m in list_modules(db)}
    selected = [key for key in dict.fromkeys(module_keys) if key in valid]
    if user.role == "admin":
        selected = sorted(valid, key=lambda key: next((m["sort_order"] for m in DEFAULT_MODULES if m["module_key"] == key), 999))
    db.query(UserFeatureModule).filter(UserFeatureModule.user_id == user.id).delete()
    for key in selected:
        db.add(UserFeatureModule(
            user_id=user.id,
            module_key=key,
            can_view=True,
            can_manage=user.role == "admin" or key == "user-admin",
            granted_by=granted_by,
        ))
    db.commit()
    return get_user_module_keys(db, user)
