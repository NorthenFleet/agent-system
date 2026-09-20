"""Deterministic artifact, evidence and acceptance checks for mission steps."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any


EVIDENCE_ALIASES = {
    "citations": {"citation", "source_ref", "context_pack"},
    "source_refs": {"citation", "source_ref", "context_pack"},
    "test_output": {"test_output", "test_report"},
    "build_output": {"build_output", "build_report"},
    "diff_summary": {"diff_summary", "code_diff"},
    "document_diff": {"document_diff", "artifact_diff"},
    "quality_notes": {"quality_notes", "review_report"},
}


class ExecutionEvidenceService:
    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "modes": {
                "shadow": "record findings without changing step outcome",
                "pilot": "enforce for eligible LangGraph document/research runs",
                "strict": "enforce for every mission",
            },
            "required_result_fields": [
                "summary",
                "artifacts",
                "evidence",
                "acceptance_results",
                "tools_used",
                "risk_notes",
            ],
            "artifact_identity": ["artifact_type", "title", "uri", "content_hash"],
            "evidence_identity": ["evidence_type", "source_ref", "summary"],
        }

    def enrich_result(
        self,
        step: dict[str, Any],
        result: dict[str, Any],
        *,
        success: bool,
        enforcement: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        enriched = self.normalize_result(result)
        enriched["execution_quality"] = self.evaluate(
            step,
            enriched,
            success=success,
            enforcement=enforcement or {"mode": "shadow", "enforced": False},
        )
        return enriched

    def normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(result or {})
        structured = enriched.get("structured_output")
        if not isinstance(structured, dict):
            structured = self._extract_json_object(str(enriched.get("output") or ""))
        if isinstance(structured, dict):
            for field in (
                "outcome",
                "summary",
                "artifacts",
                "evidence",
                "evidence_refs",
                "acceptance_results",
                "tools_used",
                "risk_notes",
            ):
                if field not in enriched and field in structured:
                    enriched[field] = structured[field]
            enriched["structured_output"] = structured

        enriched["summary"] = str(
            enriched.get("summary")
            or enriched.get("output")
            or enriched.get("error")
            or ""
        ).strip()[:8000]
        enriched["artifacts"] = self._artifacts(enriched)
        enriched["evidence"] = self._evidence(enriched)
        enriched["evidence_refs"] = self._evidence_refs(enriched)
        enriched["acceptance_results"] = self._acceptance_results(enriched)
        enriched["tools_used"] = self._string_list(enriched.get("tools_used"), limit=30)
        risk_notes = enriched.get("risk_notes")
        if isinstance(risk_notes, list):
            risk_notes = "\n".join(str(item) for item in risk_notes if str(item).strip())
        enriched["risk_notes"] = str(risk_notes or "").strip()[:4000]
        enriched["outcome"] = self._business_outcome(enriched)
        return enriched

    def evaluate(
        self,
        step: dict[str, Any],
        result: dict[str, Any],
        *,
        success: bool,
        enforcement: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = dict(enforcement or {})
        enforced = bool(policy.get("enforced"))
        mode = str(policy.get("mode") or "shadow")
        warnings: list[str] = []
        blockers: list[str] = []
        summary = str(result.get("summary") or "").strip()
        output = str(result.get("output") or result.get("error") or "").strip()
        evidence = list(result.get("evidence") or [])
        evidence_refs = list(result.get("evidence_refs") or [])
        artifacts = list(result.get("artifacts") or [])
        acceptance_results = list(result.get("acceptance_results") or [])
        tools_used = {str(item).lower() for item in (result.get("tools_used") or [])}
        business_outcome = str(result.get("outcome") or "failed")
        hard_blockers: list[str] = []

        if success and business_outcome != "succeeded":
            hard_blockers.append(f"步骤业务结果为 {business_outcome}，不得标记为已完成")

        explicitly_failed_acceptance = [
            str(item.get("criterion") or "未命名验收项")
            for item in acceptance_results
            if str(item.get("status") or "").strip().lower()
            in {"fail", "failed", "blocked", "reject", "rejected"}
        ]
        if success and explicitly_failed_acceptance:
            hard_blockers.append(
                "验收结果明确失败：" + ", ".join(explicitly_failed_acceptance)
            )
        if success:
            hard_blockers.extend(self._artifact_integrity_blockers(artifacts))
        blockers.extend(hard_blockers)

        required_evidence = self._string_list(step.get("evidence_required"), limit=30)
        acceptance = self._string_list(step.get("acceptance_criteria"), limit=30)
        required_tools = self._string_list(step.get("required_tools"), limit=30)
        output_contract = (
            step.get("output_contract")
            if isinstance(step.get("output_contract"), dict)
            else {}
        )
        required_artifact_types = self._string_list(
            output_contract.get("artifact_types"), limit=30
        )
        required_fields = self._string_list(
            output_contract.get("required_fields"), limit=30
        )

        if success and not summary:
            blockers.append("执行成功但没有返回结果摘要")
        if success:
            missing_evidence = [
                item for item in required_evidence if not self._has_evidence(item, evidence)
            ]
            self._finding(
                missing_evidence,
                f"缺少要求的证据类型：{', '.join(missing_evidence)}",
                enforced,
                blockers,
                warnings,
            )

            present_artifact_types = {
                str(item.get("artifact_type") or "").lower() for item in artifacts
            }
            missing_artifacts = [
                item
                for item in required_artifact_types
                if item.lower() not in present_artifact_types
            ]
            self._finding(
                missing_artifacts,
                f"缺少要求的交付物类型：{', '.join(missing_artifacts)}",
                enforced,
                blockers,
                warnings,
            )

            invalid_artifacts = [
                item.get("title") or item.get("artifact_type") or "unnamed"
                for item in artifacts
                if not item.get("content_hash") or not item.get("uri")
            ]
            self._finding(
                invalid_artifacts,
                "交付物缺少 uri 或 content_hash："
                + ", ".join(str(item) for item in invalid_artifacts),
                enforced,
                blockers,
                warnings,
            )

            acceptance_by_criterion = {
                str(item.get("criterion") or "").strip().lower(): str(
                    item.get("status") or ""
                ).lower()
                for item in acceptance_results
            }
            failed_acceptance = [
                criterion
                for criterion in acceptance
                if acceptance_by_criterion.get(criterion.lower()) not in {"pass", "passed"}
            ]
            self._finding(
                failed_acceptance,
                f"验收标准未逐项通过：{', '.join(failed_acceptance)}",
                enforced,
                blockers,
                warnings,
            )

            missing_tools = [
                tool
                for tool in required_tools
                if tool.lower() not in tools_used and tool.lower() not in output.lower()
            ]
            self._finding(
                missing_tools,
                f"未证明使用必需工具：{', '.join(missing_tools)}",
                enforced,
                blockers,
                warnings,
            )

            missing_fields = [
                field for field in required_fields if not self._required_field_present(field, result)
            ]
            self._finding(
                missing_fields,
                f"输出合同字段缺失：{', '.join(missing_fields)}",
                enforced,
                blockers,
                warnings,
            )

        score = max(0, 100 - len(blockers) * 30 - len(warnings) * 8)
        status = "blocked" if blockers else "warning" if warnings else "pass"
        return {
            "status": status,
            "score": score,
            "mode": mode,
            "enforced": enforced,
            "accepted": bool(success and not blockers),
            "executor_success": bool(success),
            "business_outcome": business_outcome,
            "hard_blockers": hard_blockers,
            "blockers": blockers,
            "warnings": warnings,
            "evidence_refs": evidence_refs,
            "required_evidence": required_evidence,
            "required_artifact_types": required_artifact_types,
            "required_tools": required_tools,
            "acceptance_criteria": acceptance,
            "checked_rules": [
                "result-summary",
                "required-evidence-types",
                "artifact-contract",
                "acceptance-results",
                "tool-use",
                "required-output-fields",
            ],
        }

    @staticmethod
    def _business_outcome(result: dict[str, Any]) -> str:
        if result.get("success") is False:
            return "failed"
        structured = (
            result.get("structured_output")
            if isinstance(result.get("structured_output"), dict)
            else {}
        )
        if structured.get("ok") is False or structured.get("success") is False:
            return "failed"
        raw = str(result.get("outcome") or "").strip().lower()
        aliases = {
            "success": "succeeded",
            "successful": "succeeded",
            "completed": "succeeded",
            "complete": "succeeded",
            "passed": "succeeded",
            "pass": "succeeded",
            "failure": "failed",
            "error": "failed",
            "needs-input": "needs_input",
            "needs input": "needs_input",
            "waiting_input": "needs_input",
        }
        normalized = aliases.get(raw, raw)
        if normalized in {"succeeded", "blocked", "failed", "needs_input"}:
            return normalized

        acceptance_results = (
            result.get("acceptance_results")
            if isinstance(result.get("acceptance_results"), list)
            else []
        )
        failed = any(
            str(item.get("status") or "").strip().lower()
            in {"fail", "failed", "blocked", "reject", "rejected"}
            for item in acceptance_results
            if isinstance(item, dict)
        )
        summary = str(
            result.get("summary") or result.get("output") or result.get("error") or ""
        ).lower()
        blocked_markers = (
            "阻塞",
            "无法执行",
            "不能执行",
            "缺少",
            "前置条件不满足",
            "needs input",
            "blocked",
        )
        if any(marker in summary for marker in blocked_markers):
            return "blocked"
        if failed:
            return "failed"
        return "succeeded"

    @staticmethod
    def _artifact_integrity_blockers(artifacts: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        for artifact in artifacts:
            label = str(
                artifact.get("title") or artifact.get("artifact_type") or "unnamed"
            )
            content_hash = str(artifact.get("content_hash") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
                blockers.append(f"交付物 {label} 的 content_hash 不是真实 SHA-256")
            uri = str(artifact.get("uri") or "").strip()
            if not uri:
                continue
            if os.path.isabs(uri):
                if not os.path.isfile(uri):
                    blockers.append(f"交付物 {label} 的本地路径不可访问：{uri}")
                    continue
                if re.fullmatch(r"[0-9a-f]{64}", content_hash):
                    digest = hashlib.sha256()
                    with open(uri, "rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != content_hash:
                        blockers.append(f"交付物 {label} 的 SHA-256 与文件内容不匹配")
            elif not re.match(r"^[a-z][a-z0-9+.-]*://", uri, re.IGNORECASE):
                blockers.append(f"交付物 {label} 缺少可持久定位的 URI：{uri}")
        return blockers

    @staticmethod
    def _finding(
        missing: list[Any],
        message: str,
        enforced: bool,
        blockers: list[str],
        warnings: list[str],
    ) -> None:
        if missing:
            (blockers if enforced else warnings).append(message)

    @staticmethod
    def _required_field_present(field: str, result: dict[str, Any]) -> bool:
        value = result.get(field)
        return bool(value) or value == 0 or value is False

    @staticmethod
    def _has_evidence(requirement: str, evidence: list[dict[str, Any]]) -> bool:
        required = requirement.strip().lower()
        accepted = EVIDENCE_ALIASES.get(required, {required})
        return any(
            str(item.get("evidence_type") or "").strip().lower() in accepted
            for item in evidence
        )

    def _artifacts(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        values = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(values[:30], start=1):
            if not isinstance(raw, dict):
                continue
            content = str(raw.get("content") or "")
            content_hash = str(
                raw.get("content_hash") or raw.get("checksum") or ""
            ).strip().lower()
            if not content_hash and content:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            artifact_type = str(
                raw.get("artifact_type") or raw.get("type") or ""
            ).strip()
            title = str(raw.get("title") or artifact_type or f"artifact-{index}").strip()
            if not artifact_type or not title:
                continue
            normalized.append(
                {
                    "artifact_key": str(raw.get("artifact_key") or raw.get("id") or index)[:160],
                    "artifact_type": artifact_type[:120],
                    "title": title[:500],
                    "uri": str(raw.get("uri") or raw.get("path") or "").strip()[:2000],
                    "content_hash": content_hash[:128],
                    "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
                }
            )
        return normalized

    def _evidence(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        values = result.get("evidence") if isinstance(result.get("evidence"), list) else []
        normalized: list[dict[str, Any]] = []
        for raw in values[:50]:
            if not isinstance(raw, dict):
                continue
            evidence_type = str(
                raw.get("evidence_type") or raw.get("type") or ""
            ).strip().lower()
            source_ref = str(
                raw.get("source_ref") or raw.get("ref") or raw.get("uri") or ""
            ).strip()
            summary = str(raw.get("summary") or raw.get("description") or "").strip()
            if not evidence_type or not source_ref or not summary:
                continue
            try:
                confidence = float(raw.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 1.0
            normalized.append(
                {
                    "evidence_type": evidence_type[:120],
                    "source_ref": source_ref[:2000],
                    "summary": summary[:4000],
                    "artifact_key": str(raw.get("artifact_key") or raw.get("artifact_id") or "")[:160],
                    "confidence": max(0.0, min(confidence, 1.0)),
                    "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
                }
            )

        for ref in result.get("evidence_refs") or []:
            text = str(ref or "").strip()
            if not text:
                continue
            evidence_type, separator, source_ref = text.partition(":")
            if not separator:
                evidence_type = "citation" if re.fullmatch(r"\[C\d+\]", text) else "reference"
                source_ref = text
            normalized.append(
                {
                    "evidence_type": evidence_type.lower()[:120],
                    "source_ref": source_ref[:2000],
                    "summary": f"Execution evidence reference: {text}"[:4000],
                    "artifact_key": "",
                    "confidence": 1.0,
                    "metadata": {},
                }
            )

        context = result.get("context") if isinstance(result.get("context"), dict) else {}
        if context.get("context_pack_id"):
            normalized.append(
                {
                    "evidence_type": "context_pack",
                    "source_ref": str(context["context_pack_id"])[:2000],
                    "summary": "Approved execution context snapshot",
                    "artifact_key": "",
                    "confidence": 1.0,
                    "metadata": {"binding_id": context.get("binding_id")},
                }
            )
        for citation in context.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            source_ref = str(
                citation.get("source_ref") or citation.get("title") or ""
            ).strip()
            if source_ref:
                normalized.append(
                    {
                        "evidence_type": "citation",
                        "source_ref": source_ref[:2000],
                        "summary": str(citation.get("title") or source_ref)[:4000],
                        "artifact_key": "",
                        "confidence": 1.0,
                        "metadata": citation,
                    }
                )
        seen: set[tuple[str, str, str]] = set()
        unique: list[dict[str, Any]] = []
        for item in normalized:
            key = (item["evidence_type"], item["source_ref"], item["summary"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:50]

    @staticmethod
    def _evidence_refs(result: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        for item in result.get("evidence") or []:
            if isinstance(item, dict) and item.get("source_ref"):
                refs.append(str(item["source_ref"]))
        seen: set[str] = set()
        unique: list[str] = []
        for ref in refs:
            if ref not in seen:
                seen.add(ref)
                unique.append(ref[:2000])
        return unique[:50]

    @staticmethod
    def _acceptance_results(result: dict[str, Any]) -> list[dict[str, Any]]:
        values = (
            result.get("acceptance_results")
            if isinstance(result.get("acceptance_results"), list)
            else []
        )
        normalized: list[dict[str, Any]] = []
        for raw in values[:50]:
            if not isinstance(raw, dict):
                continue
            criterion = str(raw.get("criterion") or raw.get("name") or "").strip()
            status = str(raw.get("status") or "").strip().lower()
            if criterion and status in {"pass", "passed", "fail", "failed", "blocked"}:
                normalized.append(
                    {
                        "criterion": criterion[:1000],
                        "status": "pass" if status in {"pass", "passed"} else "fail",
                        "evidence_refs": ExecutionEvidenceService._string_list(
                            raw.get("evidence_refs"), limit=20, item_limit=2000
                        ),
                        "notes": str(raw.get("notes") or "")[:2000],
                    }
                )
        return normalized

    @staticmethod
    def _string_list(
        value: Any,
        *,
        limit: int,
        item_limit: int = 300,
    ) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:item_limit] for item in value if str(item).strip()][:limit]

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
        candidates = [fenced.group(1)] if fenced else []
        candidates.append(raw)
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            candidates.append(raw[start : end + 1])
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                return value
        return None


execution_evidence_service = ExecutionEvidenceService()
