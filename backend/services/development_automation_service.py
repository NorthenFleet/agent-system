"""Approval-gated automation for software development tasks.

Plans and approval decisions live in the unified SQLite database. Codex remains
the execution engine, but it cannot start a development loop until an admin has
approved a concrete plan version.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from codex_job_service import codex_job_service
from unified_data_manager import UNIFIED_DB_PATH


TASK_TYPES = (
    ("architecture", "架构设计", "leonardo", "wheeljack", "michelangelo", 10),
    ("backend", "后端开发", "raphael", "leonardo", "michelangelo", 20),
    ("frontend", "前端开发", "donatello", "leonardo", "michelangelo", 30),
    ("database", "数据库", "raphael", "wheeljack", "michelangelo", 40),
    ("testing", "测试验证", "michelangelo", "leonardo", "optimus", 50),
    ("integration", "系统集成", "leonardo", "optimus", "michelangelo", 60),
    ("deployment", "部署发布", "bumblebee", "optimus", "michelangelo", 70),
    ("documentation", "开发文档", "wheeljack", "leonardo", "michelangelo", 80),
    ("security", "安全审查", "ironhide", "leonardo", "michelangelo", 90),
    ("performance", "性能优化", "leonardo", "wheeljack", "michelangelo", 100),
)

TERMINAL_LOOP_STATUSES = {"succeeded", "failed", "cancelled", "needs_attention"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class DevelopmentAutomationService:
    def __init__(
        self,
        db_path: str = UNIFIED_DB_PATH,
        loop_creator: Optional[Callable[..., dict]] = None,
        loop_getter: Optional[Callable[[str], Optional[dict]]] = None,
        loop_integration_retrier: Optional[Callable[[str], dict]] = None,
    ) -> None:
        self.db_path = db_path
        self.loop_creator = loop_creator or codex_job_service.create_loop
        self.loop_getter = loop_getter or codex_job_service.get_loop
        self.loop_integration_retrier = loop_integration_retrier or codex_job_service.retry_loop_integration
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS development_task_types (
                    key TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    developer_agent_id TEXT NOT NULL,
                    planner_agent_id TEXT NOT NULL,
                    evaluator_agent_id TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS development_plans (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    plan_markdown TEXT NOT NULL,
                    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
                    risk_level TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    planner_agent_id TEXT NOT NULL,
                    reviewer_agent_id TEXT NOT NULL,
                    developer_agent_id TEXT NOT NULL,
                    evaluator_agent_id TEXT NOT NULL,
                    max_rounds INTEGER NOT NULL DEFAULT 2,
                    repo TEXT,
                    review_score INTEGER NOT NULL DEFAULT 0,
                    review_summary TEXT,
                    review_details TEXT NOT NULL DEFAULT '{}',
                    loop_id TEXT,
                    execution_error TEXT,
                    created_by TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(target_kind, target_id, version)
                );

                CREATE INDEX IF NOT EXISTS idx_development_plans_project
                    ON development_plans(project_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_development_plans_target
                    ON development_plans(target_kind, target_id, version DESC);

                CREATE TABLE IF NOT EXISTS development_approval_events (
                    id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    comment TEXT,
                    plan_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES development_plans(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS development_loop_rounds (
                    id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    loop_id TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES development_plans(id) ON DELETE CASCADE,
                    UNIQUE(plan_id, loop_id, round_index, stage)
                );
                """
            )
            now = _now()
            conn.executemany(
                """
                INSERT INTO development_task_types
                    (key,label,developer_agent_id,planner_agent_id,evaluator_agent_id,sort_order,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                    label=excluded.label,
                    developer_agent_id=excluded.developer_agent_id,
                    planner_agent_id=excluded.planner_agent_id,
                    evaluator_agent_id=excluded.evaluator_agent_id,
                    sort_order=excluded.sort_order,
                    updated_at=excluded.updated_at
                """,
                [(*item, now, now) for item in TASK_TYPES],
            )
            self._ensure_columns(conn, "development_plans", {
                "source_repo": "TEXT", "workspace_path": "TEXT", "source_branch": "TEXT",
                "execution_branch": "TEXT", "integration_branch": "TEXT", "base_commit": "TEXT",
                "result_commit": "TEXT", "merge_commit": "TEXT", "workspace_status": "TEXT",
                "handoff_reason": "TEXT", "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
            })
            self._migrate_loop_round_uniqueness(conn)
            self._ensure_columns(conn, "development_loop_rounds", {
                "job_ids": "TEXT NOT NULL DEFAULT '[]'", "commit_sha": "TEXT",
                "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
            })

    @staticmethod
    def _migrate_loop_round_uniqueness(conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='development_loop_rounds'"
        ).fetchone()
        sql = " ".join(str(row["sql"] if isinstance(row, sqlite3.Row) else row[0]).split()) if row else ""
        if "UNIQUE(plan_id, round_index, stage)" not in sql:
            return
        legacy_columns = {
            item[1] for item in conn.execute("PRAGMA table_info(development_loop_rounds)").fetchall()
        }
        conn.execute("ALTER TABLE development_loop_rounds RENAME TO development_loop_rounds_legacy")
        conn.execute(
            """
            CREATE TABLE development_loop_rounds (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                loop_id TEXT NOT NULL,
                round_index INTEGER NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                job_ids TEXT NOT NULL DEFAULT '[]',
                commit_sha TEXT,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES development_plans(id) ON DELETE CASCADE,
                UNIQUE(plan_id, loop_id, round_index, stage)
            )
            """
        )
        columns = [
            name for name in (
                "id", "plan_id", "loop_id", "round_index", "stage", "status",
                "summary", "job_ids", "commit_sha", "evidence_json", "created_at", "updated_at",
            )
            if name in legacy_columns
        ]
        joined = ",".join(columns)
        conn.execute(
            f"INSERT OR IGNORE INTO development_loop_rounds ({joined}) "
            f"SELECT {joined} FROM development_loop_rounds_legacy"
        )
        conn.execute("DROP TABLE development_loop_rounds_legacy")

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def list_task_types(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM development_task_types WHERE active=1 ORDER BY sort_order,key"
            ).fetchall()
        return [dict(row) for row in rows]

    def target_execution_policy(self, target_id: str) -> str:
        """Classify managed targets before they can reach the code runner."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT p.project_type
                FROM projects p
                LEFT JOIN project_tasks t ON t.project_id=p.id
                LEFT JOIN development_points dp ON dp.project_id=p.id
                WHERE t.id=? OR dp.id=?
                LIMIT 1
                """,
                (target_id, target_id),
            ).fetchone()
        if not row:
            return "unmanaged_compatibility"
        if str(row["project_type"] or "software") == "document":
            return "document_forbidden"
        return "software_requires_plan"

    def requires_approved_plan(self, target_id: str) -> bool:
        """Compatibility wrapper for callers that only need gate/no-gate."""
        return self.target_execution_policy(target_id) != "unmanaged_compatibility"

    def list_plans(
        self,
        project_id: Optional[str] = None,
        target_kind: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> list[dict]:
        self.sync_execution_states()
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("project_id", project_id), ("target_kind", target_kind), ("target_id", target_id)):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM development_plans{where} ORDER BY updated_at DESC, version DESC",
                params,
            ).fetchall()
        return [self._public_plan(dict(row)) for row in rows]

    def get_plan(self, plan_id: str, sync: bool = True) -> Optional[dict]:
        if sync:
            self.sync_execution_states(plan_id)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM development_plans WHERE id=?", (plan_id,)).fetchone()
            if not row:
                return None
            events = conn.execute(
                "SELECT * FROM development_approval_events WHERE plan_id=? ORDER BY created_at",
                (plan_id,),
            ).fetchall()
            rounds = conn.execute(
                "SELECT * FROM development_loop_rounds WHERE plan_id=? ORDER BY round_index,created_at",
                (plan_id,),
            ).fetchall()
        data = self._public_plan(dict(row))
        data["approval_events"] = [dict(event) for event in events]
        data["loop_rounds"] = [self._public_round(dict(round_row)) for round_row in rounds]
        return data

    def create_plan(
        self,
        project_id: str,
        target_kind: str,
        target_id: str,
        instruction: str,
        created_by: str,
        task_type: Optional[str] = None,
        developer_agent_id: Optional[str] = None,
        planner_agent_id: Optional[str] = None,
        evaluator_agent_id: Optional[str] = None,
        max_rounds: int = 2,
        repo: Optional[str] = None,
    ) -> dict:
        if target_kind not in {"task", "development_point"}:
            raise ValueError("target_kind 必须是 task 或 development_point")
        if not instruction.strip():
            raise ValueError("计划目标不能为空")
        context = self._target_context(project_id, target_kind, target_id)
        resolved_type = task_type or self._classify_task_type(context)
        type_config = self._task_type(resolved_type)
        if not type_config:
            raise ValueError(f"未知开发任务类型：{resolved_type}")
        roles = {
            "planner": planner_agent_id or type_config["planner_agent_id"],
            "reviewer": "optimus" if resolved_type in {"integration", "deployment", "security"} else "wheeljack",
            "developer": developer_agent_id or type_config["developer_agent_id"],
            "evaluator": evaluator_agent_id or type_config["evaluator_agent_id"],
        }
        acceptance = self._acceptance_criteria(context, resolved_type)
        review = self._review(context, instruction, acceptance, roles)
        now = _now()
        plan_id = f"devplan-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        with self.connect() as conn:
            version = conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM development_plans WHERE target_kind=? AND target_id=?",
                (target_kind, target_id),
            ).fetchone()[0]
            plan_markdown = self._render_plan(context, resolved_type, instruction, acceptance, roles, review)
            conn.execute(
                """
                INSERT INTO development_plans (
                    id,project_id,target_kind,target_id,task_type,title,instruction,plan_markdown,
                    acceptance_criteria,risk_level,status,version,planner_agent_id,reviewer_agent_id,
                    developer_agent_id,evaluator_agent_id,max_rounds,repo,review_score,review_summary,
                    review_details,created_by,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    plan_id, project_id, target_kind, target_id, resolved_type, context["target_title"],
                    instruction.strip(), plan_markdown, json.dumps(acceptance, ensure_ascii=False),
                    review["risk_level"], "pending_approval", version, roles["planner"], roles["reviewer"],
                    roles["developer"], roles["evaluator"], max(1, min(int(max_rounds or 2), 5)), repo,
                    review["score"], review["summary"], json.dumps(review, ensure_ascii=False),
                    created_by, now, now,
                ),
            )
        return self.get_plan(plan_id, sync=False) or {}

    def decide_plan(
        self,
        plan_id: str,
        action: str,
        actor_id: str,
        actor_role: str,
        comment: str = "",
        auto_execute: bool = True,
    ) -> dict:
        action = action.strip().lower()
        if action not in {"approve", "revise", "reject"}:
            raise ValueError("action 必须是 approve、revise 或 reject")
        if actor_role != "admin":
            raise PermissionError("只有管理员可以审批开发计划")
        plan = self.get_plan(plan_id, sync=False)
        if not plan:
            raise KeyError(plan_id)
        if plan["status"] not in {"pending_approval", "revision_requested", "approved"}:
            raise ValueError(f"当前状态 {plan['status']} 不允许审批")
        status = {"approve": "approved", "revise": "revision_requested", "reject": "rejected"}[action]
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """UPDATE development_plans SET status=?, approved_by=?, approved_at=?, updated_at=? WHERE id=?""",
                (status, actor_id if action == "approve" else None, now if action == "approve" else None, now, plan_id),
            )
            conn.execute(
                """
                INSERT INTO development_approval_events
                    (id,plan_id,action,actor_id,actor_role,comment,plan_version,created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (f"approval-{uuid.uuid4().hex}", plan_id, action, actor_id, actor_role, comment, plan["version"], now),
            )
        if action == "approve" and auto_execute:
            return self.execute_plan(plan_id, actor_id)
        return self.get_plan(plan_id, sync=False) or {}

    def execute_plan(self, plan_id: str, actor_id: str) -> dict:
        plan = self.get_plan(plan_id, sync=False)
        if not plan:
            raise KeyError(plan_id)
        if plan["status"] != "approved":
            raise ValueError("开发计划必须批准后才能执行")
        if plan.get("loop_id"):
            raise ValueError("该计划已经启动执行")
        with self.connect() as conn:
            claimed = conn.execute(
                """UPDATE development_plans SET status='dispatching',updated_at=?
                    WHERE id=? AND status='approved' AND loop_id IS NULL""",
                (_now(), plan_id),
            )
            if claimed.rowcount != 1:
                raise ValueError("该计划正在执行或已经启动")
        instruction = "\n\n".join([
            "以下计划已经由管理员批准。执行过程中不得擅自扩大范围；若出现范围、权限、部署或高风险变更，停止并反馈重新审批。",
            plan["plan_markdown"],
            f"批准人：{actor_id}",
        ])
        try:
            loop = self.loop_creator(
                task_id=plan["target_id"],
                title=plan["title"],
                instruction=instruction,
                repo=plan.get("repo"),
                developer_agent_id=plan["developer_agent_id"],
                planner_agent_id=plan["planner_agent_id"],
                evaluator_agent_id=plan["evaluator_agent_id"],
                max_rounds=plan["max_rounds"],
                metadata={"development_plan_id": plan_id, "project_id": plan["project_id"], "approved_by": actor_id},
            )
        except Exception as exc:
            with self.connect() as conn:
                conn.execute(
                    """UPDATE development_plans SET status='approved',execution_error=?,updated_at=?
                        WHERE id=? AND status='dispatching'""",
                    (str(exc), _now(), plan_id),
                )
            raise
        with self.connect() as conn:
            updated = conn.execute(
                """UPDATE development_plans SET status='running',loop_id=?,execution_error=NULL,updated_at=?
                    WHERE id=? AND status='dispatching'""",
                (loop["id"], _now(), plan_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("计划派发状态已变化，无法登记新 Loop")
        return self.get_plan(plan_id, sync=False) or {}

    def retry_integration(self, plan_id: str, actor_id: str) -> dict:
        plan = self.get_plan(plan_id, sync=False)
        if not plan:
            raise KeyError(plan_id)
        if plan.get("status") != "manual_takeover" or not plan.get("loop_id"):
            raise ValueError("当前计划不处于可重试集成状态")
        loop = self.loop_integration_retrier(plan["loop_id"])
        with self.connect() as conn:
            conn.execute(
                """UPDATE development_plans SET status='running',execution_error=NULL,handoff_reason=NULL,updated_at=? WHERE id=?""",
                (_now(), plan_id),
            )
            conn.execute(
                """INSERT INTO development_approval_events
                    (id,plan_id,action,actor_id,actor_role,comment,plan_version,created_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                (f"approval-{uuid.uuid4().hex}", plan_id, "retry_integration", actor_id, "admin",
                 "管理员确认冲突已处理，重试合入集成分支", plan["version"], _now()),
            )
        self.sync_execution_states(plan_id)
        return self.get_plan(plan_id, sync=False) or {}

    def redispatch_execution(self, plan_id: str, actor_id: str) -> dict:
        self.sync_execution_states(plan_id)
        plan = self.get_plan(plan_id, sync=False)
        if not plan:
            raise KeyError(plan_id)
        if plan.get("status") not in {"failed", "cancelled", "manual_takeover"}:
            raise ValueError("只有失败、取消或中断转人工的已批准计划可以重新派发")
        if not plan.get("approved_by"):
            raise ValueError("计划尚未经过管理员批准，不能重新派发")
        if plan.get("status") == "manual_takeover":
            handoff_reason = str(plan.get("handoff_reason") or "").lower()
            interruption_markers = ("中断", "服务重启", "process exited", "runner stopped")
            if not any(marker in handoff_reason for marker in interruption_markers):
                raise ValueError("集成冲突或人工处理计划只能使用重试集成，不能重新派发")
        previous_status = plan["status"]
        with self.connect() as conn:
            claimed = conn.execute(
                """UPDATE development_plans SET status='redispatching',updated_at=?
                    WHERE id=? AND status=? AND approved_by IS NOT NULL""",
                (_now(), plan_id, previous_status),
            )
            if claimed.rowcount != 1:
                raise ValueError("该计划正在重新派发或状态已经变化")
        previous_loop_id = plan.get("loop_id")
        instruction = "\n\n".join([
            "这是管理员基于原批准范围发起的重新派发。原执行历史必须保留；本次在新的隔离工作树中重新执行，不得假装续接已退出的进程。",
            plan["plan_markdown"],
            f"重新派发人：{actor_id}",
            f"原 Loop：{previous_loop_id or '无'}",
        ])
        try:
            loop = self.loop_creator(
                task_id=plan["target_id"],
                title=plan["title"],
                instruction=instruction,
                repo=plan.get("repo"),
                developer_agent_id=plan["developer_agent_id"],
                planner_agent_id=plan["planner_agent_id"],
                evaluator_agent_id=plan["evaluator_agent_id"],
                max_rounds=plan["max_rounds"],
                metadata={
                    "development_plan_id": plan_id,
                    "project_id": plan["project_id"],
                    "approved_by": plan.get("approved_by"),
                    "redispatched_by": actor_id,
                    "previous_loop_id": previous_loop_id,
                },
            )
        except Exception as exc:
            with self.connect() as conn:
                conn.execute(
                    """UPDATE development_plans SET status=?,execution_error=?,updated_at=?
                        WHERE id=? AND status='redispatching'""",
                    (previous_status, str(exc), _now(), plan_id),
                )
            raise
        now = _now()
        with self.connect() as conn:
            updated = conn.execute(
                """UPDATE development_plans SET status='running',loop_id=?,execution_error=NULL,
                    handoff_reason=NULL,workspace_status=NULL,updated_at=?
                    WHERE id=? AND status='redispatching'""",
                (loop["id"], now, plan_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("计划重派发状态已变化，无法登记新 Loop")
            conn.execute(
                """INSERT INTO development_approval_events
                    (id,plan_id,action,actor_id,actor_role,comment,plan_version,created_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                (
                    f"approval-{uuid.uuid4().hex}",
                    plan_id,
                    "redispatch",
                    actor_id,
                    "admin",
                    f"基于原批准计划重新派发；previous_loop_id={previous_loop_id or ''};new_loop_id={loop['id']}",
                    plan["version"],
                    now,
                ),
            )
        return self.get_plan(plan_id, sync=False) or {}

    def sync_execution_states(self, plan_id: Optional[str] = None) -> None:
        with self.connect() as conn:
            if plan_id:
                rows = conn.execute(
                    """SELECT id,loop_id,status FROM development_plans
                        WHERE id=? AND status='running' AND loop_id IS NOT NULL""",
                    (plan_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id,loop_id,status FROM development_plans WHERE status='running' AND loop_id IS NOT NULL"
                ).fetchall()
        for row in rows:
            loop = self.loop_getter(row["loop_id"])
            if not loop:
                continue
            now = _now()
            with self.connect() as conn:
                for round_data in loop.get("rounds") or []:
                    round_index = int(round_data.get("round") or 0)
                    if round_index <= 0:
                        continue
                    stage = "round"
                    round_status = "completed" if round_index < int(loop.get("current_round") or 0) else str(loop.get("status") or "running")
                    checkpoint = round_data.get("checkpoint") or {}
                    evidence = {
                        "checkpoint": checkpoint,
                        "evaluation": round_data.get("evaluation") or {},
                    }
                    conn.execute(
                        """
                        INSERT INTO development_loop_rounds
                            (id,plan_id,loop_id,round_index,stage,status,summary,job_ids,commit_sha,evidence_json,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(plan_id,loop_id,round_index,stage) DO UPDATE SET
                            status=excluded.status,summary=excluded.summary,job_ids=excluded.job_ids,
                            commit_sha=excluded.commit_sha,evidence_json=excluded.evidence_json,updated_at=excluded.updated_at
                        """,
                        (
                            f"round-{row['id']}-{row['loop_id']}-{round_index}-{stage}", row["id"], row["loop_id"], round_index,
                            stage, round_status, (round_data.get("evaluation") or {}).get("summary") or "",
                            json.dumps(round_data.get("jobs") or [], ensure_ascii=False), checkpoint.get("commit_sha"),
                            json.dumps(evidence, ensure_ascii=False), now, now,
                        ),
                    )
                conn.execute(
                    """
                    UPDATE development_plans SET source_repo=?,workspace_path=?,source_branch=?,execution_branch=?,
                        integration_branch=?,base_commit=?,result_commit=?,merge_commit=?,workspace_status=?,
                        handoff_reason=?,evidence_json=?,updated_at=?
                    WHERE id=? AND loop_id=? AND status='running'
                    """,
                    (
                        loop.get("source_repo"), loop.get("execution_repo"), loop.get("source_branch"),
                        loop.get("execution_branch"), loop.get("integration_branch"), loop.get("base_commit"),
                        loop.get("result_commit"), loop.get("merge_commit"), loop.get("workspace_status"),
                        loop.get("handoff_reason"), json.dumps({"rounds": loop.get("rounds") or []}, ensure_ascii=False),
                        now, row["id"], row["loop_id"],
                    ),
                )
            loop_status = loop.get("status")
            if loop_status not in TERMINAL_LOOP_STATUSES:
                continue
            mapped = "completed" if loop_status == "succeeded" else ("manual_takeover" if loop_status == "needs_attention" else loop_status)
            with self.connect() as conn:
                conn.execute(
                    """UPDATE development_plans SET status=?,execution_error=?,updated_at=?
                        WHERE id=? AND loop_id=? AND status='running'""",
                    (mapped, loop.get("error"), _now(), row["id"], row["loop_id"]),
                )

    def _target_context(self, project_id: str, target_kind: str, target_id: str) -> dict:
        with self.connect() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if not project:
                raise KeyError(project_id)
            if str(project["project_type"] or "software") != "software":
                raise ValueError("自动化开发计划只适用于程序开发项目")
            if target_kind == "task":
                target = conn.execute(
                    "SELECT * FROM project_tasks WHERE id=? AND project_id=?", (target_id, project_id)
                ).fetchone()
                points = conn.execute(
                    "SELECT * FROM development_points WHERE task_id=? ORDER BY created_at,id", (target_id,)
                ).fetchall()
                task = target
            else:
                target = conn.execute(
                    "SELECT * FROM development_points WHERE id=? AND project_id=?", (target_id, project_id)
                ).fetchone()
                task = conn.execute("SELECT * FROM project_tasks WHERE id=?", (target["task_id"],)).fetchone() if target else None
                points = [target] if target else []
            if not target or not task:
                raise KeyError(target_id)
            project_context = _loads(project["context"], {})
            relations = project_context.get("project_relations", []) if isinstance(project_context, dict) else []
            related_background: list[dict[str, Any]] = []
            for relation in relations if isinstance(relations, list) else []:
                if not isinstance(relation, dict) or relation.get("status") != "active":
                    continue
                counterpart_id = (
                    relation.get("target_project_id")
                    if relation.get("source_project_id") == project_id
                    else relation.get("source_project_id")
                )
                if not counterpart_id:
                    continue
                counterpart = conn.execute(
                    "SELECT id,name,description,project_type,status,current_phase,context,design_doc,document_spec "
                    "FROM projects WHERE id=?",
                    (counterpart_id,),
                ).fetchone()
                if not counterpart:
                    continue
                counterpart_context = _loads(counterpart["context"], {})
                document_spec = _loads(counterpart["document_spec"], {})
                design_doc = _loads(counterpart["design_doc"], {})
                related_background.append({
                    "relation_type": relation.get("relation_type"),
                    "purpose": relation.get("purpose", ""),
                    "context_contract": relation.get("context_contract", {}),
                    "project": {
                        "id": counterpart["id"],
                        "name": counterpart["name"],
                        "description": counterpart["description"] or "",
                        "project_type": counterpart["project_type"],
                        "status": counterpart["status"],
                        "current_phase": counterpart["current_phase"],
                        "goal": counterpart_context.get("goal")
                        or document_spec.get("writing_goal")
                        or design_doc.get("summary")
                        or counterpart["description"]
                        or "",
                    },
                    "document_context": {
                        "document_type": document_spec.get("document_type", ""),
                        "writing_goal": document_spec.get("writing_goal", ""),
                        "target_audience": document_spec.get("target_audience", ""),
                        "chapters": [
                            item.get("title")
                            for item in document_spec.get("chapters", [])[:12]
                            if isinstance(item, dict) and item.get("title")
                        ],
                        "references": [
                            item.get("title")
                            for item in document_spec.get("references", [])[:8]
                            if isinstance(item, dict) and item.get("title")
                        ],
                    },
                    "software_context": {
                        "summary": design_doc.get("summary", ""),
                        "usage_requirements": design_doc.get("usage_requirements", [])[:12],
                        "system_functions": design_doc.get("system_functions", [])[:12],
                    },
                })
        return {
            "project": dict(project),
            "task": dict(task),
            "target": dict(target),
            "points": [dict(point) for point in points],
            "target_title": target["title"],
            "related_background": related_background,
        }

    def _task_type(self, key: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM development_task_types WHERE key=? AND active=1", (key,)).fetchone()
        return dict(row) if row else None

    def _classify_task_type(self, context: dict) -> str:
        task = context["task"]
        raw_type = str(task.get("type") or "").lower()
        if self._task_type(raw_type):
            return raw_type
        text = " ".join([
            str(task.get("title") or ""), str(task.get("description") or ""),
            str(context["target"].get("title") or ""),
        ]).lower()
        patterns = (
            ("testing", ("测试", "验收", "test", "e2e", "spec")),
            ("database", ("数据库", "数据表", "schema", "migration", "sqlite", "postgres")),
            ("backend", ("后端", "接口", "api", "router", "service", "python")),
            ("frontend", ("前端", "页面", "组件", "ui", "vue", "css")),
            ("deployment", ("部署", "发布", "deploy", "docker", "nginx")),
            ("integration", ("联调", "集成", "integration")),
            ("security", ("安全", "权限", "security", "auth")),
            ("performance", ("性能", "优化", "performance")),
            ("documentation", ("文档", "说明", "readme", "documentation")),
            ("architecture", ("架构", "设计", "architecture", "design")),
        )
        for key, words in patterns:
            if any(word in text for word in words):
                return key
        return "backend"

    def _acceptance_criteria(self, context: dict, task_type: str) -> list[str]:
        task = context["task"]
        criteria = _loads(task.get("acceptance_criteria"), [])
        if not isinstance(criteria, list):
            criteria = []
        if not criteria:
            criteria = [f"完成“{context['target_title']}”的最小可用闭环", "不破坏现有项目行为和数据兼容性"]
        type_checks = {
            "frontend": "前端构建通过，并验证目标页面的关键交互",
            "backend": "相关 API/服务测试通过，并覆盖错误路径",
            "database": "数据库迁移可重复执行，数据约束与回滚风险已验证",
            "testing": "新增或更新的测试可稳定复现并验证目标行为",
            "architecture": "边界、接口、数据流和兼容策略均有明确结论",
            "integration": "前后端或跨服务主链路验证通过",
            "deployment": "部署前检查通过；实际发布仍需单独批准",
        }
        criteria.append(type_checks.get(task_type, "运行与改动范围匹配的构建、测试或接口验证"))
        return list(dict.fromkeys(str(item) for item in criteria if str(item).strip()))

    def _review(self, context: dict, instruction: str, acceptance: list[str], roles: dict) -> dict:
        warnings: list[str] = []
        score = 100
        if len(instruction.strip()) < 20:
            warnings.append("目标描述较短，执行智能体必须先补充代码上下文")
            score -= 15
        if not context["points"]:
            warnings.append("任务尚未拆分开发要点，建议先细化执行单元")
            score -= 10
        if len(acceptance) < 2:
            warnings.append("验收标准不足")
            score -= 20
        risk_level = "high" if context["task"].get("type") in {"deployment", "security"} else "normal"
        summary = "预审通过，可提交管理员批准" if score >= 70 else "预审发现较多缺口，建议补充后批准"
        return {
            "score": max(score, 0), "summary": summary, "warnings": warnings,
            "risk_level": risk_level, "reviewer_agent_id": roles["reviewer"],
        }

    def _render_plan(self, context: dict, task_type: str, instruction: str, acceptance: list[str], roles: dict, review: dict) -> str:
        point_lines = [f"- {point['title']}" for point in context["points"]] or ["- 阅读代码并确认最小修改边界"]
        acceptance_lines = [f"- {item}" for item in acceptance]
        warning_lines = [f"- {item}" for item in review["warnings"]] or ["- 当前预审未发现阻断项"]
        background_lines = []
        for item in context.get("related_background", []):
            project = item.get("project", {})
            document = item.get("document_context", {})
            background_lines.extend([
                f"- 关联项目：{project.get('name')}（{project.get('project_type')}）",
                f"- 关联目的：{item.get('purpose') or item.get('relation_type') or '共享工作背景'}",
                f"- 背景目标：{project.get('goal') or project.get('description') or '未填写'}",
            ])
            if document.get("chapters"):
                background_lines.append("- 关键文档章节：" + "、".join(document["chapters"][:8]))
            if document.get("references"):
                background_lines.append("- 权威资料：" + "、".join(document["references"][:6]))
        if not background_lines:
            background_lines = ["- 当前软件项目尚未绑定课程或规则文档，执行前需从本项目设计文档确认需求。"]
        return "\n".join([
            f"# {context['target_title']} 自动化执行计划",
            "", f"- 项目：{context['project']['name']}", f"- 类型：{task_type}",
            f"- 方案：{roles['planner']}", f"- 开发：{roles['developer']}",
            f"- 评估：{roles['evaluator']}", f"- 风险：{review['risk_level']}",
            "", "## 关联项目与工作背景", *background_lines,
            "- 职责边界：关联课程/规则文档是需求与验收来源；本计划只允许修改软件项目仓库。",
            "", "## 目标与边界", instruction.strip(),
            "", "## 执行步骤", *point_lines,
            "- 运行与任务类型匹配的测试或构建", "- 由评估智能体给出通过/不通过结论；未通过自动进入下一轮",
            "", "## 验收标准", *acceptance_lines,
            "", "## 智能体预审", f"- 得分：{review['score']}", f"- 结论：{review['summary']}", *warning_lines,
            "", "## 审批约束", "- 管理员批准前禁止修改代码", "- 批准后允许在既定范围内自动迭代",
            "- 范围扩大、高风险操作和部署发布必须停止并重新审批",
        ])

    def _public_plan(self, plan: dict) -> dict:
        plan["acceptance_criteria"] = _loads(plan.get("acceptance_criteria"), [])
        plan["review_details"] = _loads(plan.get("review_details"), {})
        plan["evidence_json"] = _loads(plan.get("evidence_json"), {})
        return plan

    def _public_round(self, round_data: dict) -> dict:
        round_data["job_ids"] = _loads(round_data.get("job_ids"), [])
        round_data["evidence_json"] = _loads(round_data.get("evidence_json"), {})
        return round_data


development_automation_service = DevelopmentAutomationService()
