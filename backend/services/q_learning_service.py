"""
Q-Learning 智能任务路由 — 核心服务层

实现 Q-Learning 算法用于任务推荐:
- recommend_agents(task) — 根据 Q-value 推荐最佳 Agent
- update_q_table(task_id, agent_id, outcome) — 根据结果更新 Q-value
- get_agent_stats(agent_id) — 获取 Agent 统计
- thompson_sampling(task_type) — 探索/利用平衡

算法:
Q(s, a) ← Q(s, a) + α × [r + γ × max_a' Q(s', a') - Q(s, a)]

状态提取:
- task_type → backend/frontend/infra/research/ops
- priority → high/medium/low
- tags → required_skills

奖励:
- success = +1
- fail = -1
- timeout = -0.5

@author: 拉斐尔 (🐢 后端开发)
@created: 2026-07-08
"""
from __future__ import annotations

import copy
import random
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models.v2_models import get_session
from models.q_learning_model import QTable


class QLearningService:
    """
    Q-Learning 智能任务路由服务。

    所有操作围绕单行 QTable 记录进行 JSON 列读写。
    """

    TASK_TYPE_MAP = {
        "backend": "backend_task",
        "frontend": "frontend_task",
        "infra": "infra_task",
        "research": "research_task",
        "ops": "ops_task",
    }

    PRIORITY_WEIGHT = {
        "high": 1.5,
        "medium": 1.0,
        "low": 0.7,
    }

    REWARD = {
        "success": 1.0,
        "fail": -1.0,
        "timeout": -0.5,
    }

    def __init__(self, db: Optional[Session] = None):
        self._db = db

    def _session(self, db: Optional[Session] = None) -> Session:
        """获取数据库会话。"""
        return db or self._db or get_session()

    def _get_record(self, session: Session) -> QTable:
        """获取或创建 Q-Table 单行记录。"""
        record = session.query(QTable).first()
        if record is None:
            record = QTable(
                state_action_values={},
                agent_stats={},
                meta={
                    "learning_rate": 0.1,
                    "discount_factor": 0.9,
                    "epsilon": 0.1,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
            )
            session.add(record)
            session.flush()
        return record

    def _flush(self, record: QTable) -> None:
        """持久化 Q-Table 记录。"""
        record.meta["last_updated"] = datetime.now(timezone.utc).isoformat()
        record.updated_at = datetime.now(timezone.utc)

    # ──────────────────────────────────────────────
    # 核心方法
    # ──────────────────────────────────────────────

    def _extract_state(self, task: Dict[str, Any]) -> str:
        """从任务信息中提取状态字符串。"""
        task_type = task.get("type", "general")
        prefix = self.TASK_TYPE_MAP.get(task_type, f"{task_type}_task")
        priority = task.get("priority", "medium")
        tags = task.get("tags", [])
        tag_str = ",".join(sorted(tags)) if tags else ""
        if tag_str:
            return f"{prefix}:{priority}:{tag_str}"
        return f"{prefix}:{priority}"

    def recommend_agents(
        self,
        task: Dict[str, Any],
        top_n: int = 3,
        use_exploration: bool = True,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        推荐 Agent 列表，按 Q-value 降序排列。
        """
        session = self._session(db)
        record = self._get_record(session)
        state = self._extract_state(task)
        q_values = record.state_action_values or {}
        agent_stats = record.agent_stats or {}
        meta = record.meta or {}
        epsilon = meta.get("epsilon", 0.1)

        known_agents = set(agent_stats.keys())

        default_agents = {"raphael", "donatello", "michelangelo", "leonardo"}
        for agent_id in default_agents:
            if agent_id not in known_agents:
                known_agents.add(agent_id)
                if agent_id not in agent_stats:
                    agent_stats[agent_id] = {
                        "success_count": 0,
                        "fail_count": 0,
                        "timeout_count": 0,
                        "total_cost": 0.0,
                    }

        scores = []
        for agent_id in known_agents:
            state_action_key = f"{state}:{agent_id}"
            q_value = q_values.get(state_action_key, 0.0)

            if use_exploration and random.random() < epsilon:
                stats = agent_stats.get(agent_id, {})
                alpha = max(stats.get("success_count", 0) + 1, 1)
                beta = max(stats.get("fail_count", 0) + stats.get("timeout_count", 0) + 1, 1)
                sampled = random.betavariate(alpha, beta)
                q_value = sampled * 0.5 + q_value * 0.5

            priority = task.get("priority", "medium")
            weight = self.PRIORITY_WEIGHT.get(priority, 1.0)
            final_score = round(q_value * weight, 4)

            agent_data = agent_stats.get(agent_id, {})
            total = (
                agent_data.get("success_count", 0)
                + agent_data.get("fail_count", 0)
                + agent_data.get("timeout_count", 0)
            )
            confidence = min(total / 10.0, 1.0)

            scores.append({
                "agent_id": agent_id,
                "score": final_score,
                "q_value": round(q_value, 4),
                "confidence": round(confidence, 2),
                "total_tasks": total,
            })

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_n]

    def update_q_table(
        self,
        task_id: str,
        agent_id: str,
        outcome: str,
        task_info: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        根据任务结果更新 Q-Table。
        """
        session = self._session(db)
        record = self._get_record(session)
        q_values = record.state_action_values or {}
        agent_stats = record.agent_stats or {}
        meta = record.meta or {}

        alpha = meta.get("learning_rate", 0.1)

        if task_info:
            state = self._extract_state(task_info)
        else:
            state = "general_task:medium"

        state_action_key = f"{state}:{agent_id}"
        current_q = q_values.get(state_action_key, 0.0)
        reward = self.REWARD.get(outcome, 0.0)

        if agent_id not in agent_stats:
            agent_stats[agent_id] = {
                "success_count": 0,
                "fail_count": 0,
                "timeout_count": 0,
                "total_cost": 0.0,
            }

        if outcome == "success":
            agent_stats[agent_id]["success_count"] += 1
        elif outcome == "fail":
            agent_stats[agent_id]["fail_count"] += 1
        elif outcome == "timeout":
            agent_stats[agent_id]["timeout_count"] += 1

        next_q = reward
        td_error = next_q - current_q
        new_q = round(current_q + alpha * td_error, 4)

        q_values[state_action_key] = new_q
        record.state_action_values = copy.deepcopy(q_values)
        record.agent_stats = copy.deepcopy(agent_stats)
        record.meta = copy.deepcopy(meta)

        self._flush(record)
        # Mark JSON columns as modified so SQLAlchemy tracks the change
        flag_modified(record, 'state_action_values')
        flag_modified(record, 'agent_stats')
        flag_modified(record, 'meta')
        session.commit()

        return {
            "state_action_key": state_action_key,
            "old_q": round(current_q, 4),
            "new_q": new_q,
            "reward": reward,
            "agent_stats": agent_stats[agent_id],
        }

    def get_agent_stats(
        self, agent_id: str, db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """获取单个 Agent 的统计数据。"""
        session = self._session(db)
        record = self._get_record(session)
        agent_stats = record.agent_stats or {}
        stats = dict(agent_stats.get(agent_id, {
            "success_count": 0,
            "fail_count": 0,
            "timeout_count": 0,
            "total_cost": 0.0,
        }))
        total = (
            stats["success_count"]
            + stats["fail_count"]
            + stats["timeout_count"]
        )
        stats["total_count"] = total
        stats["success_rate"] = (
            round(stats["success_count"] / max(total, 1), 4)
            if total > 0
            else 0.0
        )
        return stats

    def get_all_agent_stats(
        self, db: Optional[Session] = None
    ) -> Dict[str, Dict[str, Any]]:
        """获取所有 Agent 的统计数据。"""
        session = self._session(db)
        record = self._get_record(session)
        agent_stats = record.agent_stats or {}
        result = {}
        for aid, stats in agent_stats.items():
            total = (
                stats.get("success_count", 0)
                + stats.get("fail_count", 0)
                + stats.get("timeout_count", 0)
            )
            result[aid] = {
                **stats,
                "total_count": total,
                "success_rate": round(
                    stats.get("success_count", 0) / max(total, 1), 4
                ) if total > 0 else 0.0,
            }
        return result

    def get_q_table(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """获取完整 Q-Table。"""
        session = self._session(db)
        record = self._get_record(session)
        return record.to_dict()

    def update_parameters(
        self,
        learning_rate: Optional[float] = None,
        discount_factor: Optional[float] = None,
        epsilon: Optional[float] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """更新 Q-Learning 超参数。"""
        session = self._session(db)
        record = self._get_record(session)
        meta = record.meta or {}

        if learning_rate is not None:
            meta["learning_rate"] = max(0.0, min(1.0, learning_rate))
        if discount_factor is not None:
            meta["discount_factor"] = max(0.0, min(1.0, discount_factor))
        if epsilon is not None:
            meta["epsilon"] = max(0.0, min(1.0, epsilon))

        record.meta = copy.deepcopy(meta)
        self._flush(record)
        flag_modified(record, 'meta')
        session.commit()
        return meta

    def thompson_sampling(
        self, task_type: str, db: Optional[Session] = None
    ) -> Dict[str, float]:
        """
        Thompson Sampling 探索机制。
        对每个 Agent 从 Beta(α, β) 采样。
        """
        session = self._session(db)
        record = self._get_record(session)
        agent_stats = record.agent_stats or {}

        samples = {}
        for agent_id, stats in agent_stats.items():
            alpha = max(stats.get("success_count", 0) + 1, 1)
            beta_val = max(
                stats.get("fail_count", 0) + stats.get("timeout_count", 0) + 1,
                1,
            )
            samples[agent_id] = round(random.betavariate(alpha, beta_val), 4)

        default_agents = {"raphael", "donatello", "michelangelo", "leonardo"}
        for agent_id in default_agents:
            if agent_id not in samples:
                samples[agent_id] = round(random.betavariate(1, 1), 4)

        return samples

    def get_state_action_value(
        self, state: str, agent_id: str, db: Optional[Session] = None
    ) -> float:
        """获取指定 state-action 的 Q 值。"""
        session = self._session(db)
        record = self._get_record(session)
        q_values = record.state_action_values or {}
        key = f"{state}:{agent_id}"
        return q_values.get(key, 0.0)
