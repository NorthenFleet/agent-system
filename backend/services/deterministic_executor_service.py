"""Bounded, side-effect-free operations selected explicitly in approved plans."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from services.openclaw_task_executor import ExecutionResult

EXECUTOR = "deterministic-v1"
CRITERION = "确定性检查通过"
MAX_BYTES = 65536


def enabled() -> bool:
    return os.getenv("COMMAND_CENTER_DETERMINISTIC_ENABLED", "false").lower() == "true"


def defaults(step: dict[str, Any]) -> None:
    if step.get("executor") != EXECUTOR:
        return
    for key, value in {
        "required_tools": ["deterministic_check"], "deliverables": ["确定性检查报告"],
        "acceptance_criteria": [CRITERION], "evidence_required": ["verification_report"],
        "output_contract": {"artifact_types": ["verification_report"], "required_fields": ["summary", "evidence_refs", "risk_notes"]},
        "side_effect": False, "max_attempts": 1,
    }.items():
        step.setdefault(key, value)


def validate(step: dict[str, Any], *, check_enabled: bool = True) -> None:
    if check_enabled and not enabled():
        raise ValueError("确定性执行器未启用")
    if step.get("executor") != EXECUTOR or step.get("task_type") != "general" or step.get("side_effect") is not False:
        raise ValueError("确定性执行只允许 general 类型的无副作用步骤")
    if not 1 <= int(step.get("max_attempts", 1)) <= 3:
        raise ValueError("确定性步骤最多允许 3 次执行")
    expected = {"executor": EXECUTOR}
    defaults(expected)
    for key in ("required_tools", "deliverables", "acceptance_criteria", "evidence_required"):
        if step.get(key) != expected[key]:
            raise ValueError(f"确定性执行契约不匹配：{key}")
    contract = step.get("output_contract") or {}
    if contract.get("artifact_types") != ["verification_report"] or set(contract.get("required_fields") or []) != {"summary", "evidence_refs", "risk_notes"}:
        raise ValueError("确定性执行输出契约不匹配")
    args = step.get("input")
    if not isinstance(args, dict):
        raise ValueError("确定性输入必须为对象")
    op = args.get("operation")
    allowed = {"operation", "text", "expected_sha256"} if op == "sha256_text" else {"operation", "text", "required_keys"}
    if op not in {"sha256_text", "json_required_keys"} or set(args) != allowed:
        raise ValueError("未知操作或参数；禁止 shell、路径及任意执行")
    if not isinstance(args.get("text"), str) or len(args["text"].encode("utf-8")) > MAX_BYTES:
        raise ValueError("输入文本必须为 UTF-8 且不超过 65536 字节")
    if op == "sha256_text":
        digest = args.get("expected_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("必须提供小写 SHA-256 预期值")
    else:
        keys = args.get("required_keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 64 or any(not isinstance(k, str) or not 1 <= len(k) <= 128 for k in keys):
            raise ValueError("required_keys 必须为 1–64 个非空短字符串")


def execute(step: dict[str, Any]) -> ExecutionResult:
    started = time.monotonic()
    try:
        validate(step)
        args = step["input"]
        digest = hashlib.sha256(args["text"].encode()).hexdigest()
        report: dict[str, Any] = {"operation": args["operation"], "input_sha256": digest}
        if args["operation"] == "sha256_text":
            passed = digest == args["expected_sha256"]
            report["expected_sha256"] = args["expected_sha256"]
        else:
            def unique_object(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise ValueError("JSON 含重复键")
                    obj[key] = value
                return obj
            def invalid_constant(value):
                raise ValueError("JSON 不允许非有限数值")
            value = json.loads(args["text"], object_pairs_hook=unique_object, parse_constant=invalid_constant)
            queue = [(value, 0)]
            nodes = 0
            while queue:
                item, depth = queue.pop()
                nodes += 1
                if depth > 32 or nodes > 4096:
                    raise ValueError("JSON 超过深度或节点预算")
                if isinstance(item, dict):
                    queue.extend((v, depth + 1) for v in item.values())
                elif isinstance(item, list):
                    queue.extend((v, depth + 1) for v in item)
            if not isinstance(value, dict):
                raise ValueError("JSON 顶层必须为对象")
            report["missing_keys"] = sorted(set(args["required_keys"]) - value.keys())
            passed = not report["missing_keys"]
        report["passed"] = passed
        content = json.dumps(report, ensure_ascii=False, sort_keys=True)
        ref = f"mission-result://{step['id']}/attempt/{step['attempt_count']}"
        summary = "确定性检查通过" if passed else "确定性检查未通过"
        payload = {"outcome": "succeeded" if passed else "failed", "summary": summary,
                   "risk_notes": "仅验证批准计划中的内联输入，不证明外部文件状态", "tools_used": ["deterministic_check"],
                   "evidence_refs": [ref], "side_effects": [],
                   "artifacts": [{"artifact_key": "verification", "artifact_type": "verification_report", "title": summary,
                                  "uri": ref, "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                                  "metadata": {"report": report, "canonical_content": content}}],
                   "evidence": [{"evidence_type": "verification_report", "source_ref": ref, "summary": summary, "artifact_key": "verification"}],
                   "acceptance_results": [{"criterion": CRITERION, "status": "pass" if passed else "fail", "evidence_refs": [ref]}]}
        return ExecutionResult(success=passed, output=json.dumps(payload, ensure_ascii=False),
                               error="" if passed else summary, duration_ms=int((time.monotonic() - started) * 1000))
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        return ExecutionResult(success=False, error=f"确定性执行拒绝：{exc}", duration_ms=int((time.monotonic() - started) * 1000))
