"""Versioned, observation-only step decisions. Never authorizes execution."""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from services.agent_capability_registry import agent_capability_registry


class DecisionRouterService:
    policy_version = "dr-shadow-v1"

    @staticmethod
    def enabled() -> bool:
        # Unknown values fail closed; there is deliberately no active mode yet.
        return os.getenv("COMMAND_CENTER_DECISION_ROUTER_MODE", "off").strip().lower() == "shadow"

    def route(self, step: dict[str, Any]) -> dict[str, Any]:
        if step.get("executor") == "deterministic-v1":
            return self._decision(step, "dispatch", "execute", "explicit_deterministic_contract", "使用批准计划明确指定的确定性检查")
        agent = str(step.get("agent_id") or "")
        supported = agent_capability_registry.agent_supports_task(agent, str(step.get("task_type") or ""))
        unavailable = agent_capability_registry.unavailable_required_tools(step.get("required_tools") or [])
        if not supported or unavailable:
            action, reason = "escalate", "capability_gap"
            detail = "能力或必需工具不匹配，建议主控重新判断"
        else:
            action, reason = "delegate", "registered_agent_match"
            detail = "按已批准计划交给具备对应能力的 Agent"
        return self._decision(step, "dispatch", action, reason, detail)

    def observe_result(self, step: dict[str, Any], result: dict[str, Any], *,
                       accepted: bool, previous: dict[str, Any] | None = None) -> dict[str, Any]:
        quality = result.get("execution_quality") or {}
        effect = result.get("effect_quality") or {}
        fingerprint = ""
        count = 0
        if accepted:
            action, reason, detail = "continue", "accepted", "结果已通过现有验收"
        else:
            category = ("execution_error" if not result.get("success") else
                        "protocol_error" if result.get("protocol_error") else "evidence_rejected")
            # No raw error is persisted here. Keep numbers/paths significant; only
            # normalize whitespace so distinct resources/errors do not collapse.
            errors = [str(result.get("error") or ""), str(result.get("protocol_error") or "")]
            errors += [str(x) for x in quality.get("blockers") or []]
            errors += [str(x) for x in effect.get("blockers") or []]
            identity = {"category": category, "task_type": step.get("task_type"),
                        "tools": sorted(step.get("required_tools") or []),
                        "resources": sorted(step.get("resources") or []),
                        "errors": sorted(re.sub(r"\s+", " ", x).strip() for x in errors if x)}
            fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            previous = previous or {}
            consecutive = (previous.get("failure_fingerprint") == fingerprint
                           and previous.get("attempt") == int(step.get("attempt_count") or 0) - 1
                           and previous.get("policy_version") == self.policy_version)
            count = int(previous.get("consecutive_failures") or 0) + 1 if consecutive else 1
            unsafe = step.get("side_effect") is not False or any(
                x.get("status") in {"applied", "unknown"} for x in result.get("side_effects") or [])
            if unsafe:
                action, reason, detail = "inspect", "effect_requires_inspection", "先核验副作用和回执，再判断恢复方式"
            elif count >= 2:
                action, reason, detail = "escalate", "repeated_failure", "连续相同失败，建议主控改变方案"
            else:
                action, reason, detail = "review", "failure_requires_review", "核对错误与证据缺口；重试仍由现有门禁决定"
        decision = self._decision(step, "completion", action, reason, detail)
        decision.update(failure_fingerprint=fingerprint, consecutive_failures=count,
                        repeated_failure=count >= 2)
        return decision

    def _decision(self, step: dict[str, Any], phase: str, action: str, reason: str, detail: str) -> dict[str, Any]:
        return {"mode": "shadow", "enforced": False, "policy_version": self.policy_version,
                "mission_id": step.get("mission_id"), "step_id": step.get("id"),
                "plan_version": step.get("plan_version"), "attempt": int(step.get("attempt_count") or 0),
                "phase": phase, "action": action, "reason_code": reason, "detail": detail,
                "actual_executor": step.get("executor"), "actual_agent_id": step.get("agent_id")}


decision_router_service = DecisionRouterService()
