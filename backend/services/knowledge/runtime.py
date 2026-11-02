"""Explicit feature gates and single-user project authorization for SB1."""
import os
from functools import lru_cache

from services.knowledge.service import KnowledgeError, KnowledgeService


def flag(name):
    return os.getenv(name, "false").lower() in {"true", "1", "yes", "on"}


def require_enabled(write=False):
    if not flag("SECOND_BRAIN_ENABLED"):
        raise KnowledgeError("disabled", "第二大脑尚未启用", 503)
    if write and not flag("SECOND_BRAIN_WRITE_ENABLED"):
        raise KnowledgeError("write_disabled", "知识写入尚未启用", 503)


@lru_cache(maxsize=1)
def knowledge_engine():
    import sqlalchemy as sa
    return sa.create_engine(database_url(), pool_pre_ping=True, connect_args={'connect_timeout': 3})


def database_url():
    """Separate authority without moving the legacy auth/writing SQLite store."""
    import sqlalchemy as sa
    value = os.getenv('SECOND_BRAIN_DATABASE_URL') or os.getenv('DATABASE_URL', '')
    try:
        if not value or sa.engine.make_url(value).get_backend_name() != 'postgresql':
            raise ValueError()
    except (ValueError, sa.exc.ArgumentError):
        raise KnowledgeError('authority_not_configured', '需要配置知识域 PostgreSQL 连接', 503)
    return value


@lru_cache(maxsize=1)
def get_service():
    def project_check(actor, project_id):
        # Existing project registry lacks universal per-project ACL. Fail closed:
        # only an explicitly configured pilot owner may use ownerless legacy projects.
        from project_manager import project_manager
        project = project_manager.get_project(project_id)
        if not project:
            return False
        owner = str(project.get("owner_user_id") or project.get("user_id") or "")
        if owner:
            return owner == actor
        configured_project = os.getenv('SECOND_BRAIN_PILOT_PROJECT_ID', '')
        return (actor == os.getenv("SECOND_BRAIN_PILOT_OWNER_ID", "")
                and (not configured_project or project_id == configured_project))
    root = os.getenv("SECOND_BRAIN_SOURCE_ROOT", "")
    if not root:
        raise KnowledgeError("storage_not_configured", "需要配置私有来源目录", 503)
    return KnowledgeService(knowledge_engine(), root, project_check=project_check)


def get_projection():
    require_enabled()
    if not flag('SECOND_BRAIN_PROJECTION_ENABLED'):
        raise KnowledgeError('projection_disabled', '投影尚未启用', 503)
    return _projection_service()


@lru_cache(maxsize=1)
def _projection_service():
    from services.knowledge.projection import ProjectionService
    root = os.getenv('SECOND_BRAIN_PROJECTION_ROOT', '')
    if not root:
        raise KnowledgeError('projection_not_configured', '需要配置独立私有投影目录', 503)
    # Existing Obsidian scans must never recursively ingest these generated pages.
    from knowledge_manager import knowledge_manager
    legacy = str(knowledge_manager.vault_path)
    if legacy:
        from pathlib import Path
        projected, vault = Path(root).expanduser().resolve(), Path(legacy).expanduser().resolve()
        if projected == vault or projected in vault.parents or vault in projected.parents:
            raise KnowledgeError('unsafe_projection_root', '投影目录必须与旧知识库扫描目录分离', 503)
    return ProjectionService(get_service(), root)
