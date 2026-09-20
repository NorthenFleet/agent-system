"""Pluggable workflow runtimes for command-center missions.

Command Center remains the business source of truth.  A runtime only owns
recoverable execution checkpoints and never writes mission/step state itself.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol, TypedDict

from repositories.command_center_repository import _postgres_dsn


TRUTHY = {"1", "true", "yes", "on"}
PILOT_FLOW_KEYS = {"document", "research"}
PILOT_RISK_LEVELS = {"L0", "L1"}
POSTGRES_CHECKPOINT_TABLES = {
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
}


class WorkflowRuntimeError(RuntimeError):
    pass


class WorkflowRuntimeUnavailable(WorkflowRuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowRuntimeResult:
    status: str
    state: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)


class WorkflowRuntime(Protocol):
    name: str

    def start(self, run: dict[str, Any]) -> WorkflowRuntimeResult: ...

    def resume(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> WorkflowRuntimeResult: ...


class PilotWorkflowState(TypedDict, total=False):
    workflow_run_id: str
    mission_id: str
    plan_version: int
    flow_key: str
    highest_risk: str
    status: str
    context_pack_id: str
    approval: dict[str, Any]
    evidence_refs: list[str]


def _package_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def sqlite_langgraph_available() -> bool:
    return _package_available("langgraph") and _package_available(
        "langgraph.checkpoint.sqlite"
    )


def postgres_langgraph_available() -> bool:
    return _package_available("langgraph") and _package_available(
        "langgraph.checkpoint.postgres"
    )


def postgres_checkpoint_required_version() -> int:
    if not postgres_langgraph_available():
        return -1
    from langgraph.checkpoint.postgres import PostgresSaver

    return len(PostgresSaver.MIGRATIONS) - 1


def _configured_checkpoint_url() -> str:
    explicit = os.getenv("COMMAND_CENTER_LANGGRAPH_CHECKPOINT_URL", "").strip()
    if explicit:
        return explicit
    command_center_url = os.getenv("COMMAND_CENTER_DATABASE_URL", "").strip()
    if command_center_url.startswith(("postgresql://", "postgresql+psycopg2://", "postgres://")):
        return command_center_url
    return ""


def langgraph_available() -> bool:
    if _configured_checkpoint_url():
        return postgres_langgraph_available()
    return sqlite_langgraph_available()


def workflow_runtime_catalog(checkpoint_database_url: str = "") -> dict[str, Any]:
    enabled = os.getenv("COMMAND_CENTER_LANGGRAPH_ENABLED", "false").lower() in TRUTHY
    postgres_url = checkpoint_database_url.strip() or _configured_checkpoint_url()
    allowed = {
        item.strip().lower()
        for item in os.getenv(
            "COMMAND_CENTER_LANGGRAPH_FLOWS", ",".join(sorted(PILOT_FLOW_KEYS))
        ).split(",")
        if item.strip()
    }
    return {
        "default_runtime": "legacy",
        "langgraph": {
            "enabled": enabled,
            "available": (
                postgres_langgraph_available() if postgres_url else sqlite_langgraph_available()
            ),
            "pilot_flows": sorted(allowed),
            "pilot_risk_levels": sorted(PILOT_RISK_LEVELS),
            "checkpoint_backend": "postgresql" if postgres_url else "sqlite",
            "role": "approval and recovery execution gate",
        },
        "ownership": {
            "business_state": "command_center",
            "execution_checkpoint": "workflow_runtime",
            "long_term_memory": "memory_service",
        },
    }


def select_workflow_runtime(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a safe runtime choice and the reason behind it."""

    catalog = workflow_runtime_catalog()
    config = catalog["langgraph"]
    flow_key = str((plan.get("flow_spec") or {}).get("flow_key") or "general")
    highest_risk = str(
        (plan.get("risk_assessment") or {}).get("highest_risk") or "L1"
    ).upper()
    reason = "pilot_selected"
    eligible = True
    if not config["enabled"]:
        reason, eligible = "feature_disabled", False
    elif not config["available"]:
        reason, eligible = "langgraph_unavailable", False
    elif flow_key not in set(config["pilot_flows"]):
        reason, eligible = "flow_not_in_pilot", False
    elif highest_risk not in PILOT_RISK_LEVELS:
        reason, eligible = "risk_above_pilot_limit", False
    return {
        "runtime": "langgraph" if eligible else "legacy",
        "eligible": eligible,
        "reason": reason,
        "flow_key": flow_key,
        "highest_risk": highest_risk,
    }


class LegacyWorkflowRuntime:
    """Adapter documenting that the existing worker is already ready to run."""

    name = "legacy"

    def start(self, run: dict[str, Any]) -> WorkflowRuntimeResult:
        return WorkflowRuntimeResult(status="ready", state=run.get("input") or {})

    def resume(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> WorkflowRuntimeResult:
        state = dict(run.get("state") or run.get("input") or {})
        state["approval"] = dict(payload)
        state["status"] = "ready"
        return WorkflowRuntimeResult(status="ready", state=state)


class LangGraphWorkflowRuntime:
    """Minimal durable pilot graph: prepare -> approval interrupt -> ready."""

    name = "langgraph"

    def __init__(self, checkpoint_path: str):
        self.checkpoint_path = str(Path(checkpoint_path))

    @staticmethod
    def _compile_graph(saver: Any) -> Any:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt

        def prepare(state: PilotWorkflowState) -> dict[str, Any]:
            return {"status": "awaiting_approval"}

        def approval_gate(state: PilotWorkflowState) -> dict[str, Any]:
            decision = interrupt(
                {
                    "kind": "plan_approval",
                    "workflow_run_id": state.get("workflow_run_id"),
                    "mission_id": state.get("mission_id"),
                    "plan_version": state.get("plan_version"),
                    "flow_key": state.get("flow_key"),
                    "highest_risk": state.get("highest_risk"),
                }
            )
            approved = bool(
                isinstance(decision, dict)
                and str(decision.get("decision") or "").lower() == "approved"
            )
            return {
                "approval": decision if isinstance(decision, dict) else {},
                "status": "ready" if approved else "cancelled",
            }

        builder = StateGraph(PilotWorkflowState)
        builder.add_node("prepare", prepare)
        builder.add_node("approval_gate", approval_gate)
        builder.add_edge(START, "prepare")
        builder.add_edge("prepare", "approval_gate")
        builder.add_edge("approval_gate", END)
        return builder.compile(checkpointer=saver)

    @contextmanager
    def _open_graph(self):
        if not sqlite_langgraph_available():
            raise WorkflowRuntimeUnavailable(
                "LangGraph runtime requires langgraph and langgraph-checkpoint-sqlite"
            )
        from langgraph.checkpoint.sqlite import SqliteSaver

        checkpoint = Path(self.checkpoint_path)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(checkpoint), check_same_thread=False)
        try:
            saver = SqliteSaver(connection)
            saver.setup()
            yield self._compile_graph(saver)
        finally:
            connection.close()

    @staticmethod
    def _config(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "configurable": {
                "thread_id": str(run.get("thread_id") or run["id"]),
            }
        }

    @staticmethod
    def _result(snapshot: Any) -> WorkflowRuntimeResult:
        values = dict(getattr(snapshot, "values", None) or {})
        next_nodes = list(getattr(snapshot, "next", None) or [])
        status = str(values.get("status") or "")
        if next_nodes:
            status = "awaiting_approval"
        elif status not in {"ready", "cancelled"}:
            status = "ready"
        return WorkflowRuntimeResult(
            status=status,
            state=values,
            checkpoint={"next_nodes": next_nodes},
        )

    def start(self, run: dict[str, Any]) -> WorkflowRuntimeResult:
        with self._open_graph() as graph:
            config = self._config(run)
            existing = graph.get_state(config)
            if getattr(existing, "values", None):
                return self._result(existing)
            initial = dict(run.get("input") or {})
            initial.setdefault("workflow_run_id", run["id"])
            initial.setdefault("mission_id", run["mission_id"])
            initial.setdefault("plan_version", int(run["plan_version"]))
            initial.setdefault("status", "preparing")
            initial.setdefault("evidence_refs", [])
            graph.invoke(initial, config=config)
            return self._result(graph.get_state(config))

    def resume(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> WorkflowRuntimeResult:
        from langgraph.types import Command

        with self._open_graph() as graph:
            config = self._config(run)
            current = self._result(graph.get_state(config))
            if current.status in {"ready", "cancelled"}:
                return current
            graph.invoke(Command(resume=dict(payload)), config=config)
            return self._result(graph.get_state(config))


class PostgresLangGraphWorkflowRuntime(LangGraphWorkflowRuntime):
    """LangGraph pilot backed by an Alembic-managed PostgreSQL checkpointer."""

    def __init__(self, database_url: str):
        self.database_url = _postgres_dsn(database_url)

    def _validate_schema(self) -> None:
        if not postgres_langgraph_available():
            raise WorkflowRuntimeUnavailable(
                "PostgreSQL LangGraph runtime requires langgraph-checkpoint-postgres"
            )
        import psycopg

        required_version = postgres_checkpoint_required_version()
        required_tables = POSTGRES_CHECKPOINT_TABLES
        try:
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT MAX(v) FROM checkpoint_migrations")
                    row = cursor.fetchone()
                    installed_version = int(row[0]) if row and row[0] is not None else -1
                    cursor.execute(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema=current_schema()
                          AND table_name = ANY(%s)
                        """,
                        (list(required_tables),),
                    )
                    installed_tables = {str(item[0]) for item in cursor.fetchall()}
        except Exception as exc:
            raise WorkflowRuntimeUnavailable(
                "LangGraph PostgreSQL checkpoint schema is unavailable; "
                "run Alembic upgrade head before starting workers"
            ) from exc
        missing_tables = sorted(required_tables - installed_tables)
        if missing_tables:
            raise WorkflowRuntimeUnavailable(
                "LangGraph PostgreSQL checkpoint schema is incomplete; missing tables: "
                + ", ".join(missing_tables)
                + ". Run Alembic upgrade head."
            )
        if installed_version < required_version:
            raise WorkflowRuntimeUnavailable(
                "LangGraph PostgreSQL checkpoint schema is outdated: "
                f"installed={installed_version}, required={required_version}; "
                "run Alembic upgrade head"
            )

    @contextmanager
    def _open_graph(self) -> Iterator[Any]:
        self._validate_schema()
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(self.database_url) as saver:
            yield self._compile_graph(saver)


class WorkflowRuntimeRouter:
    def __init__(self, checkpoint_path: str, *, checkpoint_database_url: str = ""):
        self.checkpoint_database_url = checkpoint_database_url.strip()
        self._runtimes: dict[str, WorkflowRuntime] = {
            "legacy": LegacyWorkflowRuntime(),
            "langgraph": (
                PostgresLangGraphWorkflowRuntime(self.checkpoint_database_url)
                if self.checkpoint_database_url
                else LangGraphWorkflowRuntime(checkpoint_path)
            ),
        }

    def register(self, runtime: WorkflowRuntime) -> None:
        self._runtimes[runtime.name] = runtime

    def get(self, name: str) -> WorkflowRuntime:
        try:
            return self._runtimes[name]
        except KeyError as exc:
            raise WorkflowRuntimeUnavailable(f"unknown workflow runtime: {name}") from exc

    def catalog(self) -> dict[str, Any]:
        return workflow_runtime_catalog(self.checkpoint_database_url)
