"""File-backed product registry for reusable systems and company offerings."""

from __future__ import annotations

import copy
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import data_path


PRODUCT_REGISTRY_FILE = data_path("product-registry.json")


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
    def __init__(self, file_path: str = PRODUCT_REGISTRY_FILE):
        self.file_path = file_path

    def _lock_path(self) -> str:
        return self.file_path + ".lock"

    def _default(self) -> dict[str, Any]:
        return {
            "schema": "openclaw.product-registry",
            "version": 1,
            "updated_at": _now(),
            "products": _seed_products(),
        }

    def _load_unlocked(self) -> dict[str, Any]:
        if not os.path.exists(self.file_path):
            return self._default()
        with open(self.file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("schema", "openclaw.product-registry")
        data.setdefault("version", 1)
        data.setdefault("products", [])
        return data

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _now()
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def get_registry(self) -> dict[str, Any]:
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path(), "w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load_unlocked()
                if not os.path.exists(self.file_path):
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


product_registry_service = ProductRegistryService()
