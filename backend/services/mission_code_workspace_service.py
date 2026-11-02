"""Approved code edits become isolated, retained candidates, never source merges."""
import hashlib
import json
import os
import re
from pathlib import Path

from services.git_workspace_service import GitWorkspaceService
from services.agent_execution_profile_service import resolve_profile

EXECUTOR = "isolated-code-v1"


def enabled() -> bool:
    return os.getenv("COMMAND_CENTER_CODE_WORKSPACE_ENABLED", "false").lower() == "true"


def defaults(step: dict) -> None:
    if step.get("executor") != EXECUTOR:
        return
    values = {"required_tools": ["isolated_code_candidate"], "deliverables": ["隔离代码候选"],
              "acceptance_criteria": ["已形成可审查的隔离代码候选"], "evidence_required": ["diff_summary"],
              "output_contract": {"artifact_types": ["code_diff"], "required_fields": ["summary", "evidence_refs", "risk_notes"]},
              "side_effect": True, "max_attempts": 1}
    for key, value in values.items():
        step.setdefault(key, value)


def validate(step: dict) -> None:
    if not enabled():
        raise ValueError("隔离代码执行器未启用")
    resolve_profile("worker", required=True)
    expected = {"executor": EXECUTOR}
    defaults(expected)
    for key in ("required_tools", "deliverables", "acceptance_criteria", "evidence_required", "output_contract"):
        if step.get(key) != expected[key]:
            raise ValueError(f"隔离候选不能承诺未执行的测试或源仓库合并：{key}")
    if int(step.get("max_attempts") or 1) != 1:
        raise ValueError("代码候选每个计划只允许一次执行；修复需新计划")
    args = step.get("input") or {}
    repositories = json.loads(os.getenv("COMMAND_CENTER_CODE_REPOSITORIES", "{}"))
    if step.get("task_type") not in {"backend", "frontend", "api", "database", "ui"}:
        raise ValueError("隔离执行器仅用于代码修改")
    if not isinstance(args, dict) or set(args) != {"repository_id", "base_commit"}:
        raise ValueError("代码执行只接受 repository_id 与 base_commit")
    if args["repository_id"] not in repositories or not isinstance(repositories[args["repository_id"]], str):
        raise ValueError("未授权代码仓库")
    if not isinstance(args["base_commit"], str) or not re.fullmatch(r"[0-9a-f]{40,64}", args["base_commit"]):
        raise ValueError("代码执行必须绑定完整基线提交")
    if not os.getenv("COMMAND_CENTER_CODE_WORKTREE_ROOT"):
        raise ValueError("未配置隔离工作树根目录")


class MissionCodeWorkspaceService(GitWorkspaceService):
    def __init__(self):
        super().__init__(root=os.getenv("COMMAND_CENTER_CODE_WORKTREE_ROOT", "/tmp/disabled-command-worktrees"))

    def _git(self, repo, *args, **kwargs):
        return super()._git(repo, "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false", *args, **kwargs)

    def prepare_step(self, step: dict) -> dict:
        validate(step)
        args = step["input"]
        repo = str(Path(json.loads(os.environ["COMMAND_CENTER_CODE_REPOSITORIES"])[args["repository_id"]]).resolve())
        if self._git(repo, "rev-parse", "HEAD") != args["base_commit"]:
            raise ValueError("仓库 HEAD 已变化，需重新规划并审批基线")
        key = f"mission-{step['id']}-attempt-{step['attempt_count']}"
        workspace = self.prepare(repo, key)
        if workspace["base_commit"] != args["base_commit"]:
            raise ValueError("创建工作树时基线发生变化；候选保留，拒绝执行")
        workspace["key"] = key
        return workspace

    def candidate(self, workspace: dict) -> dict:
        checkpoint = self.checkpoint(workspace, workspace["key"], 1)
        diff = self._git(workspace["execution_repo"], "diff", "--binary", workspace["base_commit"], checkpoint["commit_sha"])
        return {**workspace, **checkpoint, "workspace_status": "candidate", "integrated": False,
                "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(), "diff_summary": diff[:16000],
                "diff_truncated": len(diff) > 16000}


def candidate_result(step: dict, candidate: dict, profile: dict | None):
    from services.openclaw_task_executor import ExecutionResult
    if candidate["commit_sha"] == candidate["base_commit"] or not candidate["clean"]:
        return ExecutionResult(False, error="未形成新的干净候选提交")
    ref = f"git-candidate://{step['id']}/{candidate['commit_sha']}"
    payload = {"outcome": "succeeded", "summary": "已形成隔离代码候选，尚未合并且未运行测试",
               "risk_notes": "候选仅通过差异生成检查；功能测试和源仓库合并需后续验收", "tools_used": ["isolated_code_candidate"],
               "evidence_refs": [ref],
               "artifacts": [{"artifact_key": "candidate", "artifact_type": "code_diff", "title": "隔离代码候选",
                              "uri": ref, "content_hash": candidate["diff_sha256"], "metadata": candidate}],
               "evidence": [{"evidence_type": "diff_summary", "source_ref": ref, "summary": "Git 基线与候选提交差异", "artifact_key": "candidate"}],
               "acceptance_results": [{"criterion": "已形成可审查的隔离代码候选", "status": "pass", "evidence_refs": [ref]}],
               "side_effects": [{"effect_key": "candidate_worktree", "resource": candidate["execution_repo"],
                                 "action": "创建隔离代码候选", "status": "applied", "idempotency_key": step.get("idempotency_key"),
                                 "receipt_ref": ref, "evidence_refs": [ref]}]}
    result = ExecutionResult(True, output=json.dumps(payload, ensure_ascii=False))
    result.execution_profile = profile
    return result
