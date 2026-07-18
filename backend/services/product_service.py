"""File-backed product registry for reusable systems and company offerings."""

from __future__ import annotations

import copy
import fcntl
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import data_path
from unified_data_manager import UNIFIED_DB_PATH


PRODUCT_REGISTRY_FILE = data_path("product-registry.json")

RUNTIME_INSTANCE_STATES = {
    "pending",
    "deploying",
    "online",
    "degraded",
    "offline",
    "failed",
    "stopped",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_products() -> list[dict[str, Any]]:
    return [
        {
            "id": "openclaw-3021",
            "name": "OpenClaw 智能体系统",
            "kind": "platform",
            "category": "经营与协作中枢",
            "description": "统一项目、智能体、知识、财务和专业产品运行关系。",
            "version": "v3",
            "status": "active",
            "owner": "optimus",
            "deployment": {
                "device": "Mac mini",
                "host": "192.168.31.41",
                "port": 3021,
                "public_url": "http://192.168.31.41:3021",
                "mode": "standalone",
            },
            "capabilities": ["项目中枢", "智能体组织", "知识管理", "财务管理", "产品编排"],
            "dependencies": [],
        },
        {
            "id": "ai-planning-5130",
            "name": "无人集群任务规划系统",
            "kind": "service",
            "category": "任务规划",
            "description": "管理想定、任务链、计划生成、监督评估和重新规划。",
            "version": "v1",
            "status": "active",
            "owner": "optimus",
            "deployment": {
                "device": "Mac Pro",
                "host": "192.168.31.144",
                "port": 5130,
                "public_url": "http://192.168.31.144:5130",
                "mode": "standalone",
            },
            "capabilities": ["想定加载", "计划生成", "任务链", "闭环监督", "重规划"],
            "dependencies": [
                {"product_id": "one-sim", "type": "runtime", "description": "使用one-sim态势会话推进仿真"}
            ],
        },
        {
            "id": "one-sim",
            "name": "one-sim 无人集群仿真系统",
            "kind": "simulation",
            "category": "仿真执行",
            "description": "提供权威世界状态、实体运动、观测、命令执行和实验数据。",
            "version": "v1",
            "status": "active",
            "owner": "optimus",
            "deployment": {
                "device": "Mac Pro",
                "host": "192.168.31.144",
                "port": 5130,
                "public_url": "http://192.168.31.144:5130",
                "mode": "embedded-planning-situation",
            },
            "capabilities": ["态势状态", "仿真推进", "观测契约", "指令执行", "训练数据"],
            "dependencies": [],
        },
        {
            "id": "manual-wargame",
            "name": "手工纸质兵棋",
            "kind": "offering",
            "category": "兵棋产品",
            "description": "面向规则验证、教学推演和快速原型的实体产品。",
            "version": "prototype",
            "status": "developing",
            "owner": "待分配",
            "deployment": {"mode": "physical"},
            "capabilities": ["规则验证", "教学推演", "快速原型"],
            "dependencies": [],
        },
        {
            "id": "digital-wargame",
            "name": "电子化兵棋",
            "kind": "offering",
            "category": "兵棋产品",
            "description": "规则引擎自动化、界面交互和多人协同产品。",
            "version": "prototype",
            "status": "developing",
            "owner": "待分配",
            "deployment": {"mode": "planned"},
            "capabilities": ["自动裁决", "交互推演", "多人协同"],
            "dependencies": [{"product_id": "one-sim", "type": "engine"}],
        },
        {
            "id": "intelligent-wargame",
            "name": "智能兵棋",
            "kind": "offering",
            "category": "兵棋产品",
            "description": "智能体参与推演、AI辅助决策和强化学习训练产品。",
            "version": "planned",
            "status": "planning",
            "owner": "待分配",
            "deployment": {"mode": "planned"},
            "capabilities": ["智能对抗", "决策辅助", "强化学习"],
            "dependencies": [
                {"product_id": "ai-planning-5130", "type": "planning"},
                {"product_id": "one-sim", "type": "simulation"},
            ],
        },
    ]


class ProductRegistryService:
    def __init__(self, file_path: str = PRODUCT_REGISTRY_FILE, db_path: str | None = None):
        self.file_path = file_path
        # The live registry is authoritative in the unified dashboard database.
        # A custom registry file remains file-backed for focused tests/imports.
        self.db_path = db_path or (
            UNIFIED_DB_PATH if os.path.abspath(file_path) == os.path.abspath(PRODUCT_REGISTRY_FILE) else None
        )
        if self.db_path:
            self._init_database()

    def _lock_path(self) -> str:
        return self.file_path + ".lock"

    def _uses_database(self) -> bool:
        return bool(self.db_path)

    def _connect_database(self) -> sqlite3.Connection:
        if not self.db_path:
            raise RuntimeError("Product registry database is not configured")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _init_database(self) -> None:
        with self._connect_database() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS product_registry_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS product_registry_products (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS product_registry_deliverables (id TEXT PRIMARY KEY, product_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS product_registry_releases (id TEXT PRIMARY KEY, product_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS product_registry_runtime_instances (id TEXT PRIMARY KEY, product_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS product_registry_events (id TEXT PRIMARY KEY, product_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS product_registry_idempotency (key TEXT PRIMARY KEY, deliverable_id TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_product_deliverables_product ON product_registry_deliverables(product_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_product_releases_product ON product_registry_releases(product_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_product_runtimes_product ON product_registry_runtime_instances(product_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_product_events_product ON product_registry_events(product_id, created_at DESC);
                """
            )

    def _database_has_registry(self) -> bool:
        if not self._uses_database():
            return False
        with self._connect_database() as connection:
            return connection.execute("SELECT 1 FROM product_registry_meta WHERE key='schema'").fetchone() is not None

    def _default(self) -> dict[str, Any]:
        return {
            "schema": "openclaw.product-registry",
            "version": 3,
            "updated_at": _now(),
            "products": _seed_products(),
            "deliverables": [],
            "releases": [],
            "runtime_instances": [],
            "events": [],
            "idempotency": {},
        }

    def _load_unlocked(self) -> dict[str, Any]:
        if self._uses_database():
            with self._connect_database() as connection:
                meta = {
                    row["key"]: row["value"]
                    for row in connection.execute("SELECT key, value FROM product_registry_meta")
                }
                if not meta.get("schema"):
                    return self._load_legacy_unlocked()
                data = {
                    "schema": meta.get("schema", "openclaw.product-registry"),
                    "version": int(meta.get("version", "3")),
                    "updated_at": meta.get("updated_at", _now()),
                    "products": [json.loads(row["payload"]) for row in connection.execute("SELECT payload FROM product_registry_products ORDER BY id")],
                    "deliverables": [json.loads(row["payload"]) for row in connection.execute("SELECT payload FROM product_registry_deliverables ORDER BY created_at, id")],
                    "releases": [json.loads(row["payload"]) for row in connection.execute("SELECT payload FROM product_registry_releases ORDER BY created_at, id")],
                    "runtime_instances": [json.loads(row["payload"]) for row in connection.execute("SELECT payload FROM product_registry_runtime_instances ORDER BY updated_at, id")],
                    "events": [json.loads(row["payload"]) for row in connection.execute("SELECT payload FROM product_registry_events ORDER BY created_at, id")],
                    "idempotency": {
                        row["key"]: row["deliverable_id"]
                        for row in connection.execute("SELECT key, deliverable_id FROM product_registry_idempotency")
                    },
                }
                self._migrate_ledger_schema(data)
                return data
        return self._load_legacy_unlocked()

    def _load_legacy_unlocked(self) -> dict[str, Any]:
        if not os.path.exists(self.file_path):
            return self._default()
        with open(self.file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self._migrate_ledger_schema(data)
        return data

    @staticmethod
    def _migrate_ledger_schema(data: dict[str, Any]) -> bool:
        """Upgrade the original registry in-place without changing product records."""
        changed = False
        if data.get("schema") != "openclaw.product-registry":
            data["schema"] = "openclaw.product-registry"
            changed = True
        try:
            current_version = int(data.get("version") or 1)
        except (TypeError, ValueError):
            current_version = 1
        if current_version < 3:
            data["version"] = 3
            changed = True
        data.setdefault("schema", "openclaw.product-registry")
        for key, default in {
            "products": [],
            "deliverables": [],
            "releases": [],
            "runtime_instances": [],
            "events": [],
            "idempotency": {},
        }.items():
            if key not in data:
                data[key] = default
                changed = True
        return changed

    def ensure_ledger_schema(self) -> dict[str, Any]:
        """Persist the ledger migration once, importing legacy JSON only on first DB use."""
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                existed = self._database_has_registry() if self._uses_database() else os.path.exists(self.file_path)
                data = self._load_unlocked()
                # _load_unlocked has already normalized the schema. Compare the
                # on-disk version when it existed so routine reads do not rewrite it.
                needs_save = not existed
                if existed and not self._uses_database():
                    with open(self.file_path, "r", encoding="utf-8") as handle:
                        raw = json.load(handle)
                    needs_save = self._migrate_ledger_schema(raw)
                if needs_save:
                    self._save_unlocked(data)
                return copy.deepcopy(data)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        if self._uses_database():
            self._save_database_unlocked(data)
            return
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _now()
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def _save_database_unlocked(self, data: dict[str, Any]) -> None:
        """Persist every ledger collection atomically in the unified SQLite database."""
        data["updated_at"] = _now()
        with self._connect_database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            collections = {
                "product_registry_products": data["products"],
                "product_registry_deliverables": data["deliverables"],
                "product_registry_releases": data["releases"],
                "product_registry_runtime_instances": data["runtime_instances"],
                "product_registry_events": data["events"],
            }
            for table_name in collections:
                connection.execute(f"DELETE FROM {table_name}")
            for row in collections["product_registry_products"]:
                connection.execute(
                    "INSERT INTO product_registry_products(id, payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (row["id"], json.dumps(row, ensure_ascii=False), row.get("created_at"), row.get("updated_at")),
                )
            for table_name in (
                "product_registry_deliverables",
                "product_registry_releases",
                "product_registry_runtime_instances",
            ):
                for row in collections[table_name]:
                    connection.execute(
                        f"INSERT INTO {table_name}(id, product_id, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (row["id"], row["product_id"], json.dumps(row, ensure_ascii=False), row.get("created_at"), row.get("updated_at")),
                    )
            for row in collections["product_registry_events"]:
                connection.execute(
                    "INSERT INTO product_registry_events(id, product_id, payload, created_at) VALUES (?, ?, ?, ?)",
                    (row["id"], row["product_id"], json.dumps(row, ensure_ascii=False), row.get("created_at")),
                )
            connection.execute("DELETE FROM product_registry_idempotency")
            connection.executemany(
                "INSERT INTO product_registry_idempotency(key, deliverable_id) VALUES (?, ?)",
                list(data["idempotency"].items()),
            )
            for key, value in {
                "schema": str(data["schema"]),
                "version": str(data["version"]),
                "updated_at": str(data["updated_at"]),
            }.items():
                connection.execute(
                    "INSERT INTO product_registry_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )

    def get_registry(self) -> dict[str, Any]:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                if (self._uses_database() and not self._database_has_registry()) or (not self._uses_database() and not os.path.exists(self.file_path)):
                    self._save_unlocked(data)
                return copy.deepcopy(data)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self.get_registry()["products"] if row.get("id") == product_id),
            None,
        )

    def upsert_product(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                product = next((row for row in data["products"] if row.get("id") == product_id), None)
                if product is None:
                    product = {"id": product_id, "created_at": _now()}
                    data["products"].append(product)
                allowed = {
                    "name", "kind", "category", "description", "version", "status", "owner",
                    "repository", "deployment", "capabilities", "dependencies", "tags",
                }
                product.update({key: value for key, value in payload.items() if key in allowed})
                product["updated_at"] = _now()
                self._append_event(data, product_id, "product.updated", {
                    "product_id": product_id,
                    "changed_fields": sorted(key for key in payload if key in allowed),
                })
                self._save_unlocked(data)
                return copy.deepcopy(product)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def delete_product(self, product_id: str) -> bool:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                before = len(data["products"])
                data["products"] = [row for row in data["products"] if row.get("id") != product_id]
                if len(data["products"]) == before:
                    return False
                self._save_unlocked(data)
                return True
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _append_event(
        data: dict[str, Any],
        product_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "id": f"evt-{uuid.uuid4().hex[:12]}",
            "product_id": product_id,
            "event_type": event_type,
            "payload": copy.deepcopy(payload),
            "created_at": _now(),
        }
        data["events"].append(event)
        # A product timeline is useful, but it should not grow without bound in the registry file.
        if len(data["events"]) > 2_000:
            data["events"] = data["events"][-2_000:]
        return event

    def list_deliverables(
        self,
        product_id: str,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = [
            row for row in self.get_registry()["deliverables"]
            if row.get("product_id") == product_id
            and (not project_id or row.get("project_id") == project_id)
        ]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return copy.deepcopy(rows[:max(1, min(limit, 500))])

    def submit_deliverable(
        self,
        product_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Persist a candidate deliverable produced by a project task or agent."""
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                if not any(row.get("id") == product_id for row in data["products"]):
                    raise KeyError(product_id)
                if idempotency_key:
                    existing_id = data["idempotency"].get(idempotency_key)
                    if existing_id:
                        existing = next(
                            (row for row in data["deliverables"] if row.get("id") == existing_id),
                            None,
                        )
                        if existing:
                            return copy.deepcopy(existing)

                now = _now()
                deliverable = {
                    "id": f"dlv-{uuid.uuid4().hex[:12]}",
                    "product_id": product_id,
                    "project_id": str(payload.get("project_id") or ""),
                    "task_id": str(payload.get("task_id") or ""),
                    "development_point_id": str(payload.get("development_point_id") or ""),
                    "kind": str(payload.get("kind") or "document"),
                    "title": str(payload.get("title") or "未命名交付物"),
                    "uri": str(payload.get("uri") or ""),
                    "content_hash": str(payload.get("content_hash") or ""),
                    "version": str(payload.get("version") or ""),
                    "status": "draft",
                    "summary": str(payload.get("summary") or ""),
                    "metadata": copy.deepcopy(payload.get("metadata") or {}),
                    "produced_by_agent_id": str(payload.get("produced_by_agent_id") or ""),
                    "created_at": now,
                    "updated_at": now,
                }
                data["deliverables"].append(deliverable)
                if idempotency_key:
                    data["idempotency"][idempotency_key] = deliverable["id"]
                self._append_event(data, product_id, "deliverable.submitted", {
                    "deliverable_id": deliverable["id"],
                    "project_id": deliverable["project_id"],
                    "task_id": deliverable["task_id"],
                    "kind": deliverable["kind"],
                    "title": deliverable["title"],
                })
                self._save_unlocked(data)
                return copy.deepcopy(deliverable)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def review_deliverable(
        self,
        product_id: str,
        deliverable_id: str,
        *,
        accepted: bool,
        reviewed_by_agent_id: str,
        review_note: str = "",
    ) -> dict[str, Any] | None:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                deliverable = next(
                    (
                        row for row in data["deliverables"]
                        if row.get("id") == deliverable_id and row.get("product_id") == product_id
                    ),
                    None,
                )
                if not deliverable:
                    return None
                now = _now()
                deliverable.update({
                    "status": "accepted" if accepted else "rejected",
                    "accepted_by_agent_id": reviewed_by_agent_id if accepted else "",
                    "reviewed_by_agent_id": reviewed_by_agent_id,
                    "review_note": review_note,
                    "reviewed_at": now,
                    "accepted_at": now if accepted else "",
                    "updated_at": now,
                })
                self._append_event(data, product_id, "deliverable.accepted" if accepted else "deliverable.rejected", {
                    "deliverable_id": deliverable_id,
                    "reviewed_by_agent_id": reviewed_by_agent_id,
                    "review_note": review_note,
                })
                self._save_unlocked(data)
                return copy.deepcopy(deliverable)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def list_releases(self, product_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = [row for row in self.get_registry()["releases"] if row.get("product_id") == product_id]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return copy.deepcopy(rows[:max(1, min(limit, 500))])

    def create_release(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                product = next((row for row in data["products"] if row.get("id") == product_id), None)
                if not product:
                    raise KeyError(product_id)
                deliverable_id = str(payload.get("source_deliverable_id") or "")
                source = next((row for row in data["deliverables"] if row.get("id") == deliverable_id), None)
                if deliverable_id and (not source or source.get("product_id") != product_id):
                    raise ValueError("source deliverable does not belong to product")
                if source and source.get("status") != "accepted":
                    raise ValueError("source deliverable must be accepted before release")
                status = str(payload.get("status") or "pending")
                if status == "active" and not source:
                    raise ValueError("active release requires an accepted source deliverable")
                now = _now()
                release = {
                    "id": f"rel-{uuid.uuid4().hex[:12]}",
                    "product_id": product_id,
                    "version": str(payload.get("version") or product.get("version") or "unversioned"),
                    "environment": str(payload.get("environment") or "internal"),
                    "status": status,
                    "deployment_url": str(payload.get("deployment_url") or ""),
                    "source_deliverable_id": deliverable_id,
                    "released_by_agent_id": str(payload.get("released_by_agent_id") or ""),
                    "release_note": str(payload.get("release_note") or ""),
                    "created_at": now,
                    "updated_at": now,
                    "released_at": now if str(payload.get("status") or "") == "active" else "",
                }
                data["releases"].append(release)
                if release["status"] == "active":
                    product.update({"version": release["version"], "current_release_id": release["id"], "updated_at": now})
                self._append_event(data, product_id, "release.created", {
                    "release_id": release["id"],
                    "version": release["version"],
                    "environment": release["environment"],
                    "status": release["status"],
                })
                self._save_unlocked(data)
                return copy.deepcopy(release)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def timeline(self, product_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = [row for row in self.get_registry()["events"] if row.get("product_id") == product_id]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return copy.deepcopy(rows[:max(1, min(limit, 500))])

    def list_runtime_instances(self, product_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = [
            row for row in self.get_registry()["runtime_instances"]
            if row.get("product_id") == product_id
        ]
        rows.sort(
            key=lambda row: str(row.get("last_observed_at") or row.get("updated_at") or row.get("created_at") or ""),
            reverse=True,
        )
        return copy.deepcopy(rows[:max(1, min(limit, 500))])

    def create_runtime_instance(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Register a deployable product instance without treating it as a health probe."""
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                if not any(row.get("id") == product_id for row in data["products"]):
                    raise KeyError(product_id)
                release_id = str(payload.get("release_id") or "")
                if release_id:
                    release = next(
                        (row for row in data["releases"] if row.get("id") == release_id),
                        None,
                    )
                    if not release or release.get("product_id") != product_id:
                        raise ValueError("release does not belong to product")
                state = str(payload.get("state") or "pending")
                if state not in RUNTIME_INSTANCE_STATES:
                    raise ValueError(f"unsupported runtime state: {state}")
                now = _now()
                instance = {
                    "id": f"rtm-{uuid.uuid4().hex[:12]}",
                    "product_id": product_id,
                    "name": str(payload.get("name") or "未命名实例"),
                    "environment": str(payload.get("environment") or "internal"),
                    "state": state,
                    "release_id": release_id,
                    "version": str(payload.get("version") or ""),
                    "device": str(payload.get("device") or ""),
                    "host": str(payload.get("host") or ""),
                    "port": int(payload["port"]) if payload.get("port") not in (None, "") else None,
                    "public_url": str(payload.get("public_url") or ""),
                    "health_url": str(payload.get("health_url") or ""),
                    "summary": str(payload.get("summary") or ""),
                    "metadata": copy.deepcopy(payload.get("metadata") or {}),
                    "created_at": now,
                    "updated_at": now,
                    "last_observed_at": str(payload.get("last_observed_at") or now),
                }
                data["runtime_instances"].append(instance)
                self._append_event(data, product_id, "runtime.registered", {
                    "runtime_instance_id": instance["id"],
                    "environment": instance["environment"],
                    "state": instance["state"],
                    "release_id": instance["release_id"],
                })
                self._save_unlocked(data)
                return copy.deepcopy(instance)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def update_runtime_instance(
        self,
        product_id: str,
        runtime_instance_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                instance = next(
                    (
                        row for row in data["runtime_instances"]
                        if row.get("id") == runtime_instance_id and row.get("product_id") == product_id
                    ),
                    None,
                )
                if not instance:
                    return None
                if "release_id" in payload and payload["release_id"]:
                    release = next(
                        (row for row in data["releases"] if row.get("id") == payload["release_id"]),
                        None,
                    )
                    if not release or release.get("product_id") != product_id:
                        raise ValueError("release does not belong to product")
                if "state" in payload and payload["state"] not in RUNTIME_INSTANCE_STATES:
                    raise ValueError(f"unsupported runtime state: {payload['state']}")
                allowed = {
                    "name", "environment", "state", "release_id", "version", "device", "host", "port",
                    "public_url", "health_url", "summary", "metadata", "last_observed_at",
                }
                instance.update({key: copy.deepcopy(value) for key, value in payload.items() if key in allowed})
                instance["updated_at"] = _now()
                self._append_event(data, product_id, "runtime.updated", {
                    "runtime_instance_id": runtime_instance_id,
                    "changed_fields": sorted(key for key in payload if key in allowed),
                    "state": instance.get("state"),
                })
                self._save_unlocked(data)
                return copy.deepcopy(instance)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def record_runtime_health(
        self,
        product_id: str,
        runtime_instance_id: str,
        observation: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Persist a health observation produced by the controlled runtime probe."""
        state = str(observation.get("state") or "")
        if state not in RUNTIME_INSTANCE_STATES:
            raise ValueError(f"unsupported runtime state: {state}")
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                instance = next(
                    (
                        row for row in data["runtime_instances"]
                        if row.get("id") == runtime_instance_id and row.get("product_id") == product_id
                    ),
                    None,
                )
                if not instance:
                    return None
                previous_state = str(instance.get("state") or "pending")
                previous_summary = str(instance.get("summary") or "")
                now = _now()
                metadata = copy.deepcopy(instance.get("metadata") or {})
                metadata["last_health"] = copy.deepcopy(observation.get("details") or {})
                instance.update({
                    "state": state,
                    "summary": str(observation.get("summary") or ""),
                    "metadata": metadata,
                    "last_observed_at": now,
                    "updated_at": now,
                })
                if previous_state != instance["state"] or previous_summary != instance["summary"]:
                    self._append_event(data, product_id, "runtime.health_synced", {
                        "runtime_instance_id": runtime_instance_id,
                        "previous_state": previous_state,
                        "state": instance["state"],
                        "summary": instance["summary"],
                    })
                self._save_unlocked(data)
                return copy.deepcopy(instance)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def delete_runtime_instance(self, product_id: str, runtime_instance_id: str) -> bool:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                before = len(data["runtime_instances"])
                data["runtime_instances"] = [
                    row for row in data["runtime_instances"]
                    if not (row.get("id") == runtime_instance_id and row.get("product_id") == product_id)
                ]
                if len(data["runtime_instances"]) == before:
                    return False
                self._append_event(data, product_id, "runtime.removed", {
                    "runtime_instance_id": runtime_instance_id,
                })
                self._save_unlocked(data)
                return True
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


product_registry_service = ProductRegistryService()
