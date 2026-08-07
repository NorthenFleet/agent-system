"""Durable command-center state for the Optimus single-entry workflow."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator, Optional

from unified_data_manager import UNIFIED_DB_PATH

logger = logging.getLogger(__name__)


MISSION_STATES = (
    "received",
    "planning",
    "awaiting_approval",
    "dispatching",
    "running",
    "waiting_feedback",
    "evaluating",
    "completed",
    "failed",
    "cancelled",
)

TERMINAL_MISSION_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STEP_STATES = {"running"}
TERMINAL_STEP_STATES = {"completed", "failed", "cancelled"}

MISSION_TRANSITIONS = {
    "received": {"planning", "cancelled"},
    "planning": {"awaiting_approval", "waiting_feedback", "failed", "cancelled"},
    "awaiting_approval": {"dispatching", "planning", "cancelled"},
    "dispatching": {"running", "waiting_feedback", "cancelled"},
    "running": {"waiting_feedback", "evaluating", "cancelled"},
    "waiting_feedback": {"planning", "dispatching", "running", "cancelled"},
    "evaluating": {"completed", "waiting_feedback", "failed", "cancelled"},
    "completed": set(),
    "failed": {"planning", "cancelled"},
    "cancelled": set(),
}

APPROVE_PATTERN = re.compile(r"^(批准|同意|通过|approve)\b", re.IGNORECASE)
REJECT_PATTERN = re.compile(r"^(驳回|拒绝|reject)\b", re.IGNORECASE)
CANCEL_PATTERN = re.compile(r"^(取消|停止|终止|cancel)\b", re.IGNORECASE)
MISSION_ID_PATTERN = re.compile(r"(mission-[a-f0-9]{12})", re.IGNORECASE)

INTENT_TYPES = {
    "discussion",
    "software_project",
    "document_project",
    "mission_control",
    "clarification_required",
}
PROJECT_INTENT_TYPES = {"software_project", "document_project"}
PROJECT_TYPE_BY_INTENT = {
    "software_project": "software",
    "document_project": "document",
}
DISCUSSION_MARKERS = (
    "讨论",
    "分析",
    "给出方案",
    "方案如何",
    "是否可行",
    "评估一下",
    "怎么看",
    "解释",
    "介绍",
    "建议",
)
EXECUTION_MARKERS = (
    "执行",
    "开始开发",
    "开始实现",
    "开始撰写",
    "实施",
    "修复",
    "开发",
    "实现",
    "编写",
    "撰写",
    "生成",
    "创建",
    "部署",
    "修改",
    "优化",
    "重构",
)
SOFTWARE_MARKERS = (
    "程序",
    "代码",
    "接口",
    "api",
    "前端",
    "后端",
    "数据库",
    "bug",
    "软件",
    "3021",
    "openclaw",
    "one-sim",
)
DOCUMENT_MARKERS = (
    "论文",
    "文档",
    "报告",
    "文章",
    "章节",
    "专利",
    "教材",
    "课程",
    "课件",
    "手册",
)
COMMAND_CENTER_AGENT_NAMES = {
    "optimus": "擎天柱",
    "wheeljack": "千斤顶",
    "ironhide": "铁皮",
    "ultra-magnus": "通天晓",
    "ratchet": "救护车",
    "perceptor": "感知器",
    "jazz": "爵士",
    "shockwave": "震荡波",
    "soundwave": "声波",
    "bumblebee": "大黄蜂",
    "leonardo": "李奥纳多",
    "raphael": "拉斐尔",
    "donatello": "多纳泰罗",
    "michelangelo": "米开朗基罗",
    "command-center": "指挥中心",
}

EXECUTION_CONFIRM_PATTERN = re.compile(
    r"^(同意|确认|批准)?[，,：:\s]*(按(刚才|上述|这个)?方案)?[，,：:\s]*(执行|开始|继续|实施)",
    re.IGNORECASE,
)


class CommandCenterError(RuntimeError):
    pass


class MissionNotFound(CommandCenterError):
    pass


class InvalidMissionTransition(CommandCenterError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class CommandCenterService:
    def __init__(
        self,
        db_path: str = UNIFIED_DB_PATH,
        project_provider: Optional[Callable[[], list[dict[str, Any]]]] = None,
    ):
        self.db_path = db_path
        self.project_provider = project_provider
        self.ensure_schema()

    @contextmanager
    def connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=8)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=8000")
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS command_conversations (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    external_conversation_id TEXT NOT NULL,
                    user_external_id TEXT,
                    owner_user_id TEXT,
                    profile_user_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(channel, external_conversation_id)
                );

                CREATE TABLE IF NOT EXISTS command_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    mission_id TEXT,
                    direction TEXT NOT NULL,
                    external_message_id TEXT,
                    reply_to_external_message_id TEXT,
                    sender_id TEXT,
                    content TEXT NOT NULL,
                    message_type TEXT NOT NULL DEFAULT 'text',
                    intent_type TEXT NOT NULL DEFAULT '',
                    intent_confidence REAL NOT NULL DEFAULT 0,
                    intent_reason TEXT NOT NULL DEFAULT '',
                    execution_requested INTEGER NOT NULL DEFAULT 0,
                    routing_status TEXT NOT NULL DEFAULT '',
                    resolved_project_id TEXT,
                    reply_to_command_message_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES command_conversations(id)
                );

                CREATE TABLE IF NOT EXISTS command_external_user_bindings (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    external_user_id TEXT NOT NULL,
                    internal_user_id TEXT NOT NULL,
                    profile_user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(channel, external_user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_command_external_user_bindings_user
                    ON command_external_user_bindings(internal_user_id, status);

                CREATE TABLE IF NOT EXISTS orchestration_missions (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    source_message_id TEXT,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    project_id TEXT,
                    mission_type TEXT,
                    requested_by TEXT,
                    owner_user_id TEXT,
                    plan_version INTEGER NOT NULL DEFAULT 0,
                    current_step_id TEXT,
                    requires_approval INTEGER NOT NULL DEFAULT 1,
                    approval_status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES command_conversations(id),
                    FOREIGN KEY(source_message_id) REFERENCES command_messages(id)
                );

                CREATE INDEX IF NOT EXISTS idx_command_missions_status
                    ON orchestration_missions(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_command_missions_conversation
                    ON orchestration_missions(conversation_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS mission_plan_versions (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    rationale TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    raw_plan TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_by_agent_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, version)
                );

                CREATE TABLE IF NOT EXISTS mission_steps (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL,
                    order_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL DEFAULT 'general',
                    agent_id TEXT NOT NULL DEFAULT 'optimus',
                    executor TEXT NOT NULL DEFAULT 'openclaw',
                    status TEXT NOT NULL DEFAULT 'draft',
                    dependencies_json TEXT NOT NULL DEFAULT '[]',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    work_run_id TEXT,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, plan_version, order_index)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_steps_ready
                    ON mission_steps(status, lease_expires_at, updated_at);

                CREATE TABLE IF NOT EXISTS mission_approvals (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL,
                    decision TEXT NOT NULL DEFAULT 'pending',
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    decided_by TEXT,
                    comment TEXT,
                    external_message_id TEXT,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, plan_version)
                );

                CREATE TABLE IF NOT EXISTS mission_events (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    actor TEXT,
                    detail TEXT,
                    event_key TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_events_mission
                    ON mission_events(mission_id, created_at);

                CREATE TABLE IF NOT EXISTS mission_context_bindings (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL DEFAULT '',
                    purpose TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT 'optimus',
                    context_pack_id TEXT,
                    context_pack_version INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    query TEXT NOT NULL DEFAULT '',
                    summary TEXT,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    citation_count INTEGER NOT NULL DEFAULT 0,
                    source_types_json TEXT NOT NULL DEFAULT '[]',
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    retrieval_health_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, plan_version, step_id, purpose)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_context_bindings_scope
                    ON mission_context_bindings(mission_id, plan_version, purpose, step_id);

                CREATE TABLE IF NOT EXISTS notification_outbox (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT,
                    conversation_id TEXT,
                    command_message_id TEXT,
                    channel TEXT NOT NULL,
                    account_id TEXT NOT NULL DEFAULT 'optimus',
                    target TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    reply_to TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    locked_at TEXT,
                    lock_owner TEXT,
                    last_error TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(conversation_id) REFERENCES command_conversations(id),
                    FOREIGN KEY(command_message_id) REFERENCES command_messages(id),
                    UNIQUE(idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending
                    ON notification_outbox(status, next_attempt_at);

                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    id TEXT PRIMARY KEY,
                    outbox_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    external_message_id TEXT,
                    response TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(outbox_id) REFERENCES notification_outbox(id)
                );
                """
            )
            self._ensure_column(conn, "orchestration_missions", "owner_user_id", "TEXT")
            self._ensure_column(conn, "orchestration_missions", "mission_type", "TEXT")
            self._ensure_column(conn, "command_conversations", "owner_user_id", "TEXT")
            self._ensure_column(conn, "command_conversations", "profile_user_id", "TEXT")
            self._ensure_column(conn, "command_messages", "intent_type", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "command_messages", "intent_confidence", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "command_messages", "intent_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "command_messages", "execution_requested", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "command_messages", "routing_status", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "command_messages", "resolved_project_id", "TEXT")
            self._ensure_column(conn, "command_messages", "reply_to_command_message_id", "TEXT")
            self._ensure_column(conn, "mission_steps", "lease_token", "TEXT")
            self._ensure_column(conn, "mission_events", "event_key", "TEXT")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_command_missions_owner
                ON orchestration_missions(owner_user_id, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_command_conversations_owner
                ON command_conversations(owner_user_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_command_messages_intent
                ON command_messages(intent_type, routing_status, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_events_key
                ON mission_events(mission_id, event_key)
                WHERE event_key IS NOT NULL AND event_key != ''
                """
            )
            for mission in conn.execute(
                """
                SELECT id, requested_by, context_json
                FROM orchestration_missions
                WHERE owner_user_id IS NULL OR owner_user_id=''
                """
            ).fetchall():
                context = _loads(mission["context_json"], {})
                owner_user_id = str(
                    context.get("profile_user_id") or mission["requested_by"] or ""
                ).strip()
                if owner_user_id:
                    conn.execute(
                        "UPDATE orchestration_missions SET owner_user_id=? WHERE id=?",
                        (owner_user_id, mission["id"]),
                    )
            conn.execute(
                """
                UPDATE command_conversations
                SET owner_user_id=COALESCE(
                        NULLIF(owner_user_id, ''),
                        (SELECT internal_user_id FROM command_external_user_bindings bindings
                         WHERE bindings.channel=command_conversations.channel
                           AND bindings.external_user_id=command_conversations.user_external_id),
                        user_external_id
                    ),
                    profile_user_id=COALESCE(
                        NULLIF(profile_user_id, ''),
                        (SELECT profile_user_id FROM command_external_user_bindings bindings
                         WHERE bindings.channel=command_conversations.channel
                           AND bindings.external_user_id=command_conversations.user_external_id),
                        user_external_id
                    )
                WHERE owner_user_id IS NULL OR owner_user_id=''
                   OR profile_user_id IS NULL OR profile_user_id=''
                """
            )
            self._ensure_message_unique_index(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    description TEXT,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    "011_command_center",
                    "Create Optimus command center missions, approvals, steps, events, and outbox",
                    _iso(),
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (id, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    "013_command_center_context",
                    "Bind versioned context packs to mission plans and execution steps",
                    _iso(),
                ),
            )
            conn.execute(
                """
                UPDATE mission_approvals
                SET decision='cancelled',
                    decided_at=COALESCE(decided_at, ?),
                    decided_by=COALESCE(decided_by, 'command-center'),
                    comment=COALESCE(comment, 'Mission already terminal')
                WHERE decision='pending'
                  AND mission_id IN (
                      SELECT id FROM orchestration_missions
                      WHERE status IN ('completed', 'failed', 'cancelled')
                  )
                """,
                (_iso(),),
            )
            conn.execute(
                """
                UPDATE orchestration_missions
                SET approval_status='cancelled', updated_at=?
                WHERE status='cancelled' AND approval_status='pending'
                """,
                (_iso(),),
            )

    @staticmethod
    def _ensure_message_unique_index(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_command_messages_external
            ON command_messages(conversation_id, external_message_id)
            WHERE external_message_id IS NOT NULL AND external_message_id != ''
            """
        )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _list_projects(self) -> list[dict[str, Any]]:
        if self.project_provider is not None:
            return list(self.project_provider() or [])
        from project_manager import project_manager

        return list(project_manager.list_projects() or [])

    @staticmethod
    def _normalize_project_type(value: Any) -> str:
        clean = str(value or "").strip().lower()
        if clean in {"document", "doc", "writing", "paper"}:
            return "document"
        return "software"

    @staticmethod
    def _normalize_intent_type(value: Any) -> str:
        clean = str(value or "").strip().lower()
        aliases = {
            "software": "software_project",
            "development": "software_project",
            "document": "document_project",
            "writing": "document_project",
            "conversation": "discussion",
            "chat": "discussion",
            "clarification": "clarification_required",
            "control": "mission_control",
        }
        clean = aliases.get(clean, clean)
        return clean if clean in INTENT_TYPES else ""

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        clean = str(value or "").strip().lower()
        if clean in {"1", "true", "yes", "y", "on"}:
            return True
        if clean in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @staticmethod
    def _project_summary(project: dict[str, Any], score: int = 0) -> dict[str, Any]:
        return {
            "id": str(project.get("id") or ""),
            "name": str(project.get("name") or ""),
            "project_type": CommandCenterService._normalize_project_type(
                project.get("project_type") or project.get("type")
            ),
            "status": str(project.get("status") or ""),
            "score": score,
        }

    @staticmethod
    def _project_aliases(project: dict[str, Any]) -> list[str]:
        aliases = {
            str(project.get("id") or "").strip(),
            str(project.get("name") or "").strip(),
        }
        context = project.get("context") if isinstance(project.get("context"), dict) else {}
        for alias in context.get("aliases") or []:
            aliases.add(str(alias or "").strip())
        bindings = project.get("product_bindings") or context.get("product_bindings") or []
        for binding in bindings:
            if isinstance(binding, dict):
                aliases.add(str(binding.get("product_id") or "").strip())
        return sorted((alias for alias in aliases if alias), key=len, reverse=True)

    def validate_project_target(
        self,
        project_id: str,
        mission_type: str,
    ) -> dict[str, Any]:
        clean_id = str(project_id or "").strip()
        clean_type = self._normalize_project_type(mission_type)
        project = next(
            (item for item in self._list_projects() if str(item.get("id") or "") == clean_id),
            None,
        )
        if not project:
            raise CommandCenterError(f"project not found: {clean_id or 'empty'}")
        actual_type = self._normalize_project_type(
            project.get("project_type") or project.get("type")
        )
        if actual_type != clean_type:
            raise CommandCenterError(
                f"project type mismatch: expected {clean_type}, got {actual_type}"
            )
        if str(project.get("status") or "").lower() in {"archived", "deleted", "cancelled"}:
            raise CommandCenterError(f"project is not active: {clean_id}")
        return self._project_summary(project)

    def _resolve_project_target(
        self,
        *,
        project_id: str,
        mission_type: str,
        text: str,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
        projects = [
            project
            for project in self._list_projects()
            if self._normalize_project_type(
                project.get("project_type") or project.get("type")
            ) == mission_type
            and str(project.get("status") or "").lower()
            not in {"archived", "deleted", "cancelled"}
        ]
        clean_id = str(project_id or "").strip()
        if clean_id:
            project = next(
                (item for item in projects if str(item.get("id") or "") == clean_id),
                None,
            )
            if project:
                return project, [self._project_summary(project, 100)], ""
            return None, [self._project_summary(item) for item in projects[:8]], (
                f"项目 {clean_id} 不存在、已停用或类型与 {mission_type} 不一致"
            )

        normalized_text = " ".join(str(text or "").lower().split())
        scored: list[tuple[int, dict[str, Any]]] = []
        for project in projects:
            score = 0
            for alias in self._project_aliases(project):
                normalized_alias = " ".join(alias.lower().split())
                if normalized_alias and normalized_alias in normalized_text:
                    score = max(score, 100 if alias == project.get("id") else 80 + min(len(alias), 15))
            name_tokens = [
                token
                for token in re.split(r"[\s·._\-/]+", str(project.get("name") or "").lower())
                if len(token) >= 2
            ]
            score += 8 * sum(1 for token in name_tokens if token in normalized_text)
            if score:
                scored.append((score, project))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][1], [
                self._project_summary(project, score) for score, project in scored[:8]
            ], ""
        candidates = scored or [(0, project) for project in projects]
        return None, [
            self._project_summary(project, score) for score, project in candidates[:8]
        ], "无法唯一确定任务所属项目"

    @staticmethod
    def _heuristic_intent(text: str) -> tuple[str, bool, str, float]:
        lowered = str(text or "").lower()
        discussion = any(marker in lowered for marker in DISCUSSION_MARKERS)
        confirmed_execution = bool(EXECUTION_CONFIRM_PATTERN.search(lowered))
        execution = confirmed_execution or any(marker in lowered for marker in EXECUTION_MARKERS)
        software = any(marker in lowered for marker in SOFTWARE_MARKERS)
        document = any(marker in lowered for marker in DOCUMENT_MARKERS)
        if discussion and not confirmed_execution:
            suggested = "document_project" if document and not software else "software_project" if software else ""
            return "discussion", False, (
                f"方案或分析请求，仅讨论不执行{f'；潜在类型 {suggested}' if suggested else ''}"
            ), 0.78
        if software and document:
            return "clarification_required", execution, "软件与文档交付特征同时存在", 0.55
        if execution and software:
            return "software_project", True, "检测到软件开发交付与执行语义", 0.74
        if execution and document:
            return "document_project", True, "检测到文档交付与执行语义", 0.74
        if execution:
            return "clarification_required", True, "检测到执行要求，但无法判断项目类型", 0.52
        return "discussion", False, "未检测到需要启动项目任务的执行要求", 0.72

    @staticmethod
    def _recent_inbound_context(
        conn: sqlite3.Connection,
        conversation_id: str,
        current_text: str,
    ) -> str:
        rows = conn.execute(
            """
            SELECT content FROM command_messages
            WHERE conversation_id=? AND direction='inbound'
            ORDER BY created_at DESC LIMIT 6
            """,
            (conversation_id,),
        ).fetchall()
        values = [str(row["content"] or "").strip() for row in reversed(rows)]
        values.append(str(current_text or "").strip())
        return "\n".join(value for value in values if value)

    @staticmethod
    def _execution_objective(
        conn: sqlite3.Connection,
        conversation_id: str,
        current_text: str,
    ) -> str:
        if not EXECUTION_CONFIRM_PATTERN.search(str(current_text or "").strip()):
            return str(current_text or "").strip()
        row = conn.execute(
            """
            SELECT content FROM command_messages
            WHERE conversation_id=? AND direction='inbound'
              AND intent_type IN ('discussion','clarification_required')
            ORDER BY created_at DESC LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if not row:
            return str(current_text or "").strip()
        return f"{str(row['content'] or '').strip()}\n用户确认执行：{str(current_text or '').strip()}"


    @staticmethod
    def _task_tag_value(tags: list[str], prefix: str) -> str:
        return next((tag.split(":", 1)[1] for tag in tags if tag.startswith(prefix)), "")

    @staticmethod
    def _agent_name(agent_id: str) -> str:
        clean = str(agent_id or "").strip()
        return COMMAND_CENTER_AGENT_NAMES.get(clean, clean or "系统")

    @staticmethod
    def _serialize_ledger_task(task: Any) -> dict[str, Any]:
        item = task.to_dict() if hasattr(task, "to_dict") else dict(task)
        tags = item.get("tags") or []
        item["project_id"] = CommandCenterService._task_tag_value(tags, "project-id:")
        item["project_name"] = CommandCenterService._task_tag_value(tags, "project:")
        item["mission_id"] = CommandCenterService._task_tag_value(tags, "mission-id:")
        item["mission_type"] = CommandCenterService._task_tag_value(tags, "mission-type:")
        item["work_item_type"] = CommandCenterService._task_tag_value(tags, "entity:") or "task"
        item["agent_name"] = CommandCenterService._agent_name(str(item.get("assignee") or ""))
        return item

    def _load_task_ledger(self) -> list[dict[str, Any]]:
        try:
            from database import SessionLocal
            from models.v2_models import Task
        except Exception:
            return []
        db = SessionLocal()
        try:
            rows = db.query(Task).all()
            return [self._serialize_ledger_task(row) for row in rows]
        except Exception:
            logger.exception("Failed to load shared task ledger for command-center workbench")
            return []
        finally:
            db.close()

    def _sync_mission_ledger_safe(self, conn: sqlite3.Connection, mission_id: str) -> None:
        try:
            from services.project_task_sync import sync_command_center_mission_to_v2
            mission = self._serialize_mission(conn, self._require_mission(conn, mission_id))
            sync_command_center_mission_to_v2(mission)
        except Exception:
            logger.exception("Failed to sync command-center mission to task ledger: %s", mission_id)

    def _project_lookup(self) -> dict[str, dict[str, Any]]:
        return {str(project.get("id") or ""): project for project in self._list_projects()}

    def _workbench_item(
        self,
        mission: dict[str, Any],
        *,
        task_ledger: list[dict[str, Any]],
        project_lookup: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        mission_id = str(mission.get("id") or "")
        project_id = str(mission.get("project_id") or "")
        project = project_lookup.get(project_id) or {}
        context = mission.get("context") if isinstance(mission.get("context"), dict) else {}
        project_name = str(project.get("name") or context.get("project_name") or "")
        command_tasks = [task for task in task_ledger if task.get("mission_id") == mission_id]
        project_tasks = [
            task for task in task_ledger
            if project_id and task.get("project_id") == project_id and task.get("source") in {"project-dev", "project-doc"}
        ]
        linked_tasks = command_tasks or project_tasks[:8]
        steps = list(mission.get("steps") or [])
        active_step = next(
            (step for step in steps if step.get("status") in {"running", "ready", "draft", "failed"}),
            steps[-1] if steps else None,
        )
        current_agent_id = str((active_step or {}).get("agent_id") or "optimus")
        completed_steps = sum(1 for step in steps if step.get("status") == "completed")
        running_steps = sum(1 for step in steps if step.get("status") == "running")
        if mission.get("status") == "completed":
            progress = 100
        elif steps:
            progress = max(0, min(99, round((completed_steps + running_steps * 0.5) / len(steps) * 100)))
        else:
            progress = {"received": 5, "planning": 12, "awaiting_approval": 25, "dispatching": 35}.get(str(mission.get("status") or ""), 0)
        waiting_reason = ""
        if mission.get("status") == "awaiting_approval":
            waiting_reason = "等待您审批擎天柱生成的执行计划"
        elif mission.get("status") == "waiting_feedback":
            waiting_reason = mission.get("last_error") or "等待用户补充反馈后继续推进"
        elif mission.get("status") == "failed":
            waiting_reason = mission.get("last_error") or "任务执行失败，需要处理"
        return {
            "mission_id": mission_id,
            "mission_title": mission.get("title") or mission_id,
            "mission_status": mission.get("status"),
            "mission_type": mission.get("mission_type") or "software",
            "project_id": project_id,
            "project_name": project_name,
            "objective": mission.get("objective") or "",
            "approval_status": mission.get("approval_status") or "",
            "current_agent_id": current_agent_id,
            "current_agent_name": self._agent_name(current_agent_id),
            "active_step": active_step,
            "steps_summary": {
                "total": len(steps),
                "completed": completed_steps,
                "running": running_steps,
                "failed": sum(1 for step in steps if step.get("status") == "failed"),
                "pending": sum(1 for step in steps if step.get("status") in {"draft", "ready"}),
            },
            "linked_tasks": linked_tasks,
            "progress": progress,
            "updated_at": mission.get("updated_at"),
            "waiting_reason": waiting_reason,
        }

    def list_task_workbench(
        self,
        *,
        status: str = "",
        mission_type: str = "",
        project_id: str = "",
        agent_id: str = "",
        source: str = "",
        search: str = "",
        limit: int = 100,
        offset: int = 0,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        missions = self.list_missions(
            status=status,
            limit=max(1, min(int(limit), 500)),
            offset=max(0, int(offset)),
            owner_user_id=owner_user_id,
        )
        project_lookup = self._project_lookup()
        task_ledger = self._load_task_ledger()
        for mission in missions:
            if not any(task.get("mission_id") == mission.get("id") for task in task_ledger):
                with self.connect() as conn:
                    self._sync_mission_ledger_safe(conn, str(mission.get("id") or ""))
                task_ledger = self._load_task_ledger()
        items = [
            self._workbench_item(mission, task_ledger=task_ledger, project_lookup=project_lookup)
            for mission in missions
        ]
        if mission_type:
            items = [item for item in items if item["mission_type"] == mission_type]
        if project_id:
            items = [item for item in items if item["project_id"] == project_id]
        if agent_id:
            items = [
                item for item in items
                if item["current_agent_id"] == agent_id
                or any(task.get("assignee") == agent_id for task in item["linked_tasks"])
            ]
        if source:
            items = [item for item in items if any(task.get("source") == source for task in item["linked_tasks"])]
        if search:
            needle = search.lower()
            items = [
                item for item in items
                if needle in " ".join([
                    str(item.get("mission_title") or ""),
                    str(item.get("objective") or ""),
                    str(item.get("project_name") or ""),
                    str(item.get("current_agent_name") or ""),
                    " ".join(str(task.get("title") or "") for task in item["linked_tasks"]),
                ]).lower()
            ]
        return {"items": items, "total": len(items)}

    def _route_inbound(
        self,
        conn: sqlite3.Connection,
        *,
        conversation_id: str,
        text: str,
        metadata: dict[str, Any],
        related_mission: sqlite3.Row | None,
    ) -> dict[str, Any]:
        if related_mission:
            return {
                "intent_type": "mission_control",
                "confidence": 1.0,
                "reason": "消息明确引用或回复已有 mission",
                "execution_requested": False,
                "routing_status": "mission_control",
                "project": None,
                "project_candidates": [],
                "clarification_question": "",
                "objective": text,
            }

        if self._as_bool(metadata.get("_direct_mission")):
            direct_intent = self._normalize_intent_type(metadata.get("intent_type"))
            if direct_intent not in PROJECT_INTENT_TYPES:
                heuristic_type, _, _, _ = self._heuristic_intent(text)
                direct_intent = (
                    heuristic_type
                    if heuristic_type in PROJECT_INTENT_TYPES
                    else "software_project"
                )
            direct_project_id = str(metadata.get("project_id") or "").strip()
            return {
                "intent_type": direct_intent,
                "confidence": 1.0,
                "reason": "由已认证的项目任务入口显式创建",
                "execution_requested": True,
                "routing_status": "mission_created",
                "project": {
                    "id": direct_project_id,
                    "name": direct_project_id,
                    "project_type": PROJECT_TYPE_BY_INTENT[direct_intent],
                    "status": "active",
                },
                "project_candidates": [],
                "clarification_question": "",
                "objective": text,
            }

        hint = self._normalize_intent_type(
            metadata.get("intent_type") or metadata.get("intent_hint")
        )
        heuristic_type, heuristic_execution, heuristic_reason, heuristic_confidence = (
            self._heuristic_intent(text)
        )
        intent_type = hint or heuristic_type
        execution_requested = self._as_bool(
            metadata.get("execution_requested"),
            default=heuristic_execution,
        )
        try:
            confidence = float(metadata.get("intent_confidence", heuristic_confidence))
        except (TypeError, ValueError):
            confidence = heuristic_confidence
        confidence = max(0.0, min(confidence, 1.0))
        reason = str(metadata.get("intent_reason") or heuristic_reason).strip()[:1000]

        if intent_type == "mission_control":
            return {
                "intent_type": "clarification_required",
                "confidence": confidence,
                "reason": "任务控制消息未找到可关联的 mission",
                "execution_requested": False,
                "routing_status": "awaiting_clarification",
                "project": None,
                "project_candidates": [],
                "clarification_question": "请提供要操作的 mission 编号。",
                "objective": text,
            }

        if intent_type in PROJECT_INTENT_TYPES and not execution_requested:
            intent_type = "discussion"
            reason = f"{reason}；用户尚未明确要求执行"

        if intent_type == "discussion":
            return {
                "intent_type": intent_type,
                "confidence": confidence,
                "reason": reason,
                "execution_requested": False,
                "routing_status": "awaiting_response",
                "project": None,
                "project_candidates": [],
                "clarification_question": "",
                "objective": text,
            }

        if intent_type == "clarification_required" or (
            intent_type in PROJECT_INTENT_TYPES and confidence < 0.65
        ):
            return {
                "intent_type": "clarification_required",
                "confidence": confidence,
                "reason": reason,
                "execution_requested": execution_requested,
                "routing_status": "awaiting_clarification",
                "project": None,
                "project_candidates": [],
                "clarification_question": "这是一般讨论，还是需要执行的程序开发或文档撰写任务？",
                "objective": text,
            }

        mission_type = PROJECT_TYPE_BY_INTENT[intent_type]
        context_text = self._recent_inbound_context(conn, conversation_id, text)
        project, candidates, project_error = self._resolve_project_target(
            project_id=str(metadata.get("project_id") or ""),
            mission_type=mission_type,
            text=context_text,
        )
        if not project:
            names = "、".join(
                f"{item['name']}（{item['id']}）" for item in candidates[:5]
            )
            question = (
                f"请确认任务归属项目：{names}。" if names else "当前没有可用的同类型项目，请先创建项目。"
            )
            return {
                "intent_type": "clarification_required",
                "suggested_intent_type": intent_type,
                "confidence": confidence,
                "reason": project_error or reason,
                "execution_requested": True,
                "routing_status": "awaiting_clarification",
                "project": None,
                "project_candidates": candidates,
                "clarification_question": question,
                "objective": self._execution_objective(conn, conversation_id, text),
            }
        return {
            "intent_type": intent_type,
            "confidence": confidence,
            "reason": reason,
            "execution_requested": True,
            "routing_status": "mission_created",
            "project": project,
            "project_candidates": candidates,
            "clarification_question": "",
            "objective": self._execution_objective(conn, conversation_id, text),
        }

    def upsert_external_user_binding(
        self,
        *,
        channel: str,
        external_user_id: str,
        internal_user_id: str,
        profile_user_id: str,
        display_name: str = "",
        status: str = "active",
    ) -> dict[str, Any]:
        clean_channel = str(channel or "").strip().lower()
        clean_external = str(external_user_id or "").strip()
        clean_internal = str(internal_user_id or "").strip()
        clean_profile = str(profile_user_id or "").strip()
        clean_status = str(status or "active").strip().lower()
        if (
            not clean_channel
            or clean_channel == "dashboard"
            or not clean_external
            or not clean_internal
            or not clean_profile
        ):
            raise CommandCenterError(
                "external binding requires a non-dashboard channel and all user identifiers"
            )
        if clean_status not in {"active", "disabled"}:
            raise CommandCenterError(f"invalid external binding status: {status}")
        now = _iso()
        with self.connect(immediate=True) as conn:
            existing = conn.execute(
                """
                SELECT * FROM command_external_user_bindings
                WHERE channel=? AND external_user_id=?
                """,
                (clean_channel, clean_external),
            ).fetchone()
            binding_id = (
                existing["id"]
                if existing
                else f"external-binding-{uuid.uuid4().hex[:12]}"
            )
            conn.execute(
                """
                INSERT INTO command_external_user_bindings
                (id, channel, external_user_id, internal_user_id, profile_user_id,
                 display_name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel, external_user_id) DO UPDATE SET
                    internal_user_id=excluded.internal_user_id,
                    profile_user_id=excluded.profile_user_id,
                    display_name=excluded.display_name,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    binding_id,
                    clean_channel,
                    clean_external,
                    clean_internal,
                    clean_profile,
                    str(display_name or "").strip()[:200],
                    clean_status,
                    existing["created_at"] if existing else now,
                    now,
                ),
            )
            return dict(
                conn.execute(
                    """
                    SELECT * FROM command_external_user_bindings
                    WHERE channel=? AND external_user_id=?
                    """,
                    (clean_channel, clean_external),
                ).fetchone()
            )

    def list_external_user_bindings(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM command_external_user_bindings
                    ORDER BY channel, display_name, external_user_id
                    """
                ).fetchall()
            ]

    @staticmethod
    def _require_external_user_binding(
        conn: sqlite3.Connection,
        *,
        channel: str,
        external_user_id: str,
    ) -> sqlite3.Row:
        clean_external = str(external_user_id or "").strip()
        if not clean_external:
            raise CommandCenterError(
                f"{channel} command requires a verified non-empty sender identity"
            )
        row = conn.execute(
            """
            SELECT * FROM command_external_user_bindings
            WHERE channel=? AND external_user_id=? AND status='active'
            """,
            (str(channel or "").strip().lower(), clean_external),
        ).fetchone()
        if not row:
            raise CommandCenterError(
                f"external user is not mapped: {channel}:{clean_external}"
            )
        return row

    def process_inbound(
        self,
        *,
        channel: str,
        external_conversation_id: str,
        user_external_id: str,
        content: str,
        external_message_id: str = "",
        reply_to_external_message_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise CommandCenterError("message content is required")
        channel = str(channel or "feishu").strip().lower()
        conversation_key = str(external_conversation_id or user_external_id or "").strip()
        if not conversation_key:
            raise CommandCenterError("external conversation id is required")
        now = _iso()
        metadata = metadata or {}

        with self.connect(immediate=True) as conn:
            if channel == "dashboard":
                profile_user_id = str(
                    metadata.get("profile_user_id")
                    or metadata.get("context_user_id")
                    or user_external_id
                ).strip()
                owner_user_id = profile_user_id or str(user_external_id or "").strip()
                if not owner_user_id:
                    raise CommandCenterError(
                        "dashboard command requires an authenticated user identity"
                    )
            else:
                binding = self._require_external_user_binding(
                    conn,
                    channel=channel,
                    external_user_id=user_external_id,
                )
                profile_user_id = str(binding["profile_user_id"]).strip()
                owner_user_id = str(binding["internal_user_id"]).strip()

            conversation = conn.execute(
                """
                SELECT * FROM command_conversations
                WHERE channel=? AND external_conversation_id=?
                """,
                (channel, conversation_key),
            ).fetchone()
            if not conversation:
                conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO command_conversations
                    (id, channel, external_conversation_id, user_external_id,
                     owner_user_id, profile_user_id, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        channel,
                        conversation_key,
                        user_external_id or None,
                        owner_user_id,
                        profile_user_id,
                        _json(metadata),
                        now,
                        now,
                    ),
                )
            else:
                conversation_id = conversation["id"]
                conn.execute(
                    """
                    UPDATE command_conversations
                    SET user_external_id=COALESCE(NULLIF(?, ''), user_external_id),
                        owner_user_id=?, profile_user_id=?, metadata=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        user_external_id,
                        owner_user_id,
                        profile_user_id,
                        _json(metadata),
                        now,
                        conversation_id,
                    ),
                )

            if external_message_id:
                duplicate = conn.execute(
                    """
                    SELECT m.*, c.channel
                    FROM command_messages m
                    JOIN command_conversations c ON c.id=m.conversation_id
                    WHERE m.conversation_id=? AND m.external_message_id=?
                    """,
                    (conversation_id, external_message_id),
                ).fetchone()
                if duplicate:
                    mission = self._mission_from_message(conn, duplicate["id"])
                    return {
                        "action": "duplicate",
                        "message": self._serialize_message(duplicate),
                        "mission": self._serialize_mission(conn, mission) if mission else None,
                    }

            related_mission = self._resolve_related_mission(
                conn,
                conversation_id=conversation_id,
                content=text,
                reply_to_external_message_id=reply_to_external_message_id,
            )
            if (
                related_mission
                and channel != "dashboard"
                and (
                    not str(related_mission["requested_by"] or "").strip()
                    or str(related_mission["requested_by"] or "").strip()
                    != str(user_external_id or "").strip()
                )
            ):
                raise CommandCenterError(
                    "only the mission requester may approve, reject, cancel, or add feedback"
                )
            route = self._route_inbound(
                conn,
                conversation_id=conversation_id,
                text=text,
                metadata=metadata,
                related_mission=related_mission,
            )
            conn.execute(
                """
                UPDATE command_messages
                SET routing_status='resolved'
                WHERE conversation_id=? AND direction='inbound'
                  AND intent_type='clarification_required'
                  AND routing_status IN ('awaiting_clarification','clarification_sent')
                """,
                (conversation_id,),
            )
            message_id = f"msg-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO command_messages
                (id, conversation_id, mission_id, direction, external_message_id,
                 reply_to_external_message_id, sender_id, content, intent_type,
                 intent_confidence, intent_reason, execution_requested, routing_status,
                 resolved_project_id, metadata, created_at)
                VALUES (?, ?, ?, 'inbound', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    related_mission["id"] if related_mission else None,
                    external_message_id or None,
                    reply_to_external_message_id or None,
                    user_external_id or None,
                    text,
                    route["intent_type"],
                    route["confidence"],
                    route["reason"],
                    int(bool(route["execution_requested"])),
                    route["routing_status"],
                    (route.get("project") or {}).get("id") or None,
                    _json(metadata),
                    now,
                ),
            )

            if related_mission and APPROVE_PATTERN.search(text):
                mission = self._decide_approval(
                    conn,
                    related_mission,
                    decision="approved",
                    decided_by=user_external_id or "feishu-user",
                    comment=text,
                )
                return {
                    "action": "approved",
                    "message": self._get_message(conn, message_id),
                    "mission": self._serialize_mission(conn, mission),
                }

            if related_mission and REJECT_PATTERN.search(text):
                mission = self._decide_approval(
                    conn,
                    related_mission,
                    decision="rejected",
                    decided_by=user_external_id or "feishu-user",
                    comment=text,
                )
                return {
                    "action": "rejected",
                    "message": self._get_message(conn, message_id),
                    "mission": self._serialize_mission(conn, mission),
                }

            if related_mission and CANCEL_PATTERN.search(text):
                mission = self._cancel_mission(
                    conn,
                    related_mission,
                    actor=user_external_id or "feishu-user",
                    comment=text,
                )
                return {
                    "action": "cancelled",
                    "message": self._get_message(conn, message_id),
                    "mission": self._serialize_mission(conn, mission),
                }

            if related_mission:
                conn.execute(
                    "UPDATE command_messages SET mission_id=? WHERE id=?",
                    (related_mission["id"], message_id),
                )
                self._add_event(
                    conn,
                    related_mission["id"],
                    "feedback_received",
                    related_mission["status"],
                    related_mission["status"],
                    user_external_id or "feishu-user",
                    text,
                    {"message_id": message_id},
                )
                if related_mission["status"] == "waiting_feedback":
                    failed_steps = conn.execute(
                        """
                        SELECT COUNT(*) AS count FROM mission_steps
                        WHERE mission_id=? AND plan_version=? AND status='failed'
                        """,
                        (related_mission["id"], related_mission["plan_version"]),
                    ).fetchone()["count"]
                    next_status = "dispatching" if failed_steps else "planning"
                    if failed_steps:
                        conn.execute(
                            """
                            UPDATE mission_steps
                            SET status='ready', result_json='{}', lease_owner=NULL,
                                lease_token=NULL,
                                lease_expires_at=NULL, updated_at=?
                            WHERE mission_id=? AND plan_version=? AND status='failed'
                            """,
                            (now, related_mission["id"], related_mission["plan_version"]),
                        )
                    related_mission = self._transition(
                        conn,
                        related_mission,
                        next_status,
                        actor=user_external_id or "feishu-user",
                        detail="User feedback received; orchestration resumed",
                    )
                self._queue_notification(
                    conn,
                    mission=related_mission,
                    text=f"已收到对 {related_mission['id']} 的反馈，擎天柱会纳入后续执行。",
                    event_key=f"feedback-ack:{message_id}",
                    reply_to=external_message_id,
                )
                return {
                    "action": "feedback",
                    "message": self._get_message(conn, message_id),
                    "mission": self._serialize_mission(conn, related_mission),
                }

            if route["intent_type"] in {"discussion", "clarification_required"}:
                return {
                    "action": (
                        "discussion"
                        if route["intent_type"] == "discussion"
                        else "clarification"
                    ),
                    "message": self._get_message(conn, message_id),
                    "mission": None,
                    "intent": {
                        "type": route["intent_type"],
                        "suggested_type": route.get("suggested_intent_type", ""),
                        "confidence": route["confidence"],
                        "reason": route["reason"],
                        "execution_requested": route["execution_requested"],
                    },
                    "project_candidates": route.get("project_candidates") or [],
                    "clarification_question": route.get("clarification_question") or "",
                }

            mission_id = f"mission-{uuid.uuid4().hex[:12]}"
            objective = str(route.get("objective") or text).strip()
            title = str(metadata.get("title") or self._title_from_objective(objective)).strip()[:160]
            project_id = str((route.get("project") or {}).get("id") or "").strip()
            mission_type = PROJECT_TYPE_BY_INTENT[route["intent_type"]]
            reserve_planning = bool(metadata.get("_reserve_planning"))
            initial_status = "planning" if reserve_planning else "received"
            planning_owner = (
                str(
                    metadata.get("_planning_owner")
                    or user_external_id
                    or "dashboard-planner"
                ).strip()
                if reserve_planning
                else None
            )
            planning_lease_expires_at = (
                _iso(_now() + timedelta(seconds=120))
                if reserve_planning
                else None
            )
            mission_context = {
                "source": channel,
                "profile_user_id": profile_user_id,
                "mission_type": mission_type,
                "intent_decision": {
                    "type": route["intent_type"],
                    "confidence": route["confidence"],
                    "reason": route["reason"],
                    "execution_requested": route["execution_requested"],
                },
                "user_context": (
                    metadata.get("context")
                    if isinstance(metadata.get("context"), dict)
                    else {}
                ),
                "metadata": metadata,
            }
            conn.execute(
                """
                INSERT INTO orchestration_missions
                (id, conversation_id, source_message_id, title, objective, status,
                 project_id, mission_type, requested_by, owner_user_id, context_json,
                 lease_owner, lease_expires_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    conversation_id,
                    message_id,
                    title,
                    objective,
                    initial_status,
                    project_id or None,
                    mission_type,
                    user_external_id or None,
                    owner_user_id,
                    _json(mission_context),
                    planning_owner,
                    planning_lease_expires_at,
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE command_messages SET mission_id=? WHERE id=?",
                (mission_id, message_id),
            )
            mission = conn.execute(
                "SELECT * FROM orchestration_missions WHERE id=?",
                (mission_id,),
            ).fetchone()
            self._add_event(
                conn,
                mission_id,
                "mission_received",
                None,
                initial_status,
                user_external_id or "feishu-user",
                objective,
                {
                    "message_id": message_id,
                    "channel": channel,
                    "preplanned": reserve_planning,
                    "mission_type": mission_type,
                    "project_id": project_id,
                    "intent_confidence": route["confidence"],
                },
            )
            self._queue_notification(
                conn,
                mission=mission,
                text=(
                    f"已收到任务：{title}\n"
                    f"任务编号：{mission_id}\n"
                    "擎天柱正在梳理目标、风险和协作计划。计划生成后会请您批准，批准前不会执行。"
                ),
                event_key=f"received:{mission_id}",
                reply_to=external_message_id,
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            return {
                "action": "mission_created",
                "message": self._get_message(conn, message_id),
                "mission": self._serialize_mission(conn, mission),
                "intent": {
                    "type": route["intent_type"],
                    "confidence": route["confidence"],
                    "reason": route["reason"],
                    "execution_requested": True,
                },
            }

    def create_mission(
        self,
        *,
        objective: str,
        requested_by: str,
        project_id: str = "",
        mission_type: str = "",
        title: str = "",
        context: Optional[dict[str, Any]] = None,
        profile_user_id: str = "",
        reserve_planning: bool = False,
        planning_owner: str = "",
    ) -> dict[str, Any]:
        context_value = context or {}
        direct_type = str(
            mission_type
            or context_value.get("mission_type")
            or context_value.get("project_type")
            or ""
        ).strip()
        if not direct_type and project_id:
            project = next(
                (
                    item
                    for item in self._list_projects()
                    if str(item.get("id") or "") == str(project_id)
                ),
                None,
            )
            if project:
                direct_type = self._normalize_project_type(
                    project.get("project_type") or project.get("type")
                )
        direct_type = self._normalize_project_type(direct_type)
        return self.process_inbound(
            channel="dashboard",
            external_conversation_id=f"dashboard:{requested_by}",
            user_external_id=requested_by,
            content=objective,
            external_message_id=f"ui-{uuid.uuid4().hex}",
            metadata={
                "project_id": project_id,
                "title": title,
                "context": context_value,
                "intent_type": (
                    "document_project"
                    if direct_type == "document"
                    else "software_project"
                ),
                "execution_requested": True,
                "profile_user_id": profile_user_id
                or requested_by,
                "suppress_notification": True,
                "_direct_mission": True,
                "_reserve_planning": reserve_planning,
                "_planning_owner": planning_owner,
            },
        )["mission"]

    def create_preplanned_mission(
        self,
        *,
        objective: str,
        requested_by: str,
        plan: dict[str, Any],
        project_id: str = "",
        title: str = "",
        context: Optional[dict[str, Any]] = None,
        profile_user_id: str = "",
        auto_approve: bool = False,
        approved_by: str = "",
    ) -> dict[str, Any]:
        owner = requested_by or "dashboard-planner"
        mission = self.create_mission(
            objective=objective,
            requested_by=owner,
            project_id=project_id,
            title=title,
            context=context,
            profile_user_id=profile_user_id,
            reserve_planning=True,
            planning_owner=owner,
        )
        planned = self.save_plan(
            mission["id"],
            plan,
            created_by_agent_id=owner,
        )
        if not auto_approve:
            return planned
        return self.approve(
            mission["id"],
            decided_by=approved_by or owner,
            comment="项目迭代批次由项目经理面板批准执行",
        )

    def claim_planning_mission(
        self,
        owner: str,
        *,
        lease_seconds: int = 300,
    ) -> dict[str, Any] | None:
        now = _now()
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                """
                SELECT * FROM orchestration_missions
                WHERE status IN ('received', 'planning')
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ? OR lease_owner=?)
                ORDER BY created_at ASC LIMIT 1
                """,
                (_iso(now), owner),
            ).fetchone()
            if not row:
                return None
            previous = row["status"]
            conn.execute(
                """
                UPDATE orchestration_missions
                SET status='planning', lease_owner=?, lease_expires_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    owner,
                    _iso(now + timedelta(seconds=max(lease_seconds, 60))),
                    _iso(now),
                    row["id"],
                ),
            )
            self._add_event(
                conn,
                row["id"],
                "planning_started" if previous == "received" else "planning_resumed",
                previous,
                "planning",
                owner,
                "Optimus is producing an approval-gated plan",
                {},
            )
            return self._serialize_mission(
                conn,
                conn.execute("SELECT * FROM orchestration_missions WHERE id=?", (row["id"],)).fetchone(),
            )

    def save_plan(
        self,
        mission_id: str,
        plan: dict[str, Any],
        *,
        created_by_agent_id: str = "optimus",
    ) -> dict[str, Any]:
        steps = list(plan.get("steps") or [])
        if not steps:
            raise CommandCenterError("plan must include at least one step")
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            if mission["status"] not in {"planning", "waiting_feedback", "failed"}:
                raise InvalidMissionTransition(
                    f"cannot save plan while mission is {mission['status']}"
                )
            version = int(mission["plan_version"] or 0) + 1
            plan_id = f"plan-{uuid.uuid4().hex[:12]}"
            summary = str(plan.get("summary") or f"{len(steps)} 个协作步骤")
            conn.execute(
                """
                INSERT INTO mission_plan_versions
                (id, mission_id, version, summary, rationale, risk_level, raw_plan,
                 status, created_by_agent_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    plan_id,
                    mission_id,
                    version,
                    summary,
                    str(plan.get("rationale") or ""),
                    str(plan.get("risk_level") or "medium"),
                    _json(plan),
                    created_by_agent_id,
                    _iso(),
                ),
            )
            step_ids: dict[int, str] = {}
            for index, _step in enumerate(steps, start=1):
                step_ids[index] = f"step-{uuid.uuid4().hex[:12]}"
            for index, raw_step in enumerate(steps, start=1):
                order_index = int(raw_step.get("order_index") or index)
                dependency_ids = []
                for dependency in raw_step.get("depends_on") or []:
                    try:
                        dependency_index = int(dependency)
                    except (TypeError, ValueError):
                        continue
                    if dependency_index in step_ids and dependency_index != index:
                        dependency_ids.append(step_ids[dependency_index])
                conn.execute(
                    """
                    INSERT INTO mission_steps
                    (id, mission_id, plan_version, order_index, title, description,
                     task_type, agent_id, executor, status, dependencies_json,
                     input_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
                    """,
                    (
                        step_ids[index],
                        mission_id,
                        version,
                        order_index,
                        str(raw_step.get("title") or f"步骤 {index}"),
                        str(raw_step.get("description") or ""),
                        str(raw_step.get("task_type") or "general"),
                        str(raw_step.get("agent_id") or "optimus"),
                        str(raw_step.get("executor") or "openclaw"),
                        _json(dependency_ids),
                        _json(raw_step.get("input") or {}),
                        _iso(),
                    ),
                )
            approval_id = f"approval-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO mission_approvals
                (id, mission_id, plan_version, decision, requested_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (approval_id, mission_id, version, _iso()),
            )
            conn.execute(
                """
                UPDATE orchestration_missions
                SET status='awaiting_approval', plan_version=?, approval_status='pending',
                    lease_owner=NULL, lease_expires_at=NULL, last_error=NULL, updated_at=?
                WHERE id=?
                """,
                (version, _iso(), mission_id),
            )
            self._add_event(
                conn,
                mission_id,
                "plan_proposed",
                mission["status"],
                "awaiting_approval",
                created_by_agent_id,
                summary,
                {"version": version, "step_count": len(steps)},
            )
            updated = self._require_mission(conn, mission_id)
            lines = [
                f"任务 {mission_id} 的执行计划已生成（V{version}）",
                summary,
                "",
            ]
            for index, step in enumerate(steps, start=1):
                lines.append(
                    f"{index}. {step.get('title') or f'步骤 {index}'}"
                    f" · {step.get('agent_id') or 'optimus'}"
                )
            context_binding = conn.execute(
                """
                SELECT * FROM mission_context_bindings
                WHERE mission_id=? AND plan_version=? AND step_id='' AND purpose='planning'
                """,
                (mission_id, version),
            ).fetchone()
            lines.extend(
                [
                    "",
                    f"风险等级：{plan.get('risk_level') or 'medium'}",
                    (
                        f"背景快照：{context_binding['context_pack_id']} "
                        f"V{context_binding['context_pack_version']} · "
                        f"{context_binding['citation_count']} 条引用"
                        if context_binding and context_binding["context_pack_id"]
                        else "背景快照：检索降级，详细原因已记录"
                    ),
                    f"回复“批准 {mission_id}”开始执行；回复“驳回 {mission_id} + 意见”重新规划。",
                ]
            )
            self._queue_notification(
                conn,
                mission=updated,
                text="\n".join(lines),
                event_key=f"plan:{mission_id}:{version}",
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            return self._serialize_mission(conn, updated)

    def mark_planning_failed(self, mission_id: str, error: str, *, actor: str) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            conn.execute(
                """
                UPDATE orchestration_missions
                SET status='waiting_feedback', last_error=?, lease_owner=NULL,
                    lease_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (error[:4000], _iso(), mission_id),
            )
            self._add_event(
                conn,
                mission_id,
                "planning_failed",
                mission["status"],
                "waiting_feedback",
                actor,
                error[:1000],
                {},
            )
            updated = self._require_mission(conn, mission_id)
            self._queue_notification(
                conn,
                mission=updated,
                text=f"任务 {mission_id} 的计划生成遇到阻塞：{error[:600]}\n请补充信息或稍后重试。",
                event_key=f"planning-failed:{mission_id}:{updated['updated_at']}",
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            return self._serialize_mission(conn, updated)

    def approve(
        self,
        mission_id: str,
        *,
        decided_by: str,
        comment: str = "",
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            return self._serialize_mission(
                conn,
                self._decide_approval(
                    conn,
                    mission,
                    decision="approved",
                    decided_by=decided_by,
                    comment=comment,
                ),
            )

    def reject(
        self,
        mission_id: str,
        *,
        decided_by: str,
        comment: str = "",
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            return self._serialize_mission(
                conn,
                self._decide_approval(
                    conn,
                    mission,
                    decision="rejected",
                    decided_by=decided_by,
                    comment=comment,
                ),
            )

    def cancel(self, mission_id: str, *, actor: str, comment: str = "") -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            return self._serialize_mission(
                conn,
                self._cancel_mission(conn, mission, actor=actor, comment=comment),
            )

    def add_feedback(self, mission_id: str, *, actor: str, content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise CommandCenterError("feedback content is required")
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            message_id = f"msg-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO command_messages
                (id, conversation_id, mission_id, direction, external_message_id,
                 sender_id, content, metadata, created_at)
                VALUES (?, ?, ?, 'inbound', ?, ?, ?, '{}', ?)
                """,
                (
                    message_id,
                    mission["conversation_id"],
                    mission_id,
                    f"ui-feedback-{uuid.uuid4().hex}",
                    actor,
                    text,
                    _iso(),
                ),
            )
            self._add_event(
                conn,
                mission_id,
                "feedback_received",
                mission["status"],
                mission["status"],
                actor,
                text,
                {"message_id": message_id},
            )
            if mission["status"] == "waiting_feedback":
                failed_steps = conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM mission_steps
                    WHERE mission_id=? AND plan_version=? AND status='failed'
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchone()["count"]
                next_status = "dispatching" if failed_steps else "planning"
                if failed_steps:
                    conn.execute(
                        """
                        UPDATE mission_steps
                        SET status='ready', result_json='{}', lease_owner=NULL,
                            lease_token=NULL,
                            lease_expires_at=NULL, updated_at=?
                        WHERE mission_id=? AND plan_version=? AND status='failed'
                        """,
                        (_iso(), mission_id, mission["plan_version"]),
                    )
                mission = self._transition(
                    conn,
                    mission,
                    next_status,
                    actor=actor,
                    detail="Dashboard feedback received; orchestration resumed",
                )
            self._queue_notification(
                conn,
                mission=mission,
                text=f"已收到对 {mission_id} 的反馈，擎天柱会纳入后续执行。",
                event_key=f"feedback-ack:{message_id}",
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            return self._serialize_mission(conn, mission)

    def get_context_binding(
        self,
        mission_id: str,
        *,
        plan_version: int,
        purpose: str,
        step_id: str = "",
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM mission_context_bindings
                WHERE mission_id=? AND plan_version=? AND step_id=? AND purpose=?
                """,
                (mission_id, int(plan_version), step_id or "", purpose),
            ).fetchone()
            return self._serialize_context_binding(row) if row else None

    def bind_context_pack(
        self,
        mission_id: str,
        *,
        plan_version: int,
        purpose: str,
        agent_id: str,
        pack: Optional[dict[str, Any]] = None,
        step_id: str = "",
        query: str = "",
        error: str = "",
        actor: str = "command-center",
    ) -> dict[str, Any]:
        pack = pack or {}
        items = list(pack.get("items") or [])
        citations = list(pack.get("citations") or [])
        source_types = sorted(
            {
                str(item.get("item_type") or "")
                for item in items
                if str(item.get("item_type") or "").strip()
            }
        )
        status = str(pack.get("status") or ("degraded" if error else "empty"))
        now = _iso()
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            if step_id:
                step = conn.execute(
                    "SELECT mission_id, plan_version FROM mission_steps WHERE id=?",
                    (step_id,),
                ).fetchone()
                if (
                    not step
                    or step["mission_id"] != mission_id
                    or int(step["plan_version"]) != int(plan_version)
                ):
                    raise CommandCenterError(
                        f"step {step_id} does not belong to mission plan V{plan_version}"
                    )
            existing = conn.execute(
                """
                SELECT * FROM mission_context_bindings
                WHERE mission_id=? AND plan_version=? AND step_id=? AND purpose=?
                """,
                (mission_id, int(plan_version), step_id or "", purpose),
            ).fetchone()
            binding_id = existing["id"] if existing else f"ctxbind-{uuid.uuid4().hex[:12]}"
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO mission_context_bindings
                (id, mission_id, plan_version, step_id, purpose, agent_id,
                 context_pack_id, context_pack_version, status, query, summary,
                 item_count, citation_count, source_types_json, citations_json,
                 retrieval_health_json, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mission_id, plan_version, step_id, purpose)
                DO UPDATE SET
                    agent_id=excluded.agent_id,
                    context_pack_id=excluded.context_pack_id,
                    context_pack_version=excluded.context_pack_version,
                    status=excluded.status,
                    query=excluded.query,
                    summary=excluded.summary,
                    item_count=excluded.item_count,
                    citation_count=excluded.citation_count,
                    source_types_json=excluded.source_types_json,
                    citations_json=excluded.citations_json,
                    retrieval_health_json=excluded.retrieval_health_json,
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    binding_id,
                    mission_id,
                    int(plan_version),
                    step_id or "",
                    purpose,
                    agent_id or "optimus",
                    pack.get("id") or None,
                    int(pack.get("version") or 0),
                    status,
                    str(pack.get("query") or query or ""),
                    str(pack.get("summary") or ""),
                    len(items),
                    len(citations),
                    _json(source_types),
                    _json(citations[:50]),
                    _json(pack.get("retrieval_health") or {}),
                    str(error or "")[:4000] or None,
                    created_at,
                    now,
                ),
            )
            changed = (
                not existing
                or existing["context_pack_id"] != (pack.get("id") or None)
                or existing["status"] != status
                or (existing["error"] or "") != str(error or "")[:4000]
            )
            if changed:
                self._add_event(
                    conn,
                    mission_id,
                    (
                        "context_pack_bound"
                        if status in {"ready", "empty"}
                        else "context_retrieval_degraded"
                    ),
                    mission["status"],
                    mission["status"],
                    actor,
                    (
                        f"Bound {purpose} context {pack.get('id')} to plan V{plan_version}"
                        if pack.get("id")
                        else f"{purpose} context retrieval degraded: {error[:500]}"
                    ),
                    {
                        "plan_version": int(plan_version),
                        "step_id": step_id or None,
                        "purpose": purpose,
                        "agent_id": agent_id or "optimus",
                        "context_pack_id": pack.get("id"),
                        "context_pack_version": int(pack.get("version") or 0),
                        "status": status,
                        "item_count": len(items),
                        "citation_count": len(citations),
                        "source_types": source_types,
                    },
                )
            row = conn.execute(
                "SELECT * FROM mission_context_bindings WHERE id=?",
                (binding_id,),
            ).fetchone()
            return self._serialize_context_binding(row)

    def activate_approved_missions(self) -> int:
        with self.connect(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM orchestration_missions
                WHERE status='dispatching' AND approval_status='approved'
                ORDER BY updated_at
                """
            ).fetchall()
            for mission in rows:
                conn.execute(
                    """
                    UPDATE mission_steps SET status='ready', updated_at=?
                    WHERE mission_id=? AND plan_version=? AND status='draft'
                    """,
                    (_iso(), mission["id"], mission["plan_version"]),
                )
                self._transition(
                    conn,
                    mission,
                    "running",
                    actor="command-center",
                    detail="Approved plan entered execution",
                )
            activated = len(rows)
            # 为每个激活的 mission 写入派发通知
            for mission in rows:
                self._queue_dispatch_notification(conn, mission)
            return activated

    def requeue_stale_steps(self) -> int:
        now = _iso()
        with self.connect(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM mission_steps
                WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
                """,
                (now,),
            ).fetchall()
            for step in rows:
                conn.execute(
                    """
                    UPDATE mission_steps
                    SET status='ready', lease_owner=NULL, lease_token=NULL,
                        lease_expires_at=NULL, updated_at=?
                    WHERE id=?
                    """,
                    (now, step["id"]),
                )
                self._add_event(
                    conn,
                    step["mission_id"],
                    "step_requeued",
                    "running",
                    "running",
                    "command-center",
                    f"Recovered stale step {step['title']}",
                    {"step_id": step["id"]},
                )
            return len(rows)

    def claim_ready_steps(
        self,
        owner: str,
        *,
        limit: int = 3,
        lease_seconds: int = 900,
    ) -> list[dict[str, Any]]:
        now = _now()
        claimed: list[dict[str, Any]] = []
        with self.connect(immediate=True) as conn:
            candidates = conn.execute(
                """
                SELECT s.* FROM mission_steps s
                JOIN orchestration_missions m ON m.id=s.mission_id
                WHERE s.status='ready' AND m.status='running'
                ORDER BY m.created_at, s.order_index
                """
            ).fetchall()
            for step in candidates:
                dependencies = _loads(step["dependencies_json"], [])
                if dependencies:
                    placeholders = ",".join("?" for _ in dependencies)
                    rows = conn.execute(
                        f"SELECT id, status FROM mission_steps WHERE id IN ({placeholders})",
                        tuple(dependencies),
                    ).fetchall()
                    if len(rows) != len(dependencies) or any(row["status"] != "completed" for row in rows):
                        continue
                lease_token = f"lease-{uuid.uuid4().hex}"
                cursor = conn.execute(
                    """
                    UPDATE mission_steps
                    SET status='running', lease_owner=?, lease_token=?, lease_expires_at=?,
                        started_at=COALESCE(started_at, ?), updated_at=?
                    WHERE id=? AND status='ready'
                    """,
                    (
                        owner,
                        lease_token,
                        _iso(now + timedelta(seconds=max(lease_seconds, 60))),
                        _iso(now),
                        _iso(now),
                        step["id"],
                    ),
                )
                if cursor.rowcount == 1:
                    updated = conn.execute(
                        "SELECT * FROM mission_steps WHERE id=?",
                        (step["id"],),
                    ).fetchone()
                    claimed.append(self._serialize_step(updated))
                    self._add_event(
                        conn,
                        step["mission_id"],
                        "step_started",
                        "running",
                        "running",
                        step["agent_id"],
                        step["title"],
                        {"step_id": step["id"]},
                    )
                if len(claimed) >= max(1, limit):
                    break
        return claimed

    def attach_work_run(
        self,
        step_id: str,
        work_run_id: str,
        *,
        lease_token: str,
    ) -> None:
        with self.connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                UPDATE mission_steps
                SET work_run_id=?, updated_at=?
                WHERE id=? AND status='running' AND lease_token=?
                  AND EXISTS (
                      SELECT 1 FROM orchestration_missions mission
                      WHERE mission.id=mission_steps.mission_id
                        AND mission.status='running'
                  )
                """,
                (work_run_id, _iso(), step_id, str(lease_token or "")),
            )
            if cursor.rowcount != 1:
                raise InvalidMissionTransition(
                    f"stale or cancelled step work run rejected: {step_id}"
                )

    def renew_step_lease(
        self,
        step_id: str,
        *,
        lease_token: str,
        lease_seconds: int = 900,
    ) -> str:
        lease_expires_at = _iso(
            _now() + timedelta(seconds=max(60, int(lease_seconds)))
        )
        with self.connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                UPDATE mission_steps
                SET lease_expires_at=?, updated_at=?
                WHERE id=? AND status='running' AND lease_token=?
                  AND EXISTS (
                      SELECT 1 FROM orchestration_missions mission
                      WHERE mission.id=mission_steps.mission_id
                        AND mission.status='running'
                  )
                """,
                (
                    lease_expires_at,
                    _iso(),
                    step_id,
                    str(lease_token or ""),
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidMissionTransition(
                    f"step lease was lost or cancelled: {step_id}"
                )
        return lease_expires_at

    def complete_step(
        self,
        step_id: str,
        *,
        result: dict[str, Any],
        success: bool,
        actor: str,
        lease_token: str,
    ) -> dict[str, Any]:
        next_status = "completed" if success else "failed"
        with self.connect(immediate=True) as conn:
            step = conn.execute("SELECT * FROM mission_steps WHERE id=?", (step_id,)).fetchone()
            if not step:
                raise CommandCenterError(f"step not found: {step_id}")
            cursor = conn.execute(
                """
                UPDATE mission_steps
                SET status=?, result_json=?, lease_owner=NULL, lease_token=NULL,
                    lease_expires_at=NULL,
                    completed_at=?, updated_at=?
                WHERE id=? AND status='running' AND lease_token=?
                  AND EXISTS (
                      SELECT 1 FROM orchestration_missions mission
                      WHERE mission.id=mission_steps.mission_id
                        AND mission.status='running'
                  )
                """,
                (
                    next_status,
                    _json(result),
                    _iso(),
                    _iso(),
                    step_id,
                    str(lease_token or ""),
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidMissionTransition(
                    f"stale or cancelled step completion rejected: {step_id}"
                )
            self._add_event(
                conn,
                step["mission_id"],
                "step_completed" if success else "step_failed",
                "running",
                "running",
                actor,
                step["title"],
                {"step_id": step_id, "result": result},
            )
            self._sync_mission_ledger_safe(conn, step["mission_id"])
            return self._serialize_step(
                conn.execute("SELECT * FROM mission_steps WHERE id=?", (step_id,)).fetchone()
            )

    def claim_evaluation_mission(self, owner: str, *, lease_seconds: int = 300) -> dict[str, Any] | None:
        with self.connect(immediate=True) as conn:
            missions = conn.execute(
                """
                SELECT * FROM orchestration_missions
                WHERE status IN ('running', 'evaluating')
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ? OR lease_owner=?)
                ORDER BY updated_at
                """,
                (_iso(), owner),
            ).fetchall()
            for mission in missions:
                counts = {
                    row["status"]: row["count"]
                    for row in conn.execute(
                        """
                        SELECT status, COUNT(*) AS count FROM mission_steps
                        WHERE mission_id=? AND plan_version=?
                        GROUP BY status
                        """,
                        (mission["id"], mission["plan_version"]),
                    ).fetchall()
                }
                if counts.get("failed"):
                    if mission["status"] != "waiting_feedback":
                        previous = mission["status"]
                        conn.execute(
                            """
                            UPDATE orchestration_missions
                            SET status='waiting_feedback', last_error=?,
                                lease_owner=NULL, lease_expires_at=NULL, updated_at=?
                            WHERE id=?
                            """,
                            ("One or more mission steps failed", _iso(), mission["id"]),
                        )
                        self._add_event(
                            conn,
                            mission["id"],
                            "mission_blocked",
                            previous,
                            "waiting_feedback",
                            "command-center",
                            "One or more mission steps failed",
                            {"counts": counts},
                        )
                        updated = self._require_mission(conn, mission["id"])
                        self._queue_notification(
                            conn,
                            mission=updated,
                            text=(
                                f"任务 {mission['id']} 执行遇到阻塞。"
                                "请在指挥中心查看失败步骤并回复补充意见，擎天柱会继续推进。"
                            ),
                            event_key=f"blocked:{mission['id']}:{updated['updated_at']}",
                        )
                    continue
                if counts and sum(counts.values()) == counts.get("completed", 0):
                    conn.execute(
                        """
                        UPDATE orchestration_missions
                        SET status='evaluating', lease_owner=?, lease_expires_at=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            owner,
                            _iso(_now() + timedelta(seconds=max(lease_seconds, 60))),
                            _iso(),
                            mission["id"],
                        ),
                    )
                    self._add_event(
                        conn,
                        mission["id"],
                        "evaluation_started",
                        mission["status"],
                        "evaluating",
                        owner,
                        "All steps completed; Optimus is evaluating the outcome",
                        {},
                    )
                    return self._serialize_mission(
                        conn,
                        self._require_mission(conn, mission["id"]),
                    )
            return None

    def complete_mission(
        self,
        mission_id: str,
        *,
        summary: str,
        success: bool,
        actor: str = "optimus",
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            next_status = "completed" if success else "waiting_feedback"
            conn.execute(
                """
                UPDATE orchestration_missions
                SET status=?, last_error=?, lease_owner=NULL, lease_expires_at=NULL,
                    completed_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    next_status,
                    None if success else summary[:4000],
                    _iso() if success else None,
                    _iso(),
                    mission_id,
                ),
            )
            self._add_event(
                conn,
                mission_id,
                "mission_completed" if success else "evaluation_failed",
                mission["status"],
                next_status,
                actor,
                summary,
                {},
            )
            updated = self._require_mission(conn, mission_id)
            self._queue_notification(
                conn,
                mission=updated,
                text=(
                    f"任务 {mission_id} 已完成。\n{summary}"
                    if success
                    else f"任务 {mission_id} 需要您的反馈。\n{summary}"
                ),
                event_key=f"result:{mission_id}:{updated['updated_at']}",
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            return self._serialize_mission(conn, updated)

    def record_memory_event(
        self,
        mission_id: str,
        *,
        event_type: str,
        actor: str,
        detail: str,
        metadata: Optional[dict[str, Any]] = None,
        notify: bool = False,
    ) -> dict[str, Any]:
        allowed = {
            "memory_candidates_proposed",
            "memory_candidate_generation_failed",
            "memory_candidate_published",
            "memory_candidate_rejected",
        }
        if event_type not in allowed:
            raise CommandCenterError(f"invalid memory event type: {event_type}")
        payload = metadata or {}
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            identities = payload.get("candidate_ids") or [
                payload.get("candidate_id")
                or payload.get("job_id")
                or event_type
            ]
            identity = str(identities[0])
            self._add_event(
                conn,
                mission_id,
                event_type,
                mission["status"],
                mission["status"],
                actor,
                detail[:4000],
                payload,
                event_key=f"memory:{event_type}:{identity}",
            )
            if notify:
                self._queue_notification(
                    conn,
                    mission=mission,
                    text=f"任务 {mission_id}：{detail}",
                    event_key=f"memory:{mission_id}:{event_type}:{identity}",
                )
            return self._serialize_mission(
                conn,
                self._require_mission(conn, mission_id),
            )

    def claim_outbox(self, owner: str, *, limit: int = 10) -> list[dict[str, Any]]:
        now = _iso()
        claimed: list[dict[str, Any]] = []
        with self.connect(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM notification_outbox
                WHERE status IN ('pending', 'retry')
                  AND next_attempt_at <= ?
                  AND (locked_at IS NULL OR locked_at <= ?)
                ORDER BY created_at LIMIT ?
                """,
                (now, _iso(_now() - timedelta(minutes=5)), max(1, limit)),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status='sending', locked_at=?, lock_owner=?, attempts=attempts+1
                    WHERE id=?
                    """,
                    (now, owner, row["id"]),
                )
                claimed.append(
                    self._serialize_outbox(
                        conn.execute(
                            "SELECT * FROM notification_outbox WHERE id=?",
                            (row["id"],),
                        ).fetchone()
                    )
                )
        return claimed

    def record_delivery(
        self,
        outbox_id: str,
        *,
        success: bool,
        response: str = "",
        error: str = "",
        external_message_id: str = "",
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM notification_outbox WHERE id=?",
                (outbox_id,),
            ).fetchone()
            if not row:
                raise CommandCenterError(f"outbox item not found: {outbox_id}")
            delivery_id = f"delivery-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO notification_deliveries
                (id, outbox_id, attempt, success, external_message_id, response, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    outbox_id,
                    row["attempts"],
                    1 if success else 0,
                    external_message_id or None,
                    response[:8000],
                    error[:4000],
                    _iso(),
                ),
            )
            if success:
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status='sent', sent_at=?, locked_at=NULL, lock_owner=NULL,
                        last_error=NULL
                    WHERE id=?
                    """,
                    (_iso(), outbox_id),
                )
                if row["command_message_id"] and external_message_id:
                    conn.execute(
                        """
                        UPDATE command_messages SET external_message_id=?
                        WHERE id=?
                        """,
                        (external_message_id, row["command_message_id"]),
                    )
            else:
                delay = min(600, 5 * (2 ** max(0, int(row["attempts"]) - 1)))
                next_status = "dead" if int(row["attempts"]) >= 6 else "retry"
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status=?, next_attempt_at=?, locked_at=NULL, lock_owner=NULL,
                        last_error=?
                    WHERE id=?
                    """,
                    (
                        next_status,
                        _iso(_now() + timedelta(seconds=delay)),
                        error[:4000],
                        outbox_id,
                    ),
                )
            return self._serialize_outbox(
                conn.execute("SELECT * FROM notification_outbox WHERE id=?", (outbox_id,)).fetchone()
            )

    def get_mission(
        self,
        mission_id: str,
        *,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            mission = self._require_mission(conn, mission_id)
            if owner_user_id and str(mission["owner_user_id"] or "") != str(owner_user_id):
                raise MissionNotFound(mission_id)
            return self._serialize_mission(conn, mission)

    def record_conversation_response(
        self,
        message_id: str,
        *,
        content: str,
        sender_id: str = "optimus",
        external_message_id: str = "",
    ) -> dict[str, Any]:
        clean_content = str(content or "").strip()
        if not clean_content:
            raise CommandCenterError("response content is required")
        with self.connect(immediate=True) as conn:
            inbound = conn.execute(
                """
                SELECT * FROM command_messages
                WHERE id=? AND direction='inbound'
                """,
                (message_id,),
            ).fetchone()
            if not inbound:
                raise CommandCenterError(f"inbound message not found: {message_id}")
            existing = conn.execute(
                """
                SELECT * FROM command_messages
                WHERE reply_to_command_message_id=? AND direction='outbound'
                ORDER BY created_at DESC LIMIT 1
                """,
                (message_id,),
            ).fetchone()
            if existing:
                return {
                    "action": "duplicate",
                    "message": self._serialize_message(existing),
                }
            response_id = f"msg-{uuid.uuid4().hex[:12]}"
            routing_status = (
                "clarification_sent"
                if inbound["intent_type"] == "clarification_required"
                else "answered"
            )
            conn.execute(
                """
                INSERT INTO command_messages
                (id, conversation_id, mission_id, direction, external_message_id,
                 sender_id, content, intent_type, intent_confidence, intent_reason,
                 execution_requested, routing_status, resolved_project_id,
                 reply_to_command_message_id, metadata, created_at)
                VALUES (?, ?, ?, 'outbound', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    inbound["conversation_id"],
                    inbound["mission_id"],
                    external_message_id or None,
                    sender_id or "optimus",
                    clean_content,
                    inbound["intent_type"],
                    inbound["intent_confidence"],
                    inbound["intent_reason"],
                    inbound["execution_requested"],
                    routing_status,
                    inbound["resolved_project_id"],
                    message_id,
                    _json({"in_reply_to_message_id": message_id}),
                    _iso(),
                ),
            )
            conn.execute(
                "UPDATE command_messages SET routing_status=? WHERE id=?",
                (routing_status, message_id),
            )
            conn.execute(
                "UPDATE command_conversations SET updated_at=? WHERE id=?",
                (_iso(), inbound["conversation_id"]),
            )
            return {
                "action": "recorded",
                "message": self._get_message(conn, response_id),
            }

    def list_routed_messages(
        self,
        *,
        owner_user_id: str = "",
        intent_type: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            clauses = ["messages.direction='inbound'", "messages.intent_type!=''"]
            params: list[Any] = []
            if owner_user_id:
                clauses.append("conversations.owner_user_id=?")
                params.append(str(owner_user_id))
            normalized_intent = self._normalize_intent_type(intent_type)
            if normalized_intent:
                clauses.append("messages.intent_type=?")
                params.append(normalized_intent)
            params.append(max(1, min(int(limit), 200)))
            rows = conn.execute(
                f"""
                SELECT messages.*
                FROM command_messages messages
                JOIN command_conversations conversations
                  ON conversations.id=messages.conversation_id
                WHERE {' AND '.join(clauses)}
                ORDER BY messages.created_at DESC LIMIT ?
                """,
                params,
            ).fetchall()
            results = []
            for row in rows:
                item = self._serialize_message(row)
                response = conn.execute(
                    """
                    SELECT * FROM command_messages
                    WHERE reply_to_command_message_id=? AND direction='outbound'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (row["id"],),
                ).fetchone()
                item["response"] = self._serialize_message(response) if response else None
                results.append(item)
            return results

    def list_missions(
        self,
        *,
        status: str = "",
        limit: int = 100,
        offset: int = 0,
        owner_user_id: str = "",
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if status:
                clauses.append("status=?")
                params.append(status)
            if owner_user_id:
                clauses.append("owner_user_id=?")
                params.append(str(owner_user_id))
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.extend((max(1, min(limit, 500)), max(0, offset)))
            rows = conn.execute(
                f"""
                SELECT * FROM orchestration_missions
                {where}
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
            return [self._serialize_mission(conn, row, include_detail=False) for row in rows]

    def summary(self, *, owner_user_id: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            owner_clause = " WHERE owner_user_id=?" if owner_user_id else ""
            owner_params = (str(owner_user_id),) if owner_user_id else ()
            by_status = {
                row["status"]: row["count"]
                for row in conn.execute(
                    f"""
                    SELECT status, COUNT(*) AS count
                    FROM orchestration_missions
                    {owner_clause}
                    GROUP BY status
                    """,
                    owner_params,
                ).fetchall()
            }
            pending_approvals = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM mission_approvals approvals
                JOIN orchestration_missions missions ON missions.id=approvals.mission_id
                WHERE approvals.decision='pending'
                  AND missions.status='awaiting_approval'
                  {"AND missions.owner_user_id=?" if owner_user_id else ""}
                """,
                owner_params,
            ).fetchone()["count"]
            outbox_pending = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM notification_outbox outbox
                LEFT JOIN orchestration_missions missions ON missions.id=outbox.mission_id
                WHERE outbox.status IN ('pending','retry','sending')
                  {"AND missions.owner_user_id=?" if owner_user_id else ""}
                """,
                owner_params,
            ).fetchone()["count"]
            context_by_status = {
                row["status"]: row["count"]
                for row in conn.execute(
                    f"""
                    SELECT bindings.status, COUNT(*) AS count
                    FROM mission_context_bindings bindings
                    JOIN orchestration_missions missions ON missions.id=bindings.mission_id
                    {"WHERE missions.owner_user_id=?" if owner_user_id else ""}
                    GROUP BY bindings.status
                    """,
                    owner_params,
                ).fetchall()
            }
            routed_counts = {
                row["intent_type"]: row["count"]
                for row in conn.execute(
                    f"""
                    SELECT messages.intent_type, COUNT(*) AS count
                    FROM command_messages messages
                    JOIN command_conversations conversations
                      ON conversations.id=messages.conversation_id
                    WHERE messages.direction='inbound'
                      AND messages.intent_type!=''
                      {"AND conversations.owner_user_id=?" if owner_user_id else ""}
                    GROUP BY messages.intent_type
                    """,
                    owner_params,
                ).fetchall()
            }
            clarification_pending = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM command_messages messages
                JOIN command_conversations conversations
                  ON conversations.id=messages.conversation_id
                WHERE messages.direction='inbound'
                  AND messages.intent_type='clarification_required'
                  AND messages.routing_status IN ('awaiting_clarification','clarification_sent')
                  {"AND conversations.owner_user_id=?" if owner_user_id else ""}
                """,
                owner_params,
            ).fetchone()["count"]
            return {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "pending_approvals": pending_approvals,
                "outbox_pending": outbox_pending,
                "context_by_status": context_by_status,
                "context_ready": context_by_status.get("ready", 0),
                "context_degraded": sum(
                    count
                    for status, count in context_by_status.items()
                    if status not in {"ready", "empty"}
                ),
                "routed_by_intent": routed_counts,
                "discussion_count": routed_counts.get("discussion", 0),
                "clarification_pending": clarification_pending,
                "active": sum(
                    count
                    for status, count in by_status.items()
                    if status not in TERMINAL_MISSION_STATES
                ),
            }

    def _decide_approval(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
        *,
        decision: str,
        decided_by: str,
        comment: str,
    ) -> sqlite3.Row:
        if mission["status"] != "awaiting_approval":
            raise InvalidMissionTransition(
                f"mission {mission['id']} is not awaiting approval"
            )
        if decision not in {"approved", "rejected"}:
            raise CommandCenterError(f"invalid approval decision: {decision}")
        next_status = "dispatching" if decision == "approved" else "planning"
        conn.execute(
            """
            UPDATE mission_approvals
            SET decision=?, decided_at=?, decided_by=?, comment=?
            WHERE mission_id=? AND plan_version=?
            """,
            (
                decision,
                _iso(),
                decided_by,
                comment,
                mission["id"],
                mission["plan_version"],
            ),
        )
        conn.execute(
            """
            UPDATE mission_plan_versions SET status=?
            WHERE mission_id=? AND version=?
            """,
            (decision, mission["id"], mission["plan_version"]),
        )
        conn.execute(
            """
            UPDATE orchestration_missions
            SET status=?, approval_status=?, lease_owner=NULL, lease_expires_at=NULL,
                updated_at=?
            WHERE id=?
            """,
            (next_status, decision, _iso(), mission["id"]),
        )
        self._add_event(
            conn,
            mission["id"],
            f"plan_{decision}",
            "awaiting_approval",
            next_status,
            decided_by,
            comment or decision,
            {"version": mission["plan_version"]},
        )
        updated = self._require_mission(conn, mission["id"])
        self._queue_notification(
            conn,
            mission=updated,
            text=(
                f"任务 {mission['id']} 的计划已批准，开始调度智能体执行。"
                if decision == "approved"
                else f"任务 {mission['id']} 的计划已驳回，擎天柱将根据意见重新规划。"
            ),
            event_key=f"approval:{mission['id']}:{mission['plan_version']}:{decision}",
        )
        self._sync_mission_ledger_safe(conn, mission["id"])
        return updated

    def _cancel_mission(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
        *,
        actor: str,
        comment: str,
    ) -> sqlite3.Row:
        if mission["status"] in TERMINAL_MISSION_STATES:
            return mission
        conn.execute(
            """
            UPDATE orchestration_missions
            SET status='cancelled',
                approval_status=CASE
                    WHEN approval_status='pending' THEN 'cancelled'
                    ELSE approval_status
                END,
                lease_owner=NULL, lease_expires_at=NULL, updated_at=?
            WHERE id=?
            """,
            (_iso(), mission["id"]),
        )
        conn.execute(
            """
            UPDATE mission_approvals
            SET decision='cancelled', decided_at=?, decided_by=?, comment=?
            WHERE mission_id=? AND decision='pending'
            """,
            (_iso(), actor, comment or "Mission cancelled", mission["id"]),
        )
        conn.execute(
            """
            UPDATE mission_plan_versions
            SET status='cancelled'
            WHERE mission_id=? AND status='pending'
            """,
            (mission["id"],),
        )
        conn.execute(
            """
            UPDATE mission_steps SET status='cancelled', lease_owner=NULL,
                lease_token=NULL, lease_expires_at=NULL, completed_at=?, updated_at=?
            WHERE mission_id=? AND status NOT IN ('completed', 'failed', 'cancelled')
            """,
            (_iso(), _iso(), mission["id"]),
        )
        self._add_event(
            conn,
            mission["id"],
            "mission_cancelled",
            mission["status"],
            "cancelled",
            actor,
            comment or "Mission cancelled",
            {},
        )
        updated = self._require_mission(conn, mission["id"])
        self._queue_notification(
            conn,
            mission=updated,
            text=f"任务 {mission['id']} 已取消。",
            event_key=f"cancelled:{mission['id']}",
        )
        self._sync_mission_ledger_safe(conn, mission["id"])
        return updated

    def _resolve_related_mission(
        self,
        conn: sqlite3.Connection,
        *,
        conversation_id: str,
        content: str,
        reply_to_external_message_id: str,
    ) -> sqlite3.Row | None:
        match = MISSION_ID_PATTERN.search(content)
        if match:
            row = conn.execute(
                """
                SELECT * FROM orchestration_missions
                WHERE id=? AND conversation_id=?
                """,
                (match.group(1).lower(), conversation_id),
            ).fetchone()
            if row:
                return row
        if reply_to_external_message_id:
            row = conn.execute(
                """
                SELECT m.* FROM orchestration_missions m
                JOIN command_messages cm ON cm.mission_id=m.id
                WHERE cm.conversation_id=? AND cm.external_message_id=?
                ORDER BY cm.created_at DESC LIMIT 1
                """,
                (conversation_id, reply_to_external_message_id),
            ).fetchone()
            if row:
                return row
        if APPROVE_PATTERN.search(content) or REJECT_PATTERN.search(content) or CANCEL_PATTERN.search(content):
            return conn.execute(
                """
                SELECT * FROM orchestration_missions
                WHERE conversation_id=? AND status NOT IN ('completed','failed','cancelled')
                ORDER BY created_at DESC LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        return None

    def _transition(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
        next_status: str,
        *,
        actor: str,
        detail: str,
    ) -> sqlite3.Row:
        previous = mission["status"]
        if next_status != previous and next_status not in MISSION_TRANSITIONS.get(previous, set()):
            raise InvalidMissionTransition(f"invalid mission transition: {previous} -> {next_status}")
        conn.execute(
            """
            UPDATE orchestration_missions
            SET status=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=?
            WHERE id=?
            """,
            (next_status, _iso(), mission["id"]),
        )
        self._add_event(
            conn,
            mission["id"],
            "state_changed",
            previous,
            next_status,
            actor,
            detail,
            {},
        )
        self._sync_mission_ledger_safe(conn, mission["id"])
        return self._require_mission(conn, mission["id"])

    def _queue_notification(
        self,
        conn: sqlite3.Connection,
        *,
        mission: sqlite3.Row,
        text: str,
        event_key: str,
        reply_to: str = "",
        account_id: str = "",
    ) -> None:
        conversation = conn.execute(
            "SELECT * FROM command_conversations WHERE id=?",
            (mission["conversation_id"],),
        ).fetchone()
        if not conversation:
            return
        metadata = _loads(conversation["metadata"], {})
        if metadata.get("suppress_notification") or conversation["channel"] == "dashboard":
            return
        target = str(metadata.get("target") or conversation["external_conversation_id"] or "").strip()
        if not target:
            return
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        account_id_val = str(account_id).strip() if account_id else "optimus"
        conn.execute(
            """
            INSERT INTO command_messages
            (id, conversation_id, mission_id, direction, sender_id, content, metadata, created_at)
            VALUES (?, ?, ?, 'outbound', 'optimus', ?, '{}', ?)
            """,
            (message_id, mission["conversation_id"], mission["id"], text, _iso()),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO notification_outbox
            (id, mission_id, conversation_id, command_message_id, channel,
             account_id, target, message_text, reply_to, status, attempts,
             next_attempt_at, payload, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, '{}', ?, ?)
            """,
            (
                f"outbox-{uuid.uuid4().hex[:12]}",
                mission["id"],
                mission["conversation_id"],
                message_id,
                conversation["channel"],
                account_id_val,
                target,
                text,
                reply_to or None,
                _iso(),
                event_key,
                _iso(),
            ),
        )

    def _queue_dispatch_notification(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
    ) -> None:
        """任务批准后，生成派发摘要通知，写入 outbox 等待飞书发送。"""
        steps = conn.execute(
            """
            SELECT agent_id, title, order_index, status, dependencies_json
            FROM mission_steps WHERE mission_id=? AND plan_version=?
            ORDER BY order_index
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchall()
        if not steps:
            return
        mission_title = mission["title"] or mission["id"][:12]
        lines = [f"📋 **任务已派发**（{mission_title}）"]
        lines.append("")
        for s in steps:
            agent = str(s["agent_id"] or "")
            title = str(s["title"] or "")
            deps = _loads(s["dependencies_json"], [])
            dep_text = f" (等待 {len(deps)} 个前置步骤)" if deps else ""
            status_icon = "⏳" if s["status"] in ("draft", "ready") else "🔄"
            lines.append(f"{status_icon} **{agent}**：{title}{dep_text}")
        lines.append("")
        lines.append("各智能体完成后会直接通过飞书向您汇报结果。")
        self._queue_notification(
            conn,
            mission=mission,
            text="\n".join(lines),
            event_key=f"dispatch:{mission['id']}:{mission['plan_version']}",
        )

    def enqueue_step_notification(
        self,
        step: dict[str, Any],
        mission: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """在 step 完成后，将通知写入 outbox，使用执行者自己的飞书账号发送。"""
        success = bool(result.get("success"))
        agent_id = str(step.get("agent_id") or "")
        step_title = str(step.get("title") or "")
        output = str(result.get("output") or result.get("error") or "")[:500]
        if success:
            text = f"✅ [{agent_id}] {step_title} 已完成"
        else:
            text = f"❌ [{agent_id}] {step_title} 执行失败：{output[:200]}"
        with self.connect(immediate=True) as conn:
            conv = conn.execute(
                "SELECT * FROM command_conversations WHERE id=?",
                (mission.get("conversation_id") or "",),
            ).fetchone()
            if not conv:
                return
            metadata = _loads(conv["metadata_json"] or "{}", {})
            if metadata.get("suppress_notification") or conv["channel"] == "dashboard":
                return
            target = str(metadata.get("target") or conv["external_conversation_id"] or "").strip()
            if not target:
                return
            message_id = f"msg-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO command_messages
                (id, conversation_id, mission_id, direction, sender_id, content, metadata, created_at)
                VALUES (?, ?, ?, 'outbound', ?, ?, '{}', ?)
                """,
                (message_id, conv["id"], mission["id"], agent_id, text, _iso()),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO notification_outbox
                (id, mission_id, conversation_id, command_message_id, channel,
                 account_id, target, message_text, reply_to, status, attempts,
                 next_attempt_at, payload, idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, '{}', ?, ?)
                """,
                (
                    f"outbox-{uuid.uuid4().hex[:12]}",
                    mission["id"],
                    conv["id"],
                    message_id,
                    conv["channel"] or "feishu",
                    agent_id,
                    target,
                    text,
                    None,
                    _iso(),
                    f"step-done:{step['id']}:{_iso()}",
                    _iso(),
                ),
            )

    def _add_event(
        self,
        conn: sqlite3.Connection,
        mission_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor: str,
        detail: str,
        metadata: dict[str, Any],
        event_key: str = "",
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO mission_events
            (id, mission_id, event_type, from_status, to_status, actor,
             detail, event_key, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"event-{uuid.uuid4().hex[:12]}",
                mission_id,
                event_type,
                from_status,
                to_status,
                actor,
                detail,
                event_key or None,
                _json(metadata),
                _iso(),
            ),
        )

    @staticmethod
    def _title_from_objective(objective: str) -> str:
        compact = " ".join(str(objective).split())
        return compact[:60] + ("…" if len(compact) > 60 else "")

    @staticmethod
    def _require_mission(conn: sqlite3.Connection, mission_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM orchestration_missions WHERE id=?",
            (mission_id,),
        ).fetchone()
        if not row:
            raise MissionNotFound(mission_id)
        return row

    @staticmethod
    def _get_message(conn: sqlite3.Connection, message_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM command_messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            raise CommandCenterError(f"message not found: {message_id}")
        return CommandCenterService._serialize_message(row)

    @staticmethod
    def _mission_from_message(conn: sqlite3.Connection, message_id: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT m.* FROM orchestration_missions m
            JOIN command_messages cm ON cm.mission_id=m.id
            WHERE cm.id=?
            """,
            (message_id,),
        ).fetchone()

    @staticmethod
    def _serialize_message(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["metadata"] = _loads(item.get("metadata"), {})
        return item

    @staticmethod
    def _serialize_step(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["dependencies"] = _loads(item.pop("dependencies_json", "[]"), [])
        item["input"] = _loads(item.pop("input_json", "{}"), {})
        item["result"] = _loads(item.pop("result_json", "{}"), {})
        return item

    @staticmethod
    def _serialize_context_binding(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["source_types"] = _loads(item.pop("source_types_json", "[]"), [])
        item["citations"] = _loads(item.pop("citations_json", "[]"), [])
        item["retrieval_health"] = _loads(
            item.pop("retrieval_health_json", "{}"),
            {},
        )
        return item

    @staticmethod
    def _serialize_outbox(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = _loads(item.get("payload"), {})
        return item

    def _serialize_mission(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        include_detail: bool = True,
    ) -> dict[str, Any]:
        item = dict(row)
        item["requires_approval"] = bool(item["requires_approval"])
        item["context"] = _loads(item.pop("context_json", "{}"), {})
        conversation = conn.execute(
            "SELECT * FROM command_conversations WHERE id=?",
            (item["conversation_id"],),
        ).fetchone()
        item["conversation"] = dict(conversation) if conversation else None
        if item["conversation"]:
            item["conversation"]["metadata"] = _loads(item["conversation"].get("metadata"), {})
        steps = conn.execute(
            """
            SELECT * FROM mission_steps
            WHERE mission_id=? AND plan_version=?
            ORDER BY order_index
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        item["steps"] = [self._serialize_step(step) for step in steps]
        binding_rows = conn.execute(
            """
            SELECT * FROM mission_context_bindings
            WHERE mission_id=? AND plan_version=?
            ORDER BY purpose, step_id
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        bindings = [self._serialize_context_binding(binding) for binding in binding_rows]
        item["context_bindings"] = bindings
        item["planning_context"] = next(
            (
                binding
                for binding in bindings
                if binding["purpose"] == "planning" and not binding["step_id"]
            ),
            None,
        )
        step_bindings = {
            binding["step_id"]: binding
            for binding in bindings
            if binding["purpose"] == "execution" and binding["step_id"]
        }
        for step in item["steps"]:
            step["context_binding"] = step_bindings.get(step["id"])
        plan = conn.execute(
            """
            SELECT * FROM mission_plan_versions
            WHERE mission_id=? AND version=?
            """,
            (item["id"], item["plan_version"]),
        ).fetchone()
        item["plan"] = dict(plan) if plan else None
        if item["plan"]:
            item["plan"]["raw_plan"] = _loads(item["plan"].get("raw_plan"), {})
        approval = conn.execute(
            """
            SELECT * FROM mission_approvals
            WHERE mission_id=? AND plan_version=?
            """,
            (item["id"], item["plan_version"]),
        ).fetchone()
        item["approval"] = dict(approval) if approval else None
        if include_detail:
            events = conn.execute(
                """
                SELECT * FROM mission_events
                WHERE mission_id=? ORDER BY created_at
                """,
                (item["id"],),
            ).fetchall()
            item["events"] = [
                {
                    **dict(event),
                    "metadata": _loads(event["metadata"], {}),
                }
                for event in events
            ]
            messages = conn.execute(
                """
                SELECT * FROM command_messages
                WHERE mission_id=? ORDER BY created_at
                """,
                (item["id"],),
            ).fetchall()
            item["messages"] = [self._serialize_message(message) for message in messages]
        return item


command_center_service = CommandCenterService()
