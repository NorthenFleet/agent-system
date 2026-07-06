"""
Q-Learning 智能任务路由服务

基于 Q-Table 的 Agent 推荐引擎，结合 Thompson Sampling 实现智能任务分配。

@author 🟥 拉斐尔
"""
import os
import json
import math
import random
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

Q_TABLE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "q-table.json")

# Default Q-Table 预设值（基于当前已知分工）
DEFAULT_Q_TABLE = {
    "backend_task": {"raphael": 0.7, "donatello": 0.3},
    "frontend_task": {"donatello": 0.8, "michelangelo": 0.5},
    "infra_task": {"wheeljack": 0.9},
    "research_task": {"shockwave": 0.8},
    "ops_task": {"bumblebee": 0.7},
}


class QLearningService:
    """
    Q-Learning 核心服务

    Q-Table 存储在 JSON 文件中，支持读写、更新和 Thompson Sampling 选择。
    """

    def __init__(
        self,
        learning_rate: float = 0.1,
        discount_factor: float = 0.9,
        epsilon: float = 0.1,
        q_table_path: Optional[str] = None,
    ):
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.q_table_path = q_table_path or Q_TABLE_PATH
        self._q_table: Dict[str, Dict[str, float]] = {}
        self._load_or_init()

    # ─── 文件操作 ───

    def _load_or_init(self) -> None:
        """加载已有 Q-Table，不存在则用默认值初始化。"""
        if os.path.exists(self.q_table_path):
            try:
                with open(self.q_table_path, "r", encoding="utf-8") as f:
                    self._q_table = json.load(f)
                logger.info(f"Q-Table 加载成功，共 {len(self._q_table)} 个任务类型")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Q-Table 加载失败，使用默认值: {e}")
                self._q_table = dict(DEFAULT_Q_TABLE)
                self._save()
        else:
            self._q_table = dict(DEFAULT_Q_TABLE)
            self._save()

    def _save(self) -> None:
        """持久化 Q-Table 到 JSON 文件。"""
        try:
            os.makedirs(os.path.dirname(self.q_table_path), exist_ok=True)
            with open(self.q_table_path, "w", encoding="utf-8") as f:
                json.dump(self._q_table, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Q-Table 保存失败: {e}")

    # ─── 公开 API ───

    def set_initial_q_table(self, initial_data: Dict[str, Dict[str, float]]) -> None:
        """手动设定初始 Q 值，覆盖现有 Q-Table。"""
        self._q_table = {
            task_type: {agent: float(score) for agent, score in agents.items()}
            for task_type, agents in initial_data.items()
        }
        self._save()
        logger.info(f"Q-Table 已手动设定，共 {len(self._q_table)} 个任务类型")

    def get_q_table(self) -> Dict[str, Dict[str, float]]:
        """返回完整 Q-Table。"""
        return dict(self._q_table)

    def get_recommendation(
        self,
        task_type: str,
        priority: str = "medium",
        tags: Optional[List[str]] = None,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        根据任务特征返回推荐 Agent 列表（含评分和 Q 值）。

        结合 Q-Table 查分 + ε-贪心策略 + Thompson Sampling 进行推荐。
        """
        agent_scores = self._get_scores_for_task_type(task_type)

        if not agent_scores:
            # 回退：返回默认列表
            return []

        # 根据优先级做简单加权
        priority_weight = {"high": 1.3, "medium": 1.0, "low": 0.8}.get(priority, 1.0)

        # 根据 tags 做微调（如果有匹配的 tag-agent 关联）
        tag_adjustments: Dict[str, float] = {}
        if tags:
            tag_adjustments = self._tag_adjustments(tags)

        results = []
        for agent_id, base_q in agent_scores.items():
            adjusted_q = base_q * priority_weight + tag_adjustments.get(agent_id, 0.0)
            adjusted_q = max(0.0, min(1.0, adjusted_q))

            results.append({
                "agent_id": agent_id,
                "q_value": round(adjusted_q, 4),
                "base_q_value": round(base_q, 4),
                "score": round(adjusted_q * 100, 2),
            })

        # Thompson Sampling 选择
        selected = self.thompson_sampling(agent_scores)

        # 排序：TS 选中的置顶，其余按 score 降序
        results.sort(key=lambda x: x["score"], reverse=True)
        for r in results:
            if r["agent_id"] == selected:
                r["thompson_selected"] = True
            else:
                r["thompson_selected"] = False

        return results[:top_k]

    def update_after_completion(
        self,
        task_id: str,
        agent_id: str,
        outcome: str,
        task_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        根据任务结果更新 Q-Table。

        outcome:
            success: Q += learning_rate * (1 - Q)
            fail:    Q += learning_rate * (0 - Q)
            timeout: Q += learning_rate * (-0.5 - Q)
        """
        if outcome not in ("success", "fail", "timeout"):
            raise ValueError(f"不支持的 outcome: {outcome}")

        # 推断 task_type
        if not task_type:
            task_type = self._infer_task_type(task_id)

        if task_type not in self._q_table:
            self._q_table[task_type] = {}

        current_q = self._q_table[task_type].get(agent_id, 0.5)

        reward_map = {
            "success": 1.0,
            "fail": 0.0,
            "timeout": -0.5,
        }
        reward = reward_map[outcome]
        new_q = current_q + self.learning_rate * (reward - current_q)
        new_q = max(-1.0, min(1.0, new_q))

        self._q_table[task_type][agent_id] = round(new_q, 4)
        self._save()

        return {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_type": task_type,
            "outcome": outcome,
            "old_q": round(current_q, 4),
            "new_q": round(new_q, 4),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def thompson_sampling(self, agent_scores: Dict[str, float]) -> Optional[str]:
        """
        用 Beta 分布做 Thompson Sampling 选择 Agent。

        将 Q 值映射为 Beta(α, β) 参数，采样后取最大值的 Agent。
        """
        if not agent_scores:
            return None

        samples: Dict[str, float] = {}
        for agent_id, q in agent_scores.items():
            # 将 Q 值映射到 Beta 分布参数
            # q ∈ [0,1] → α = 1 + q*10, β = 1 + (1-q)*10
            alpha = 1.0 + max(0.0, min(1.0, q)) * 10.0
            beta_param = 1.0 + max(0.0, min(1.0, 1.0 - q)) * 10.0
            samples[agent_id] = random.betavariate(alpha, beta_param)

        # 选择采样值最大的 Agent
        return max(samples, key=samples.get)

    # ─── 内部方法 ───

    def _get_scores_for_task_type(self, task_type: str) -> Dict[str, float]:
        """获取某个任务类型下所有 Agent 的 Q 值。"""
        agents = self._q_table.get(task_type, {})
        # 如果没有完全匹配，尝试模糊匹配
        if not agents:
            for key in self._q_table:
                if task_type.lower() in key.lower() or key.lower() in task_type.lower():
                    agents = self._q_table.get(key, {})
                    break
        return dict(agents)

    def _infer_task_type(self, task_id: str) -> str:
        """根据 task_id 推断任务类型（简单策略，可被覆盖）。"""
        return f"inferred_{task_id}"

    def _tag_adjustments(self, tags: List[str]) -> Dict[str, float]:
        """根据 tags 对 Agent Q 值做微调。"""
        # 预设 tag → agent 关联权重
        tag_agent_map = {
            "fastapi": {"raphael": 0.05},
            "react": {"donatello": 0.05},
            "vue": {"michelangelo": 0.05},
            "k8s": {"wheeljack": 0.05},
            "ml": {"shockwave": 0.05},
            "monitoring": {"bumblebee": 0.05},
        }
        adjustments: Dict[str, float] = {}
        for tag in tags:
            tag_lower = tag.lower()
            for t_key, agent_weights in tag_agent_map.items():
                if t_key in tag_lower or tag_lower in t_key:
                    for agent_id, weight in agent_weights.items():
                        adjustments[agent_id] = adjustments.get(agent_id, 0.0) + weight
        return adjustments
