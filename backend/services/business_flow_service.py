"""Versioned business-flow contracts for command-center missions.

Phase one deliberately keeps the runtime unchanged.  This module defines the
stable contract that planners and the existing command-center executor must
honour: domain templates, lifecycle metadata, risk policy, execution budgets,
and deterministic validation.  A later workflow runtime (for example
LangGraph) can consume the same contract without becoming the business source
of truth.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


MISSION_LIFECYCLE = {
    "received": ["planning", "cancelled"],
    "planning": ["awaiting_approval", "waiting_feedback", "failed", "cancelled"],
    "awaiting_approval": ["dispatching", "planning", "cancelled"],
    "dispatching": ["running", "waiting_feedback", "cancelled"],
    "running": ["waiting_feedback", "evaluating", "cancelled"],
    "waiting_feedback": ["planning", "dispatching", "running", "cancelled"],
    "evaluating": ["completed", "waiting_feedback", "failed", "cancelled"],
    "completed": [],
    "failed": ["planning", "cancelled"],
    "cancelled": [],
}

STEP_LIFECYCLE = {
    "draft": ["ready", "cancelled"],
    "ready": ["awaiting_approval", "running", "cancelled"],
    "awaiting_approval": ["ready", "failed", "cancelled"],
    "running": ["completed", "failed", "ready", "cancelled"],
    "completed": [],
    "failed": ["ready", "cancelled"],
    "cancelled": [],
}

RISK_LEVELS: dict[str, dict[str, Any]] = {
    "L0": {
        "name": "只读分析",
        "legacy_level": "low",
        "step_approval": False,
        "max_attempts": 3,
        "description": "不改变业务或外部系统状态。",
    },
    "L1": {
        "name": "可逆内部变更",
        "legacy_level": "low",
        "step_approval": False,
        "max_attempts": 2,
        "description": "受控的内部写入，可验证且可回滚。",
    },
    "L2": {
        "name": "重要业务变更",
        "legacy_level": "medium",
        "step_approval": False,
        "max_attempts": 2,
        "description": "影响重要数据或运行状态，必须有证据和补偿路径。",
    },
    "L3": {
        "name": "不可逆或外部动作",
        "legacy_level": "high",
        "step_approval": True,
        "max_attempts": 1,
        "description": "付款、删除、生产发布、外部发送或权限变更。",
    },
}

CONTRACT_SCHEMAS: dict[str, dict[str, Any]] = {
    "flow": {
        "required": [
            "flow_key",
            "version",
            "business_type",
            "phases",
            "required_gates",
            "budgets",
            "approval_policy",
        ],
        "identity": ["flow_key", "version"],
    },
    "step": {
        "required": [
            "order_index",
            "title",
            "objective",
            "phase",
            "task_type",
            "agent_id",
            "depends_on",
            "output_contract",
            "acceptance_criteria",
            "evidence_required",
            "risk_class",
            "timeout_seconds",
            "max_attempts",
            "idempotency_key",
            "rollback_plan",
        ],
        "identity": ["mission_id", "plan_version", "order_index"],
    },
    "artifact": {
        "required": ["artifact_type", "title", "uri", "content_hash", "produced_by_step_id"],
        "optional": ["media_type", "size", "version", "metadata"],
        "immutable_fields": ["content_hash", "produced_by_step_id"],
    },
    "evidence": {
        "required": ["evidence_type", "source_ref", "summary", "collected_by", "collected_at"],
        "optional": ["artifact_id", "confidence", "metadata"],
        "accepted_types": [
            "context_pack",
            "citations",
            "diff_summary",
            "test_output",
            "build_output",
            "review_report",
            "document_diff",
            "finance_evidence",
            "ops_log",
            "result_summary",
        ],
    },
    "approval": {
        "required": ["scope", "subject_ref", "decision", "decided_by", "decided_at"],
        "decision_values": ["pending", "approved", "rejected", "cancelled"],
        "scope_values": ["plan", "step", "delivery"],
    },
}

TASK_PHASES = {
    "architecture": "planning",
    "coordination": "planning",
    "research": "research",
    "knowledge": "research",
    "backend": "implementation",
    "api": "implementation",
    "database": "implementation",
    "frontend": "implementation",
    "ui": "implementation",
    "writing": "production",
    "document": "production",
    "finance": "processing",
    "operations": "operation",
    "sales": "operation",
    "testing": "verification",
    "review": "verification",
    "general": "execution",
}

SIDE_EFFECT_TASK_TYPES = {
    "backend",
    "api",
    "database",
    "frontend",
    "ui",
    "finance",
    "operations",
    "sales",
}

L3_MARKERS = (
    "付款",
    "转账",
    "入账",
    "冲销",
    "报销",
    "生产发布",
    "上线发布",
    "删除数据",
    "销毁",
    "外部发送",
    "公开发布",
    "权限变更",
    "payment",
    "transfer",
    "production deploy",
    "delete production",
)

FLOW_SPECS: dict[str, dict[str, Any]] = {
    "general": {
        "flow_key": "general",
        "version": "1.0.0",
        "business_type": "general",
        "name": "通用业务执行流",
        "phases": ["intake", "planning", "execution", "verification", "delivery"],
        "required_task_groups": [],
        "required_gates": ["plan_quality", "plan_approval", "evidence_gate"],
        "budgets": {"max_steps": 12, "max_parallel_steps": 4, "max_replans": 2, "default_timeout_seconds": 900},
        "approval_policy": {"plan_approval": True, "delivery_approval": False, "l3_step_approval": True},
    },
    "software": {
        "flow_key": "software",
        "version": "1.0.0",
        "business_type": "software",
        "name": "软件开发交付流",
        "phases": ["intake", "planning", "implementation", "verification", "delivery"],
        "required_task_groups": [
            {"name": "架构设计", "any_of": ["architecture"]},
            {"name": "实现", "any_of": ["backend", "api", "database", "frontend", "ui"]},
            {"name": "测试验证", "any_of": ["testing", "review"]},
        ],
        "required_gates": ["plan_quality", "plan_approval", "test_gate", "evidence_gate"],
        "budgets": {"max_steps": 12, "max_parallel_steps": 4, "max_replans": 2, "default_timeout_seconds": 1200},
        "approval_policy": {"plan_approval": True, "delivery_approval": False, "l3_step_approval": True},
    },
    "document": {
        "flow_key": "document",
        "version": "1.0.0",
        "business_type": "document",
        "name": "文档生产交付流",
        "phases": ["intake", "planning", "research", "production", "verification", "delivery"],
        "required_task_groups": [
            {"name": "资料与证据", "any_of": ["research", "knowledge"]},
            {"name": "内容生产", "any_of": ["writing", "document"]},
            {"name": "审校", "any_of": ["review"]},
        ],
        "required_gates": ["plan_quality", "plan_approval", "citation_gate", "evidence_gate"],
        "budgets": {"max_steps": 12, "max_parallel_steps": 3, "max_replans": 2, "default_timeout_seconds": 1200},
        "approval_policy": {"plan_approval": True, "delivery_approval": True, "l3_step_approval": True},
    },
    "finance": {
        "flow_key": "finance",
        "version": "1.0.0",
        "business_type": "finance",
        "name": "财务处理流",
        "phases": ["intake", "validation", "processing", "verification", "approval", "delivery"],
        "required_task_groups": [
            {"name": "财务处理", "any_of": ["finance"]},
            {"name": "独立复核", "any_of": ["review"]},
        ],
        "required_gates": ["plan_quality", "plan_approval", "finance_review", "human_approval", "evidence_gate"],
        "budgets": {"max_steps": 10, "max_parallel_steps": 2, "max_replans": 1, "default_timeout_seconds": 900},
        "approval_policy": {"plan_approval": True, "delivery_approval": True, "l3_step_approval": True},
    },
    "research": {
        "flow_key": "research",
        "version": "1.0.0",
        "business_type": "research",
        "name": "情报研究流",
        "phases": ["intake", "planning", "research", "verification", "delivery"],
        "required_task_groups": [
            {"name": "资料检索", "any_of": ["research", "knowledge"]},
            {"name": "交叉验证", "any_of": ["review"]},
        ],
        "required_gates": ["plan_quality", "plan_approval", "source_gate", "evidence_gate"],
        "budgets": {"max_steps": 12, "max_parallel_steps": 4, "max_replans": 2, "default_timeout_seconds": 900},
        "approval_policy": {"plan_approval": True, "delivery_approval": False, "l3_step_approval": True},
    },
    "operations": {
        "flow_key": "operations",
        "version": "1.0.0",
        "business_type": "operations",
        "name": "运维操作流",
        "phases": ["intake", "planning", "operation", "verification", "delivery"],
        "required_task_groups": [
            {"name": "运维执行", "any_of": ["operations"]},
            {"name": "状态验证", "any_of": ["testing", "review"]},
        ],
        "required_gates": ["plan_quality", "plan_approval", "ops_check", "evidence_gate"],
        "budgets": {"max_steps": 10, "max_parallel_steps": 2, "max_replans": 1, "default_timeout_seconds": 900},
        "approval_policy": {"plan_approval": True, "delivery_approval": False, "l3_step_approval": True},
    },
}


class BusinessFlowRegistry:
    """Resolve, bind and validate a versioned business-flow contract."""

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "flows": [deepcopy(spec) for _, spec in sorted(FLOW_SPECS.items())],
            "risk_levels": deepcopy(RISK_LEVELS),
            "contracts": deepcopy(CONTRACT_SCHEMAS),
            "state_machines": {
                "mission": deepcopy(MISSION_LIFECYCLE),
                "step": deepcopy(STEP_LIFECYCLE),
            },
        }

    def resolve(self, mission: Any = None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        context = self._mission_context(mission)
        user_context = context.get("user_context") if isinstance(context.get("user_context"), dict) else {}
        requested = str(
            context.get("business_flow_key")
            or user_context.get("business_flow_key")
            or self._mission_value(mission, "mission_type")
            or context.get("mission_type")
            or (plan or {}).get("business_type")
            or (plan or {}).get("flow_key")
            or ""
        ).strip().lower()
        aliases = {
            "software_project": "software",
            "development": "software",
            "writing": "document",
            "paper": "document",
            "finance_operation": "finance",
            "financial": "finance",
            "intelligence": "research",
            "ops": "operations",
        }
        requested = aliases.get(requested, requested)
        if requested not in FLOW_SPECS:
            requested = self._infer_type(str(self._mission_value(mission, "objective") or ""))
        return deepcopy(FLOW_SPECS.get(requested, FLOW_SPECS["general"]))

    def enrich_plan(self, plan: dict[str, Any], mission: Any = None) -> dict[str, Any]:
        enriched = deepcopy(plan)
        spec = self.resolve(mission, enriched)
        mission_id = str(self._mission_value(mission, "id") or "mission")
        plan_version = self._int_value(self._mission_value(mission, "plan_version"), 0) + 1
        default_timeout = self._int_value(spec["budgets"].get("default_timeout_seconds"), 900)

        for index, step in enumerate(enriched.get("steps") or [], start=1):
            if not isinstance(step, dict):
                continue
            task_type = str(step.get("task_type") or "general").strip().lower()
            step["phase"] = str(step.get("phase") or TASK_PHASES.get(task_type, "execution"))
            step["objective"] = str(
                step.get("objective") or step.get("description") or step.get("title") or f"步骤 {index}"
            )[:1000]
            step["output_contract"] = self._output_contract(step)
            step["timeout_seconds"] = self._bounded_int(
                step.get("timeout_seconds"), default_timeout, 30, 7200
            )
            risk_class = self._step_risk(step, spec)
            step["risk_class"] = risk_class
            step["risk_level"] = RISK_LEVELS[risk_class]["legacy_level"]
            step["approval_required"] = bool(
                step.get("approval_required") or RISK_LEVELS[risk_class]["step_approval"]
            )
            step["max_attempts"] = self._bounded_int(
                step.get("max_attempts"), RISK_LEVELS[risk_class]["max_attempts"], 1, 5
            )
            step["resources"] = self._string_list(step.get("resources"), limit=12)
            step["side_effect"] = bool(step.get("side_effect") or task_type in SIDE_EFFECT_TASK_TYPES)
            current_idempotency_key = str(step.get("idempotency_key") or "").strip()
            generated_idempotency_key = bool(step.get("idempotency_key_generated"))
            if not current_idempotency_key or generated_idempotency_key:
                step["idempotency_key"] = f"{mission_id}:plan:{plan_version}:step:{index}"[:240]
                step["idempotency_key_generated"] = True
            else:
                step["idempotency_key"] = current_idempotency_key[:240]
                step["idempotency_key_generated"] = False
            rollback_plan = str(step.get("rollback_plan") or self._default_rollback(task_type)).strip()
            step["rollback_plan"] = rollback_plan[:1000]
            step["compensation"] = self._compensation(step.get("compensation"), rollback_plan)

        risk = self.assess_risk(enriched, spec)
        enriched["business_type"] = spec["business_type"]
        enriched["flow_spec"] = {
            "flow_key": spec["flow_key"],
            "version": spec["version"],
            "name": spec["name"],
            "business_type": spec["business_type"],
            "phases": deepcopy(spec["phases"]),
            "required_gates": deepcopy(spec["required_gates"]),
            "budgets": deepcopy(spec["budgets"]),
            "approval_policy": deepcopy(spec["approval_policy"]),
        }
        enriched["risk_assessment"] = risk
        enriched["approval_policy"] = {
            **deepcopy(spec["approval_policy"]),
            "highest_risk": risk["highest_risk"],
            "step_approvals": risk["step_approvals"],
        }
        enriched["execution_policy"] = {
            "runtime": "command-center",
            "state_machine": "mission-v1",
            "require_context_snapshot": True,
            "require_evidence": True,
            "idempotency_required_for_side_effects": True,
        }
        enriched["flow_validation"] = self.evaluate(enriched, spec)
        return enriched

    def evaluate(self, plan: dict[str, Any], spec: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = deepcopy(spec or self.resolve(None, plan))
        blockers: list[str] = []
        warnings: list[str] = []
        steps = [step for step in (plan.get("steps") or []) if isinstance(step, dict)]
        budgets = resolved.get("budgets") or {}
        max_steps = self._int_value(budgets.get("max_steps"), 12)
        if len(steps) > max_steps:
            blockers.append(f"流程 {resolved['flow_key']} 最多允许 {max_steps} 个步骤")

        task_types = {str(step.get("task_type") or "general").lower() for step in steps}
        missing_groups = []
        for group in resolved.get("required_task_groups") or []:
            allowed = {str(item) for item in group.get("any_of") or []}
            if allowed and not allowed.intersection(task_types):
                missing_groups.append(str(group.get("name") or "/".join(sorted(allowed))))
        if missing_groups:
            warnings.append("领域流程缺少必要环节：" + "、".join(missing_groups))

        for index, step in enumerate(steps, start=1):
            risk_class = str(step.get("risk_class") or "")
            if risk_class not in RISK_LEVELS:
                blockers.append(f"第 {index} 步风险等级无效：{risk_class or '空'}")
                continue
            if step.get("side_effect") and not str(step.get("idempotency_key") or "").strip():
                blockers.append(f"第 {index} 步有外部或内部写入，但缺少幂等键")
            if risk_class in {"L2", "L3"}:
                if not str(step.get("rollback_plan") or "").strip():
                    blockers.append(f"第 {index} 步为 {risk_class}，但缺少回滚或补偿方案")
                if not step.get("evidence_required"):
                    blockers.append(f"第 {index} 步为 {risk_class}，但缺少证据要求")
            if risk_class == "L3" and not step.get("approval_required"):
                blockers.append(f"第 {index} 步为 L3，但未配置独立审批")

        warnings.extend(self._resource_conflicts(steps))
        return {
            "status": "blocked" if blockers else "warning" if warnings else "pass",
            "flow_key": resolved["flow_key"],
            "flow_version": resolved["version"],
            "blockers": blockers,
            "warnings": warnings,
            "checked_rules": [
                "flow-budget",
                "domain-coverage",
                "risk-class",
                "approval-policy",
                "idempotency",
                "compensation",
                "resource-conflict",
            ],
        }

    def assess_risk(self, plan: dict[str, Any], spec: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = spec or self.resolve(None, plan)
        steps = [step for step in (plan.get("steps") or []) if isinstance(step, dict)]
        ranks = {name: index for index, name in enumerate(RISK_LEVELS)}
        highest = "L0"
        step_approvals: list[int] = []
        by_level = {level: 0 for level in RISK_LEVELS}
        for index, step in enumerate(steps, start=1):
            level = str(step.get("risk_class") or self._step_risk(step, resolved))
            if level not in RISK_LEVELS:
                level = "L1"
            by_level[level] += 1
            if ranks[level] > ranks[highest]:
                highest = level
            if bool(step.get("approval_required") or RISK_LEVELS[level]["step_approval"]):
                step_approvals.append(index)
        return {
            "highest_risk": highest,
            "by_level": by_level,
            "step_approvals": step_approvals,
            "plan_approval_required": bool((resolved.get("approval_policy") or {}).get("plan_approval", True)),
            "delivery_approval_required": bool((resolved.get("approval_policy") or {}).get("delivery_approval", False)),
        }

    def planning_contract(self, mission: Any) -> dict[str, Any]:
        spec = self.resolve(mission)
        return {
            "flow_key": spec["flow_key"],
            "version": spec["version"],
            "phases": spec["phases"],
            "required_task_groups": spec["required_task_groups"],
            "required_gates": spec["required_gates"],
            "budgets": spec["budgets"],
            "risk_levels": {
                key: {
                    "name": value["name"],
                    "step_approval": value["step_approval"],
                    "max_attempts": value["max_attempts"],
                }
                for key, value in RISK_LEVELS.items()
            },
        }

    @staticmethod
    def _output_contract(step: dict[str, Any]) -> dict[str, Any]:
        current = step.get("output_contract")
        if isinstance(current, dict):
            artifact_types = BusinessFlowRegistry._string_list(current.get("artifact_types"), limit=12)
            required_fields = BusinessFlowRegistry._string_list(current.get("required_fields"), limit=12)
        else:
            artifact_types = []
            required_fields = []
        if not artifact_types:
            artifact_types = BusinessFlowRegistry._string_list(step.get("deliverables"), limit=12)
        if not artifact_types:
            artifact_types = [str(step.get("title") or "任务交付物")[:300]]
        if not required_fields:
            required_fields = ["summary", "evidence_refs", "risk_notes"]
        return {"artifact_types": artifact_types, "required_fields": required_fields}

    @staticmethod
    def _compensation(value: Any, rollback_plan: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "type": str(value.get("type") or "manual")[:80],
                "instructions": str(value.get("instructions") or rollback_plan)[:1000],
            }
        return {"type": "manual", "instructions": rollback_plan[:1000]}

    @staticmethod
    def _default_rollback(task_type: str) -> str:
        if task_type in {"backend", "api", "database", "frontend", "ui", "testing", "architecture"}:
            return "保留变更和验证证据；如验证失败，停止合并并退回上一可用版本。"
        if task_type in {"writing", "document", "research", "knowledge"}:
            return "保留草稿与来源记录；如审校失败，退回上一版并标注待补充项。"
        if task_type == "finance":
            return "未完成审批前不得执行；失败时保留凭证并转人工复核。"
        if task_type == "operations":
            return "停止后续变更，恢复上一已验证配置并记录运行回执。"
        return "停止后续步骤，保留执行证据并等待重新规划。"

    @staticmethod
    def _step_risk(step: dict[str, Any], spec: dict[str, Any]) -> str:
        ranks = {name: index for index, name in enumerate(RISK_LEVELS)}
        inferred = "L0"
        text = " ".join(
            str(step.get(field) or "")
            for field in ("title", "description", "objective", "task_type")
        ).lower()
        task_type = str(step.get("task_type") or "general").lower()
        if any(marker.lower() in text for marker in L3_MARKERS):
            inferred = "L3"
        elif spec.get("business_type") == "finance" or task_type == "finance":
            inferred = "L2"
        elif task_type == "operations":
            inferred = "L2"
        elif task_type in SIDE_EFFECT_TASK_TYPES:
            inferred = "L1"

        explicit = str(step.get("risk_class") or "").upper()
        if explicit in RISK_LEVELS:
            return explicit if ranks[explicit] >= ranks[inferred] else inferred
        legacy = str(step.get("risk_level") or "").lower()
        if legacy == "high":
            return "L3"
        if legacy == "medium":
            return "L2" if ranks["L2"] >= ranks[inferred] else inferred
        return inferred

    @staticmethod
    def _resource_conflicts(steps: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        by_resource: dict[str, list[int]] = {}
        dependency_map: dict[int, set[int]] = {}
        for index, step in enumerate(steps, start=1):
            order = BusinessFlowRegistry._int_value(step.get("order_index"), index)
            dependency_map[order] = {
                BusinessFlowRegistry._int_value(item, -1)
                for item in step.get("depends_on") or []
            }
            for resource in BusinessFlowRegistry._string_list(step.get("resources"), limit=12):
                by_resource.setdefault(resource, []).append(order)
        for resource, orders in by_resource.items():
            if len(orders) < 2:
                continue
            for left_index, left in enumerate(orders):
                for right in orders[left_index + 1 :]:
                    if left not in dependency_map.get(right, set()) and right not in dependency_map.get(left, set()):
                        warnings.append(f"资源 {resource} 被步骤 {left} 和 {right} 并行修改，建议增加依赖或锁")
        return warnings

    @staticmethod
    def _infer_type(objective: str) -> str:
        text = str(objective or "").lower()
        marker_groups = (
            ("finance", ("财务", "发票", "付款", "报销", "对账", "预算")),
            ("document", ("文档", "报告", "论文", "文章", "教材", "课件")),
            ("software", ("开发", "代码", "接口", "api", "前端", "后端", "数据库", "bug")),
            ("operations", ("运维", "部署", "服务器", "监控", "故障")),
            ("research", ("调研", "研究", "情报", "检索", "竞品")),
        )
        for business_type, markers in marker_groups:
            if any(marker in text for marker in markers):
                return business_type
        return "general"

    @staticmethod
    def _string_list(value: Any, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text[:300])
            if len(result) >= limit:
                break
        return result

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

    @classmethod
    def _mission_context(cls, mission: Any) -> dict[str, Any]:
        value = cls._mission_value(mission, "context")
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                import json

                parsed = json.loads(value)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        raw = cls._mission_value(mission, "context_json")
        if isinstance(raw, str):
            try:
                import json

                parsed = json.loads(raw)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _int_value(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _bounded_int(cls, value: Any, default: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(cls._int_value(value, default), maximum))


business_flow_registry = BusinessFlowRegistry()
