"""Durable command-center state for the Optimus single-entry workflow."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator, Optional

from unified_data_manager import UNIFIED_DB_PATH, unified_data_manager
from repositories.command_center_repository import (
    CommandCenterRepository,
    create_command_center_repository,
)
from services.business_flow_service import MISSION_LIFECYCLE
from services.plan_quality_service import plan_quality_service
from services.execution_evidence_service import execution_evidence_service
from services.compensation_service import compensation_service
from services.workflow_runtime import (
    POSTGRES_CHECKPOINT_TABLES,
    postgres_checkpoint_required_version,
    select_workflow_runtime,
    workflow_runtime_catalog,
)

logger = logging.getLogger(__name__)


MISSION_STATES = tuple(MISSION_LIFECYCLE)

COMMAND_CENTER_REQUIRED_TABLES = (
    "command_conversations",
    "command_messages",
    "command_external_user_bindings",
    "orchestration_missions",
    "mission_runs",
    "mission_plan_versions",
    "mission_steps",
    "mission_step_approvals",
    "mission_effects",
    "mission_compensations",
    "mission_approvals",
    "mission_events",
    "mission_context_bindings",
    "workflow_runs",
    "mission_artifacts",
    "mission_evidence",
    "mission_acceptance_gates",
    "notification_outbox",
    "notification_deliveries",
    "command_center_workers",
    "agent_teams",
    "agent_team_roles",
    "agent_instances",
    "shared_tasks",
    "shared_task_dependencies",
    "task_claims",
    "agent_task_context_bindings",
    "agent_messages",
    "team_events",
)

TERMINAL_MISSION_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STEP_STATES = {"running"}
TERMINAL_STEP_STATES = {"completed", "failed", "cancelled"}

MISSION_TRANSITIONS = {
    state: set(next_states)
    for state, next_states in MISSION_LIFECYCLE.items()
}

APPROVE_PATTERN = re.compile(r"^(批准|同意|通过|approve)\b", re.IGNORECASE)
REJECT_PATTERN = re.compile(r"^(驳回|拒绝|reject)\b", re.IGNORECASE)
CANCEL_PATTERN = re.compile(r"^(取消|停止|终止|cancel)\b", re.IGNORECASE)
MISSION_ID_PATTERN = re.compile(r"(mission-[a-f0-9]{12})", re.IGNORECASE)

INTENT_TYPES = {
    "discussion",
    "software_project",
    "document_project",
    "finance_operation",
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
FINANCE_MARKERS = (
    "财务",
    "经费",
    "预算",
    "报销",
    "发票",
    "付款",
    "收款",
    "银行流水",
    "对账",
    "入账",
    "支出",
    "冲销",
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
        db_path: str | None = None,
        project_provider: Optional[Callable[[], list[dict[str, Any]]]] = None,
        workflow_runtime_selector: Optional[
            Callable[[dict[str, Any]], dict[str, Any]]
        ] = None,
        repository: CommandCenterRepository | None = None,
    ):
        if repository is not None and db_path is not None:
            raise ValueError("Pass either db_path or repository, not both")
        self.repository = repository or create_command_center_repository(
            db_path=db_path or UNIFIED_DB_PATH,
            database_url=(
                os.getenv("COMMAND_CENTER_DATABASE_URL")
                if db_path is None
                else None
            ),
        )
        # Kept for compatibility with memory/context services that share the
        # controlled-pilot SQLite file. New code should use storage_info().
        self.db_path = self.repository.source_of_truth
        self.project_provider = project_provider
        self.workflow_runtime_selector = (
            workflow_runtime_selector or select_workflow_runtime
        )
        self.ensure_schema()

    def connect(self, *, immediate: bool = False) -> Iterator[Any]:
        """Compatibility facade; transaction ownership lives in the repository."""
        return self.repository.transaction(immediate=immediate)

    def storage_info(self) -> dict[str, Any]:
        return self.repository.describe()

    def storage_runtime_metrics(self) -> dict[str, Any]:
        return self.repository.runtime_metrics()

    def register_worker(
        self,
        worker_id: str,
        *,
        role: str = "orchestrator",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _iso()
        with self.connect(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO command_center_workers
                (id, role, state, started_at, last_seen_at, stopped_at, metadata_json)
                VALUES (?, ?, 'running', ?, ?, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role=excluded.role,
                    state='running',
                    started_at=excluded.started_at,
                    last_seen_at=excluded.last_seen_at,
                    stopped_at=NULL,
                    metadata_json=excluded.metadata_json
                """,
                (worker_id, role, now, now, _json(metadata or {})),
            )
        return {"id": worker_id, "role": role, "state": "running", "last_seen_at": now}

    def heartbeat_worker(self, worker_id: str) -> bool:
        now = _iso()
        with self.connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                UPDATE command_center_workers
                SET state='running', last_seen_at=?, stopped_at=NULL
                WHERE id=?
                """,
                (now, worker_id),
            )
            return int(cursor.rowcount or 0) == 1

    def stop_worker(self, worker_id: str) -> bool:
        now = _iso()
        with self.connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                UPDATE command_center_workers
                SET state='stopped', last_seen_at=?, stopped_at=?
                WHERE id=?
                """,
                (now, now, worker_id),
            )
            return int(cursor.rowcount or 0) == 1

    def worker_runtime_status(
        self,
        *,
        required_workers: int | None = None,
        stale_after_seconds: int | None = None,
    ) -> dict[str, Any]:
        required = max(
            1,
            int(
                required_workers
                if required_workers is not None
                else os.getenv("COMMAND_CENTER_REQUIRED_WORKERS", "1")
            ),
        )
        stale_after = max(
            5,
            int(
                stale_after_seconds
                if stale_after_seconds is not None
                else os.getenv("COMMAND_CENTER_WORKER_STALE_SECONDS", "20")
            ),
        )
        cutoff = _iso(_now() - timedelta(seconds=stale_after))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, state, started_at, last_seen_at, stopped_at, metadata_json
                FROM command_center_workers
                ORDER BY id
                """
            ).fetchall()
        workers = []
        for row in rows:
            item = dict(row)
            item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
            item["live"] = bool(
                item.get("state") == "running"
                and str(item.get("last_seen_at") or "") >= cutoff
            )
            workers.append(item)
        live = [item for item in workers if item["live"]]
        stale = [
            item
            for item in workers
            if item.get("state") == "running" and not item["live"]
        ]
        return {
            "status": "ready" if len(live) >= required else "degraded",
            "required": required,
            "live": len(live),
            "stale": len(stale),
            "stale_after_seconds": stale_after,
            "workers": workers,
        }

    def ensure_schema(self) -> None:
        if not self.repository.capabilities.runtime_schema_management:
            with self.connect() as conn:
                missing = [
                    table
                    for table in COMMAND_CENTER_REQUIRED_TABLES
                    if not self.repository.table_exists(conn, table)
                ]
            if missing:
                raise CommandCenterError(
                    "Command Center schema is not migrated; missing tables: "
                    + ", ".join(missing)
                    + ". Run Alembic upgrade head before starting the service."
                )
            return
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
                    target_agent_id TEXT NOT NULL DEFAULT 'optimus',
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

                CREATE TABLE IF NOT EXISTS mission_runs (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL UNIQUE,
                    correlation_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    active_plan_version INTEGER NOT NULL DEFAULT 0,
                    workflow_run_id TEXT,
                    outcome TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_runs_status
                    ON mission_runs(status, updated_at);

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

                CREATE TABLE IF NOT EXISTS mission_step_approvals (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    request_version INTEGER NOT NULL,
                    risk_class TEXT NOT NULL,
                    action_summary TEXT NOT NULL,
                    contract_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    requested_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    decided_at TEXT,
                    decided_by TEXT,
                    comment TEXT,
                    consumed_at TEXT,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(step_id) REFERENCES mission_steps(id),
                    UNIQUE(step_id, request_version)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_step_approvals_pending
                    ON mission_step_approvals(mission_id, plan_version, status, expires_at);

                CREATE TABLE IF NOT EXISTS mission_effects (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    mission_run_id TEXT,
                    correlation_id TEXT,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    work_run_id TEXT,
                    effect_key TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    receipt_ref TEXT,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    fingerprint TEXT NOT NULL UNIQUE,
                    reported_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(step_id) REFERENCES mission_steps(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_effects_scope
                    ON mission_effects(mission_id, plan_version, step_id, status);

                CREATE TABLE IF NOT EXISTS mission_compensations (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    mission_run_id TEXT,
                    correlation_id TEXT,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    effect_id TEXT NOT NULL UNIQUE,
                    compensation_type TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    contract_hash TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending_approval',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 1,
                    requested_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by TEXT,
                    approval_comment TEXT,
                    authorization_expires_at TEXT,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(step_id) REFERENCES mission_steps(id),
                    FOREIGN KEY(effect_id) REFERENCES mission_effects(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_compensations_pending
                    ON mission_compensations(status, lease_expires_at, requested_at);

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

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    mission_run_id TEXT,
                    correlation_id TEXT,
                    plan_version INTEGER NOT NULL,
                    runtime TEXT NOT NULL,
                    flow_key TEXT NOT NULL DEFAULT 'general',
                    highest_risk TEXT NOT NULL DEFAULT 'L1',
                    selection_reason TEXT NOT NULL DEFAULT '',
                    thread_id TEXT NOT NULL,
                    checkpoint_namespace TEXT NOT NULL DEFAULT 'pilot',
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    resume_payload_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, plan_version)
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_runs_pending
                    ON workflow_runs(runtime, status, next_attempt_at, lease_expires_at);

                CREATE TABLE IF NOT EXISTS mission_artifacts (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    mission_run_id TEXT,
                    correlation_id TEXT,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    work_run_id TEXT,
                    artifact_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(step_id) REFERENCES mission_steps(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_artifacts_scope
                    ON mission_artifacts(mission_id, plan_version, step_id, created_at);

                CREATE TABLE IF NOT EXISTS mission_evidence (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    mission_run_id TEXT,
                    correlation_id TEXT,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    artifact_id TEXT,
                    evidence_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    collected_by TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1,
                    fingerprint TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(step_id) REFERENCES mission_steps(id),
                    FOREIGN KEY(artifact_id) REFERENCES mission_artifacts(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_evidence_scope
                    ON mission_evidence(mission_id, plan_version, step_id, evidence_type);

                CREATE TABLE IF NOT EXISTS mission_acceptance_gates (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    mission_run_id TEXT,
                    correlation_id TEXT,
                    plan_version INTEGER NOT NULL,
                    step_id TEXT NOT NULL DEFAULT '',
                    gate_type TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    enforced INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    score INTEGER NOT NULL DEFAULT 0,
                    blockers_json TEXT NOT NULL DEFAULT '[]',
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    evaluated_by TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, plan_version, step_id, gate_type)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_acceptance_scope
                    ON mission_acceptance_gates(mission_id, plan_version, status, enforced);

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

                CREATE TABLE IF NOT EXISTS command_center_workers (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL DEFAULT 'orchestrator',
                    state TEXT NOT NULL DEFAULT 'running',
                    started_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    stopped_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_command_center_workers_live
                    ON command_center_workers(state, last_seen_at);

                CREATE TABLE IF NOT EXISTS agent_teams (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    leader_agent_id TEXT NOT NULL DEFAULT 'optimus',
                    status TEXT NOT NULL DEFAULT 'forming',
                    policy_version TEXT NOT NULL DEFAULT 'agent-team-v1',
                    max_members INTEGER NOT NULL DEFAULT 8,
                    max_parallel_tasks INTEGER NOT NULL DEFAULT 4,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    UNIQUE(mission_id, generation)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_teams_one_active
                    ON agent_teams(mission_id)
                    WHERE status NOT IN ('completed', 'failed', 'cancelled');

                CREATE TABLE IF NOT EXISTS agent_team_roles (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    role_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL DEFAULT '[]',
                    required_tools_json TEXT NOT NULL DEFAULT '[]',
                    min_instances INTEGER NOT NULL DEFAULT 0,
                    max_instances INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    UNIQUE(team_id, role_key)
                );

                CREATE TABLE IF NOT EXISTS agent_instances (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    instance_key TEXT NOT NULL,
                    base_agent_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'starting',
                    capacity INTEGER NOT NULL DEFAULT 1,
                    active_claims INTEGER NOT NULL DEFAULT 0,
                    context_thread_id TEXT,
                    context_pack_id TEXT,
                    last_seen_at TEXT,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    circuit_open_until TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    stopped_at TEXT,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(role_id) REFERENCES agent_team_roles(id),
                    UNIQUE(team_id, instance_key)
                );

                CREATE INDEX IF NOT EXISTS idx_agent_instances_schedulable
                    ON agent_instances(team_id, status, active_claims, last_seen_at);

                CREATE TABLE IF NOT EXISTS shared_tasks (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    mission_step_id TEXT,
                    task_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    task_type TEXT NOT NULL DEFAULT 'general',
                    status TEXT NOT NULL DEFAULT 'draft',
                    priority INTEGER NOT NULL DEFAULT 50,
                    risk_class TEXT NOT NULL DEFAULT 'L1',
                    dependencies_json TEXT NOT NULL DEFAULT '[]',
                    required_capabilities_json TEXT NOT NULL DEFAULT '[]',
                    required_tools_json TEXT NOT NULL DEFAULT '[]',
                    input_contract_json TEXT NOT NULL DEFAULT '{}',
                    output_contract_json TEXT NOT NULL DEFAULT '{}',
                    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
                    evidence_required_json TEXT NOT NULL DEFAULT '[]',
                    max_claims INTEGER NOT NULL DEFAULT 3,
                    idempotency_key TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(mission_step_id) REFERENCES mission_steps(id),
                    UNIQUE(team_id, task_key),
                    UNIQUE(team_id, idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_shared_tasks_queue
                    ON shared_tasks(team_id, status, priority, updated_at);

                CREATE TABLE IF NOT EXISTS shared_task_dependencies (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    shared_task_id TEXT NOT NULL,
                    depends_on_task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
                    FOREIGN KEY(depends_on_task_id) REFERENCES shared_tasks(id),
                    UNIQUE(shared_task_id, depends_on_task_id),
                    CHECK(shared_task_id <> depends_on_task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_shared_task_dependencies_ready
                    ON shared_task_dependencies(team_id, shared_task_id, depends_on_task_id);

                CREATE TABLE IF NOT EXISTS task_claims (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    shared_task_id TEXT NOT NULL,
                    agent_instance_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'claimed',
                    score REAL NOT NULL DEFAULT 0,
                    rationale_json TEXT NOT NULL DEFAULT '{}',
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    work_run_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT,
                    claimed_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
                    FOREIGN KEY(agent_instance_id) REFERENCES agent_instances(id),
                    UNIQUE(shared_task_id, attempt),
                    UNIQUE(shared_task_id, fencing_token)
                );

                CREATE INDEX IF NOT EXISTS idx_task_claims_active
                    ON task_claims(shared_task_id, status, lease_expires_at);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_task_claims_one_active
                    ON task_claims(shared_task_id)
                    WHERE status IN ('claimed', 'running', 'verifying');

                CREATE TABLE IF NOT EXISTS agent_task_context_bindings (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    shared_task_id TEXT NOT NULL,
                    task_claim_id TEXT NOT NULL,
                    work_run_id TEXT,
                    context_pack_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    source_refs_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
                    FOREIGN KEY(task_claim_id) REFERENCES task_claims(id)
                );

                CREATE INDEX IF NOT EXISTS idx_agent_task_context_active
                    ON agent_task_context_bindings(team_id, shared_task_id, task_claim_id, status);

                CREATE TABLE IF NOT EXISTS agent_messages (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    shared_task_id TEXT,
                    from_instance_id TEXT NOT NULL,
                    to_instance_id TEXT,
                    to_role_id TEXT,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
                    requires_ack INTEGER NOT NULL DEFAULT 0,
                    acknowledged_at TEXT,
                    correlation_id TEXT,
                    idempotency_key TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
                    FOREIGN KEY(from_instance_id) REFERENCES agent_instances(id),
                    FOREIGN KEY(to_instance_id) REFERENCES agent_instances(id),
                    FOREIGN KEY(to_role_id) REFERENCES agent_team_roles(id),
                    UNIQUE(team_id, idempotency_key),
                    CHECK(
                        (to_instance_id IS NOT NULL AND to_role_id IS NULL)
                        OR (to_instance_id IS NULL AND to_role_id IS NOT NULL)
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_agent_messages_route
                    ON agent_messages(team_id, to_instance_id, to_role_id, created_at);

                CREATE TABLE IF NOT EXISTS team_events (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    agent_instance_id TEXT,
                    shared_task_id TEXT,
                    detail TEXT NOT NULL DEFAULT '',
                    event_key TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES agent_teams(id),
                    FOREIGN KEY(mission_id) REFERENCES orchestration_missions(id),
                    FOREIGN KEY(agent_instance_id) REFERENCES agent_instances(id),
                    FOREIGN KEY(shared_task_id) REFERENCES shared_tasks(id),
                    UNIQUE(team_id, sequence),
                    UNIQUE(team_id, event_key)
                );

                CREATE INDEX IF NOT EXISTS idx_team_events_stream
                    ON team_events(team_id, sequence);
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
            self._ensure_column(conn, "command_messages", "target_agent_id", "TEXT NOT NULL DEFAULT 'optimus'")
            self._ensure_column(conn, "command_messages", "resolved_project_id", "TEXT")
            self._ensure_column(conn, "command_messages", "reply_to_command_message_id", "TEXT")
            self._ensure_column(conn, "mission_steps", "lease_token", "TEXT")
            self._ensure_column(
                conn,
                "task_claims",
                "team_id",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "task_claims",
                "fencing_token",
                "INTEGER NOT NULL DEFAULT 0",
            )
            conn.execute(
                """
                UPDATE task_claims
                SET team_id=COALESCE(
                    NULLIF(team_id, ''),
                    (SELECT team_id FROM shared_tasks WHERE id=task_claims.shared_task_id),
                    ''
                )
                WHERE team_id=''
                """
            )
            conn.execute(
                """
                UPDATE task_claims
                SET fencing_token=attempt
                WHERE fencing_token=0
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_task_claims_fencing
                ON task_claims(shared_task_id, fencing_token)
                """
            )
            self._ensure_column(
                conn,
                "mission_steps",
                "attempt_count",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(conn, "mission_events", "event_key", "TEXT")
            self._ensure_column(conn, "mission_events", "mission_run_id", "TEXT")
            self._ensure_column(conn, "mission_events", "correlation_id", "TEXT")
            self._ensure_column(
                conn,
                "mission_events",
                "run_sequence",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(conn, "workflow_runs", "mission_run_id", "TEXT")
            self._ensure_column(conn, "workflow_runs", "correlation_id", "TEXT")
            self._ensure_column(conn, "mission_artifacts", "mission_run_id", "TEXT")
            self._ensure_column(conn, "mission_artifacts", "correlation_id", "TEXT")
            self._ensure_column(conn, "mission_evidence", "mission_run_id", "TEXT")
            self._ensure_column(conn, "mission_evidence", "correlation_id", "TEXT")
            self._ensure_column(
                conn,
                "mission_acceptance_gates",
                "mission_run_id",
                "TEXT",
            )
            self._ensure_column(
                conn,
                "mission_acceptance_gates",
                "correlation_id",
                "TEXT",
            )
            self._ensure_column(conn, "mission_effects", "mission_run_id", "TEXT")
            self._ensure_column(conn, "mission_effects", "correlation_id", "TEXT")
            self._ensure_column(conn, "mission_compensations", "mission_run_id", "TEXT")
            self._ensure_column(conn, "mission_compensations", "correlation_id", "TEXT")
            self._ensure_column(
                conn,
                "mission_compensations",
                "authorization_expires_at",
                "TEXT",
            )
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
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_events_run_sequence
                ON mission_events(mission_run_id, run_sequence)
                WHERE mission_run_id IS NOT NULL AND mission_run_id != ''
                  AND run_sequence > 0
                """
            )
            self._backfill_mission_runs(conn)
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

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = self.repository.table_columns(conn, table)
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _backfill_mission_runs(self, conn: sqlite3.Connection) -> None:
        missions = conn.execute(
            "SELECT id FROM orchestration_missions ORDER BY created_at, id"
        ).fetchall()
        for mission in missions:
            run = self._ensure_mission_run(conn, str(mission["id"]))
            sequence = int(
                conn.execute(
                    """
                    SELECT COALESCE(MAX(run_sequence), 0) AS value
                    FROM mission_events
                    WHERE mission_run_id=? AND run_sequence > 0
                    """,
                    (run["id"],),
                ).fetchone()["value"]
                or 0
            )
            pending_events = conn.execute(
                """
                SELECT id FROM mission_events
                WHERE mission_id=?
                  AND (mission_run_id IS NULL OR mission_run_id='' OR run_sequence=0)
                ORDER BY created_at, id
                """,
                (mission["id"],),
            ).fetchall()
            for event in pending_events:
                sequence += 1
                conn.execute(
                    """
                    UPDATE mission_events
                    SET mission_run_id=?, correlation_id=?, run_sequence=?
                    WHERE id=?
                    """,
                    (run["id"], run["correlation_id"], sequence, event["id"]),
                )

    def _ensure_mission_run(
        self,
        conn: sqlite3.Connection,
        mission_id: str,
    ) -> sqlite3.Row:
        mission = self._require_mission(conn, mission_id)
        row = conn.execute(
            "SELECT * FROM mission_runs WHERE mission_id=?",
            (mission_id,),
        ).fetchone()
        if not row:
            now = _iso()
            run_id = f"mrun-{uuid.uuid4().hex[:16]}"
            correlation_id = f"mission-{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO mission_runs
                (id, mission_id, correlation_id, status, active_plan_version,
                 created_at, updated_at, ended_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    mission_id,
                    correlation_id,
                    mission["status"],
                    int(mission["plan_version"] or 0),
                    mission["created_at"] or now,
                    now,
                    mission["completed_at"],
                ),
            )
            row = conn.execute(
                "SELECT * FROM mission_runs WHERE id=?",
                (run_id,),
            ).fetchone()

        workflow = conn.execute(
            """
            SELECT id FROM workflow_runs
            WHERE mission_id=? AND plan_version=?
            """,
            (mission_id, mission["plan_version"]),
        ).fetchone()
        terminal = mission["status"] in TERMINAL_MISSION_STATES
        ended_at = (
            mission["completed_at"] or row["ended_at"] or _iso()
            if terminal
            else None
        )
        conn.execute(
            """
            UPDATE mission_runs
            SET status=?, active_plan_version=?, workflow_run_id=?,
                outcome=?, ended_at=?, updated_at=?
            WHERE id=?
            """,
            (
                mission["status"],
                int(mission["plan_version"] or 0),
                workflow["id"] if workflow else None,
                mission["status"] if terminal else "",
                ended_at,
                _iso(),
                row["id"],
            ),
        )
        conn.execute(
            """
            UPDATE workflow_runs
            SET mission_run_id=?, correlation_id=?
            WHERE mission_id=?
              AND (mission_run_id IS NULL OR mission_run_id=''
                   OR correlation_id IS NULL OR correlation_id='')
            """,
            (row["id"], row["correlation_id"], mission_id),
        )
        for table in (
            "mission_artifacts",
            "mission_evidence",
            "mission_acceptance_gates",
            "mission_effects",
            "mission_compensations",
        ):
            conn.execute(
                f"""
                UPDATE {table}
                SET mission_run_id=?, correlation_id=?
                WHERE mission_id=?
                  AND (mission_run_id IS NULL OR mission_run_id=''
                       OR correlation_id IS NULL OR correlation_id='')
                """,
                (row["id"], row["correlation_id"], mission_id),
            )
        return conn.execute(
            "SELECT * FROM mission_runs WHERE id=?",
            (row["id"],),
        ).fetchone()

    @staticmethod
    def _serialize_mission_run(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
        return item

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
            "finance": "finance_operation",
            "financial": "finance_operation",
            "accounting": "finance_operation",
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
        finance = any(marker in lowered for marker in FINANCE_MARKERS)
        if finance and not (execution and software):
            return "finance_operation", execution, "检测到财务查询或财务作业语义", 0.86
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

    @staticmethod
    def _space_node_position(agent_id: str, parent_id: str = "") -> tuple[int, int, str]:
        positions = {
            "optimus": (50, 18, "commander"),
            "main": (76, 18, "assistant"),
            "wheeljack": (25, 38, "pm"),
            "ironhide": (50, 38, "pm"),
            "ultra-magnus": (75, 38, "pm"),
            "leonardo": (28, 61, "development"),
            "raphael": (43, 68, "development"),
            "donatello": (58, 68, "development"),
            "michelangelo": (73, 61, "development"),
            "bumblebee": (18, 84, "support"),
            "perceptor": (33, 87, "support"),
            "ratchet": (48, 88, "support"),
            "jazz": (63, 87, "support"),
            "shockwave": (78, 84, "support"),
            "soundwave": (90, 76, "support"),
            "inspector": (90, 61, "support"),
        }
        if agent_id in positions:
            return positions[agent_id]
        lane = {
            "executive-office": "assistant",
            "project-managers": "pm",
            "development": "development",
            "business-support": "support",
        }.get(parent_id, "agent")
        return (50, 50, lane)

    @staticmethod
    def _space_status_from_step(status: str) -> str:
        if status == "completed":
            return "completed"
        if status == "failed":
            return "blocked"
        if status == "running":
            return "working"
        if status in {"ready", "draft"}:
            return "assigned"
        return "idle"

    @staticmethod
    def _space_progress_from_step(status: str) -> int:
        return {
            "completed": 100,
            "running": 55,
            "ready": 20,
            "draft": 10,
            "failed": 70,
            "cancelled": 0,
        }.get(status, 0)

    def agent_space(
        self,
        *,
        mission_id: str = "",
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        """Project the single-entry Optimus workflow into a read-only topology."""
        missions = self.list_missions(limit=150, owner_user_id=owner_user_id)
        project_lookup = self._project_lookup()
        task_ledger = self._load_task_ledger()
        items = [
            self._workbench_item(mission, task_ledger=task_ledger, project_lookup=project_lookup)
            for mission in missions
        ]
        terminal = TERMINAL_MISSION_STATES
        selected_item = next((item for item in items if item.get("mission_id") == mission_id), None)
        if not selected_item:
            selected_item = next((item for item in items if item.get("mission_status") not in terminal), None)
        if not selected_item and items:
            selected_item = items[0]

        selected_mission_id = str((selected_item or {}).get("mission_id") or mission_id or "")
        selected_mission: dict[str, Any] = {}
        if selected_mission_id:
            try:
                selected_mission = self.get_mission(
                    selected_mission_id,
                    owner_user_id=owner_user_id,
                )
            except CommandCenterError:
                selected_mission = {}

        try:
            org = unified_data_manager.get_agent_organization_document()
        except Exception:
            org = {"root": {}, "nodes": [], "relations": []}

        org_nodes = [org.get("root"), *(org.get("nodes") or [])]
        visible_agents: list[dict[str, Any]] = []
        for node in org_nodes:
            if not isinstance(node, dict):
                continue
            if node.get("node_type") not in {"agent", "assistant"}:
                continue
            agent_id = str(node.get("agent_id") or node.get("id") or "")
            if not agent_id:
                continue
            x, y, lane = self._space_node_position(agent_id, str(node.get("parent_id") or ""))
            visible_agents.append({
                "id": agent_id,
                "agent_id": agent_id,
                "name": node.get("name") or self._agent_name(agent_id),
                "role": node.get("title") or "",
                "emoji": node.get("emoji") or "",
                "node_type": node.get("node_type"),
                "parent_id": node.get("parent_id") or "",
                "lane": lane,
                "x": x,
                "y": y,
            })

        steps = selected_mission.get("steps") or []
        steps_by_agent: dict[str, list[dict[str, Any]]] = {}
        steps_by_id: dict[str, dict[str, Any]] = {}
        for step in steps:
            if not isinstance(step, dict):
                continue
            steps_by_id[str(step.get("id") or "")] = step
            steps_by_agent.setdefault(str(step.get("agent_id") or "optimus"), []).append(step)

        active_agent_ids = {
            str(step.get("agent_id") or "")
            for step in steps
            if isinstance(step, dict) and step.get("status") in {"running", "ready", "draft", "failed"}
        }
        active_agent_ids.discard("")
        active_mission_counts: dict[str, int] = {}
        for item in items:
            if item.get("mission_status") in terminal:
                continue
            agent_id = str(item.get("current_agent_id") or "optimus")
            active_mission_counts[agent_id] = active_mission_counts.get(agent_id, 0) + 1

        nodes = []
        for node in visible_agents:
            agent_id = node["agent_id"]
            agent_steps = steps_by_agent.get(agent_id, [])
            current_step = next(
                (step for step in agent_steps if step.get("status") in {"running", "failed", "ready", "draft"}),
                agent_steps[-1] if agent_steps else None,
            )
            status = "coordinating" if agent_id == "optimus" and selected_mission else "idle"
            progress = 0
            current_task = ""
            if current_step:
                status = self._space_status_from_step(str(current_step.get("status") or ""))
                progress = self._space_progress_from_step(str(current_step.get("status") or ""))
                current_task = str(current_step.get("title") or "")
            elif active_mission_counts.get(agent_id):
                status = "working"
                progress = 35
            if agent_id in active_agent_ids and status == "idle":
                status = "assigned"
            if selected_item and agent_id == "optimus":
                status = "coordinating"
                progress = max(progress, min(100, int(selected_item.get("progress") or 0)))
                current_task = selected_item.get("active_step", {}).get("title") if isinstance(selected_item.get("active_step"), dict) else ""
                current_task = current_task or "拆分、协调、验收与汇报"
            nodes.append({
                **node,
                "status": status,
                "progress": progress,
                "current_task": current_task,
                "active_mission_count": active_mission_counts.get(agent_id, 0),
                "is_commander": agent_id == "optimus",
                "can_direct_command": agent_id == "optimus",
            })

        node_ids = {node["id"] for node in nodes}
        edges: list[dict[str, Any]] = []

        def add_edge(source: str, target: str, edge_type: str, label: str, *, step_id: str = "", active: bool = False) -> None:
            if source not in node_ids or target not in node_ids or source == target:
                return
            edge_id = f"{edge_type}:{source}:{target}:{step_id or label}"
            if any(edge["id"] == edge_id for edge in edges):
                return
            edges.append({
                "id": edge_id,
                "from": source,
                "to": target,
                "type": edge_type,
                "label": label,
                "step_id": step_id,
                "active": active,
            })

        for target in ("main", "wheeljack", "ironhide", "ultra-magnus", "leonardo", "bumblebee", "perceptor", "ratchet", "jazz", "shockwave", "soundwave"):
            add_edge("optimus", target, "command", "擎天柱统一调度")
        for target in ("raphael", "donatello", "michelangelo"):
            add_edge("leonardo", target, "development", "开发级协同")
        add_edge("optimus", "inspector", "review", "质量观察")

        for step in steps:
            if not isinstance(step, dict):
                continue
            target = str(step.get("agent_id") or "")
            step_id = str(step.get("id") or "")
            step_status = str(step.get("status") or "")
            add_edge(
                "optimus",
                target,
                "delegates",
                str(step.get("title") or "任务分工"),
                step_id=step_id,
                active=step_status in {"running", "ready", "draft", "failed"},
            )
            for dependency_id in step.get("dependencies") or []:
                dependency = steps_by_id.get(str(dependency_id))
                if dependency:
                    add_edge(
                        str(dependency.get("agent_id") or ""),
                        target,
                        "depends_on",
                        "依赖",
                        step_id=step_id,
                        active=step_status in {"running", "ready", "draft", "failed"},
                    )

        return {
            "commander": "optimus",
            "single_entry": True,
            "mission": {
                "id": selected_mission.get("id") or selected_mission_id,
                "title": selected_mission.get("title") or (selected_item or {}).get("mission_title") or "",
                "status": selected_mission.get("status") or (selected_item or {}).get("mission_status") or "",
                "progress": (selected_item or {}).get("progress") or 0,
                "active_step": (selected_item or {}).get("active_step"),
            },
            "nodes": nodes,
            "edges": edges,
            "lanes": [
                {"id": "commander", "label": "总指挥"},
                {"id": "pm", "label": "项目经理"},
                {"id": "development", "label": "开发执行"},
                {"id": "support", "label": "保障能力"},
            ],
            "updated_at": _iso(),
        }

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

        if intent_type == "finance_operation":
            return {
                "intent_type": intent_type,
                "confidence": confidence,
                "reason": reason,
                "execution_requested": execution_requested,
                "routing_status": "awaiting_finance_processing",
                "target_agent_id": "soundwave",
                "project": None,
                "project_candidates": [],
                "clarification_question": "",
                "objective": text,
            }

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
                "target_agent_id": "optimus",
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
                "target_agent_id": "optimus",
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

    def get_external_user_binding(self, *, channel: str, external_user_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            return dict(
                self._require_external_user_binding(
                    conn,
                    channel=channel,
                    external_user_id=external_user_id,
                )
            )

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
                 target_agent_id, resolved_project_id, metadata, created_at)
                VALUES (?, ?, ?, 'inbound', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    route.get("target_agent_id") or "optimus",
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

            if route["intent_type"] in {"discussion", "clarification_required", "finance_operation"}:
                return {
                    "action": (
                        "finance_intake"
                        if route["intent_type"] == "finance_operation"
                        else "discussion"
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
                    "target_agent_id": route.get("target_agent_id") or "optimus",
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
                self.repository.claim_query(
                    """
                SELECT * FROM orchestration_missions
                WHERE status IN ('received', 'planning')
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ? OR lease_owner=?)
                ORDER BY created_at ASC LIMIT 1
                    """
                ),
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
        steps = list(plan.get("steps") or []) if isinstance(plan, dict) else []
        if not steps:
            raise CommandCenterError("plan must include at least one step")
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            if mission["status"] not in {"planning", "waiting_feedback", "failed"}:
                raise InvalidMissionTransition(
                    f"cannot save plan while mission is {mission['status']}"
                )
            plan = plan_quality_service.enrich_plan(plan, mission=mission)
            quality = plan.get("plan_quality") if isinstance(plan.get("plan_quality"), dict) else {}
            blockers = quality.get("blockers") if isinstance(quality.get("blockers"), list) else []
            if blockers:
                raise CommandCenterError(
                    "计划质量检查未通过：" + "；".join(str(item) for item in blockers[:4])
                )
            steps = list(plan.get("steps") or [])
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
            runtime_selection = self.workflow_runtime_selector(plan)
            runtime_name = str(runtime_selection.get("runtime") or "legacy")
            if runtime_name not in {"legacy", "langgraph"}:
                runtime_selection = {
                    **runtime_selection,
                    "runtime": "legacy",
                    "eligible": False,
                    "reason": "invalid_runtime_selection",
                }
                runtime_name = "legacy"
            workflow_run_id = f"workflow-{uuid.uuid4().hex[:12]}"
            mission_run = self._ensure_mission_run(conn, mission_id)
            planning_binding = conn.execute(
                """
                SELECT context_pack_id FROM mission_context_bindings
                WHERE mission_id=? AND plan_version=? AND step_id='' AND purpose='planning'
                """,
                (mission_id, version),
            ).fetchone()
            workflow_input = {
                "workflow_run_id": workflow_run_id,
                "mission_run_id": mission_run["id"],
                "correlation_id": mission_run["correlation_id"],
                "mission_id": mission_id,
                "plan_version": version,
                "flow_key": str(runtime_selection.get("flow_key") or "general"),
                "highest_risk": str(
                    runtime_selection.get("highest_risk") or "L1"
                ),
                "context_pack_id": (
                    str(planning_binding["context_pack_id"] or "")
                    if planning_binding
                    else ""
                ),
                "status": "ready" if runtime_name == "legacy" else "pending_start",
                "evidence_refs": [],
            }
            now = _iso()
            conn.execute(
                """
                INSERT INTO workflow_runs
                (id, mission_id, mission_run_id, correlation_id,
                 plan_version, runtime, flow_key, highest_risk,
                 selection_reason, thread_id, checkpoint_namespace, status,
                 input_json, state_json, next_attempt_at, created_at, updated_at,
                 completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pilot', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    mission_id,
                    mission_run["id"],
                    mission_run["correlation_id"],
                    version,
                    runtime_name,
                    workflow_input["flow_key"],
                    workflow_input["highest_risk"],
                    str(runtime_selection.get("reason") or ""),
                    workflow_run_id,
                    "ready" if runtime_name == "legacy" else "start_pending",
                    _json(workflow_input),
                    _json(workflow_input if runtime_name == "legacy" else {}),
                    now,
                    now,
                    now,
                    now if runtime_name == "legacy" else None,
                ),
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
                {
                    "version": version,
                    "step_count": len(steps),
                    "flow_key": (plan.get("flow_spec") or {}).get("flow_key"),
                    "flow_version": (plan.get("flow_spec") or {}).get("version"),
                    "highest_risk": (plan.get("risk_assessment") or {}).get("highest_risk"),
                    "quality_score": (plan.get("plan_quality") or {}).get("score"),
                    "workflow_runtime": runtime_name,
                    "workflow_runtime_reason": runtime_selection.get("reason"),
                },
            )
            updated = self._require_mission(conn, mission_id)
            lines = [
                f"任务 {mission_id} 的执行计划已生成（V{version}）",
                summary,
                "",
            ]
            for index, step in enumerate(steps, start=1):
                risk_class = str(step.get("risk_class") or "")
                approval_label = " · 需明确审批" if step.get("approval_required") else ""
                lines.append(
                    f"{index}. {step.get('title') or f'步骤 {index}'}"
                    f" · {step.get('agent_id') or 'optimus'}"
                    f"{f' · {risk_class}' if risk_class else ''}"
                    f"{approval_label}"
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

    def list_step_approvals(
        self,
        mission_id: str,
        *,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            mission = self._require_mission(conn, mission_id)
            if owner_user_id and str(mission["owner_user_id"] or "") != str(owner_user_id):
                raise MissionNotFound(mission_id)
            mission_run = self._ensure_mission_run(conn, mission_id)
            rows = conn.execute(
                """
                SELECT * FROM mission_step_approvals
                WHERE mission_id=? AND plan_version=?
                ORDER BY step_id, request_version DESC
                """,
                (mission_id, mission["plan_version"]),
            ).fetchall()
            approvals = [self._serialize_step_approval(row) for row in rows]
            current: dict[str, dict[str, Any]] = {}
            for approval in approvals:
                current.setdefault(approval["step_id"], approval)
            return {
                "mission_id": mission_id,
                "mission_run_id": mission_run["id"],
                "correlation_id": mission_run["correlation_id"],
                "plan_version": int(mission["plan_version"]),
                "policy": self.step_approval_policy(),
                "current": list(current.values()),
                "history": approvals,
            }

    def decide_step_approval(
        self,
        mission_id: str,
        step_id: str,
        *,
        approval_id: str,
        contract_hash: str,
        decision: str,
        decided_by: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise CommandCenterError(f"invalid step approval decision: {decision}")
        if decision == "rejected" and not str(comment or "").strip():
            raise CommandCenterError("rejecting a high-risk step requires a comment")
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            if mission["status"] != "running":
                raise InvalidMissionTransition(
                    f"mission {mission_id} is not running"
                )
            step_row = conn.execute(
                """
                SELECT * FROM mission_steps
                WHERE id=? AND mission_id=? AND plan_version=?
                """,
                (step_id, mission_id, mission["plan_version"]),
            ).fetchone()
            if not step_row:
                raise CommandCenterError(f"step not found in current plan: {step_id}")
            if step_row["status"] != "awaiting_approval":
                raise InvalidMissionTransition(
                    f"step {step_id} is not awaiting approval"
                )
            approval = conn.execute(
                """
                SELECT * FROM mission_step_approvals
                WHERE step_id=? ORDER BY request_version DESC LIMIT 1
                """,
                (step_id,),
            ).fetchone()
            if not approval or approval["id"] != str(approval_id or ""):
                raise InvalidMissionTransition("step approval request is stale")
            if approval["status"] != "pending":
                raise InvalidMissionTransition(
                    f"step approval is already {approval['status']}"
                )
            if approval["expires_at"] <= _iso():
                conn.execute(
                    "UPDATE mission_step_approvals SET status='expired' WHERE id=?",
                    (approval["id"],),
                )
                raise InvalidMissionTransition("step approval request has expired")
            step = self._serialize_step(step_row)
            self._attach_plan_step_contract(conn, step)
            actual_hash = self._step_contract_hash(step)
            if (
                not contract_hash
                or contract_hash != approval["contract_hash"]
                or actual_hash != approval["contract_hash"]
            ):
                conn.execute(
                    "UPDATE mission_step_approvals SET status='cancelled' WHERE id=?",
                    (approval["id"],),
                )
                raise InvalidMissionTransition(
                    "step contract changed; request a new approval"
                )
            decided_at = _iso()
            expires_at = approval["expires_at"]
            if decision == "approved":
                expires_at = _iso(
                    _now()
                    + timedelta(
                        seconds=self.step_approval_policy()["approval_ttl_seconds"]
                    )
                )
            conn.execute(
                """
                UPDATE mission_step_approvals
                SET status=?, decided_at=?, decided_by=?, comment=?, expires_at=?
                WHERE id=? AND status='pending'
                """,
                (
                    decision,
                    decided_at,
                    decided_by,
                    str(comment or "")[:4000],
                    expires_at,
                    approval["id"],
                ),
            )
            if decision == "approved":
                conn.execute(
                    "UPDATE mission_steps SET status='ready', updated_at=? WHERE id=?",
                    (_iso(), step_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE mission_steps
                    SET status='failed', result_json=?, completed_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        _json(
                            {
                                "success": False,
                                "error": "high-risk step rejected",
                                "approval_id": approval["id"],
                                "comment": comment,
                            }
                        ),
                        _iso(),
                        _iso(),
                        step_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE orchestration_missions
                    SET status='waiting_feedback', last_error=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        f"高风险步骤“{step['title']}”审批被拒绝：{comment}"[:4000],
                        _iso(),
                        mission_id,
                    ),
                )
            self._add_event(
                conn,
                mission_id,
                f"step_approval_{decision}",
                "running",
                "running" if decision == "approved" else "waiting_feedback",
                decided_by,
                comment or decision,
                {
                    "step_id": step_id,
                    "approval_id": approval["id"],
                    "contract_hash": actual_hash,
                    "expires_at": expires_at,
                },
            )
            updated_mission = self._require_mission(conn, mission_id)
            self._queue_notification(
                conn,
                mission=updated_mission,
                text=(
                    f"高风险步骤“{step['title']}”已获得独立授权，将在授权有效期内执行。"
                    if decision == "approved"
                    else f"高风险步骤“{step['title']}”已拒绝，任务等待调整。"
                ),
                event_key=f"step-approval:{approval['id']}:{decision}",
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            updated = conn.execute(
                "SELECT * FROM mission_step_approvals WHERE id=?",
                (approval["id"],),
            ).fetchone()
            return {
                "success": True,
                "approval": self._serialize_step_approval(updated),
                "mission": self._serialize_mission(conn, updated_mission),
            }

    def list_compensations(
        self,
        mission_id: str,
        *,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            mission = self._require_mission(conn, mission_id)
            if owner_user_id and str(mission["owner_user_id"] or "") != str(owner_user_id):
                raise MissionNotFound(mission_id)
            effects = conn.execute(
                """
                SELECT * FROM mission_effects
                WHERE mission_id=? AND plan_version=? ORDER BY reported_at, id
                """,
                (mission_id, mission["plan_version"]),
            ).fetchall()
            compensations = conn.execute(
                """
                SELECT * FROM mission_compensations
                WHERE mission_id=? AND plan_version=? ORDER BY requested_at, id
                """,
                (mission_id, mission["plan_version"]),
            ).fetchall()
            return {
                "mission_id": mission_id,
                "plan_version": int(mission["plan_version"]),
                "policy": compensation_service.catalog()["policy"],
                "effects": [self._serialize_effect(row) for row in effects],
                "compensations": [
                    self._serialize_compensation(row) for row in compensations
                ],
            }

    def decide_compensation(
        self,
        compensation_id: str,
        *,
        expected_mission_id: str = "",
        contract_hash: str,
        decision: str,
        decided_by: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise CommandCenterError(f"invalid compensation decision: {decision}")
        if decision == "rejected" and not str(comment or "").strip():
            raise CommandCenterError("rejecting compensation requires a comment")
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM mission_compensations WHERE id=?",
                (compensation_id,),
            ).fetchone()
            if not row:
                raise CommandCenterError(f"compensation not found: {compensation_id}")
            if expected_mission_id and row["mission_id"] != expected_mission_id:
                raise CommandCenterError(
                    f"compensation {compensation_id} does not belong to mission {expected_mission_id}"
                )
            mission = self._require_mission(conn, row["mission_id"])
            if mission["status"] not in {"running", "waiting_feedback"}:
                raise InvalidMissionTransition(
                    f"mission {mission['id']} cannot decide compensation while {mission['status']}"
                )
            if row["plan_version"] != mission["plan_version"]:
                raise InvalidMissionTransition("compensation belongs to a stale plan")
            if row["status"] not in {"pending_approval", "failed"}:
                raise InvalidMissionTransition(
                    f"compensation is already {row['status']}"
                )
            if not contract_hash or contract_hash != row["contract_hash"]:
                raise InvalidMissionTransition("compensation contract hash mismatch")
            next_status = "ready" if decision == "approved" else "rejected"
            try:
                approval_ttl = int(
                    os.getenv("COMMAND_CENTER_COMPENSATION_APPROVAL_TTL", "1800")
                )
            except (TypeError, ValueError):
                approval_ttl = 1800
            authorization_expires_at = (
                _iso(_now() + timedelta(seconds=max(60, approval_ttl)))
                if decision == "approved"
                else None
            )
            conn.execute(
                """
                UPDATE mission_compensations
                SET status=?, approved_at=?, approved_by=?, approval_comment=?,
                    authorization_expires_at=?,
                    last_error=CASE WHEN ?='ready' THEN NULL ELSE last_error END,
                    updated_at=?
                WHERE id=? AND status IN ('pending_approval', 'failed')
                """,
                (
                    next_status,
                    _iso(),
                    decided_by,
                    str(comment or "")[:4000],
                    authorization_expires_at,
                    next_status,
                    _iso(),
                    compensation_id,
                ),
            )
            self._add_event(
                conn,
                mission["id"],
                f"compensation_{decision}",
                mission["status"],
                mission["status"],
                decided_by,
                comment or decision,
                {
                    "compensation_id": compensation_id,
                    "effect_id": row["effect_id"],
                    "contract_hash": row["contract_hash"],
                    "authorization_expires_at": authorization_expires_at,
                },
            )
            self._sync_mission_ledger_safe(conn, mission["id"])
            updated = conn.execute(
                "SELECT * FROM mission_compensations WHERE id=?",
                (compensation_id,),
            ).fetchone()
            return {
                "success": True,
                "compensation": self._serialize_compensation(updated),
                "mission": self._serialize_mission(conn, mission),
            }

    def requeue_stale_compensations(self) -> int:
        with self.connect(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM mission_compensations
                WHERE status='running' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                """,
                (_iso(),),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE mission_compensations
                    SET status='pending_approval', approved_at=NULL, approved_by=NULL,
                        approval_comment=NULL, lease_owner=NULL, lease_token=NULL,
                        authorization_expires_at=NULL, lease_expires_at=NULL,
                        last_error='Interrupted compensation requires reapproval',
                        updated_at=?
                    WHERE id=? AND status='running'
                    """,
                    (_iso(), row["id"]),
                )
                mission = self._require_mission(conn, row["mission_id"])
                self._add_event(
                    conn,
                    row["mission_id"],
                    "compensation_reapproval_required",
                    mission["status"],
                    mission["status"],
                    "command-center",
                    "补偿执行租约过期，必须重新审批后才能重试",
                    {"compensation_id": row["id"]},
                )
            return len(rows)

    def expire_compensation_approvals(self) -> int:
        with self.connect(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM mission_compensations
                WHERE status='ready' AND authorization_expires_at IS NOT NULL
                  AND authorization_expires_at <= ?
                """,
                (_iso(),),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE mission_compensations
                    SET status='pending_approval', approved_at=NULL, approved_by=NULL,
                        approval_comment=NULL, authorization_expires_at=NULL,
                        last_error='Compensation authorization expired', updated_at=?
                    WHERE id=? AND status='ready'
                    """,
                    (_iso(), row["id"]),
                )
                mission = self._require_mission(conn, row["mission_id"])
                self._add_event(
                    conn,
                    row["mission_id"],
                    "compensation_approval_expired",
                    mission["status"],
                    mission["status"],
                    "command-center",
                    "补偿授权已过期，需要重新审批",
                    {"compensation_id": row["id"]},
                )
            return len(rows)

    def claim_ready_compensation(
        self,
        owner: str,
        *,
        lease_seconds: int = 900,
    ) -> dict[str, Any] | None:
        now = _now()
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                self.repository.claim_query(
                    """
                SELECT compensations.*
                FROM mission_compensations compensations
                JOIN orchestration_missions missions ON missions.id=compensations.mission_id
                WHERE compensations.status='ready'
                  AND compensations.authorization_expires_at > ?
                  AND compensations.plan_version=missions.plan_version
                AND missions.status IN ('running', 'waiting_feedback')
                ORDER BY compensations.requested_at LIMIT 1
                    """,
                    table_alias="compensations",
                ),
                (_iso(now),),
            ).fetchone()
            if not row:
                return None
            lease_token = f"compensation-lease-{uuid.uuid4().hex}"
            cursor = conn.execute(
                """
                UPDATE mission_compensations
                SET status='running', attempts=attempts+1, lease_owner=?, lease_token=?,
                    lease_expires_at=?, started_at=COALESCE(started_at, ?), updated_at=?
                WHERE id=? AND status='ready'
                """,
                (
                    owner,
                    lease_token,
                    _iso(now + timedelta(seconds=max(lease_seconds, 60))),
                    _iso(now),
                    _iso(now),
                    row["id"],
                ),
            )
            if cursor.rowcount != 1:
                return None
            updated = conn.execute(
                "SELECT * FROM mission_compensations WHERE id=?",
                (row["id"],),
            ).fetchone()
            item = self._serialize_compensation(updated, include_private=True)
            effect = conn.execute(
                "SELECT * FROM mission_effects WHERE id=?", (row["effect_id"],)
            ).fetchone()
            step = conn.execute(
                "SELECT * FROM mission_steps WHERE id=?", (row["step_id"],)
            ).fetchone()
            item["effect"] = self._serialize_effect(effect)
            item["step"] = self._serialize_step(step)
            self._attach_plan_step_contract(conn, item["step"])
            return item

    def renew_compensation_lease(
        self,
        compensation_id: str,
        *,
        lease_token: str,
        lease_seconds: int = 900,
    ) -> str:
        expires_at = _iso(
            _now() + timedelta(seconds=max(60, int(lease_seconds)))
        )
        with self.connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                UPDATE mission_compensations
                SET lease_expires_at=?, updated_at=?
                WHERE id=? AND status='running' AND lease_token=?
                """,
                (expires_at, _iso(), compensation_id, lease_token),
            )
            if cursor.rowcount != 1:
                raise InvalidMissionTransition(
                    f"compensation lease was lost: {compensation_id}"
                )
        return expires_at

    def complete_compensation(
        self,
        compensation_id: str,
        *,
        lease_token: str,
        result: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        normalized = compensation_service.normalize_compensation_result(result)
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM mission_compensations WHERE id=?",
                (compensation_id,),
            ).fetchone()
            if not row:
                raise CommandCenterError(f"compensation not found: {compensation_id}")
            if row["status"] != "running" or row["lease_token"] != lease_token:
                raise InvalidMissionTransition("stale compensation completion rejected")
            accepted = bool(normalized["accepted"])
            next_status = "completed" if accepted else "failed"
            conn.execute(
                """
                UPDATE mission_compensations
                SET status=?, result_json=?, last_error=?, lease_owner=NULL,
                    lease_token=NULL, lease_expires_at=NULL, completed_at=?, updated_at=?
                WHERE id=? AND status='running' AND lease_token=?
                """,
                (
                    next_status,
                    _json(normalized),
                    None if accepted else str(normalized.get("summary") or "Compensation failed")[:4000],
                    _iso(),
                    _iso(),
                    compensation_id,
                    lease_token,
                ),
            )
            if accepted:
                conn.execute(
                    """
                    UPDATE mission_effects
                    SET status='reverted', receipt_ref=?, evidence_refs_json=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        normalized["receipt_ref"],
                        _json(normalized["evidence_refs"]),
                        _iso(),
                        row["effect_id"],
                    ),
                )
            mission = self._require_mission(conn, row["mission_id"])
            self._add_event(
                conn,
                row["mission_id"],
                "compensation_completed" if accepted else "compensation_failed",
                mission["status"],
                mission["status"],
                actor,
                normalized["summary"],
                {
                    "compensation_id": compensation_id,
                    "effect_id": row["effect_id"],
                    "accepted": accepted,
                    "receipt_ref": normalized["receipt_ref"],
                },
            )
            self._sync_mission_ledger_safe(conn, row["mission_id"])
            updated = conn.execute(
                "SELECT * FROM mission_compensations WHERE id=?",
                (compensation_id,),
            ).fetchone()
            return self._serialize_compensation(updated)

    def cancel(self, mission_id: str, *, actor: str, comment: str = "") -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            return self._serialize_mission(
                conn,
                self._cancel_mission(conn, mission, actor=actor, comment=comment),
            )

    def reopen_for_recovery(
        self,
        mission_id: str,
        *,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        detail = str(reason or "").strip()
        if not detail:
            raise CommandCenterError("recovery reason is required")
        with self.connect(immediate=True) as conn:
            mission = self._require_mission(conn, mission_id)
            if mission["status"] != "completed":
                raise InvalidMissionTransition(
                    f"only a completed mission can be reopened for recovery: {mission['status']}"
                )
            previous_plan_version = int(mission["plan_version"] or 0)
            conn.execute(
                """
                UPDATE orchestration_missions
                SET status='waiting_feedback', completed_at=NULL, last_error=?,
                    lease_owner=NULL, lease_expires_at=NULL, updated_at=?
                WHERE id=? AND status='completed'
                """,
                (detail[:4000], _iso(), mission_id),
            )
            self._add_event(
                conn,
                mission_id,
                "mission_reopened_for_recovery",
                "completed",
                "waiting_feedback",
                actor,
                detail[:1000],
                {"previous_plan_version": previous_plan_version},
            )
            self._sync_mission_ledger_safe(conn, mission_id)
            return self._serialize_mission(
                conn,
                self._require_mission(conn, mission_id),
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
                unresolved_compensations = conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM mission_compensations
                    WHERE mission_id=? AND plan_version=? AND status!='completed'
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchone()["count"]
                if unresolved_compensations:
                    self._queue_notification(
                        conn,
                        mission=mission,
                        text=(
                            f"已收到对 {mission_id} 的反馈，但仍有 "
                            f"{unresolved_compensations} 个副作用补偿未完成。"
                            "完成或处理补偿前不会重试原步骤。"
                        ),
                        event_key=f"feedback-compensation-blocked:{message_id}",
                    )
                    self._sync_mission_ledger_safe(conn, mission_id)
                    return self._serialize_mission(conn, mission)
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
                  AND NOT EXISTS (
                      SELECT 1 FROM workflow_runs wr
                      WHERE wr.mission_id=orchestration_missions.id
                        AND wr.plan_version=orchestration_missions.plan_version
                        AND wr.runtime='langgraph'
                        AND wr.status!='ready'
                  )
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

    @staticmethod
    def step_approval_policy() -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "required_for": ["approval_required=true", "risk_class=L3"],
            "binding": "mission_id + plan_version + step_id + contract_hash",
            "single_use": True,
            "approval_ttl_seconds": max(
                60, int(os.getenv("COMMAND_CENTER_STEP_APPROVAL_TTL", "1800"))
            ),
            "request_ttl_seconds": max(
                300,
                int(os.getenv("COMMAND_CENTER_STEP_APPROVAL_REQUEST_TTL", "86400")),
            ),
            "retry_policy": "a consumed approval is never reused after an interrupted execution",
        }

    @staticmethod
    def _step_contract_hash(step: dict[str, Any]) -> str:
        protected = {
            "mission_id": step.get("mission_id"),
            "plan_version": int(step.get("plan_version") or 0),
            "step_id": step.get("id"),
            "order_index": int(step.get("order_index") or 0),
            "title": step.get("title") or "",
            "description": step.get("description") or "",
            "objective": step.get("objective") or "",
            "agent_id": step.get("agent_id") or "",
            "task_type": step.get("task_type") or "",
            "input": step.get("input") or {},
            "risk_class": step.get("risk_class") or "",
            "approval_required": bool(step.get("approval_required")),
            "side_effect": bool(step.get("side_effect")),
            "resources": step.get("resources") or [],
            "idempotency_key": step.get("idempotency_key") or "",
            "rollback_plan": step.get("rollback_plan") or "",
            "compensation": step.get("compensation") or {},
        }
        canonical = json.dumps(
            protected,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _request_step_approval(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
        step: dict[str, Any],
        *,
        reason: str,
    ) -> sqlite3.Row:
        current = conn.execute(
            """
            SELECT * FROM mission_step_approvals
            WHERE step_id=? ORDER BY request_version DESC LIMIT 1
            """,
            (step["id"],),
        ).fetchone()
        contract_hash = self._step_contract_hash(step)
        if (
            current
            and current["status"] == "pending"
            and current["contract_hash"] == contract_hash
            and current["expires_at"] > _iso()
        ):
            conn.execute(
                "UPDATE mission_steps SET status='awaiting_approval', updated_at=? WHERE id=?",
                (_iso(), step["id"]),
            )
            return current

        request_version = int(current["request_version"] or 0) + 1 if current else 1
        approval_id = f"step-approval-{uuid.uuid4().hex[:12]}"
        request_ttl = self.step_approval_policy()["request_ttl_seconds"]
        action_summary = str(
            step.get("objective") or step.get("description") or step.get("title") or ""
        )[:1000]
        conn.execute(
            """
            INSERT INTO mission_step_approvals
            (id, mission_id, plan_version, step_id, request_version, risk_class,
             action_summary, contract_hash, status, requested_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                approval_id,
                mission["id"],
                mission["plan_version"],
                step["id"],
                request_version,
                str(step.get("risk_class") or "L3"),
                action_summary,
                contract_hash,
                _iso(),
                _iso(_now() + timedelta(seconds=request_ttl)),
            ),
        )
        conn.execute(
            "UPDATE mission_steps SET status='awaiting_approval', updated_at=? WHERE id=?",
            (_iso(), step["id"]),
        )
        self._add_event(
            conn,
            mission["id"],
            "step_approval_requested",
            mission["status"],
            mission["status"],
            "command-center",
            f"步骤“{step['title']}”等待独立审批",
            {
                "step_id": step["id"],
                "approval_id": approval_id,
                "request_version": request_version,
                "risk_class": step.get("risk_class"),
                "contract_hash": contract_hash,
                "reason": reason,
                "rollback_plan": step.get("rollback_plan") or "",
            },
        )
        self._queue_notification(
            conn,
            mission=mission,
            text=(
                f"任务 {mission['id']} 的高风险步骤等待独立审批：\n"
                f"步骤：{step['title']}\n"
                f"风险：{step.get('risk_class') or 'L3'}\n"
                f"动作：{action_summary}\n"
                f"回滚：{step.get('rollback_plan') or '未提供'}\n"
                f"审批编号：{approval_id}"
            ),
            event_key=f"step-approval-request:{approval_id}",
        )
        return conn.execute(
            "SELECT * FROM mission_step_approvals WHERE id=?",
            (approval_id,),
        ).fetchone()

    def _authorize_step_execution(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
        step: dict[str, Any],
    ) -> tuple[bool, str]:
        if not bool(step.get("approval_required")):
            return True, ""
        contract_hash = self._step_contract_hash(step)
        approval = conn.execute(
            """
            SELECT * FROM mission_step_approvals
            WHERE step_id=? ORDER BY request_version DESC LIMIT 1
            """,
            (step["id"],),
        ).fetchone()
        if approval:
            valid = (
                approval["status"] == "approved"
                and not approval["consumed_at"]
                and approval["contract_hash"] == contract_hash
                and approval["expires_at"] > _iso()
            )
            if valid:
                return True, str(approval["id"])
            if approval["status"] in {"pending", "approved"}:
                next_status = (
                    "expired"
                    if approval["expires_at"] <= _iso()
                    else "cancelled"
                )
                conn.execute(
                    "UPDATE mission_step_approvals SET status=? WHERE id=?",
                    (next_status, approval["id"]),
                )
        reason = (
            "retry_after_interrupted_execution"
            if approval and approval["consumed_at"]
            else "contract_changed"
            if approval and approval["contract_hash"] != contract_hash
            else "approval_required"
        )
        self._request_step_approval(conn, mission, step, reason=reason)
        return False, ""

    def expire_step_approvals(self) -> int:
        """Rotate stale requests/authorizations without ever making a step runnable."""

        now = _iso()
        rotated = 0
        with self.connect(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT approvals.*, steps.status AS step_status
                FROM mission_step_approvals approvals
                JOIN mission_steps steps ON steps.id=approvals.step_id
                JOIN orchestration_missions missions ON missions.id=approvals.mission_id
                WHERE approvals.status IN ('pending', 'approved')
                  AND approvals.expires_at <= ?
                  AND approvals.plan_version=missions.plan_version
                  AND missions.status='running'
                  AND steps.status IN ('ready', 'awaiting_approval')
                ORDER BY approvals.requested_at
                """,
                (now,),
            ).fetchall()
            for approval in rows:
                latest = conn.execute(
                    """
                    SELECT id FROM mission_step_approvals
                    WHERE step_id=? ORDER BY request_version DESC LIMIT 1
                    """,
                    (approval["step_id"],),
                ).fetchone()
                if not latest or latest["id"] != approval["id"]:
                    continue
                conn.execute(
                    "UPDATE mission_step_approvals SET status='expired' WHERE id=?",
                    (approval["id"],),
                )
                step_row = conn.execute(
                    "SELECT * FROM mission_steps WHERE id=?", (approval["step_id"],)
                ).fetchone()
                mission = self._require_mission(conn, approval["mission_id"])
                step = self._serialize_step(step_row)
                self._attach_plan_step_contract(conn, step)
                self._request_step_approval(
                    conn,
                    mission,
                    step,
                    reason="approval_expired",
                )
                rotated += 1
        return rotated

    def claim_workflow_run(
        self,
        owner: str,
        *,
        lease_seconds: int = 180,
    ) -> dict[str, Any] | None:
        """Lease one pending runtime action for crash-safe worker processing."""

        now = _now()
        with self.connect(immediate=True) as conn:
            row = conn.execute(
                self.repository.claim_query(
                    """
                SELECT * FROM workflow_runs
                WHERE runtime='langgraph'
                  AND status IN (
                      'start_pending', 'resume_pending',
                      'running_start', 'running_resume'
                  )
                  AND next_attempt_at <= ?
                AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                ORDER BY created_at LIMIT 1
                    """
                ),
                (_iso(now), _iso(now)),
            ).fetchone()
            if not row:
                return None
            action = "resume" if row["status"] in {
                "resume_pending",
                "running_resume",
            } else "start"
            lease_token = f"workflow-lease-{uuid.uuid4().hex}"
            running_status = f"running_{action}"
            cursor = conn.execute(
                """
                UPDATE workflow_runs
                SET status=?, attempts=attempts+1, lease_owner=?, lease_token=?,
                    lease_expires_at=?, updated_at=?
                WHERE id=? AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                """,
                (
                    running_status,
                    owner,
                    lease_token,
                    _iso(now + timedelta(seconds=max(lease_seconds, 30))),
                    _iso(now),
                    row["id"],
                    _iso(now),
                ),
            )
            if cursor.rowcount != 1:
                return None
            leased = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (row["id"],)
            ).fetchone()
            item = self._serialize_workflow_run(leased, include_private=True)
            item["action"] = action
            return item

    def complete_workflow_run(
        self,
        run_id: str,
        *,
        lease_token: str,
        status: str,
        state: Optional[dict[str, Any]] = None,
        checkpoint: Optional[dict[str, Any]] = None,
        actor: str = "command-center-runtime",
    ) -> dict[str, Any]:
        if status not in {"awaiting_approval", "ready", "cancelled"}:
            raise CommandCenterError(f"invalid workflow runtime status: {status}")
        with self.connect(immediate=True) as conn:
            run = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
            if not run:
                raise CommandCenterError(f"workflow run not found: {run_id}")
            if str(run["lease_token"] or "") != str(lease_token or ""):
                raise CommandCenterError(f"workflow run lease lost: {run_id}")
            resume_payload = _loads(run["resume_payload_json"], {})
            next_status = status
            if status == "awaiting_approval" and resume_payload:
                next_status = "resume_pending"
            completed_at = _iso() if next_status in {"ready", "cancelled"} else None
            conn.execute(
                """
                UPDATE workflow_runs
                SET status=?, state_json=?, checkpoint_json=?, last_error=NULL,
                    lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL,
                    next_attempt_at=?, updated_at=?, completed_at=?
                WHERE id=? AND lease_token=?
                """,
                (
                    next_status,
                    _json(state or {}),
                    _json(checkpoint or {}),
                    _iso(),
                    _iso(),
                    completed_at,
                    run_id,
                    lease_token,
                ),
            )
            mission = self._require_mission(conn, run["mission_id"])
            self._add_event(
                conn,
                run["mission_id"],
                "workflow_runtime_checkpointed",
                mission["status"],
                mission["status"],
                actor,
                f"Workflow {run_id} reached {next_status}",
                {
                    "workflow_run_id": run_id,
                    "runtime": run["runtime"],
                    "runtime_status": next_status,
                    "checkpoint": checkpoint or {},
                },
            )
            self._sync_mission_ledger_safe(conn, run["mission_id"])
            updated = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
            return self._serialize_workflow_run(updated)

    def fail_workflow_run(
        self,
        run_id: str,
        *,
        lease_token: str,
        error: str,
        actor: str = "command-center-runtime",
    ) -> dict[str, Any]:
        max_attempts = max(
            1, int(os.getenv("COMMAND_CENTER_WORKFLOW_MAX_ATTEMPTS", "3"))
        )
        with self.connect(immediate=True) as conn:
            run = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
            if not run:
                raise CommandCenterError(f"workflow run not found: {run_id}")
            if str(run["lease_token"] or "") != str(lease_token or ""):
                raise CommandCenterError(f"workflow run lease lost: {run_id}")
            action = "resume" if run["status"] == "running_resume" else "start"
            terminal = int(run["attempts"] or 0) >= max_attempts
            next_status = "failed" if terminal else f"{action}_pending"
            delay = min(60, 2 ** max(1, int(run["attempts"] or 1)))
            conn.execute(
                """
                UPDATE workflow_runs
                SET status=?, next_attempt_at=?, lease_owner=NULL, lease_token=NULL,
                    lease_expires_at=NULL, last_error=?, updated_at=?, completed_at=?
                WHERE id=? AND lease_token=?
                """,
                (
                    next_status,
                    _iso(_now() + timedelta(seconds=delay)),
                    str(error or "")[:4000],
                    _iso(),
                    _iso() if terminal else None,
                    run_id,
                    lease_token,
                ),
            )
            mission = self._require_mission(conn, run["mission_id"])
            self._add_event(
                conn,
                run["mission_id"],
                "workflow_runtime_failed" if terminal else "workflow_runtime_retrying",
                mission["status"],
                mission["status"],
                actor,
                str(error or "")[:1000],
                {
                    "workflow_run_id": run_id,
                    "attempt": int(run["attempts"] or 0),
                    "max_attempts": max_attempts,
                    "next_status": next_status,
                },
            )
            if terminal and mission["status"] not in TERMINAL_MISSION_STATES:
                target = (
                    "planning"
                    if mission["status"] == "awaiting_approval"
                    else "waiting_feedback"
                )
                if target in MISSION_TRANSITIONS.get(mission["status"], set()):
                    conn.execute(
                        """
                        UPDATE orchestration_missions
                        SET status=?, last_error=?, updated_at=? WHERE id=?
                        """,
                        (target, str(error or "")[:4000], _iso(), mission["id"]),
                    )
                    if target == "planning":
                        conn.execute(
                            """
                            UPDATE mission_approvals
                            SET decision='runtime_failed', decided_at=?, decided_by=?,
                                comment=?
                            WHERE mission_id=? AND plan_version=? AND decision='pending'
                            """,
                            (
                                _iso(),
                                actor,
                                str(error or "")[:1000],
                                mission["id"],
                                run["plan_version"],
                            ),
                        )
                        conn.execute(
                            """
                            UPDATE mission_plan_versions SET status='runtime_failed'
                            WHERE mission_id=? AND version=?
                            """,
                            (mission["id"], run["plan_version"]),
                        )
                    failed_mission = self._require_mission(conn, mission["id"])
                    self._queue_notification(
                        conn,
                        mission=failed_mission,
                        text=(
                            f"任务 {mission['id']} 的工作流运行时在 "
                            f"{max_attempts} 次尝试后仍失败："
                            f"{str(error or '')[:500]}"
                        ),
                        event_key=f"workflow-failed:{run_id}",
                    )
            self._sync_mission_ledger_safe(conn, run["mission_id"])
            updated = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
            return self._serialize_workflow_run(updated)

    def get_workflow_run(
        self,
        mission_id: str,
        *,
        plan_version: int | None = None,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            version = plan_version
            if version is None:
                mission = self._require_mission(conn, mission_id)
                version = int(mission["plan_version"] or 0)
            row = conn.execute(
                """
                SELECT * FROM workflow_runs
                WHERE mission_id=? AND plan_version=?
                """,
                (mission_id, int(version)),
            ).fetchone()
            return self._serialize_workflow_run(row) if row else None

    def workflow_runtime_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            counts = {
                row["status"]: int(row["count"])
                for row in conn.execute(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM workflow_runs GROUP BY status
                    """
                ).fetchall()
            }
            runtimes = {
                row["runtime"]: int(row["count"])
                for row in conn.execute(
                    """
                    SELECT runtime, COUNT(*) AS count
                    FROM workflow_runs GROUP BY runtime
                    """
                ).fetchall()
            }
            checkpoint_storage: dict[str, Any] = {
                "status": "local" if self.repository.backend == "sqlite" else "unprobed",
                "backend": "sqlite" if self.repository.backend == "sqlite" else "postgresql",
            }
            if self.repository.backend == "postgresql":
                missing = sorted(
                    table
                    for table in POSTGRES_CHECKPOINT_TABLES
                    if not self.repository.table_exists(conn, table)
                )
                installed_version = -1
                if "checkpoint_migrations" not in missing:
                    row = conn.execute(
                        "SELECT MAX(v) AS version FROM checkpoint_migrations"
                    ).fetchone()
                    installed_version = int(row["version"]) if row and row["version"] is not None else -1
                required_version = postgres_checkpoint_required_version()
                checkpoint_storage = {
                    "status": (
                        "ready"
                        if not missing and installed_version >= required_version >= 0
                        else "degraded"
                    ),
                    "backend": "postgresql",
                    "installed_version": installed_version,
                    "required_version": required_version,
                    "missing_tables": missing,
                    "runtime_ddl": False,
                }
        checkpoint_database_url = (
            str(getattr(self.repository, "database_url", ""))
            if self.repository.backend == "postgresql"
            else ""
        )
        return {
            **workflow_runtime_catalog(checkpoint_database_url),
            "by_status": counts,
            "by_runtime": runtimes,
            "checkpoint_storage": checkpoint_storage,
        }

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
                self.repository.claim_query(
                    """
                SELECT s.* FROM mission_steps s
                JOIN orchestration_missions m ON m.id=s.mission_id
                WHERE s.status='ready' AND m.status='running'
                  AND s.plan_version=m.plan_version
                ORDER BY m.created_at, s.order_index
                LIMIT ?
                    """,
                    table_alias="s",
                ),
                (max(1, limit),),
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
                mission = self._require_mission(conn, step["mission_id"])
                step_contract = self._serialize_step(step)
                self._attach_plan_step_contract(conn, step_contract)
                authorized, step_approval_id = self._authorize_step_execution(
                    conn,
                    mission,
                    step_contract,
                )
                if not authorized:
                    continue
                lease_token = f"lease-{uuid.uuid4().hex}"
                cursor = conn.execute(
                    """
                    UPDATE mission_steps
                    SET status='running', attempt_count=attempt_count+1,
                        lease_owner=?, lease_token=?, lease_expires_at=?,
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
                    if step_approval_id:
                        conn.execute(
                            """
                            UPDATE mission_step_approvals
                            SET status='consumed', consumed_at=?
                            WHERE id=? AND status='approved' AND consumed_at IS NULL
                            """,
                            (_iso(now), step_approval_id),
                        )
                    updated = conn.execute(
                        "SELECT * FROM mission_steps WHERE id=?",
                        (step["id"],),
                    ).fetchone()
                    serialized_step = self._serialize_step(updated)
                    self._attach_plan_step_contract(conn, serialized_step)
                    if step_approval_id:
                        approval_row = conn.execute(
                            "SELECT * FROM mission_step_approvals WHERE id=?",
                            (step_approval_id,),
                        ).fetchone()
                        serialized_step["step_approval"] = self._serialize_step_approval(
                            approval_row
                        )
                    claimed.append(serialized_step)
                    self._add_event(
                        conn,
                        step["mission_id"],
                        "step_started",
                        "running",
                        "running",
                        step["agent_id"],
                        step["title"],
                        {
                            "step_id": step["id"],
                            "step_approval_id": step_approval_id or None,
                        },
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

    def _execution_enforcement(
        self,
        conn: sqlite3.Connection,
        step: dict[str, Any],
    ) -> dict[str, Any]:
        mode = os.getenv("COMMAND_CENTER_EVIDENCE_ENFORCEMENT", "pilot").strip().lower()
        if mode not in {"shadow", "pilot", "strict"}:
            mode = "shadow"
        workflow = conn.execute(
            """
            SELECT runtime, flow_key, highest_risk FROM workflow_runs
            WHERE mission_id=? AND plan_version=?
            """,
            (step["mission_id"], step["plan_version"]),
        ).fetchone()
        flow_key = str(workflow["flow_key"] if workflow else "general")
        highest_risk = str(workflow["highest_risk"] if workflow else "L1")
        pilot_eligible = bool(
            workflow
            and workflow["runtime"] == "langgraph"
            and flow_key in {"document", "research"}
            and highest_risk in {"L0", "L1"}
        )
        enforced = mode == "strict" or (mode == "pilot" and pilot_eligible)
        return {
            "mode": mode,
            "enforced": enforced,
            "reason": (
                "strict_mode"
                if mode == "strict"
                else "eligible_langgraph_pilot"
                if pilot_eligible
                else "shadow_observation"
            ),
            "flow_key": flow_key,
            "highest_risk": highest_risk,
            "runtime": str(workflow["runtime"] if workflow else "legacy"),
        }

    @staticmethod
    def _record_fingerprint(*values: Any) -> str:
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _persist_execution_records(
        self,
        conn: sqlite3.Connection,
        *,
        step: sqlite3.Row,
        result: dict[str, Any],
        actor: str,
    ) -> None:
        mission_run = self._ensure_mission_run(conn, str(step["mission_id"]))
        artifact_ids: dict[str, str] = {}
        for artifact in result.get("artifacts") or []:
            if not isinstance(artifact, dict):
                continue
            fingerprint = self._record_fingerprint(
                step["mission_id"],
                step["plan_version"],
                step["id"],
                artifact.get("artifact_type"),
                artifact.get("uri"),
                artifact.get("content_hash"),
            )
            artifact_id = f"artifact-{fingerprint[:20]}"
            conn.execute(
                """
                INSERT OR IGNORE INTO mission_artifacts
                (id, mission_id, mission_run_id, correlation_id,
                 plan_version, step_id, work_run_id,
                 artifact_type, title, uri, content_hash, fingerprint,
                 metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    step["mission_id"],
                    mission_run["id"],
                    mission_run["correlation_id"],
                    step["plan_version"],
                    step["id"],
                    step["work_run_id"],
                    str(artifact.get("artifact_type") or "")[:120],
                    str(artifact.get("title") or "")[:500],
                    str(artifact.get("uri") or "")[:2000],
                    str(artifact.get("content_hash") or "")[:128],
                    fingerprint,
                    _json(artifact.get("metadata") or {}),
                    _iso(),
                ),
            )
            row = conn.execute(
                "SELECT id FROM mission_artifacts WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if row:
                artifact_ids[str(artifact.get("artifact_key") or "")] = row["id"]

        for evidence in result.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            fingerprint = self._record_fingerprint(
                step["mission_id"],
                step["plan_version"],
                step["id"],
                evidence.get("evidence_type"),
                evidence.get("source_ref"),
                evidence.get("summary"),
            )
            artifact_id = artifact_ids.get(
                str(evidence.get("artifact_key") or "")
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO mission_evidence
                (id, mission_id, mission_run_id, correlation_id,
                 plan_version, step_id, artifact_id,
                 evidence_type, source_ref, summary, collected_by,
                 collected_at, confidence, fingerprint, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evidence-{fingerprint[:20]}",
                    step["mission_id"],
                    mission_run["id"],
                    mission_run["correlation_id"],
                    step["plan_version"],
                    step["id"],
                    artifact_id,
                    str(evidence.get("evidence_type") or "")[:120],
                    str(evidence.get("source_ref") or "")[:2000],
                    str(evidence.get("summary") or "")[:4000],
                    actor,
                    _iso(),
                    float(evidence.get("confidence", 1.0)),
                    fingerprint,
                    _json(evidence.get("metadata") or {}),
                ),
            )

        quality = result.get("execution_quality") or {}
        self._upsert_acceptance_gate(
            conn,
            mission_id=step["mission_id"],
            plan_version=int(step["plan_version"]),
            step_id=step["id"],
            gate_type="execution_evidence",
            quality=quality,
            actor=actor,
        )

    def _upsert_acceptance_gate(
        self,
        conn: sqlite3.Connection,
        *,
        mission_id: str,
        plan_version: int,
        step_id: str,
        gate_type: str,
        quality: dict[str, Any],
        actor: str,
    ) -> None:
        mission_run = self._ensure_mission_run(conn, mission_id)
        gate_id = "gate-" + self._record_fingerprint(
            mission_id, plan_version, step_id, gate_type
        )[:20]
        conn.execute(
            """
            INSERT INTO mission_acceptance_gates
            (id, mission_id, mission_run_id, correlation_id,
             plan_version, step_id, gate_type, mode, enforced,
             status, accepted, score, blockers_json, warnings_json, details_json,
             evaluated_by, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mission_id, plan_version, step_id, gate_type)
            DO UPDATE SET
                mode=excluded.mode,
                enforced=excluded.enforced,
                status=excluded.status,
                accepted=excluded.accepted,
                score=excluded.score,
                blockers_json=excluded.blockers_json,
                warnings_json=excluded.warnings_json,
                details_json=excluded.details_json,
                evaluated_by=excluded.evaluated_by,
                evaluated_at=excluded.evaluated_at
            """,
            (
                gate_id,
                mission_id,
                mission_run["id"],
                mission_run["correlation_id"],
                int(plan_version),
                step_id or "",
                gate_type,
                str(quality.get("mode") or "shadow"),
                int(bool(quality.get("enforced"))),
                str(quality.get("status") or "blocked"),
                int(bool(quality.get("accepted"))),
                int(quality.get("score") or 0),
                _json(quality.get("blockers") or []),
                _json(quality.get("warnings") or []),
                _json(quality),
                actor,
                _iso(),
            ),
        )

    def _persist_effect_records(
        self,
        conn: sqlite3.Connection,
        *,
        step: sqlite3.Row,
        step_contract: dict[str, Any],
        result: dict[str, Any],
        next_status: str,
        actor: str,
    ) -> list[str]:
        effect_ids: list[str] = []
        mission = self._require_mission(conn, step["mission_id"])
        mission_run = self._ensure_mission_run(conn, step["mission_id"])
        for effect in result.get("side_effects") or []:
            fingerprint = self._record_fingerprint(
                step["mission_id"],
                step["plan_version"],
                step["id"],
                effect.get("effect_key"),
            )
            effect_id = f"effect-{fingerprint[:20]}"
            conn.execute(
                """
                INSERT INTO mission_effects
                (id, mission_id, mission_run_id, correlation_id, plan_version,
                 step_id, work_run_id, effect_key,
                 resource, action, status, idempotency_key, receipt_ref,
                 evidence_refs_json, metadata_json, fingerprint, reported_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    status=excluded.status,
                    receipt_ref=excluded.receipt_ref,
                    evidence_refs_json=excluded.evidence_refs_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    effect_id,
                    step["mission_id"],
                    mission_run["id"],
                    mission_run["correlation_id"],
                    int(step["plan_version"]),
                    step["id"],
                    step["work_run_id"],
                    str(effect.get("effect_key") or "")[:160],
                    str(effect.get("resource") or "")[:500],
                    str(effect.get("action") or "")[:1000],
                    str(effect.get("status") or "unknown"),
                    str(effect.get("idempotency_key") or "")[:240],
                    str(effect.get("receipt_ref") or "")[:2000] or None,
                    _json(effect.get("evidence_refs") or []),
                    _json(effect.get("metadata") or {}),
                    fingerprint,
                    _iso(),
                    _iso(),
                ),
            )
            effect_ids.append(effect_id)
            if (
                next_status != "completed"
                and str(effect.get("status")) in {"applied", "unknown"}
            ):
                self._create_compensation_case(
                    conn,
                    mission=mission,
                    step=step,
                    step_contract=step_contract,
                    effect_id=effect_id,
                    effect=effect,
                    actor=actor,
                )
        return effect_ids

    def _create_compensation_case(
        self,
        conn: sqlite3.Connection,
        *,
        mission: sqlite3.Row,
        step: sqlite3.Row,
        step_contract: dict[str, Any],
        effect_id: str,
        effect: dict[str, Any],
        actor: str,
    ) -> sqlite3.Row:
        existing = conn.execute(
            "SELECT * FROM mission_compensations WHERE effect_id=?",
            (effect_id,),
        ).fetchone()
        if existing:
            return existing
        contract = compensation_service.compensation_contract(step_contract, effect)
        mission_run = self._ensure_mission_run(conn, mission["id"])
        compensation_id = f"compensation-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO mission_compensations
            (id, mission_id, mission_run_id, correlation_id, plan_version,
             step_id, effect_id, compensation_type,
             instructions, resource, contract_hash, idempotency_key, status,
             attempts, max_attempts, requested_at, result_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', 0, 1, ?, '{}', ?)
            """,
            (
                compensation_id,
                mission["id"],
                mission_run["id"],
                mission_run["correlation_id"],
                int(step["plan_version"]),
                step["id"],
                effect_id,
                contract["type"],
                contract["instructions"],
                contract["resource"],
                contract["contract_hash"],
                contract["idempotency_key"],
                _iso(),
                _iso(),
            ),
        )
        self._add_event(
            conn,
            mission["id"],
            "compensation_requested",
            mission["status"],
            mission["status"],
            actor,
            f"副作用状态为 {effect.get('status')}，等待补偿审批",
            {
                "compensation_id": compensation_id,
                "effect_id": effect_id,
                "step_id": step["id"],
                "resource": contract["resource"],
                "contract_hash": contract["contract_hash"],
            },
        )
        self._queue_notification(
            conn,
            mission=mission,
            text=(
                f"任务 {mission['id']} 检测到需要处理的副作用：\n"
                f"资源：{contract['resource']}\n"
                f"状态：{effect.get('status')}\n"
                f"补偿方案：{contract['instructions']}\n"
                f"补偿编号：{compensation_id}\n"
                "补偿不会自动执行，请在指挥中心审核。"
            ),
            event_key=f"compensation-request:{compensation_id}",
        )
        return conn.execute(
            "SELECT * FROM mission_compensations WHERE id=?",
            (compensation_id,),
        ).fetchone()

    def complete_step(
        self,
        step_id: str,
        *,
        result: dict[str, Any],
        success: bool,
        actor: str,
        lease_token: str,
    ) -> dict[str, Any]:
        with self.connect(immediate=True) as conn:
            step = conn.execute("SELECT * FROM mission_steps WHERE id=?", (step_id,)).fetchone()
            if not step:
                raise CommandCenterError(f"step not found: {step_id}")
            step_contract = self._serialize_step(step)
            self._attach_plan_step_contract(conn, step_contract)
            enforcement = self._execution_enforcement(conn, step_contract)
            result = execution_evidence_service.enrich_result(
                step_contract,
                result,
                success=success,
                enforcement=enforcement,
            )
            result = compensation_service.enrich_execution_result(
                step_contract,
                result,
            )
            quality = result.get("execution_quality") or {}
            effect_quality = result.get("effect_quality") or {}
            semantic_accepted = bool(
                quality.get("business_outcome") == "succeeded"
                and not quality.get("hard_blockers")
            )
            effective_success = bool(
                success
                and semantic_accepted
                and (
                    not quality.get("enforced")
                    or quality.get("accepted")
                )
                and effect_quality.get("accepted", True)
            )
            max_attempts = max(1, int(step_contract.get("max_attempts") or 1))
            unsafe_effect = any(
                item.get("status") in {"applied", "unknown"}
                for item in (result.get("side_effects") or [])
            )
            retry_evidence = bool(
                success
                and semantic_accepted
                and quality.get("enforced")
                and not quality.get("accepted")
                and effect_quality.get("accepted", True)
                and not unsafe_effect
                and int(step["attempt_count"] or 0) < max_attempts
            )
            next_status = (
                "completed"
                if effective_success
                else "ready"
                if retry_evidence
                else "failed"
            )
            result["completion_decision"] = {
                "executor_success": bool(success),
                "accepted": effective_success,
                "retry_scheduled": retry_evidence,
                "attempt": int(step["attempt_count"] or 0),
                "max_attempts": max_attempts,
                "enforcement": enforcement,
                "effect_quality": effect_quality,
            }
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
                    _iso() if next_status in {"completed", "failed"} else None,
                    _iso(),
                    step_id,
                    str(lease_token or ""),
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidMissionTransition(
                    f"stale or cancelled step completion rejected: {step_id}"
                )
            self._persist_execution_records(
                conn,
                step=step,
                result=result,
                actor=actor,
            )
            effect_ids = self._persist_effect_records(
                conn,
                step=step,
                step_contract=step_contract,
                result=result,
                next_status=next_status,
                actor=actor,
            )
            result["effect_ids"] = effect_ids
            conn.execute(
                "UPDATE mission_steps SET result_json=? WHERE id=?",
                (_json(result), step_id),
            )
            event_type = (
                "step_completed"
                if next_status == "completed"
                else "step_evidence_retry_scheduled"
                if retry_evidence
                else "step_effect_rejected"
                if success and not effect_quality.get("accepted", True)
                else "step_evidence_rejected"
                if success
                else "step_failed"
            )
            self._add_event(
                conn,
                step["mission_id"],
                event_type,
                "running",
                "running",
                actor,
                step["title"],
                {
                    "step_id": step_id,
                    "result": result,
                    "next_step_status": next_status,
                },
            )
            self._sync_mission_ledger_safe(conn, step["mission_id"])
            updated_step = self._serialize_step(
                conn.execute("SELECT * FROM mission_steps WHERE id=?", (step_id,)).fetchone()
            )
            self._attach_plan_step_contract(conn, updated_step)
            self._attach_step_delivery_records(conn, updated_step)
            return updated_step

    def _evaluate_delivery_gate(
        self,
        conn: sqlite3.Connection,
        mission: sqlite3.Row,
        *,
        actor: str,
    ) -> dict[str, Any]:
        steps = conn.execute(
            """
            SELECT * FROM mission_steps
            WHERE mission_id=? AND plan_version=? ORDER BY order_index
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchall()
        sample_step = self._serialize_step(steps[0]) if steps else {
            "mission_id": mission["id"],
            "plan_version": mission["plan_version"],
        }
        enforcement = self._execution_enforcement(conn, sample_step)
        gate_rows = conn.execute(
            """
            SELECT * FROM mission_acceptance_gates
            WHERE mission_id=? AND plan_version=?
              AND gate_type='execution_evidence' AND step_id!=''
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchall()
        by_step = {row["step_id"]: row for row in gate_rows}
        blockers: list[str] = []
        warnings: list[str] = []
        for step in steps:
            gate = by_step.get(step["id"])
            if not gate:
                blockers.append(f"步骤 {step['title']} 缺少执行验收记录")
            elif not bool(gate["accepted"]):
                blockers.append(f"步骤 {step['title']} 未通过执行验收")

        artifact_count = conn.execute(
            """
            SELECT COUNT(*) AS count FROM mission_artifacts
            WHERE mission_id=? AND plan_version=?
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchone()["count"]
        evidence_count = conn.execute(
            """
            SELECT COUNT(*) AS count FROM mission_evidence
            WHERE mission_id=? AND plan_version=?
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchone()["count"]
        if steps and not artifact_count:
            blockers.append("任务没有持久化交付物")
        if steps and not evidence_count:
            blockers.append("任务没有持久化执行证据")

        if not enforcement["enforced"]:
            warnings = blockers
            blockers = []
        unresolved_compensations = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM mission_compensations
            WHERE mission_id=? AND plan_version=? AND status!='completed'
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchone()["count"]
        if unresolved_compensations:
            blockers.append(
                f"任务存在 {unresolved_compensations} 个未完成的副作用补偿"
            )
        gate_enforced = bool(enforcement["enforced"] or unresolved_compensations)
        quality = {
            "status": "blocked" if blockers else "warning" if warnings else "pass",
            "score": max(0, 100 - len(blockers) * 30 - len(warnings) * 8),
            "mode": enforcement["mode"],
            "enforced": gate_enforced,
            "accepted": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "artifact_count": int(artifact_count),
            "evidence_count": int(evidence_count),
            "step_gate_count": len(gate_rows),
            "step_count": len(steps),
            "unresolved_compensations": int(unresolved_compensations),
            "checked_rules": [
                "all-step-gates",
                "mission-artifacts",
                "mission-evidence",
                "side-effect-compensation",
            ],
        }
        self._upsert_acceptance_gate(
            conn,
            mission_id=mission["id"],
            plan_version=int(mission["plan_version"]),
            step_id="",
            gate_type="delivery_evidence",
            quality=quality,
            actor=actor,
        )
        return quality

    def get_delivery_evidence(
        self,
        mission_id: str,
        *,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            mission = self._require_mission(conn, mission_id)
            if owner_user_id and str(mission["owner_user_id"] or "") != str(owner_user_id):
                raise MissionNotFound(mission_id)
            mission_run = self._ensure_mission_run(conn, mission_id)
            artifacts = [
                self._serialize_artifact(row)
                for row in conn.execute(
                    """
                    SELECT * FROM mission_artifacts
                    WHERE mission_id=? AND plan_version=? ORDER BY created_at, id
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchall()
            ]
            evidence = [
                self._serialize_evidence(row)
                for row in conn.execute(
                    """
                    SELECT * FROM mission_evidence
                    WHERE mission_id=? AND plan_version=? ORDER BY collected_at, id
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchall()
            ]
            gates = [
                self._serialize_acceptance_gate(row)
                for row in conn.execute(
                    """
                    SELECT * FROM mission_acceptance_gates
                    WHERE mission_id=? AND plan_version=? ORDER BY step_id, gate_type
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchall()
            ]
            effects = [
                self._serialize_effect(row)
                for row in conn.execute(
                    """
                    SELECT * FROM mission_effects
                    WHERE mission_id=? AND plan_version=? ORDER BY reported_at, id
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchall()
            ]
            compensations = [
                self._serialize_compensation(row)
                for row in conn.execute(
                    """
                    SELECT * FROM mission_compensations
                    WHERE mission_id=? AND plan_version=? ORDER BY requested_at, id
                    """,
                    (mission_id, mission["plan_version"]),
                ).fetchall()
            ]
            return {
                "mission_id": mission_id,
                "mission_run_id": mission_run["id"],
                "correlation_id": mission_run["correlation_id"],
                "plan_version": int(mission["plan_version"]),
                "artifacts": artifacts,
                "evidence": evidence,
                "acceptance_gates": gates,
                "effects": effects,
                "compensations": compensations,
                "summary": {
                    "artifact_count": len(artifacts),
                    "evidence_count": len(evidence),
                    "gate_count": len(gates),
                    "blocked_gates": sum(
                        1 for gate in gates if gate["enforced"] and not gate["accepted"]
                    ),
                    "effect_count": len(effects),
                    "unresolved_compensations": sum(
                        1 for item in compensations if item["status"] != "completed"
                    ),
                },
            }

    def claim_evaluation_mission(self, owner: str, *, lease_seconds: int = 300) -> dict[str, Any] | None:
        with self.connect(immediate=True) as conn:
            missions = conn.execute(
                self.repository.claim_query(
                    """
                SELECT * FROM orchestration_missions
                WHERE status IN ('running', 'evaluating')
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ? OR lease_owner=?)
                ORDER BY updated_at
                    """
                ),
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
                    delivery_gate = self._evaluate_delivery_gate(
                        conn,
                        mission,
                        actor=owner,
                    )
                    if delivery_gate["enforced"] and not delivery_gate["accepted"]:
                        conn.execute(
                            """
                            UPDATE orchestration_missions
                            SET status='waiting_feedback', last_error=?,
                                lease_owner=NULL, lease_expires_at=NULL, updated_at=?
                            WHERE id=?
                            """,
                            (
                                "；".join(delivery_gate["blockers"])[:4000],
                                _iso(),
                                mission["id"],
                            ),
                        )
                        self._add_event(
                            conn,
                            mission["id"],
                            "delivery_evidence_rejected",
                            mission["status"],
                            "waiting_feedback",
                            owner,
                            "；".join(delivery_gate["blockers"])[:1000],
                            {"delivery_gate": delivery_gate},
                        )
                        continue
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
            # Mission completion is a terminal, idempotent operation.  A
            # recovered evaluator may replay the completion command after it
            # has lost the acknowledgement; returning the persisted result
            # avoids duplicate completion events and final-delivery outbox
            # records.
            if mission["status"] == "completed":
                return self._serialize_mission(conn, mission)
            delivery_gate = self._evaluate_delivery_gate(
                conn,
                mission,
                actor=actor,
            )
            if success and delivery_gate["enforced"] and not delivery_gate["accepted"]:
                success = False
                summary = (
                    "交付证据门禁未通过："
                    + "；".join(delivery_gate["blockers"])
                    + "\n"
                    + summary
                )[:4000]
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
                self.repository.claim_query(
                    """
                SELECT * FROM notification_outbox
                WHERE status IN ('pending', 'retry')
                  AND next_attempt_at <= ?
                AND (locked_at IS NULL OR locked_at <= ?)
                ORDER BY created_at LIMIT ?
                    """
                ),
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

    def get_mission_run_ledger(
        self,
        mission_id: str,
        *,
        owner_user_id: str = "",
    ) -> dict[str, Any]:
        delivery = self.get_delivery_evidence(
            mission_id,
            owner_user_id=owner_user_id,
        )
        with self.connect() as conn:
            mission = self._require_mission(conn, mission_id)
            if owner_user_id and str(mission["owner_user_id"] or "") != str(owner_user_id):
                raise MissionNotFound(mission_id)
            run = self._ensure_mission_run(conn, mission_id)
            events = [
                {
                    **dict(row),
                    "metadata": _loads(row["metadata"], {}),
                }
                for row in conn.execute(
                    """
                    SELECT * FROM mission_events
                    WHERE mission_run_id=?
                    ORDER BY run_sequence, created_at, id
                    """,
                    (run["id"],),
                ).fetchall()
            ]
            workflows = [
                self._serialize_workflow_run(row)
                for row in conn.execute(
                    """
                    SELECT * FROM workflow_runs
                    WHERE mission_run_id=? ORDER BY plan_version, created_at
                    """,
                    (run["id"],),
                ).fetchall()
            ]
            step_runs: list[dict[str, Any]] = []
            work_run_columns = (
                self.repository.table_columns(conn, "work_runs")
                if self.repository.table_exists(conn, "work_runs")
                else set()
            )
            if "mission_run_id" in work_run_columns:
                for row in conn.execute(
                    """
                    SELECT * FROM work_runs
                    WHERE mission_run_id=? ORDER BY created_at, attempt, id
                    """,
                    (run["id"],),
                ).fetchall():
                    item = dict(row)
                    item["input_context"] = _loads(item.get("input_context"), {})
                    item["execution_result"] = _loads(item.get("execution_result"), {})
                    item["metrics"] = _loads(item.get("metrics"), {})
                    step_runs.append(item)
            return {
                "run": self._serialize_mission_run(run),
                "mission": {
                    "id": mission["id"],
                    "title": mission["title"],
                    "status": mission["status"],
                    "project_id": mission["project_id"],
                    "plan_version": int(mission["plan_version"] or 0),
                },
                "events": events,
                "workflow_runs": workflows,
                "step_runs": step_runs,
                "delivery": delivery,
                "summary": {
                    "event_count": len(events),
                    "workflow_run_count": len(workflows),
                    "step_run_count": len(step_runs),
                },
            }

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
            clean_sender = str(sender_id or "optimus").strip()
            expected_sender = str(inbound["target_agent_id"] or "optimus").strip()
            if clean_sender != expected_sender:
                raise CommandCenterError(
                    f"response agent mismatch: expected {expected_sender}, got {clean_sender}"
                )
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
                 execution_requested, routing_status, target_agent_id, resolved_project_id,
                 reply_to_command_message_id, metadata, created_at)
                VALUES (?, ?, ?, 'outbound', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    inbound["conversation_id"],
                    inbound["mission_id"],
                    external_message_id or None,
                    clean_sender,
                    clean_content,
                    inbound["intent_type"],
                    inbound["intent_confidence"],
                    inbound["intent_reason"],
                    inbound["execution_requested"],
                    routing_status,
                    clean_sender,
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
            pending_step_approvals = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM mission_step_approvals approvals
                JOIN orchestration_missions missions ON missions.id=approvals.mission_id
                WHERE approvals.status='pending'
                  AND approvals.plan_version=missions.plan_version
                  AND missions.status='running'
                  {"AND missions.owner_user_id=?" if owner_user_id else ""}
                """,
                owner_params,
            ).fetchone()["count"]
            pending_compensations = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM mission_compensations compensations
                JOIN orchestration_missions missions ON missions.id=compensations.mission_id
                WHERE compensations.status IN ('pending_approval', 'ready', 'running', 'failed')
                  AND compensations.plan_version=missions.plan_version
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
                "pending_step_approvals": pending_step_approvals,
                "pending_compensations": pending_compensations,
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
        if decision == "approved":
            approval_payload = {
                "decision": "approved",
                "decided_by": decided_by,
                "comment": comment,
                "decided_at": _iso(),
            }
            conn.execute(
                """
                UPDATE workflow_runs
                SET resume_payload_json=?,
                    status=CASE
                        WHEN runtime='langgraph' AND status='awaiting_approval'
                            THEN 'resume_pending'
                        ELSE status
                    END,
                    next_attempt_at=?, updated_at=?
                WHERE mission_id=? AND plan_version=?
                """,
                (
                    _json(approval_payload),
                    _iso(),
                    _iso(),
                    mission["id"],
                    mission["plan_version"],
                ),
            )
        else:
            conn.execute(
                """
                UPDATE workflow_runs
                SET status='cancelled', lease_owner=NULL, lease_token=NULL,
                    lease_expires_at=NULL, updated_at=?, completed_at=?
                WHERE mission_id=? AND plan_version=?
                """,
                (_iso(), _iso(), mission["id"], mission["plan_version"]),
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
        workflow = conn.execute(
            """
            SELECT runtime FROM workflow_runs
            WHERE mission_id=? AND plan_version=?
            """,
            (mission["id"], mission["plan_version"]),
        ).fetchone()
        approved_text = (
            f"任务 {mission['id']} 的计划已批准，"
            + (
                "正在从持久化审批点恢复并准备调度。"
                if workflow and workflow["runtime"] == "langgraph"
                else "开始调度智能体执行。"
            )
        )
        self._queue_notification(
            conn,
            mission=updated,
            text=(
                approved_text
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
        conn.execute(
            """
            UPDATE mission_step_approvals
            SET status='cancelled', decided_at=COALESCE(decided_at, ?),
                decided_by=COALESCE(decided_by, ?),
                comment=COALESCE(comment, ?)
            WHERE mission_id=? AND status IN ('pending', 'approved')
            """,
            (_iso(), actor, comment or "Mission cancelled", mission["id"]),
        )
        conn.execute(
            """
            UPDATE mission_compensations
            SET status='cancelled', lease_owner=NULL, lease_token=NULL,
                lease_expires_at=NULL, completed_at=?, updated_at=?
            WHERE mission_id=?
              AND status NOT IN ('completed', 'failed', 'rejected', 'cancelled')
            """,
            (_iso(), _iso(), mission["id"]),
        )
        conn.execute(
            """
            UPDATE workflow_runs
            SET status='cancelled', lease_owner=NULL, lease_token=NULL,
                lease_expires_at=NULL, updated_at=?, completed_at=?
            WHERE mission_id=? AND status NOT IN ('ready', 'failed', 'cancelled')
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
            metadata = _loads(conv["metadata"] or "{}", {})
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
        run = self._ensure_mission_run(conn, mission_id)
        next_sequence = int(
            conn.execute(
                """
                SELECT COALESCE(MAX(run_sequence), 0) + 1 AS value
                FROM mission_events WHERE mission_run_id=?
                """,
                (run["id"],),
            ).fetchone()["value"]
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO mission_events
            (id, mission_id, event_type, from_status, to_status, actor,
             detail, event_key, metadata, mission_run_id, correlation_id,
             run_sequence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                run["id"],
                run["correlation_id"],
                next_sequence,
                _iso(),
            ),
        )
        self._ensure_mission_run(conn, mission_id)

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

    def _attach_plan_step_contract(self, conn: sqlite3.Connection, step: dict[str, Any]) -> None:
        plan = conn.execute(
            """
            SELECT raw_plan FROM mission_plan_versions
            WHERE mission_id=? AND version=?
            """,
            (step.get("mission_id"), step.get("plan_version")),
        ).fetchone()
        if not plan:
            return
        raw_plan = _loads(plan["raw_plan"], {})
        if isinstance(raw_plan, dict):
            self._merge_plan_step_contracts([step], raw_plan)

    def _attach_step_delivery_records(
        self,
        conn: sqlite3.Connection,
        step: dict[str, Any],
    ) -> None:
        step["artifacts"] = [
            self._serialize_artifact(row)
            for row in conn.execute(
                "SELECT * FROM mission_artifacts WHERE step_id=? ORDER BY created_at, id",
                (step["id"],),
            ).fetchall()
        ]
        step["evidence"] = [
            self._serialize_evidence(row)
            for row in conn.execute(
                "SELECT * FROM mission_evidence WHERE step_id=? ORDER BY collected_at, id",
                (step["id"],),
            ).fetchall()
        ]
        gate = conn.execute(
            """
            SELECT * FROM mission_acceptance_gates
            WHERE step_id=? AND gate_type='execution_evidence'
            """,
            (step["id"],),
        ).fetchone()
        step["acceptance_gate"] = (
            self._serialize_acceptance_gate(gate) if gate else None
        )
        approval = conn.execute(
            """
            SELECT * FROM mission_step_approvals
            WHERE step_id=? ORDER BY request_version DESC LIMIT 1
            """,
            (step["id"],),
        ).fetchone()
        step["step_approval"] = (
            self._serialize_step_approval(approval) if approval else None
        )
        step["effects"] = [
            self._serialize_effect(row)
            for row in conn.execute(
                "SELECT * FROM mission_effects WHERE step_id=? ORDER BY reported_at, id",
                (step["id"],),
            ).fetchall()
        ]
        step["compensations"] = [
            self._serialize_compensation(row)
            for row in conn.execute(
                "SELECT * FROM mission_compensations WHERE step_id=? ORDER BY requested_at, id",
                (step["id"],),
            ).fetchall()
        ]

    @staticmethod
    def _merge_plan_step_contracts(steps: list[dict[str, Any]], raw_plan: dict[str, Any]) -> None:
        raw_steps = raw_plan.get("steps") if isinstance(raw_plan.get("steps"), list) else []
        by_order: dict[int, dict[str, Any]] = {}
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                continue
            try:
                order_index = int(raw_step.get("order_index") or index)
            except (TypeError, ValueError):
                order_index = index
            by_order[order_index] = raw_step
        contract_fields = (
            "phase",
            "objective",
            "required_tools",
            "tool_requirements",
            "deliverables",
            "output_contract",
            "acceptance_criteria",
            "evidence_required",
            "risk_level",
            "risk_class",
            "approval_required",
            "side_effect",
            "resources",
            "idempotency_key",
            "timeout_seconds",
            "max_attempts",
            "rollback_plan",
            "compensation",
            "capability_match",
        )
        for step in steps:
            raw_step = by_order.get(int(step.get("order_index") or 0))
            if not raw_step:
                continue
            for field in contract_fields:
                if field in raw_step:
                    step[field] = raw_step[field]

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

    @staticmethod
    def _serialize_workflow_run(
        row: sqlite3.Row,
        *,
        include_private: bool = False,
    ) -> dict[str, Any]:
        item = dict(row)
        item["input"] = _loads(item.pop("input_json", "{}"), {})
        item["state"] = _loads(item.pop("state_json", "{}"), {})
        item["checkpoint"] = _loads(item.pop("checkpoint_json", "{}"), {})
        resume_payload = _loads(item.pop("resume_payload_json", "{}"), {})
        if include_private:
            item["resume_payload"] = resume_payload
        return item

    @staticmethod
    def _serialize_artifact(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
        return item

    @staticmethod
    def _serialize_evidence(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
        return item

    @staticmethod
    def _serialize_step_approval(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["single_use"] = True
        item["consumed"] = bool(item.get("consumed_at"))
        return item

    @staticmethod
    def _serialize_effect(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["evidence_refs"] = _loads(item.pop("evidence_refs_json", "[]"), [])
        item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
        return item

    @staticmethod
    def _serialize_compensation(
        row: sqlite3.Row,
        *,
        include_private: bool = False,
    ) -> dict[str, Any]:
        item = dict(row)
        item["result"] = _loads(item.pop("result_json", "{}"), {})
        if not include_private:
            item.pop("lease_token", None)
        return item

    @staticmethod
    def _serialize_acceptance_gate(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["enforced"] = bool(item["enforced"])
        item["accepted"] = bool(item["accepted"])
        item["blockers"] = _loads(item.pop("blockers_json", "[]"), [])
        item["warnings"] = _loads(item.pop("warnings_json", "[]"), [])
        item["details"] = _loads(item.pop("details_json", "{}"), {})
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
        mission_run = self._ensure_mission_run(conn, item["id"])
        item["mission_run"] = self._serialize_mission_run(mission_run)
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
            if isinstance(item["plan"]["raw_plan"], dict):
                item["plan"]["plan_quality"] = item["plan"]["raw_plan"].get("plan_quality")
                self._merge_plan_step_contracts(item["steps"], item["plan"]["raw_plan"])
        workflow_run = conn.execute(
            """
            SELECT * FROM workflow_runs
            WHERE mission_id=? AND plan_version=?
            """,
            (item["id"], item["plan_version"]),
        ).fetchone()
        item["workflow_run"] = (
            self._serialize_workflow_run(workflow_run) if workflow_run else None
        )
        artifact_rows = conn.execute(
            """
            SELECT * FROM mission_artifacts
            WHERE mission_id=? AND plan_version=? ORDER BY created_at, id
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        evidence_rows = conn.execute(
            """
            SELECT * FROM mission_evidence
            WHERE mission_id=? AND plan_version=? ORDER BY collected_at, id
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        gate_rows = conn.execute(
            """
            SELECT * FROM mission_acceptance_gates
            WHERE mission_id=? AND plan_version=? ORDER BY step_id, gate_type
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        item["artifacts"] = [self._serialize_artifact(row) for row in artifact_rows]
        item["evidence"] = [self._serialize_evidence(row) for row in evidence_rows]
        item["acceptance_gates"] = [
            self._serialize_acceptance_gate(row) for row in gate_rows
        ]
        step_approval_rows = conn.execute(
            """
            SELECT * FROM mission_step_approvals
            WHERE mission_id=? AND plan_version=?
            ORDER BY step_id, request_version DESC
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        item["step_approvals"] = [
            self._serialize_step_approval(row) for row in step_approval_rows
        ]
        current_step_approvals: dict[str, dict[str, Any]] = {}
        for approval in item["step_approvals"]:
            current_step_approvals.setdefault(approval["step_id"], approval)
        effect_rows = conn.execute(
            """
            SELECT * FROM mission_effects
            WHERE mission_id=? AND plan_version=? ORDER BY reported_at, id
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        compensation_rows = conn.execute(
            """
            SELECT * FROM mission_compensations
            WHERE mission_id=? AND plan_version=? ORDER BY requested_at, id
            """,
            (item["id"], item["plan_version"]),
        ).fetchall()
        item["effects"] = [self._serialize_effect(row) for row in effect_rows]
        item["compensations"] = [
            self._serialize_compensation(row) for row in compensation_rows
        ]
        for step in item["steps"]:
            step["artifacts"] = [
                artifact for artifact in item["artifacts"] if artifact["step_id"] == step["id"]
            ]
            step["evidence"] = [
                evidence for evidence in item["evidence"] if evidence["step_id"] == step["id"]
            ]
            step["acceptance_gate"] = next(
                (
                    gate
                    for gate in item["acceptance_gates"]
                    if gate["step_id"] == step["id"]
                    and gate["gate_type"] == "execution_evidence"
                ),
                None,
            )
            step["step_approval"] = current_step_approvals.get(step["id"])
            step["effects"] = [
                effect for effect in item["effects"] if effect["step_id"] == step["id"]
            ]
            step["compensations"] = [
                compensation
                for compensation in item["compensations"]
                if compensation["step_id"] == step["id"]
            ]
        item["delivery_gate"] = next(
            (
                gate
                for gate in item["acceptance_gates"]
                if not gate["step_id"] and gate["gate_type"] == "delivery_evidence"
            ),
            None,
        )
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
