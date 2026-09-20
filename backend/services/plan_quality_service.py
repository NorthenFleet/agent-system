"""Plan quality gates for command-center missions.

This service keeps the first quality loop deliberately local and deterministic:
LLMs may propose a plan, but the command center enriches it with explicit
deliverables/evidence and blocks structurally unsafe plans before approval.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.agent_capability_registry import agent_capability_registry
from services.business_flow_service import business_flow_registry


VALID_AGENTS = set(agent_capability_registry.agent_ids())
TASK_TYPE_DEFAULTS = agent_capability_registry.catalog()["task_type_defaults"]



class PlanQualityService:
    """Enrich and evaluate mission plans before they are exposed for approval."""

    def enrich_plan(self, plan: dict[str, Any], mission: dict[str, Any] | None = None) -> dict[str, Any]:
        enriched = deepcopy(plan)
        enriched["schema_version"] = str(enriched.get("schema_version") or "2.0")
        steps = enriched.get("steps") if isinstance(enriched.get("steps"), list) else []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            task_type = str(step.get("task_type") or "general").strip().lower()
            defaults = agent_capability_registry.step_defaults(task_type)
            step.setdefault("order_index", index)
            self._ensure_list_field(step, "required_tools", defaults["required_tools"])
            self._ensure_list_field(step, "deliverables", defaults["deliverables"])
            self._ensure_list_field(step, "acceptance_criteria", defaults["acceptance_criteria"])
            self._ensure_list_field(step, "evidence_required", defaults["evidence_required"])
            step["tool_requirements"] = agent_capability_registry.describe_tools(step.get("required_tools") or [])
            step["capability_match"] = agent_capability_registry.agent_supports_task(
                str(step.get("agent_id") or ""),
                task_type,
            )
            step.setdefault("risk_level", str(enriched.get("risk_level") or "medium"))
            if "rollback_plan" not in step:
                step["rollback_plan"] = self._default_rollback(task_type)
        enriched = business_flow_registry.enrich_plan(enriched, mission=mission)
        enriched["capability_registry"] = {
            "version": "p1-local",
            "agent_count": len(agent_capability_registry.agent_ids()),
            "tool_count": len(agent_capability_registry.catalog()["tools"]),
        }
        enriched["plan_quality"] = self.evaluate(enriched, mission=mission)
        return enriched

    def evaluate(self, plan: dict[str, Any], mission: dict[str, Any] | None = None) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        mission_context = self._mission_context(mission)
        mission_type = str(self._mission_value(mission, "mission_type") or mission_context.get("mission_type") or "")
        tool_summary = {"total": 0, "unknown": 0, "unavailable": 0}
        flow_validation = plan.get("flow_validation") if isinstance(plan.get("flow_validation"), dict) else {}
        blockers.extend(str(item) for item in flow_validation.get("blockers") or [])
        warnings.extend(str(item) for item in flow_validation.get("warnings") or [])

        if not steps:
            blockers.append("计划必须包含至少一个执行步骤")
        if len(steps) > 12:
            blockers.append("计划步骤不能超过 12 个")

        seen_order_indexes: set[int] = set()
        task_types: set[str] = set()
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                blockers.append(f"第 {index} 步不是有效对象")
                continue
            title = str(step.get("title") or "").strip()
            task_type = str(step.get("task_type") or "general").strip().lower()
            agent_id = str(step.get("agent_id") or "").strip()
            task_types.add(task_type)
            if not title:
                warnings.append(f"第 {index} 步缺少标题")
            if not agent_capability_registry.known_agent(agent_id):
                blockers.append(f"第 {index} 步分配给未知智能体：{agent_id or '空'}")
            elif not agent_capability_registry.agent_supports_task(agent_id, task_type):
                warnings.append(f"第 {index} 步的类型 {task_type} 与智能体 {agent_id} 能力不完全匹配")
            order_index = self._int_value(step.get("order_index"), index)
            if order_index in seen_order_indexes:
                blockers.append(f"第 {index} 步 order_index 重复：{order_index}")
            seen_order_indexes.add(order_index)
            for dependency in step.get("depends_on") or []:
                dependency_index = self._int_value(dependency, -1)
                if dependency_index <= 0 or dependency_index >= order_index:
                    blockers.append(f"第 {index} 步依赖必须指向前序步骤：{dependency}")
            self._require_list_field(step, "required_tools", index, warnings)
            self._require_list_field(step, "deliverables", index, warnings)
            self._require_list_field(step, "acceptance_criteria", index, warnings)
            self._require_list_field(step, "evidence_required", index, warnings)
            for tool in agent_capability_registry.describe_tools(step.get("required_tools") or []):
                tool_summary["total"] += 1
                status = str(tool.get("status") or "unknown")
                tool_id = str(tool.get("id") or "")
                if status == "unknown":
                    tool_summary["unknown"] += 1
                    blockers.append(f"第 {index} 步要求未注册工具：{tool_id}")
                elif status not in {"available", "manual"}:
                    tool_summary["unavailable"] += 1
                    warnings.append(f"第 {index} 步工具不可用或待接入：{tool_id}")

        if mission_type == "software" or self._looks_like_software(mission):
            missing = {"architecture", "testing"} - task_types
            if missing:
                warnings.append("软件任务必须包含架构与测试/评估步骤")
            if not ({"backend", "frontend", "api", "database", "ui"} & task_types):
                warnings.append("软件任务建议至少包含后端或前端实现步骤")
        if mission_type == "document" or self._looks_like_document(mission):
            missing = {"research", "writing", "review"} - task_types
            if missing:
                warnings.append("文档任务必须包含资料、撰写和审校步骤")

        score = max(0, 100 - len(blockers) * 35 - len(warnings) * 8)
        status = "blocked" if blockers else "warning" if warnings else "pass"
        if not suggestions and warnings:
            suggestions.append("补齐每一步的工具、产物、验收标准和证据字段后再审批")
        if tool_summary["unknown"] or tool_summary["unavailable"]:
            suggestions.append("请在工具注册表中补齐工具状态，或调整步骤所需工具")
        return {
            "status": status,
            "score": score,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "suggestions": suggestions,
            "tool_summary": tool_summary,
            "flow_key": str(flow_validation.get("flow_key") or "general"),
            "flow_version": str(flow_validation.get("flow_version") or "1.0.0"),
            "risk_assessment": deepcopy(plan.get("risk_assessment") or {}),
            "checked_rules": [
                "schema",
                "business-flow",
                "risk-policy",
                "idempotency",
                "compensation",
                "agent-capability",
                "tool-registry",
                "dependency-dag",
                "deliverables",
                "acceptance",
                "evidence",
                "domain-coverage",
            ],
        }

    @staticmethod
    def _default_rollback(task_type: str) -> str:
        if task_type in {"backend", "frontend", "testing", "architecture"}:
            return "保留变更证据；如验证失败，停止合并并退回上一可用版本。"
        if task_type in {"writing", "research", "knowledge"}:
            return "保留草稿与引用记录；如审校失败，退回上一版并标注待补充项。"
        if task_type == "finance":
            return "不得入账；保留凭证并退回人工复核。"
        return "停止后续步骤，记录失败原因并等待擎天柱重新规划。"

    @staticmethod
    def _ensure_list_field(step: dict[str, Any], field: str, default: list[str]) -> None:
        value = step.get(field)
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            if normalized:
                step[field] = normalized
                return
        step[field] = list(default)

    @staticmethod
    def _require_list_field(step: dict[str, Any], field: str, index: int, warnings: list[str]) -> None:
        value = step.get(field)
        if not isinstance(value, list) or not any(str(item).strip() for item in value):
            warnings.append(f"第 {index} 步缺少 {field}")

    @staticmethod
    def _int_value(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _looks_like_software(mission: dict[str, Any] | None) -> bool:
        text = str(PlanQualityService._mission_value(mission, "objective") or "").lower()
        return any(marker in text for marker in ("开发", "代码", "接口", "api", "前端", "后端", "数据库", "bug"))

    @staticmethod
    def _looks_like_document(mission: dict[str, Any] | None) -> bool:
        text = str(PlanQualityService._mission_value(mission, "objective") or "")
        return any(marker in text for marker in ("论文", "文档", "报告", "文章", "章节", "专利", "教材", "课程", "课件"))

    @staticmethod
    def _mission_value(mission: Any, key: str) -> Any:
        if not mission:
            return None
        if isinstance(mission, dict):
            return mission.get(key)
        try:
            return mission[key]
        except (KeyError, IndexError, TypeError):
            return None

    @staticmethod
    def _mission_context(mission: Any) -> dict[str, Any]:
        value = PlanQualityService._mission_value(mission, "context")
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                import json

                parsed = json.loads(value)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}


plan_quality_service = PlanQualityService()
