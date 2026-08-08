"""Server-side independent AI review for staged finance intake jobs."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent_messenger import agent_messenger
from services.finance_intake_service import finance_intake_coordinator


logger = logging.getLogger(__name__)


def _extract_json_object(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


class FinanceReviewOrchestrator:
    async def review_job(self, job_id: str) -> dict[str, Any]:
        try:
            job = finance_intake_coordinator.get_agent_job(job_id, agent_id="inspector")
            if job["status"] != "needs_review":
                return {"status": "skipped", "job": {"id": job_id, "state": job["status"]}}
            review_context = {
                "job_id": job["id"],
                "operation_type": job["operation_type"],
                "request_text": job["request_text"],
                "normalized_payload": job["normalized_payload"],
                "validation_report": job["validation_report"],
                "lock_version": job["lock_version"],
            }
            prompt = (
                "你是独立财务复核智能体检查员。不要调用任何工具，不要访问数据库，不要发送消息。"
                "只根据下面给出的原始请求、结构化抽取和确定性校验复核。"
                "如果确定性校验 valid=false，decision 必须为 reject。"
                "输出且只输出一个 JSON 对象，格式为："
                '{"decision":"approve|reject","summary":"结论",'
                '"findings":[{"code":"...","message":"..."}],"confidence":0.0}。'
                "approve 仅表示暂存数据通过复核，不代表入账、付款或报销完成。\n\n"
                f"复核上下文：{json.dumps(review_context, ensure_ascii=False)}"
            )
            response = await agent_messenger.request_agent(
                "inspector",
                prompt,
                timeout_seconds=180,
            )
            result = _extract_json_object(response)
            if not result:
                raise RuntimeError("检查员未返回结构化 JSON")
            decision = str(result.get("decision") or "").strip().lower()
            summary = str(result.get("summary") or "").strip()
            findings = result.get("findings")
            try:
                confidence = float(result.get("confidence"))
            except (TypeError, ValueError) as exc:
                raise RuntimeError("检查员返回了无效置信度") from exc
            if decision not in {"approve", "reject"} or not summary:
                raise RuntimeError("检查员返回了无效复核结论")
            if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
                raise RuntimeError("检查员 findings 必须是对象数组")
            reviewed = finance_intake_coordinator.submit_review(
                job_id,
                reviewer_agent_id="inspector",
                decision=decision,
                summary=summary,
                findings=findings,
                confidence=confidence,
                expected_version=int(job["lock_version"]),
            )
            return {"status": "completed", **reviewed}
        except Exception as exc:
            logger.warning("finance independent review failed job=%s error=%s", job_id, exc)
            try:
                finance_intake_coordinator.record_review_failure(job_id, error=str(exc))
            except Exception:
                logger.exception("failed to record finance review error job=%s", job_id)
            return {"status": "failed", "job_id": job_id, "error": str(exc)[:500]}


finance_review_orchestrator = FinanceReviewOrchestrator()
