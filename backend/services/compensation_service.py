"""Deterministic side-effect journal and compensation contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


EFFECT_STATUSES = {"applied", "not_applied", "unknown"}
COMPENSATION_RESULT_STATUSES = {"reverted", "not_needed", "failed"}


class CompensationService:
    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "effect_statuses": sorted(EFFECT_STATUSES),
            "compensation_statuses": [
                "pending_approval",
                "ready",
                "running",
                "completed",
                "failed",
                "rejected",
                "cancelled",
            ],
            "policy": {
                "automatic_execution": False,
                "approval_required": True,
                "approval_single_use": True,
                "approval_ttl_env": "COMMAND_CENTER_COMPENSATION_APPROVAL_TTL",
                "unknown_effect_requires_review": True,
                "stable_idempotency_key_required": True,
                "interrupted_execution_requires_reapproval": True,
            },
        }

    def enrich_execution_result(
        self,
        step: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(result or {})
        structured = enriched.get("structured_output")
        if (
            "side_effects" not in enriched
            and isinstance(structured, dict)
            and "side_effects" in structured
        ):
            enriched["side_effects"] = structured["side_effects"]
        enriched["side_effects"] = self.normalize_effects(step, enriched)
        enriched["effect_quality"] = self.evaluate_effects(step, enriched["side_effects"])
        return enriched

    def normalize_effects(
        self,
        step: dict[str, Any],
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        values = result.get("side_effects")
        values = values if isinstance(values, list) else []
        normalized: list[dict[str, Any]] = []
        expected_key = str(step.get("idempotency_key") or "").strip()
        resources = [str(item) for item in (step.get("resources") or []) if str(item)]
        for index, raw in enumerate(values[:20], start=1):
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "unknown").strip().lower()
            if status not in EFFECT_STATUSES:
                status = "unknown"
            resource = str(raw.get("resource") or "").strip()
            action = str(raw.get("action") or "").strip()
            effect_key = str(raw.get("effect_key") or raw.get("id") or f"effect-{index}").strip()
            normalized.append(
                {
                    "effect_key": effect_key[:160],
                    "resource": (resource or (resources[0] if resources else "unspecified"))[:500],
                    "action": (action or str(step.get("objective") or step.get("title") or ""))[:1000],
                    "status": status,
                    "idempotency_key": str(raw.get("idempotency_key") or "").strip()[:240],
                    "receipt_ref": str(raw.get("receipt_ref") or raw.get("receipt") or "").strip()[:2000],
                    "evidence_refs": self._strings(raw.get("evidence_refs"), 20, 2000),
                    "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
                }
            )
        if bool(step.get("side_effect")) and not normalized:
            structured = (
                result.get("structured_output")
                if isinstance(result.get("structured_output"), dict)
                else {}
            )
            structured_error = (
                structured.get("error")
                if isinstance(structured.get("error"), dict)
                else {}
            )
            transport_failed_before_execution = bool(
                result.get("success") is False
                and structured.get("ok") is False
                and str(structured_error.get("type") or "").lower() == "cli_error"
            )
            normalized.append(
                {
                    "effect_key": "unreported-effect",
                    "resource": resources[0] if resources else "unspecified",
                    "action": str(step.get("objective") or step.get("title") or "")[:1000],
                    "status": (
                        "not_applied" if transport_failed_before_execution else "unknown"
                    ),
                    "idempotency_key": expected_key[:240],
                    "receipt_ref": "",
                    "evidence_refs": [],
                    "metadata": {
                        "synthetic": True,
                        "reason": (
                            "transport_failed_before_agent_execution"
                            if transport_failed_before_execution
                            else "executor_did_not_report_effect"
                        ),
                    },
                }
            )
        return normalized

    @staticmethod
    def evaluate_effects(
        step: dict[str, Any],
        effects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not bool(step.get("side_effect")):
            return {
                "status": "not_applicable",
                "accepted": True,
                "enforced": False,
                "blockers": [],
                "warnings": [],
            }
        blockers: list[str] = []
        expected_key = str(step.get("idempotency_key") or "").strip()
        if not effects:
            blockers.append("副作用步骤没有返回 effect journal")
        for effect in effects:
            label = str(effect.get("effect_key") or "effect")
            if effect.get("status") == "unknown":
                blockers.append(f"副作用 {label} 的落地状态未知")
            if not effect.get("idempotency_key"):
                blockers.append(f"副作用 {label} 缺少幂等键")
            elif expected_key and effect.get("idempotency_key") != expected_key:
                blockers.append(f"副作用 {label} 使用了非合同幂等键")
            if effect.get("status") == "applied" and not effect.get("receipt_ref"):
                blockers.append(f"已落地副作用 {label} 缺少执行回执")
        return {
            "status": "blocked" if blockers else "pass",
            "accepted": not blockers,
            "enforced": True,
            "blockers": blockers,
            "warnings": [],
            "effect_count": len(effects),
            "applied_count": sum(1 for item in effects if item.get("status") == "applied"),
            "unknown_count": sum(1 for item in effects if item.get("status") == "unknown"),
            "checked_rules": [
                "effect-journal-present",
                "effect-status-known",
                "stable-idempotency-key",
                "applied-effect-receipt",
            ],
        }

    @staticmethod
    def compensation_contract(
        step: dict[str, Any],
        effect: dict[str, Any],
    ) -> dict[str, Any]:
        configured = step.get("compensation") if isinstance(step.get("compensation"), dict) else {}
        instructions = str(
            configured.get("instructions") or step.get("rollback_plan") or ""
        ).strip()[:4000]
        effect_key = str(effect.get("effect_key") or "effect")
        original_key = str(step.get("idempotency_key") or "")
        key = f"compensate:{original_key}:{effect_key}"[:240]
        contract = {
            "type": str(configured.get("type") or "manual")[:80],
            "instructions": instructions,
            "resource": str(effect.get("resource") or "")[:500],
            "effect_key": effect_key[:160],
            "original_idempotency_key": original_key[:240],
            "idempotency_key": key,
        }
        canonical = json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        contract["contract_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return contract

    @staticmethod
    def normalize_compensation_result(result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result or {})
        structured = payload.get("structured_output")
        if not isinstance(structured, dict):
            structured = CompensationService._extract_json(str(payload.get("output") or ""))
        if isinstance(structured, dict):
            for field in ("summary", "status", "receipt_ref", "evidence_refs", "risk_notes"):
                if field not in payload and field in structured:
                    payload[field] = structured[field]
            payload["structured_output"] = structured
        status = str(payload.get("status") or "failed").strip().lower()
        if status not in COMPENSATION_RESULT_STATUSES:
            status = "failed"
        payload["status"] = status
        payload["summary"] = str(
            payload.get("summary") or payload.get("output") or payload.get("error") or ""
        ).strip()[:4000]
        payload["receipt_ref"] = str(payload.get("receipt_ref") or "").strip()[:2000]
        payload["evidence_refs"] = CompensationService._strings(
            payload.get("evidence_refs"), 30, 2000
        )
        payload["risk_notes"] = str(payload.get("risk_notes") or "").strip()[:4000]
        payload["accepted"] = bool(
            payload["status"] in {"reverted", "not_needed"}
            and payload["summary"]
            and payload["receipt_ref"]
            and payload["evidence_refs"]
        )
        return payload

    @staticmethod
    def _strings(value: Any, limit: int, item_limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:item_limit] for item in value if str(item).strip()][:limit]

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None


compensation_service = CompensationService()
