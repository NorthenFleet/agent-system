"""
Unified data management backend.

This module creates a central SQLite database that can mirror the current
project-management source of truth and register dashboard pages/data sources.
It intentionally keeps existing V2/V3/legacy APIs alive while providing one
place for admin views to inspect and manage the system.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any


BASE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BACKEND_DATA_DIR = os.path.join(BASE_DIR, "data")

UNIFIED_DB_PATH = os.path.join(BACKEND_DATA_DIR, "unified_dashboard.db")
PROJECTS_V3_FILE = os.path.join(DATA_DIR, "projects-v3.json")
AGENT_ORGANIZATION_FILE = os.path.join(BACKEND_DATA_DIR, "agent_organization.json")
BACKUP_DIR = os.path.join(BACKEND_DATA_DIR, "backups")
MANAGED_STORAGE_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".json", ".jsonl"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _loads(value: str | None, fallback: Any):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


DEFAULT_FRONTEND_PAGES = [
    {
        "id": "dashboard",
        "title": "仪表盘",
        "nav_label": "仪表盘",
        "view_key": "dashboard",
        "source_file": "frontend-v2/src/views/Dashboard.vue",
        "api_dependencies": ["/api/v3/agents/dashboard", "/api/devices", "/api/tasks", "/api/email/stats"],
        "status": "active",
        "sort_order": 10,
        "metadata": {"category": "overview"},
    },
    {
        "id": "project-management",
        "title": "项目管理",
        "nav_label": "项目管理",
        "view_key": "tasks",
        "source_file": "frontend-v2/src/views/ProjectHub.vue",
        "api_dependencies": ["/api/v3/projects", "/api/v3/projects/{project_id}/iteration-context", "/api/v3/agents/status"],
        "status": "active",
        "sort_order": 20,
        "metadata": {"category": "projects", "source_of_truth": "unified_dashboard.db"},
    },
    {
        "id": "data-management",
        "title": "数据管理",
        "nav_label": "数据管理",
        "view_key": "dataAdmin",
        "source_file": "frontend-v2/src/views/DataAdmin.vue",
        "api_dependencies": ["/api/admin/data/overview", "/api/admin/data/sources", "/api/admin/data/pages"],
        "status": "active",
        "sort_order": 25,
        "metadata": {"category": "admin"},
    },
    {
        "id": "knowledge",
        "title": "知识库",
        "nav_label": "知识库",
        "view_key": "knowledge",
        "source_file": "frontend-v2/src/views/Knowledge.vue",
        "api_dependencies": ["/api/knowledge/stats", "/api/knowledge/nodes"],
        "status": "active",
        "sort_order": 30,
        "metadata": {"category": "knowledge"},
    },
    {
        "id": "agents",
        "title": "智能体团队",
        "nav_label": "智能体团队",
        "view_key": "agents",
        "source_file": "frontend-v2/src/views/Agents.vue",
        "api_dependencies": ["/api/v3/agents/dashboard", "/api/v3/agents/status", "/api/agents/{agent_id}/memory"],
        "status": "active",
        "sort_order": 40,
        "metadata": {"category": "agents"},
    },
    {
        "id": "skills",
        "title": "技能管理",
        "nav_label": "技能管理",
        "view_key": "skills",
        "source_file": "frontend-v2/src/views/Tools.vue",
        "api_dependencies": ["/api/v3/skills", "/api/v3/agents/{agent_id}/skills"],
        "status": "merged",
        "sort_order": 50,
        "metadata": {"category": "agents", "merged_into": "tools"},
    },
    {
        "id": "scheduled",
        "title": "定时任务",
        "nav_label": "定时任务",
        "view_key": "scheduled",
        "source_file": "frontend-v2/src/views/Tools.vue",
        "api_dependencies": ["/api/scheduled-tasks"],
        "status": "merged",
        "sort_order": 60,
        "metadata": {"category": "operations", "merged_into": "tools"},
    },
    {
        "id": "devices",
        "title": "设备清单",
        "nav_label": "设备清单",
        "view_key": "devices",
        "source_file": "frontend-v2/src/views/Monitoring.vue",
        "api_dependencies": ["/api/devices"],
        "status": "merged",
        "sort_order": 70,
        "metadata": {"category": "operations", "merged_into": "monitoring"},
    },
    {
        "id": "community",
        "title": "活动社区",
        "nav_label": "活动社区",
        "view_key": "bar",
        "source_file": "frontend-v2/src/views/Community.vue",
        "api_dependencies": ["/api/bar/messages", "/api/forum/threads"],
        "status": "active",
        "sort_order": 80,
        "metadata": {"category": "collaboration"},
    },
    {
        "id": "news",
        "title": "新闻资讯",
        "nav_label": "新闻资讯",
        "view_key": "news",
        "source_file": "frontend-v2/src/views/News.vue",
        "api_dependencies": ["/api/news"],
        "status": "active",
        "sort_order": 90,
        "metadata": {"category": "information"},
    },
    {
        "id": "products",
        "title": "产品矩阵",
        "nav_label": "产品矩阵",
        "view_key": "products",
        "source_file": "frontend-v2/src/views/Products.vue",
        "api_dependencies": ["/api/v2/products"],
        "status": "active",
        "sort_order": 95,
        "metadata": {"category": "portfolio"},
    },
]


class UnifiedDataManager:
    def __init__(self, db_path: str = UNIFIED_DB_PATH):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    record_count INTEGER NOT NULL DEFAULT 0,
                    last_synced_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS frontend_pages (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    nav_label TEXT NOT NULL,
                    view_key TEXT NOT NULL UNIQUE,
                    source_file TEXT NOT NULL,
                    api_dependencies TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    sort_order INTEGER NOT NULL DEFAULT 100,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    project_type TEXT NOT NULL DEFAULT 'software',
                    status TEXT,
                    priority TEXT,
                    owner_agent TEXT,
                    project_manager_agent TEXT,
                    progress REAL NOT NULL DEFAULT 0,
                    current_phase TEXT,
                    context TEXT NOT NULL DEFAULT '{}',
                    design_doc TEXT NOT NULL DEFAULT '{}',
                    document_spec TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT,
                    source_id TEXT NOT NULL DEFAULT 'projects-v3-json'
                );

                CREATE TABLE IF NOT EXISTS software_project_specs (
                    project_id TEXT PRIMARY KEY,
                    requirements TEXT NOT NULL DEFAULT '[]',
                    design_doc TEXT NOT NULL DEFAULT '{}',
                    architecture TEXT NOT NULL DEFAULT '{}',
                    database_design TEXT NOT NULL DEFAULT '{}',
                    api_design TEXT NOT NULL DEFAULT '[]',
                    frontend_design TEXT NOT NULL DEFAULT '{}',
                    test_plan TEXT NOT NULL DEFAULT '[]',
                    deployment_plan TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_project_specs (
                    project_id TEXT PRIMARY KEY,
                    document_type TEXT,
                    writing_goal TEXT,
                    target_audience TEXT,
                    outline TEXT NOT NULL DEFAULT '[]',
                    chapter_plan TEXT NOT NULL DEFAULT '[]',
                    image_plan TEXT NOT NULL DEFAULT '[]',
                    reference_plan TEXT NOT NULL DEFAULT '[]',
                    source_word TEXT NOT NULL DEFAULT '{}',
                    working_markdown TEXT NOT NULL DEFAULT '{}',
                    section_links TEXT NOT NULL DEFAULT '[]',
                    sync_status TEXT NOT NULL DEFAULT '{}',
                    output_format TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_sections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    parent_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT,
                    content_brief TEXT,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    status TEXT,
                    assigned_agent_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_assets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    section_id TEXT,
                    type TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    file_path TEXT,
                    status TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(section_id) REFERENCES document_sections(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS project_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'development',
                    title TEXT NOT NULL,
                    description TEXT,
                    assignee_agent TEXT,
                    assignee_agent_id TEXT,
                    status TEXT,
                    priority TEXT,
                    progress REAL NOT NULL DEFAULT 0,
                    dependencies TEXT NOT NULL DEFAULT '[]',
                    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
                    context TEXT NOT NULL DEFAULT '{}',
                    result_summary TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS development_points (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT,
                    weight REAL NOT NULL DEFAULT 1,
                    assigned_agent TEXT,
                    completion_evidence TEXT,
                    checklist TEXT NOT NULL DEFAULT '[]',
                    context TEXT NOT NULL DEFAULT '{}',
                    completed_at TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(task_id) REFERENCES project_tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_logs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    agent_id TEXT,
                    action TEXT,
                    content TEXT,
                    created_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS storage_backups (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    backup_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ok',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL DEFAULT 'system',
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    before_state TEXT,
                    after_state TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    agent_type TEXT NOT NULL DEFAULT 'agent',
                    role TEXT,
                    emoji TEXT,
                    team TEXT,
                    category TEXT,
                    layer TEXT,
                    agent_group TEXT,
                    status TEXT,
                    current_task TEXT,
                    device_id TEXT,
                    slogan TEXT,
                    avatar TEXT,
                    avatar_colors TEXT NOT NULL DEFAULT '[]',
                    responsibilities TEXT NOT NULL DEFAULT '[]',
                    config TEXT NOT NULL DEFAULT '{}',
                    memory TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    visible INTEGER NOT NULL DEFAULT 1,
                    visible_in_org INTEGER NOT NULL DEFAULT 1,
                    is_clone INTEGER NOT NULL DEFAULT 0,
                    clone_of_agent_id TEXT,
                    source TEXT NOT NULL DEFAULT 'local',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_org_nodes (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    agent_id TEXT,
                    node_type TEXT NOT NULL,
                    name TEXT,
                    emoji TEXT,
                    title TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 100,
                    visible INTEGER NOT NULL DEFAULT 1,
                    registered INTEGER NOT NULL DEFAULT 0,
                    planned INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_runtime_status (
                    agent_id TEXT PRIMARY KEY,
                    status TEXT,
                    current_task TEXT,
                    last_seen TEXT,
                    last_heartbeat TEXT,
                    cpu_usage REAL,
                    memory_usage REAL,
                    task_queue_len INTEGER,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'openclaw-runtime',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_assignments (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    project_id TEXT,
                    task_id TEXT,
                    development_point_id TEXT,
                    role_in_task TEXT,
                    status TEXT,
                    assigned_by TEXT,
                    assigned_at TEXT,
                    updated_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS agent_skills (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    level TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(agent_id, skill_id)
                );

                CREATE TABLE IF NOT EXISTS agent_memories (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    memory_type TEXT,
                    title TEXT,
                    content TEXT,
                    source TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ip TEXT,
                    os TEXT,
                    role TEXT,
                    status TEXT,
                    location TEXT,
                    description TEXT,
                    specs TEXT NOT NULL DEFAULT '{}',
                    ports TEXT NOT NULL DEFAULT '[]',
                    assigned_agents TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS device_health_records (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    ip TEXT,
                    ping_success INTEGER NOT NULL DEFAULT 0,
                    ports TEXT NOT NULL DEFAULT '[]',
                    status TEXT,
                    response_time_ms REAL,
                    checked_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            self._ensure_column(conn, "projects", "project_type", "TEXT NOT NULL DEFAULT 'software'")
            self._ensure_column(conn, "projects", "project_manager_agent", "TEXT")
            self._ensure_column(conn, "projects", "document_spec", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "document_project_specs", "source_word", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "document_project_specs", "working_markdown", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "document_project_specs", "section_links", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "document_project_specs", "sync_status", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "project_tasks", "type", "TEXT NOT NULL DEFAULT 'development'")
            self._ensure_column(conn, "project_tasks", "assignee_agent_id", "TEXT")
            self._ensure_column(conn, "project_tasks", "dependencies", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "project_tasks", "acceptance_criteria", "TEXT NOT NULL DEFAULT '[]'")
            # Historical JSON imports used an empty string for an unbound asset.
            # With foreign keys enabled the canonical representation must be NULL.
            conn.execute("UPDATE document_assets SET section_id=NULL WHERE section_id='' ")
            self._ensure_agent_columns(conn)
            self._record_migration(conn, "001_unified_project_management", "Create unified project management tables")
            self._record_migration(conn, "002_storage_governance", "Create storage backups and data asset governance tables")
            self._record_migration(conn, "003_agents_devices_audit", "Create agents, devices, health records, and audit logs")
            self._record_migration(conn, "004_agent_management", "Create agent management, org, runtime, skills, memory, and assignment tables")
            self._seed_pages(conn)

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _ensure_agent_columns(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(conn, "agents", "display_name", "TEXT")
        self._ensure_column(conn, "agents", "agent_type", "TEXT NOT NULL DEFAULT 'agent'")
        self._ensure_column(conn, "agents", "category", "TEXT")
        self._ensure_column(conn, "agents", "enabled", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "agents", "visible", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "agents", "visible_in_org", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "agents", "is_clone", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "agents", "clone_of_agent_id", "TEXT")
        self._ensure_column(conn, "agents", "source", "TEXT NOT NULL DEFAULT 'local'")

    def _record_migration(self, conn: sqlite3.Connection, migration_id: str, description: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (id, description, applied_at) VALUES (?, ?, ?)",
            (migration_id, description, _now_iso()),
        )

    def _seed_pages(self, conn: sqlite3.Connection) -> None:
        now = _now_iso()
        for page in DEFAULT_FRONTEND_PAGES:
            conn.execute(
                """
                INSERT OR IGNORE INTO frontend_pages
                (id, title, nav_label, view_key, source_file, api_dependencies, status, sort_order, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page["id"],
                    page["title"],
                    page["nav_label"],
                    page["view_key"],
                    page["source_file"],
                    _json(page.get("api_dependencies", [])),
                    page.get("status", "active"),
                    page.get("sort_order", 100),
                    _json(page.get("metadata", {})),
                    now,
                ),
            )

    def sync_all(self) -> dict:
        result = self.current_project_counts()
        if result["projects"] == 0 and os.path.exists(PROJECTS_V3_FILE):
            result = self.sync_projects_v3()
        with self.connect() as conn:
            self._refresh_sources(conn, result)
        self.discover_storage_assets()
        return self.overview()

    def current_project_counts(self) -> dict:
        with self.connect() as conn:
            return {
                "projects": self._table_count(conn, "projects"),
                "tasks": self._table_count(conn, "project_tasks"),
                "development_points": self._table_count(conn, "development_points"),
                "logs": self._table_count(conn, "project_logs"),
                "available": True,
                "source_of_truth": "unified-sqlite",
            }

    def sync_projects_v3(self) -> dict:
        if not os.path.exists(PROJECTS_V3_FILE):
            return {"projects": 0, "tasks": 0, "development_points": 0, "logs": 0, "available": False}

        with open(PROJECTS_V3_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        projects = data.get("projects", [])
        logs = data.get("logs", [])

        task_count = 0
        point_count = 0
        with self.connect() as conn:
            conn.execute("DELETE FROM project_logs")
            conn.execute("DELETE FROM development_points")
            conn.execute("DELETE FROM project_tasks")
            conn.execute("DELETE FROM projects")

            task_count, point_count = self._insert_project_document(conn, projects, logs)

        return {
            "projects": len(projects),
            "tasks": task_count,
            "development_points": point_count,
            "logs": len(logs),
            "available": True,
        }

    def _refresh_sources(self, conn: sqlite3.Connection, project_result: dict) -> None:
        now = _now_iso()
        sources = [
            {
                "id": "projects-v3-json",
                "name": "V3 项目管理 JSON",
                "source_type": "json",
                "path": PROJECTS_V3_FILE,
                "record_count": project_result.get("projects", 0),
                "metadata": {
                    "projects": project_result.get("projects", 0),
                    "tasks": project_result.get("tasks", 0),
                    "development_points": project_result.get("development_points", 0),
                    "logs": project_result.get("logs", 0),
                    "available": os.path.exists(PROJECTS_V3_FILE),
                    "legacy_source": True,
                },
            },
            {
                "id": "unified-sqlite",
                "name": "统一数据管理 SQLite",
                "source_type": "sqlite",
                "path": self.db_path,
                "record_count": self._table_count(conn, "projects"),
                "metadata": {"tables": self.schema_summary(conn), "source_of_truth": True},
            },
        ]
        for source in sources:
            conn.execute(
                """
                INSERT OR REPLACE INTO data_sources
                (id, name, source_type, path, status, record_count, last_synced_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source["id"],
                    source["name"],
                    source["source_type"],
                    source["path"],
                    "active" if os.path.exists(source["path"]) else "missing",
                    source["record_count"],
                    now,
                    _json(source["metadata"]),
                ),
            )

    def _refresh_agent_sources(self, conn: sqlite3.Connection) -> None:
        now = _now_iso()
        sources = [
            {
                "id": "agents-json",
                "name": "智能体档案 JSON",
                "source_type": "json",
                "path": os.path.join(BACKEND_DATA_DIR, "agents.json"),
                "record_count": self._table_count(conn, "agents"),
                "metadata": {"legacy_source": True, "mirrored_to": "agents"},
            },
            {
                "id": "agent-organization-json",
                "name": "智能体组织 JSON",
                "source_type": "json",
                "path": AGENT_ORGANIZATION_FILE,
                "record_count": self._table_count(conn, "agent_org_nodes"),
                "metadata": {"legacy_source": True, "mirrored_to": "agent_org_nodes"},
            },
            {
                "id": "agent-management-sqlite",
                "name": "智能体管理 SQLite",
                "source_type": "sqlite",
                "path": self.db_path,
                "record_count": self._table_count(conn, "agents"),
                "metadata": {"tables": ["agents", "agent_org_nodes", "agent_runtime_status"], "source_of_truth": True},
            },
        ]
        for source in sources:
            conn.execute(
                """
                INSERT OR REPLACE INTO data_sources
                (id, name, source_type, path, status, record_count, last_synced_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source["id"],
                    source["name"],
                    source["source_type"],
                    source["path"],
                    "active" if os.path.exists(source["path"]) else "missing",
                    source["record_count"],
                    now,
                    _json(source["metadata"]),
                ),
            )

    def _table_count(self, conn: sqlite3.Connection, table_name: str) -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])

    def list_migrations(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM schema_migrations ORDER BY applied_at, id").fetchall()
            return [{"id": row["id"], "description": row["description"], "applied_at": row["applied_at"]} for row in rows]

    def record_audit(
        self,
        action: str,
        target_type: str,
        target_id: str,
        actor: str = "system",
        before_state: Any = None,
        after_state: Any = None,
        metadata: dict | None = None,
    ) -> dict:
        created_at = _now_iso()
        audit_id = f"audit-{created_at.replace(':', '').replace('+', 'Z')}-{target_type}-{target_id}"
        entry = {
            "id": audit_id,
            "actor": actor or "system",
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "before_state": before_state,
            "after_state": after_state,
            "metadata": metadata or {},
            "created_at": created_at,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs
                (id, actor, action, target_type, target_id, before_state, after_state, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    entry["actor"],
                    action,
                    target_type,
                    target_id,
                    _json(before_state) if before_state is not None else None,
                    _json(after_state) if after_state is not None else None,
                    _json(entry["metadata"]),
                    created_at,
                ),
            )
        return entry

    def list_audit_logs(self, limit: int = 100, target_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM audit_logs"
        params: list[Any] = []
        if target_type:
            sql += " WHERE target_type=?"
            params.append(target_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._audit_row(row) for row in rows]

    def import_agents_from_json(self, path: str | None = None, overwrite: bool = False) -> dict:
        path = path or os.path.join(BACKEND_DATA_DIR, "agents.json")
        if not os.path.exists(path):
            return {"imported": 0, "path": path, "available": False}
        with open(path, "r", encoding="utf-8") as f:
            agents = json.load(f)
        if not isinstance(agents, list):
            return {"imported": 0, "path": path, "available": True, "error": "agents json is not a list"}
        if overwrite:
            with self.connect() as conn:
                conn.execute("DELETE FROM agents")
        self.save_agents(agents, actor="migration", audit=False)
        self.record_audit("import_agents", "dataset", "agents", actor="migration", after_state={"count": len(agents), "path": path})
        return {"imported": len(agents), "path": path, "available": True}

    def import_agent_organization_from_json(self, path: str | None = None, overwrite: bool = True) -> dict:
        path = path or AGENT_ORGANIZATION_FILE
        if not os.path.exists(path):
            return {"imported": 0, "path": path, "available": False}
        with open(path, "r", encoding="utf-8") as f:
            document = json.load(f)
        root = document.get("root") or {}
        nodes = document.get("nodes") or []
        if not isinstance(root, dict) or not isinstance(nodes, list):
            return {"imported": 0, "path": path, "available": True, "error": "agent organization json is invalid"}

        now = _now_iso()
        all_nodes = [{**root, "parent_id": root.get("parent_id")}] + nodes
        with self.connect() as conn:
            if overwrite:
                conn.execute("DELETE FROM agent_org_nodes")
            for node in all_nodes:
                self._upsert_agent_org_node(conn, node, now)
                self._ensure_agent_from_org_node(conn, node, now)
            self._refresh_agent_sources(conn)

        self.record_audit(
            "import_agent_organization",
            "dataset",
            "agent_organization",
            actor="migration",
            after_state={"nodes": len(all_nodes), "path": path},
        )
        return {"imported": len(all_nodes), "path": path, "available": True}

    def import_devices_from_json(self, devices_path: str | None = None, health_path: str | None = None, overwrite: bool = False) -> dict:
        devices_path = devices_path or os.path.join(DATA_DIR, "devices.json")
        health_path = health_path or os.path.join(DATA_DIR, "device_health.json")
        imported_devices = 0
        imported_health = 0
        if os.path.exists(devices_path):
            with open(devices_path, "r", encoding="utf-8") as f:
                devices = json.load(f)
            if isinstance(devices, list):
                if overwrite:
                    with self.connect() as conn:
                        conn.execute("DELETE FROM devices")
                self.save_devices(devices, actor="migration", audit=False)
                imported_devices = len(devices)
        if os.path.exists(health_path):
            with open(health_path, "r", encoding="utf-8") as f:
                health = json.load(f)
            if isinstance(health, dict):
                if overwrite:
                    with self.connect() as conn:
                        conn.execute("DELETE FROM device_health_records")
                imported_health = self.save_device_health_records(health, actor="migration", audit=False)
        self.record_audit(
            "import_devices",
            "dataset",
            "devices",
            actor="migration",
            after_state={"devices": imported_devices, "health_records": imported_health, "devices_path": devices_path, "health_path": health_path},
        )
        return {"devices": imported_devices, "health_records": imported_health, "devices_path": devices_path, "health_path": health_path}

    def ensure_operational_data_imported(self) -> dict:
        results = {}
        with self.connect() as conn:
            agent_count = self._table_count(conn, "agents")
            org_count = self._table_count(conn, "agent_org_nodes")
            device_count = self._table_count(conn, "devices")
            health_count = self._table_count(conn, "device_health_records")
        if agent_count == 0:
            results["agents"] = self.import_agents_from_json()
        if org_count == 0:
            results["agent_organization"] = self.import_agent_organization_from_json()
        if device_count == 0 or health_count == 0:
            results["devices"] = self.import_devices_from_json()
        return results

    def list_agents(self) -> list[dict]:
        self.ensure_operational_data_imported()
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
            return [self._agent_row(row) for row in rows]

    def save_agents(self, agents: list[dict], actor: str = "system", audit: bool = True) -> int:
        now = _now_iso()
        before = self.list_agents() if audit else None
        with self.connect() as conn:
            conn.execute("DELETE FROM agents")
            for agent in agents:
                self._upsert_agent(conn, agent, now)
        if audit:
            self.record_audit("save_agents", "dataset", "agents", actor=actor, before_state=before, after_state={"count": len(agents)})
        return len(agents)

    def update_agent(self, agent_id: str, updates: dict, actor: str = "system") -> dict | None:
        before = self.get_agent(agent_id)
        if not before:
            return None
        updated = {**before, **updates, "updated_at": _now_iso()}
        with self.connect() as conn:
            self._upsert_agent(conn, updated, updated["updated_at"])
        self.record_audit("update_agent", "agent", agent_id, actor=actor, before_state=before, after_state=updated)
        return updated

    def get_agent(self, agent_id: str) -> dict | None:
        self.ensure_operational_data_imported()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
            return self._agent_row(row) if row else None

    def list_agent_org_nodes(self, include_hidden: bool = False) -> list[dict]:
        self.ensure_operational_data_imported()
        sql = "SELECT * FROM agent_org_nodes"
        params: list[Any] = []
        if not include_hidden:
            sql += " WHERE visible=1"
        sql += " ORDER BY sort_order, id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._agent_org_node_row(row) for row in rows]

    def get_agent_organization_document(self, include_hidden: bool = False) -> dict:
        nodes = self.list_agent_org_nodes(include_hidden=include_hidden)
        root = next((node for node in nodes if not node.get("parent_id")), None)
        if not root:
            return {"version": 3, "root": {}, "nodes": [], "relations": [], "source": "unified-sqlite"}

        children = [node for node in nodes if node["id"] != root["id"]]
        relations = [
            {
                "from": node["parent_id"],
                "to": node["id"],
                "type": node.get("metadata", {}).get("relation_type", "contains"),
                "label": node.get("title") or node.get("name") or node["id"],
            }
            for node in children
            if node.get("parent_id")
        ]
        return {
            "version": 3,
            "root": self._org_node_document(root),
            "nodes": [self._org_node_document(node) for node in children],
            "relations": relations,
            "source": "unified-sqlite",
        }

    def save_agent_org_nodes(self, root: dict, nodes: list[dict], actor: str = "system") -> dict:
        now = _now_iso()
        before = self.get_agent_organization_document(include_hidden=True)
        all_nodes = [{**root, "parent_id": root.get("parent_id")}] + nodes
        with self.connect() as conn:
            conn.execute("DELETE FROM agent_org_nodes")
            for node in all_nodes:
                self._upsert_agent_org_node(conn, node, now)
                self._ensure_agent_from_org_node(conn, node, now)
            self._refresh_agent_sources(conn)
        after = self.get_agent_organization_document(include_hidden=True)
        self.record_audit("save_agent_org", "dataset", "agent_organization", actor=actor, before_state=before, after_state=after)
        return after

    def upsert_agent_runtime_status(self, agent_id: str, runtime: dict, source: str = "openclaw-runtime") -> dict:
        now = _now_iso()
        row = {
            "agent_id": agent_id,
            "status": runtime.get("status", ""),
            "current_task": runtime.get("current_task", ""),
            "last_seen": runtime.get("last_seen"),
            "last_heartbeat": runtime.get("last_heartbeat"),
            "cpu_usage": runtime.get("cpu_usage"),
            "memory_usage": runtime.get("memory_usage"),
            "task_queue_len": runtime.get("task_queue_len"),
            "raw_json": runtime,
            "source": source,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_runtime_status
                (agent_id, status, current_task, last_seen, last_heartbeat, cpu_usage, memory_usage, task_queue_len, raw_json, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    row["status"],
                    row["current_task"],
                    row["last_seen"],
                    row["last_heartbeat"],
                    row["cpu_usage"],
                    row["memory_usage"],
                    row["task_queue_len"],
                    _json(row["raw_json"]),
                    row["source"],
                    row["updated_at"],
                ),
            )
        return row

    def list_devices(self) -> list[dict]:
        self.ensure_operational_data_imported()
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
            return [self._device_row(row) for row in rows]

    def save_devices(self, devices: list[dict], actor: str = "system", audit: bool = True) -> int:
        now = _now_iso()
        before = self.list_devices() if audit else None
        with self.connect() as conn:
            conn.execute("DELETE FROM devices")
            for device in devices:
                self._upsert_device(conn, device, now)
        if audit:
            self.record_audit("save_devices", "dataset", "devices", actor=actor, before_state=before, after_state={"count": len(devices)})
        return len(devices)

    def get_device(self, device_id: str) -> dict | None:
        self.ensure_operational_data_imported()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            return self._device_row(row) if row else None

    def add_device(self, device: dict, actor: str = "system") -> dict:
        now = _now_iso()
        device = {**device}
        device.setdefault("created_at", now)
        device["updated_at"] = device.get("updated_at") or now
        with self.connect() as conn:
            self._upsert_device(conn, device, now)
        self.record_audit("add_device", "device", device["id"], actor=actor, after_state=device)
        return device

    def update_device(self, device_id: str, updates: dict, actor: str = "system") -> dict | None:
        before = self.get_device(device_id)
        if not before:
            return None
        updated = {**before, **updates, "updated_at": _now_iso()}
        with self.connect() as conn:
            self._upsert_device(conn, updated, updated["updated_at"])
        self.record_audit("update_device", "device", device_id, actor=actor, before_state=before, after_state=updated)
        return updated

    def delete_device(self, device_id: str, actor: str = "system") -> bool:
        before = self.get_device(device_id)
        if not before:
            return False
        with self.connect() as conn:
            conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
        self.record_audit("delete_device", "device", device_id, actor=actor, before_state=before)
        return True

    def load_device_health_records(self) -> dict[str, list[dict]]:
        self.ensure_operational_data_imported()
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM device_health_records ORDER BY checked_at, id").fetchall()
        records: dict[str, list[dict]] = {}
        for row in rows:
            record = self._device_health_row(row)
            records.setdefault(record["device_id"], []).append(record)
        return records

    def save_device_health_records(self, health_records: dict[str, list[dict]], actor: str = "system", audit: bool = True) -> int:
        inserted = 0
        with self.connect() as conn:
            conn.execute("DELETE FROM device_health_records")
            for device_id, records in (health_records or {}).items():
                for record in records[-100:]:
                    self._insert_device_health_record(conn, device_id, record)
                    inserted += 1
        if audit:
            self.record_audit("save_device_health", "dataset", "device_health", actor=actor, after_state={"records": inserted})
        return inserted

    def append_device_health_record(self, record: dict, actor: str = "system") -> dict:
        device_id = record.get("device_id", "")
        with self.connect() as conn:
            self._insert_device_health_record(conn, device_id, record)
            rows = conn.execute(
                "SELECT id FROM device_health_records WHERE device_id=? ORDER BY checked_at DESC, id DESC",
                (device_id,),
            ).fetchall()
            for stale in rows[100:]:
                conn.execute("DELETE FROM device_health_records WHERE id=?", (stale["id"],))
        self.record_audit("append_device_health", "device", device_id, actor=actor, after_state=record)
        return record

    def discover_storage_assets(self) -> dict:
        assets = []
        roots = [
            ("backend-data", BACKEND_DATA_DIR),
            ("project-data", DATA_DIR),
        ]
        for root_label, root_path in roots:
            if not os.path.isdir(root_path):
                continue
            for dirpath, dirnames, filenames in os.walk(root_path):
                dirnames[:] = [
                    dirname for dirname in dirnames
                    if dirname not in {"__pycache__", ".pytest_cache", "backups"}
                ]
                for filename in filenames:
                    path = os.path.join(dirpath, filename)
                    if self._is_managed_storage_file(path):
                        assets.append(self._inspect_storage_asset(path, root_label))

        now = _now_iso()
        with self.connect() as conn:
            for asset in assets:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO data_sources
                    (id, name, source_type, path, status, record_count, last_synced_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset["id"],
                        asset["name"],
                        asset["source_type"],
                        asset["path"],
                        asset["status"],
                        asset["record_count"],
                        now,
                        _json(asset["metadata"]),
                    ),
                )
            for row in conn.execute("SELECT id, path FROM data_sources").fetchall():
                if row["path"] and not os.path.exists(row["path"]):
                    conn.execute(
                        "UPDATE data_sources SET status=?, last_synced_at=? WHERE id=?",
                        ("missing", now, row["id"]),
                    )
        return {"assets": assets, "total": len(assets), "updated_at": now}

    def health_check(self) -> dict:
        self.discover_storage_assets()
        sources = []
        issues = []
        for source in self.list_sources():
            check = self._check_source_health(source)
            sources.append(check)
            if check["status"] != "ok":
                issues.append({
                    "source_id": source["id"],
                    "severity": "error" if check["status"] in {"missing", "corrupt"} else "warning",
                    "message": check.get("message", check["status"]),
                })

        unified_checks = self._unified_integrity_checks()
        issues.extend(unified_checks["issues"])
        status = "ok"
        if any(issue["severity"] == "error" for issue in issues):
            status = "error"
        elif issues:
            status = "warning"
        return {
            "status": status,
            "checked_at": _now_iso(),
            "sources": sources,
            "unified_integrity": unified_checks,
            "issues": issues,
        }

    def create_backup(self, source_id: str = "unified-sqlite") -> dict:
        if source_id == "all":
            created = []
            for source in self.list_sources():
                if source["status"] == "active" and os.path.exists(source["path"]):
                    created.append(self.create_backup(source["id"]))
            return {"source_id": "all", "backups": created, "total": len(created)}

        source = self.get_source(source_id)
        if not source:
            return {"source_id": source_id, "status": "missing", "error": "source not found"}
        if not os.path.exists(source["path"]):
            return {"source_id": source_id, "status": "missing", "error": "source path missing"}

        os.makedirs(BACKUP_DIR, exist_ok=True)
        created_at = _now_iso()
        safe_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in source_id)
        filename = f"{created_at.replace(':', '').replace('+', 'Z')}-{safe_id}-{os.path.basename(source['path'])}"
        backup_path = os.path.join(BACKUP_DIR, filename)
        metadata = {"source_type": source["source_type"], "source_metadata": source.get("metadata", {})}
        try:
            if source["source_type"] == "sqlite":
                self._backup_sqlite(source["path"], backup_path)
                metadata["backup_method"] = "sqlite-backup-api"
            else:
                shutil.copy2(source["path"], backup_path)
                metadata["backup_method"] = "copy2"
            status = "ok"
            error = ""
        except Exception as exc:
            status = "error"
            error = str(exc)
            metadata["error"] = error
        size_bytes = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
        backup_id = f"backup-{safe_id}-{created_at.replace(':', '').replace('+', 'Z')}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO storage_backups
                (id, source_id, source_path, backup_path, size_bytes, status, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    backup_id,
                    source_id,
                    source["path"],
                    backup_path,
                    size_bytes,
                    status,
                    created_at,
                    _json(metadata),
                ),
            )
        result = {
            "id": backup_id,
            "source_id": source_id,
            "source_path": source["path"],
            "backup_path": backup_path,
            "size_bytes": size_bytes,
            "status": status,
            "created_at": created_at,
        }
        if error:
            result["error"] = error
        return result

    def list_backups(self, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM storage_backups ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit or 50), 200)),),
            ).fetchall()
            return [self._backup_row(row) for row in rows]

    def optimize_sqlite(self, source_id: str = "unified-sqlite", vacuum: bool = False) -> dict:
        if source_id == "all":
            results = [
                self.optimize_sqlite(source["id"], vacuum)
                for source in self.list_sources()
                if source["source_type"] == "sqlite" and source["status"] == "active"
            ]
            status = "ok" if all(result.get("status") == "ok" for result in results) else "warning"
            return {"source_id": "all", "status": status, "results": results}

        source = self.get_source(source_id)
        if not source:
            return {"source_id": source_id, "status": "missing", "error": "source not found"}
        if source["source_type"] != "sqlite":
            return {"source_id": source_id, "status": "skipped", "error": "source is not sqlite"}
        if not os.path.exists(source["path"]):
            return {"source_id": source_id, "status": "missing", "error": "source path missing"}

        started_at = _now_iso()
        try:
            conn = sqlite3.connect(source["path"])
            conn.execute("PRAGMA foreign_keys=ON")
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            conn.execute("ANALYZE")
            conn.execute("PRAGMA optimize")
            if vacuum:
                conn.execute("VACUUM")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            status = "ok" if integrity == "ok" else "warning"
            return {
                "source_id": source_id,
                "path": source["path"],
                "status": status,
                "journal_mode": journal_mode,
                "vacuum": bool(vacuum),
                "integrity_check": integrity,
                "started_at": started_at,
                "finished_at": _now_iso(),
            }
        except Exception as exc:
            return {
                "source_id": source_id,
                "path": source["path"],
                "status": "error",
                "error": str(exc),
                "started_at": started_at,
                "finished_at": _now_iso(),
            }

    def get_source(self, source_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
            return self._source_row(row) if row else None

    def _is_managed_storage_file(self, path: str) -> bool:
        name = os.path.basename(path)
        if name.startswith(".") or name.endswith(".lock") or name.endswith(".tmp"):
            return False
        _, ext = os.path.splitext(path)
        return ext.lower() in MANAGED_STORAGE_EXTENSIONS

    def _inspect_storage_asset(self, path: str, root_label: str) -> dict:
        abs_path = os.path.abspath(path)
        stat = os.stat(abs_path)
        source_type = self._source_type_for_path(abs_path)
        status = "active"
        record_count = 0
        metadata = {
            "root": root_label,
            "relpath": self._relative_storage_path(abs_path),
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "extension": os.path.splitext(abs_path)[1].lower(),
        }
        try:
            if source_type == "sqlite":
                schema = self._sqlite_schema_for_path(abs_path)
                metadata["schema"] = schema
                record_count = sum(table["rows"] for table in schema)
            elif source_type == "json":
                json_meta = self._json_metadata(abs_path)
                metadata.update(json_meta)
                record_count = json_meta.get("record_count", 0)
            elif source_type == "jsonl":
                line_count = self._jsonl_line_count(abs_path)
                metadata["line_count"] = line_count
                record_count = line_count
        except Exception as exc:
            status = "corrupt"
            metadata["error"] = str(exc)

        return {
            "id": self._source_id_for_path(abs_path),
            "name": metadata["relpath"],
            "source_type": source_type,
            "path": abs_path,
            "status": status,
            "record_count": record_count,
            "metadata": metadata,
        }

    def _source_id_for_path(self, path: str) -> str:
        abs_path = os.path.abspath(path)
        if abs_path == os.path.abspath(self.db_path):
            return "unified-sqlite"
        if abs_path == os.path.abspath(PROJECTS_V3_FILE):
            return "projects-v3-json"
        relpath = self._relative_storage_path(abs_path)
        safe = "".join(ch if ch.isalnum() else "-" for ch in relpath.lower()).strip("-")
        return f"storage-{safe}"

    def _relative_storage_path(self, path: str) -> str:
        for root in (PROJECT_ROOT, BASE_DIR):
            try:
                relpath = os.path.relpath(path, root)
                if not relpath.startswith(".."):
                    return relpath
            except ValueError:
                continue
        return path

    def _source_type_for_path(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in {".db", ".sqlite", ".sqlite3"}:
            return "sqlite"
        if ext == ".jsonl":
            return "jsonl"
        if ext == ".json":
            return "json"
        return "file"

    def _sqlite_schema_for_path(self, path: str) -> list[dict]:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            tables = []
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
                table_name = row["name"]
                tables.append({
                    "name": table_name,
                    "rows": int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]),
                })
            return tables
        finally:
            conn.close()

    def _json_metadata(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"shape": "list", "record_count": len(data)}
        if isinstance(data, dict):
            list_counts = {
                key: len(value)
                for key, value in data.items()
                if isinstance(value, list)
            }
            record_count = sum(list_counts.values()) if list_counts else len(data)
            return {
                "shape": "dict",
                "keys": list(data.keys())[:40],
                "list_counts": list_counts,
                "record_count": record_count,
            }
        return {"shape": type(data).__name__, "record_count": 1}

    def _jsonl_line_count(self, path: str) -> int:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def _check_source_health(self, source: dict) -> dict:
        if not os.path.exists(source["path"]):
            return {"source_id": source["id"], "status": "missing", "message": "source path missing"}
        try:
            if source["source_type"] == "sqlite":
                conn = sqlite3.connect(source["path"])
                try:
                    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    conn.close()
                return {
                    "source_id": source["id"],
                    "status": "ok" if integrity == "ok" else "corrupt",
                    "integrity_check": integrity,
                }
            if source["source_type"] == "json":
                self._json_metadata(source["path"])
                return {"source_id": source["id"], "status": "ok"}
            if source["source_type"] == "jsonl":
                self._jsonl_line_count(source["path"])
                return {"source_id": source["id"], "status": "ok"}
            return {"source_id": source["id"], "status": "ok"}
        except Exception as exc:
            return {"source_id": source["id"], "status": "corrupt", "message": str(exc)}

    def _unified_integrity_checks(self) -> dict:
        checks = {}
        issues = []
        with self.connect() as conn:
            checks["orphan_tasks"] = self._scalar(conn, "SELECT COUNT(*) FROM project_tasks t LEFT JOIN projects p ON p.id=t.project_id WHERE p.id IS NULL")
            checks["orphan_points_by_task"] = self._scalar(conn, "SELECT COUNT(*) FROM development_points dp LEFT JOIN project_tasks t ON t.id=dp.task_id WHERE t.id IS NULL")
            checks["orphan_points_by_project"] = self._scalar(conn, "SELECT COUNT(*) FROM development_points dp LEFT JOIN projects p ON p.id=dp.project_id WHERE p.id IS NULL")
            checks["orphan_logs"] = self._scalar(conn, "SELECT COUNT(*) FROM project_logs l LEFT JOIN projects p ON p.id=l.project_id WHERE p.id IS NULL")
        for name, count in checks.items():
            if count:
                issues.append({"severity": "error", "message": f"{name}: {count}"})
        return {"status": "ok" if not issues else "error", "checks": checks, "issues": issues}

    def _scalar(self, conn: sqlite3.Connection, sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    def _backup_sqlite(self, source_path: str, backup_path: str) -> None:
        source = sqlite3.connect(source_path)
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    def _upsert_agent(self, conn: sqlite3.Connection, agent: dict, now: str) -> None:
        metadata = {
            key: value
            for key, value in agent.items()
            if key not in {
                "id", "name", "display_name", "agent_type", "role", "emoji", "team", "category", "layer", "group", "agent_group",
                "status", "current_task", "device_id", "slogan", "avatar", "avatar_colors",
                "responsibilities", "config", "memory", "enabled", "visible", "visible_in_org",
                "is_clone", "clone_of_agent_id", "source", "metadata", "created_at", "updated_at",
            }
        }
        explicit_metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
        metadata.update(explicit_metadata)
        conn.execute(
            """
            INSERT OR REPLACE INTO agents
            (id, name, display_name, agent_type, role, emoji, team, category, layer, agent_group, status, current_task,
             device_id, slogan, avatar, avatar_colors, responsibilities, config, memory, enabled, visible,
             visible_in_org, is_clone, clone_of_agent_id, source, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent.get("id"),
                agent.get("name", agent.get("id", "")),
                agent.get("display_name", agent.get("name", "")),
                agent.get("agent_type", "agent"),
                agent.get("role", ""),
                agent.get("emoji", ""),
                agent.get("team", ""),
                agent.get("category", ""),
                agent.get("layer", ""),
                agent.get("group") or agent.get("agent_group", ""),
                agent.get("status", "idle"),
                agent.get("current_task", ""),
                agent.get("device_id", ""),
                agent.get("slogan", ""),
                agent.get("avatar", ""),
                _json(agent.get("avatar_colors", [])),
                _json(agent.get("responsibilities", [])),
                _json(agent.get("config", {})),
                _json(agent.get("memory", [])),
                1 if agent.get("enabled", True) else 0,
                1 if agent.get("visible", True) else 0,
                1 if agent.get("visible_in_org", True) else 0,
                1 if agent.get("is_clone", False) else 0,
                agent.get("clone_of_agent_id", ""),
                agent.get("source", "local"),
                _json(metadata),
                agent.get("created_at") or now,
                agent.get("updated_at") or now,
            ),
        )

    def _upsert_agent_org_node(self, conn: sqlite3.Connection, node: dict, now: str) -> None:
        node_id = node.get("id")
        if not node_id:
            return
        metadata = {
            key: value
            for key, value in node.items()
            if key not in {
                "id", "parent_id", "agent_id", "node_type", "name", "emoji", "title", "order",
                "sort_order", "visible", "registered", "planned", "metadata", "created_at", "updated_at",
            }
        }
        explicit_metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        metadata.update(explicit_metadata)
        conn.execute(
            """
            INSERT OR REPLACE INTO agent_org_nodes
            (id, parent_id, agent_id, node_type, name, emoji, title, sort_order, visible, registered, planned, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                node.get("parent_id"),
                node.get("agent_id"),
                node.get("node_type", "agent"),
                node.get("name", node_id),
                node.get("emoji", ""),
                node.get("title", ""),
                int(node.get("sort_order", node.get("order", 100)) or 100),
                1 if node.get("visible", True) else 0,
                1 if node.get("registered", False) else 0,
                1 if node.get("planned", False) else 0,
                _json(metadata),
                node.get("created_at") or now,
                node.get("updated_at") or now,
            ),
        )

    def _ensure_agent_from_org_node(self, conn: sqlite3.Connection, node: dict, now: str) -> None:
        agent_id = node.get("agent_id")
        if not agent_id:
            return
        existing = conn.execute("SELECT id FROM agents WHERE id=?", (agent_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE agents
                SET name=COALESCE(NULLIF(name, ''), ?),
                    display_name=COALESCE(NULLIF(display_name, ''), ?),
                    emoji=COALESCE(NULLIF(emoji, ''), ?),
                    visible_in_org=?,
                    updated_at=COALESCE(updated_at, ?)
                WHERE id=?
                """,
                (
                    node.get("name", agent_id),
                    node.get("name", agent_id),
                    node.get("emoji", ""),
                    1 if node.get("visible", True) else 0,
                    now,
                    agent_id,
                ),
            )
            return
        agent_type = node.get("node_type", "agent")
        self._upsert_agent(conn, {
            "id": agent_id,
            "name": node.get("name", agent_id),
            "display_name": node.get("name", agent_id),
            "agent_type": agent_type,
            "role": node.get("title", ""),
            "emoji": node.get("emoji", ""),
            "category": self._category_for_org_node(node),
            "enabled": bool(node.get("registered", True)),
            "visible": True,
            "visible_in_org": bool(node.get("visible", True)),
            "is_clone": "-" in agent_id and any(part in agent_id for part in ("leonardo", "raphael", "donatello", "michelangelo")),
            "source": "agent-organization",
            "metadata": {"org_node_id": node.get("id")},
            "created_at": now,
            "updated_at": now,
        }, now)

    def _category_for_org_node(self, node: dict) -> str:
        title = str(node.get("title", "") or "")
        node_id = str(node.get("id", "") or "")
        parent_id = str(node.get("parent_id", "") or "")
        if node.get("node_type") == "assistant":
            return "assistant"
        if parent_id == "project-managers" or "PM" in title:
            return "pm"
        if parent_id == "ninja-turtles":
            return "developer"
        if parent_id == "support":
            return "support"
        if node_id == "optimus":
            return "coordinator"
        return "agent"

    def _upsert_device(self, conn: sqlite3.Connection, device: dict, now: str) -> None:
        metadata = {
            key: value
            for key, value in device.items()
            if key not in {
                "id", "name", "ip", "os", "role", "status", "location", "description",
                "specs", "ports", "assigned_agents", "metadata", "created_at", "updated_at",
            }
        }
        explicit_metadata = device.get("metadata") if isinstance(device.get("metadata"), dict) else {}
        metadata.update(explicit_metadata)
        conn.execute(
            """
            INSERT OR REPLACE INTO devices
            (id, name, ip, os, role, status, location, description, specs, ports, assigned_agents, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device.get("id"),
                device.get("name", device.get("id", "")),
                device.get("ip", ""),
                device.get("os", "Unknown"),
                device.get("role", "Unknown"),
                device.get("status", "unknown"),
                device.get("location", ""),
                device.get("description", ""),
                _json(device.get("specs", {})),
                _json(device.get("ports", [])),
                _json(device.get("assigned_agents", [])),
                _json(metadata),
                device.get("created_at") or now,
                device.get("updated_at") or now,
            ),
        )

    def _insert_device_health_record(self, conn: sqlite3.Connection, device_id: str, record: dict) -> None:
        checked_at = record.get("checked_at") or _now_iso()
        record_id = record.get("id") or f"health-{device_id}-{checked_at.replace(':', '').replace('+', 'Z')}"
        metadata = {
            key: value
            for key, value in record.items()
            if key not in {"id", "device_id", "ip", "ping_success", "ports", "status", "response_time_ms", "checked_at", "metadata"}
        }
        explicit_metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        metadata.update(explicit_metadata)
        conn.execute(
            """
            INSERT OR REPLACE INTO device_health_records
            (id, device_id, ip, ping_success, ports, status, response_time_ms, checked_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                record.get("device_id") or device_id,
                record.get("ip", ""),
                1 if record.get("ping_success") else 0,
                _json(record.get("ports", [])),
                record.get("status", ""),
                record.get("response_time_ms"),
                checked_at,
                _json(metadata),
            ),
        )

    def load_projects_document(self) -> dict:
        with self.connect() as conn:
            project_rows = conn.execute("SELECT * FROM projects ORDER BY created_at, id").fetchall()
            projects = []
            for project_row in project_rows:
                project = self._project_document_row(project_row)
                self._hydrate_typed_project_specs(conn, project)
                task_rows = conn.execute(
                    "SELECT * FROM project_tasks WHERE project_id=? ORDER BY created_at, id",
                    (project["id"],),
                ).fetchall()
                tasks = []
                for task_row in task_rows:
                    task = self._task_document_row(task_row)
                    point_rows = conn.execute(
                        "SELECT * FROM development_points WHERE task_id=? ORDER BY created_at, id",
                        (task["id"],),
                    ).fetchall()
                    task["development_points"] = [self._point_document_row(point_row) for point_row in point_rows]
                    tasks.append(task)
                project["tasks"] = tasks
                projects.append(project)
            logs = [
                self._log_document_row(row)
                for row in conn.execute("SELECT * FROM project_logs ORDER BY created_at, id").fetchall()
            ]
            return {"version": 2, "last_updated": _now_iso(), "projects": projects, "logs": logs}

    def save_projects_document(self, data: dict) -> dict:
        projects = data.get("projects", [])
        logs = data.get("logs", [])
        with self.connect() as conn:
            # Keep stable rows while the document-shaped compatibility API is in
            # use. This prevents unrelated runs and audit records from observing
            # an empty project store during each update.
            conn.execute("BEGIN IMMEDIATE")
            task_count, point_count = self._insert_project_document(conn, projects, logs)
            self._delete_missing_ids(
                conn,
                "projects",
                "id",
                [project.get("id") for project in projects if project.get("id")],
            )
            self._delete_missing_ids(
                conn,
                "project_logs",
                "id",
                [log.get("id") for log in logs if log.get("id")],
            )
            self._refresh_sources(conn, {
                "projects": len(projects),
                "tasks": task_count,
                "development_points": point_count,
                "logs": len(logs),
                "available": True,
                "source_of_truth": "unified-sqlite",
            })
        return {"projects": len(projects), "tasks": task_count, "development_points": point_count, "logs": len(logs)}

    def _delete_missing_ids(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        id_column: str,
        incoming_ids: list[str],
        *,
        scope_column: str = "",
        scope_value: str = "",
    ) -> None:
        """Delete rows omitted from a complete document, optionally in one project."""
        scope_sql = f" WHERE {scope_column}=?" if scope_column else ""
        scope_params: list[Any] = [scope_value] if scope_column else []
        if not incoming_ids:
            conn.execute(f"DELETE FROM {table_name}{scope_sql}", scope_params)
            return
        placeholders = ",".join("?" for _ in incoming_ids)
        connector = " AND " if scope_column else " WHERE "
        conn.execute(
            f"DELETE FROM {table_name}{scope_sql}{connector}{id_column} NOT IN ({placeholders})",
            [*scope_params, *incoming_ids],
        )

    def _insert_project_document(self, conn: sqlite3.Connection, projects: list[dict], logs: list[dict]) -> tuple[int, int]:
        task_count = 0
        point_count = 0
        for project in projects:
            project_id = project.get("id")
            if not project_id:
                continue
            context = project.get("context") if isinstance(project.get("context"), dict) else {}
            project_type = project.get("project_type") or project.get("type") or context.get("project_type") or "software"
            design_doc = project.get("design_doc") if isinstance(project.get("design_doc"), dict) else {}
            document_spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
            conn.execute(
                """
                INSERT INTO projects
                (id, name, description, project_type, status, priority, owner_agent, project_manager_agent, progress, current_phase, context, design_doc, document_spec, created_at, updated_at, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    project_type=excluded.project_type,
                    status=excluded.status,
                    priority=excluded.priority,
                    owner_agent=excluded.owner_agent,
                    project_manager_agent=excluded.project_manager_agent,
                    progress=excluded.progress,
                    current_phase=excluded.current_phase,
                    context=excluded.context,
                    design_doc=excluded.design_doc,
                    document_spec=excluded.document_spec,
                    updated_at=excluded.updated_at,
                    source_id=excluded.source_id
                """,
                (
                    project_id,
                    project.get("name", ""),
                    project.get("description", ""),
                    project_type,
                    project.get("status", ""),
                    project.get("priority", ""),
                    project.get("owner_agent", ""),
                    project.get("project_manager_agent") or project.get("owner_agent", "") or "optimus",
                    float(project.get("progress") or 0),
                    project.get("current_phase", ""),
                    _json(context),
                    _json(design_doc),
                    _json(document_spec),
                    project.get("created_at"),
                    project.get("updated_at"),
                    project.get("source_id") or "unified-sqlite",
                ),
            )
            # Typed project documents are scoped to one project, so replacing
            # their derived rows does not disturb other projects or work runs.
            conn.execute("DELETE FROM document_assets WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM document_sections WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM document_project_specs WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM software_project_specs WHERE project_id=?", (project_id,))
            self._insert_typed_project_specs(conn, project_id, project_type, design_doc, document_spec, project.get("updated_at"))
            incoming_task_ids: list[str] = []
            incoming_point_ids: list[str] = []
            for task in project.get("tasks", []):
                task_id = task.get("id")
                if not task_id:
                    continue
                incoming_task_ids.append(task_id)
                task_count += 1
                task_context = task.get("context") if isinstance(task.get("context"), dict) else {}
                conn.execute(
                    """
                    INSERT INTO project_tasks
                    (id, project_id, type, title, description, assignee_agent, assignee_agent_id, status, priority, progress, dependencies, acceptance_criteria, context, result_summary, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        project_id=excluded.project_id,
                        type=excluded.type,
                        title=excluded.title,
                        description=excluded.description,
                        assignee_agent=excluded.assignee_agent,
                        assignee_agent_id=excluded.assignee_agent_id,
                        status=excluded.status,
                        priority=excluded.priority,
                        progress=excluded.progress,
                        dependencies=excluded.dependencies,
                        acceptance_criteria=excluded.acceptance_criteria,
                        context=excluded.context,
                        result_summary=excluded.result_summary,
                        updated_at=excluded.updated_at
                    """,
                    (
                        task_id,
                        project_id,
                        task.get("type") or task_context.get("task_type") or ("writing" if project_type == "document" else "development"),
                        task.get("title", ""),
                        task.get("description", ""),
                        task.get("assignee_agent", ""),
                        task.get("assignee_agent_id") or task.get("assignee_agent", ""),
                        task.get("status", ""),
                        task.get("priority", ""),
                        float(task.get("progress") or 0),
                        _json(task.get("dependencies", [])),
                        _json(task.get("acceptance_criteria", [])),
                        _json(task_context),
                        task.get("result_summary", ""),
                        task.get("created_at"),
                        task.get("updated_at"),
                    ),
                )
                for point in task.get("development_points", []):
                    point_id = point.get("id")
                    if not point_id:
                        continue
                    incoming_point_ids.append(point_id)
                    point_count += 1
                    conn.execute(
                        """
                        INSERT INTO development_points
                        (id, task_id, project_id, title, description, status, weight, assigned_agent, completion_evidence, checklist, context, completed_at, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            task_id=excluded.task_id,
                            project_id=excluded.project_id,
                            title=excluded.title,
                            description=excluded.description,
                            status=excluded.status,
                            weight=excluded.weight,
                            assigned_agent=excluded.assigned_agent,
                            completion_evidence=excluded.completion_evidence,
                            checklist=excluded.checklist,
                            context=excluded.context,
                            completed_at=excluded.completed_at,
                            updated_at=excluded.updated_at
                        """,
                        (
                            point_id,
                            task_id,
                            project_id,
                            point.get("title", ""),
                            point.get("description", ""),
                            point.get("status", ""),
                            float(point.get("weight") or 1),
                            point.get("assigned_agent", ""),
                            point.get("completion_evidence", ""),
                            _json(point.get("checklist", [])),
                            _json(point.get("context", {})),
                            point.get("completed_at"),
                            point.get("created_at"),
                            point.get("updated_at"),
                        ),
                    )
            self._delete_missing_ids(
                conn,
                "development_points",
                "id",
                incoming_point_ids,
                scope_column="project_id",
                scope_value=project_id,
            )
            self._delete_missing_ids(
                conn,
                "project_tasks",
                "id",
                incoming_task_ids,
                scope_column="project_id",
                scope_value=project_id,
            )
        for log in logs:
            log_id = log.get("id")
            if not log_id:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO project_logs
                (id, project_id, task_id, agent_id, action, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    log.get("project_id"),
                    log.get("task_id"),
                    log.get("agent_id"),
                    log.get("action"),
                    log.get("content"),
                    log.get("created_at"),
                ),
            )
        return task_count, point_count

    def _insert_typed_project_specs(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        project_type: str,
        design_doc: dict,
        document_spec: dict,
        updated_at: str | None,
    ) -> None:
        if project_type == "document":
            chapters = document_spec.get("chapters") if isinstance(document_spec.get("chapters"), list) else []
            assets = document_spec.get("assets") if isinstance(document_spec.get("assets"), list) else []
            conn.execute(
                """
                INSERT OR REPLACE INTO document_project_specs
                (project_id, document_type, writing_goal, target_audience, outline, chapter_plan, image_plan, reference_plan, source_word, working_markdown, section_links, sync_status, output_format, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    document_spec.get("document_type", ""),
                    document_spec.get("writing_goal", ""),
                    document_spec.get("target_audience", ""),
                    _json(document_spec.get("outline", [])),
                    _json(chapters),
                    _json(assets),
                    _json(document_spec.get("references", [])),
                    _json(document_spec.get("source_word", {})),
                    _json(document_spec.get("working_markdown", {})),
                    _json(document_spec.get("section_links", [])),
                    _json(document_spec.get("sync_status", {})),
                    document_spec.get("output_format", ""),
                    updated_at,
                ),
            )
            section_id_by_title: dict[str, str] = {}
            for index, chapter in enumerate(chapters):
                if not isinstance(chapter, dict):
                    chapter = {"title": str(chapter)}
                section_id = chapter.get("id") or f"{project_id}-section-{index + 1}"
                title = chapter.get("title", "")
                if title:
                    section_id_by_title[title] = section_id
                conn.execute(
                    """
                    INSERT OR REPLACE INTO document_sections
                    (id, project_id, parent_id, title, summary, content_brief, order_index, status, assigned_agent_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section_id,
                        project_id,
                        chapter.get("parent_id", ""),
                        title,
                        chapter.get("summary", ""),
                        chapter.get("main_content") or chapter.get("content_brief", ""),
                        int(chapter.get("order_index") if chapter.get("order_index") is not None else index),
                        chapter.get("status", "planning"),
                        chapter.get("assigned_agent") or chapter.get("assigned_agent_id", ""),
                        _json({
                            "key_points": chapter.get("key_points", []),
                            "outline_items": chapter.get("outline_items", []),
                            "subsections": chapter.get("subsections", []),
                            "required_assets": chapter.get("required_assets", []),
                            "images": chapter.get("images", []),
                        }),
                    ),
                )
            for index, asset in enumerate(assets):
                if not isinstance(asset, dict):
                    asset = {"title": str(asset)}
                section_id = asset.get("section_id") or asset.get("chapter_id") or section_id_by_title.get(asset.get("chapter_title", ""), "")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO document_assets
                    (id, project_id, section_id, type, title, description, file_path, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset.get("id") or f"{project_id}-asset-{index + 1}",
                        project_id,
                        section_id or None,
                        asset.get("type", "image"),
                        asset.get("title", ""),
                        asset.get("description", ""),
                        asset.get("file_path", ""),
                        asset.get("status", "planned"),
                        _json({
                            "chapter_title": asset.get("chapter_title", ""),
                            "order_index": asset.get("order_index", index),
                        }),
                    ),
                )
            return

        conn.execute(
            """
            INSERT OR REPLACE INTO software_project_specs
            (project_id, requirements, design_doc, architecture, database_design, api_design, frontend_design, test_plan, deployment_plan, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                _json(design_doc.get("usage_requirements", [])),
                _json(design_doc),
                _json(design_doc.get("system_architecture", {})),
                _json(design_doc.get("data_structure", {})),
                _json(design_doc.get("api_interfaces", [])),
                _json(design_doc.get("frontend_design", {})),
                _json(design_doc.get("test_plan", [])),
                _json(design_doc.get("deployment_plan", [])),
                updated_at,
            ),
        )

    def schema_summary(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        owns_connection = conn is None
        if owns_connection:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
        try:
            tables = []
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
                name = row["name"]
                tables.append({"name": name, "rows": self._table_count(conn, name)})
            return tables
        finally:
            if owns_connection:
                conn.close()

    def overview(self) -> dict:
        with self.connect() as conn:
            if not conn.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]:
                self._refresh_sources(conn, {"projects": 0, "tasks": 0, "development_points": 0, "logs": 0, "available": os.path.exists(PROJECTS_V3_FILE)})
            return {
                "database": {"path": self.db_path, "status": "ready", "schema": self.schema_summary(conn)},
                "totals": {
                    "projects": self._table_count(conn, "projects"),
                    "tasks": self._table_count(conn, "project_tasks"),
                    "development_points": self._table_count(conn, "development_points"),
                    "logs": self._table_count(conn, "project_logs"),
                    "frontend_pages": self._table_count(conn, "frontend_pages"),
                    "data_sources": self._table_count(conn, "data_sources"),
                    "storage_backups": self._table_count(conn, "storage_backups"),
                    "schema_migrations": self._table_count(conn, "schema_migrations"),
                    "audit_logs": self._table_count(conn, "audit_logs"),
                    "agents": self._table_count(conn, "agents"),
                    "agent_org_nodes": self._table_count(conn, "agent_org_nodes"),
                    "agent_runtime_status": self._table_count(conn, "agent_runtime_status"),
                    "agent_assignments": self._table_count(conn, "agent_assignments"),
                    "agent_skills": self._table_count(conn, "agent_skills"),
                    "agent_memories": self._table_count(conn, "agent_memories"),
                    "devices": self._table_count(conn, "devices"),
                    "device_health_records": self._table_count(conn, "device_health_records"),
                },
                "data_sources": self.list_sources(conn),
                "frontend_pages": self.list_pages(conn),
                "recent_backups": self.list_backups(5),
                "updated_at": _now_iso(),
            }

    def list_sources(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        owns_connection = conn is None
        if owns_connection:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM data_sources ORDER BY id").fetchall()
            return [self._source_row(row) for row in rows]
        finally:
            if owns_connection:
                conn.close()

    def list_pages(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        owns_connection = conn is None
        if owns_connection:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM frontend_pages ORDER BY sort_order, id").fetchall()
            return [self._page_row(row) for row in rows]
        finally:
            if owns_connection:
                conn.close()

    def update_page(self, page_id: str, payload: dict) -> dict | None:
        allowed = {"title", "nav_label", "status", "sort_order", "metadata"}
        updates = {key: value for key, value in payload.items() if key in allowed and value is not None}
        if not updates:
            return self.get_page(page_id)
        updates["updated_at"] = _now_iso()
        if "metadata" in updates:
            updates["metadata"] = _json(updates["metadata"])
        fields = ", ".join(f"{key}=?" for key in updates)
        values = list(updates.values())
        values.append(page_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE frontend_pages SET {fields} WHERE id=?", values)
        return self.get_page(page_id)

    def get_page(self, page_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM frontend_pages WHERE id=?", (page_id,)).fetchone()
            return self._page_row(row) if row else None

    def list_projects(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT p.*,
                       COUNT(DISTINCT t.id) AS task_count,
                       COUNT(DISTINCT dp.id) AS development_point_count
                FROM projects p
                LEFT JOIN project_tasks t ON t.project_id = p.id
                LEFT JOIN development_points dp ON dp.project_id = p.id
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.name
                """
            ).fetchall()
            return [self._project_row(row) for row in rows]

    def _source_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "source_type": row["source_type"],
            "path": row["path"],
            "status": row["status"],
            "record_count": row["record_count"],
            "last_synced_at": row["last_synced_at"],
            "metadata": _loads(row["metadata"], {}),
        }

    def _page_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "nav_label": row["nav_label"],
            "view_key": row["view_key"],
            "source_file": row["source_file"],
            "api_dependencies": _loads(row["api_dependencies"], []),
            "status": row["status"],
            "sort_order": row["sort_order"],
            "metadata": _loads(row["metadata"], {}),
            "updated_at": row["updated_at"],
        }

    def _hydrate_typed_project_specs(self, conn: sqlite3.Connection, project: dict) -> None:
        project_type = project.get("project_type") or "software"
        if project_type == "document":
            spec_row = conn.execute("SELECT * FROM document_project_specs WHERE project_id=?", (project["id"],)).fetchone()
            section_rows = conn.execute(
                "SELECT * FROM document_sections WHERE project_id=? ORDER BY order_index, id",
                (project["id"],),
            ).fetchall()
            asset_rows = conn.execute(
                "SELECT * FROM document_assets WHERE project_id=? ORDER BY rowid",
                (project["id"],),
            ).fetchall()
            sections = []
            for row in section_rows:
                metadata = _loads(row["metadata"], {})
                sections.append({
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "parent_id": row["parent_id"] or "",
                    "title": row["title"] or "",
                    "summary": row["summary"] or "",
                    "main_content": row["content_brief"] or "",
                    "content_brief": row["content_brief"] or "",
                    "order_index": row["order_index"],
                    "status": row["status"] or "planning",
                    "assigned_agent": row["assigned_agent_id"] or "",
                    "assigned_agent_id": row["assigned_agent_id"] or "",
                    "key_points": metadata.get("key_points", []),
                    "outline_items": metadata.get("outline_items", []),
                    "subsections": metadata.get("subsections", []),
                    "required_assets": metadata.get("required_assets", []),
                    "images": metadata.get("images", []),
                })
            assets = []
            for row in asset_rows:
                metadata = _loads(row["metadata"], {})
                assets.append({
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "chapter_id": row["section_id"] or "",
                    "section_id": row["section_id"] or "",
                    "chapter_title": metadata.get("chapter_title", ""),
                    "type": row["type"] or "image",
                    "title": row["title"] or "",
                    "description": row["description"] or "",
                    "file_path": row["file_path"] or "",
                    "status": row["status"] or "planned",
                    "order_index": metadata.get("order_index", 0),
                })
            if spec_row:
                typed_spec = {
                    "document_type": spec_row["document_type"] or "",
                    "writing_goal": spec_row["writing_goal"] or "",
                    "target_audience": spec_row["target_audience"] or "",
                    "outline": _loads(spec_row["outline"], []),
                    "chapters": sections or _loads(spec_row["chapter_plan"], []),
                    "assets": assets or _loads(spec_row["image_plan"], []),
                    "references": _loads(spec_row["reference_plan"], []),
                    "source_word": _loads(spec_row["source_word"], {}),
                    "working_markdown": _loads(spec_row["working_markdown"], {}),
                    "section_links": _loads(spec_row["section_links"], []),
                    "sync_status": _loads(spec_row["sync_status"], {}),
                    "output_format": spec_row["output_format"] or "",
                }
                project["document_spec"] = {
                    **(project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}),
                    **typed_spec,
                }
            return

        spec_row = conn.execute("SELECT * FROM software_project_specs WHERE project_id=?", (project["id"],)).fetchone()
        if spec_row:
            design_doc = _loads(spec_row["design_doc"], project.get("design_doc", {}))
            design_doc.setdefault("usage_requirements", _loads(spec_row["requirements"], []))
            design_doc.setdefault("system_architecture", _loads(spec_row["architecture"], {}))
            design_doc.setdefault("data_structure", _loads(spec_row["database_design"], {}))
            design_doc.setdefault("api_interfaces", _loads(spec_row["api_design"], []))
            design_doc.setdefault("frontend_design", _loads(spec_row["frontend_design"], {}))
            design_doc.setdefault("test_plan", _loads(spec_row["test_plan"], []))
            design_doc.setdefault("deployment_plan", _loads(spec_row["deployment_plan"], []))
            project["design_doc"] = design_doc

    def _project_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "project_type": row["project_type"] if "project_type" in row.keys() else "software",
            "status": row["status"],
            "priority": row["priority"],
            "owner_agent": row["owner_agent"],
            "project_manager_agent": row["project_manager_agent"] if "project_manager_agent" in row.keys() else "",
            "progress": row["progress"],
            "current_phase": row["current_phase"],
            "context": _loads(row["context"], {}),
            "document_spec": _loads(row["document_spec"], {}) if "document_spec" in row.keys() else {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "source_id": row["source_id"],
            "task_count": row["task_count"],
            "development_point_count": row["development_point_count"],
        }

    def _project_document_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "project_type": row["project_type"] if "project_type" in row.keys() else "software",
            "type": row["project_type"] if "project_type" in row.keys() else "software",
            "status": row["status"] or "",
            "priority": row["priority"] or "",
            "owner_agent": row["owner_agent"] or "",
            "project_manager_agent": row["project_manager_agent"] if "project_manager_agent" in row.keys() else "",
            "progress": float(row["progress"] or 0),
            "current_phase": row["current_phase"] or "",
            "context": _loads(row["context"], {}),
            "design_doc": _loads(row["design_doc"], {}),
            "document_spec": _loads(row["document_spec"], {}) if "document_spec" in row.keys() else {},
            "tasks": [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "source_id": row["source_id"],
        }

    def _task_document_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "type": row["type"] if "type" in row.keys() else "development",
            "title": row["title"],
            "description": row["description"] or "",
            "assignee_agent": row["assignee_agent"] or "",
            "assignee_agent_id": row["assignee_agent_id"] if "assignee_agent_id" in row.keys() else (row["assignee_agent"] or ""),
            "status": row["status"] or "",
            "priority": row["priority"] or "",
            "progress": float(row["progress"] or 0),
            "dependencies": _loads(row["dependencies"], []),
            "acceptance_criteria": _loads(row["acceptance_criteria"], []),
            "context": _loads(row["context"], {}),
            "result_summary": row["result_summary"] or "",
            "development_points": [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _point_document_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "title": row["title"],
            "description": row["description"] or "",
            "status": row["status"] or "",
            "weight": float(row["weight"] or 1),
            "assigned_agent": row["assigned_agent"] or "",
            "completion_evidence": row["completion_evidence"] or "",
            "checklist": _loads(row["checklist"], []),
            "context": _loads(row["context"], {}),
            "completed_at": row["completed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _log_document_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "task_id": row["task_id"],
            "agent_id": row["agent_id"],
            "action": row["action"],
            "content": row["content"],
            "created_at": row["created_at"],
        }

    def _backup_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "source_id": row["source_id"],
            "source_path": row["source_path"],
            "backup_path": row["backup_path"],
            "size_bytes": row["size_bytes"],
            "status": row["status"],
            "created_at": row["created_at"],
            "metadata": _loads(row["metadata"], {}),
        }

    def _audit_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "actor": row["actor"],
            "action": row["action"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "before_state": _loads(row["before_state"], None),
            "after_state": _loads(row["after_state"], None),
            "metadata": _loads(row["metadata"], {}),
            "created_at": row["created_at"],
        }

    def _agent_row(self, row: sqlite3.Row) -> dict:
        agent = {
            "id": row["id"],
            "name": row["name"],
            "display_name": row["display_name"] or row["name"],
            "agent_type": row["agent_type"] or "agent",
            "role": row["role"] or "",
            "emoji": row["emoji"] or "",
            "team": row["team"] or "",
            "category": row["category"] or "",
            "layer": row["layer"] or "",
            "group": row["agent_group"] or "",
            "status": row["status"] or "idle",
            "current_task": row["current_task"] or "",
            "device_id": row["device_id"] or "",
            "slogan": row["slogan"] or "",
            "avatar": row["avatar"] or "",
            "avatar_colors": _loads(row["avatar_colors"], []),
            "responsibilities": _loads(row["responsibilities"], []),
            "config": _loads(row["config"], {}),
            "memory": _loads(row["memory"], []),
            "enabled": bool(row["enabled"]),
            "visible": bool(row["visible"]),
            "visible_in_org": bool(row["visible_in_org"]),
            "is_clone": bool(row["is_clone"]),
            "clone_of_agent_id": row["clone_of_agent_id"] or "",
            "source": row["source"] or "local",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        metadata = _loads(row["metadata"], {})
        if isinstance(metadata, dict):
            agent.update(metadata)
        return agent

    def _agent_org_node_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "agent_id": row["agent_id"],
            "node_type": row["node_type"],
            "name": row["name"] or "",
            "emoji": row["emoji"] or "",
            "title": row["title"] or "",
            "order": row["sort_order"],
            "sort_order": row["sort_order"],
            "visible": bool(row["visible"]),
            "registered": bool(row["registered"]),
            "planned": bool(row["planned"]),
            "metadata": _loads(row["metadata"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _org_node_document(self, node: dict) -> dict:
        doc = {
            "id": node["id"],
            "node_type": node["node_type"],
            "name": node.get("name", ""),
            "registered": bool(node.get("registered", False)),
        }
        if node.get("parent_id"):
            doc["parent_id"] = node["parent_id"]
        if node.get("agent_id"):
            doc["agent_id"] = node["agent_id"]
        if node.get("emoji"):
            doc["emoji"] = node["emoji"]
        if node.get("title"):
            doc["title"] = node["title"]
        if node.get("sort_order") is not None:
            doc["order"] = node["sort_order"]
        if node.get("visible") is False:
            doc["visible"] = False
        if node.get("planned"):
            doc["planned"] = True
        metadata = node.get("metadata") or {}
        if metadata:
            doc["metadata"] = metadata
        return doc

    def _device_row(self, row: sqlite3.Row) -> dict:
        device = {
            "id": row["id"],
            "name": row["name"],
            "ip": row["ip"] or "",
            "os": row["os"] or "Unknown",
            "role": row["role"] or "Unknown",
            "status": row["status"] or "unknown",
            "location": row["location"] or "",
            "description": row["description"] or "",
            "specs": _loads(row["specs"], {}),
            "ports": _loads(row["ports"], []),
            "assigned_agents": _loads(row["assigned_agents"], []),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        metadata = _loads(row["metadata"], {})
        if isinstance(metadata, dict):
            device.update(metadata)
        return device

    def _device_health_row(self, row: sqlite3.Row) -> dict:
        record = {
            "id": row["id"],
            "device_id": row["device_id"],
            "ip": row["ip"] or "",
            "ping_success": bool(row["ping_success"]),
            "ports": _loads(row["ports"], []),
            "status": row["status"] or "",
            "checked_at": row["checked_at"],
            "response_time_ms": row["response_time_ms"],
        }
        metadata = _loads(row["metadata"], {})
        if isinstance(metadata, dict):
            record.update(metadata)
        return record


unified_data_manager = UnifiedDataManager()
