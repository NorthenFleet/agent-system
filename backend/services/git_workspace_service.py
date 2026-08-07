"""Git worktree isolation and integration for approved Codex development loops."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import threading
from typing import Any


WORKTREE_ROOT = os.path.expanduser(os.getenv("CODEX_WORKTREE_ROOT", "~/.openclaw/codex-worktrees"))
INTEGRATION_BRANCH = os.getenv("CODEX_INTEGRATION_BRANCH", "codex/integration")


class GitWorkspaceError(RuntimeError):
    pass


class GitWorkspaceService:
    def __init__(
        self,
        root: str = WORKTREE_ROOT,
        integration_branch: str = INTEGRATION_BRANCH,
        remote_target: str = "",
        remote_port: str = "",
        remote_key: str = "",
    ) -> None:
        self.remote_target = remote_target
        self.remote_port = remote_port
        self.remote_key = os.path.expanduser(remote_key) if remote_key else ""
        self.root = root if remote_target else os.path.abspath(os.path.expanduser(root))
        self.integration_branch = integration_branch
        self._integration_lock = threading.RLock()

    def prepare(self, repo: str, loop_id: str) -> dict[str, Any]:
        repo = os.path.abspath(os.path.expanduser(repo))
        self._git(repo, "rev-parse", "--is-inside-work-tree")
        git_root = self._git(repo, "rev-parse", "--show-toplevel")
        repo_relative_path = os.path.relpath(repo, git_root)
        if repo_relative_path == os.pardir or repo_relative_path.startswith(os.pardir + os.sep):
            raise GitWorkspaceError(f"执行目录不在 Git 工作树内：{repo}")
        base_commit = self._git(git_root, "rev-parse", "HEAD")
        source_branch = self._git(git_root, "branch", "--show-current", check=False) or "detached"
        slug = self._slug(loop_id)
        branch = f"codex/{slug}"
        path = os.path.join(self.root, self._repo_key(git_root), slug)
        self._mkdir(os.path.dirname(path))
        if self._path_exists(path):
            raise GitWorkspaceError(f"工作树目录已存在：{path}")
        if self._ref_exists(git_root, branch):
            raise GitWorkspaceError(f"执行分支已存在：{branch}")
        self._git(git_root, "worktree", "add", "-b", branch, path, base_commit)
        execution_repo = path if repo_relative_path == "." else os.path.join(path, repo_relative_path)
        if not self._path_is_dir(execution_repo):
            self._git(git_root, "worktree", "remove", path, check=False)
            raise GitWorkspaceError(f"隔离工作树缺少目标执行目录：{execution_repo}")
        return {
            "source_repo": git_root,
            "source_working_directory": repo,
            "source_branch": source_branch,
            "base_commit": base_commit,
            "repo_relative_path": repo_relative_path,
            "execution_worktree_root": path,
            "execution_repo": execution_repo,
            "execution_branch": branch,
            "integration_branch": self.integration_branch,
            "workspace_status": "ready",
        }

    def checkpoint(self, workspace: dict[str, Any], loop_id: str, round_index: int) -> dict[str, Any]:
        path = str(workspace.get("execution_worktree_root") or workspace["execution_repo"])
        before = self._git(path, "rev-parse", "HEAD")
        porcelain = self._git(path, "status", "--porcelain=v1", "--untracked-files=all", check=False)
        changed_files = [line.split(maxsplit=1)[1] for line in porcelain.splitlines() if len(line.split(maxsplit=1)) == 2]
        relative_path = str(workspace.get("repo_relative_path") or ".").strip("/\\") or "."
        if relative_path != ".":
            allowed_prefix = relative_path.replace(os.sep, "/") + "/"
            boundary_violations = [
                changed
                for changed in changed_files
                if changed.replace(os.sep, "/") != relative_path.replace(os.sep, "/")
                and not changed.replace(os.sep, "/").startswith(allowed_prefix)
            ]
            if boundary_violations:
                raise GitWorkspaceError(
                    "检测到目标项目目录之外的修改："
                    + "、".join(boundary_violations[:20])
                )
        if changed_files:
            self._git(path, "add", "-A")
            self._git(
                path,
                "-c", "user.name=OpenClaw Codex",
                "-c", "user.email=openclaw-codex@local",
                "commit", "-m", f"OpenClaw {loop_id} round {round_index}",
            )
        commit_sha = self._git(path, "rev-parse", "HEAD")
        diff_stat = self._git(path, "diff", "--stat", f"{before}..{commit_sha}", check=False)
        return {
            "round": round_index,
            "commit_sha": commit_sha,
            "created_commit": commit_sha != before,
            "changed_files": changed_files,
            "diff_stat": diff_stat,
            "clean": not bool(self._git(path, "status", "--porcelain", check=False)),
        }

    def integrate(self, workspace: dict[str, Any], loop_id: str) -> dict[str, Any]:
        source_repo = str(workspace["source_repo"])
        execution_branch = str(workspace["execution_branch"])
        base_commit = str(workspace["base_commit"])
        integration_branch = str(workspace.get("integration_branch") or self.integration_branch)
        integration_path = os.path.join(self.root, self._repo_key(source_repo), "_integration")
        with self._integration_lock:
            self._mkdir(os.path.dirname(integration_path))
            if not self._path_is_dir(integration_path):
                if self._ref_exists(source_repo, integration_branch):
                    self._git(source_repo, "worktree", "add", integration_path, integration_branch)
                else:
                    self._git(source_repo, "worktree", "add", "-b", integration_branch, integration_path, base_commit)
            current_branch = self._git(integration_path, "branch", "--show-current")
            if current_branch != integration_branch:
                raise GitWorkspaceError(f"集成工作树分支异常：{current_branch}")
            if self._git(integration_path, "status", "--porcelain", check=False):
                raise GitWorkspaceError(f"集成工作树存在未提交修改：{integration_path}")
            try:
                self._git(
                    integration_path,
                    "-c", "user.name=OpenClaw Codex",
                    "-c", "user.email=openclaw-codex@local",
                    "merge", "--no-ff", execution_branch,
                    "-m", f"Integrate OpenClaw loop {loop_id}",
                )
            except GitWorkspaceError:
                self._git(integration_path, "merge", "--abort", check=False)
                raise
            merge_commit = self._git(integration_path, "rev-parse", "HEAD")
            return {
                "integration_branch": integration_branch,
                "integration_path": integration_path,
                "merge_commit": merge_commit,
                "result_commit": self._git(source_repo, "rev-parse", execution_branch),
                "workspace_status": "integrated",
            }

    def release_execution_worktree(self, workspace: dict[str, Any]) -> None:
        source_repo = str(workspace.get("source_repo") or "")
        path = str(workspace.get("execution_worktree_root") or workspace.get("execution_repo") or "")
        if source_repo and path and self._path_is_dir(path):
            self._git(source_repo, "worktree", "remove", path, check=False)
            if self.remote_target:
                self._remote(["rm", "-rf", "--", path], check=False)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)

    def _git(self, cwd: str, *args: str, check: bool = True) -> str:
        if self.remote_target:
            return self._remote(["git", "-C", cwd, *args], check=check)
        proc = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        output = proc.stdout.strip()
        if check and proc.returncode != 0:
            raise GitWorkspaceError(output or f"git {' '.join(args)} 失败")
        return output

    def _ref_exists(self, repo: str, branch: str) -> bool:
        if self.remote_target:
            return bool(self._remote(["git", "-C", repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", "&&", "printf", "yes"], check=False))
        proc = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=repo, timeout=30,
        )
        return proc.returncode == 0

    def _mkdir(self, path: str) -> None:
        if self.remote_target:
            self._remote(["mkdir", "-p", path])
        else:
            os.makedirs(path, exist_ok=True)

    def _path_exists(self, path: str) -> bool:
        if self.remote_target:
            return self._remote(["test", "-e", path, "&&", "printf", "yes"], check=False) == "yes"
        return os.path.exists(path)

    def _path_is_dir(self, path: str) -> bool:
        if self.remote_target:
            return self._remote(["test", "-d", path, "&&", "printf", "yes"], check=False) == "yes"
        return os.path.isdir(path)

    def _remote(self, parts: list[str], check: bool = True) -> str:
        ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if self.remote_port:
            ssh.extend(["-p", self.remote_port])
        if self.remote_key:
            ssh.extend(["-i", self.remote_key])
        operators = {"&&", "||", ";"}
        script = " ".join(part if part in operators else shlex.quote(str(part)) for part in parts)
        proc = subprocess.run(
            [*ssh, self.remote_target, "bash", "-lc", shlex.quote(script)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180,
        )
        output = proc.stdout.strip()
        if check and proc.returncode != 0:
            raise GitWorkspaceError(output or f"远程命令失败：{script}")
        return output

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")[:80]

    @staticmethod
    def _repo_key(repo: str) -> str:
        name = os.path.basename(repo.rstrip(os.sep)) or "repo"
        digest = hashlib.sha1(repo.encode("utf-8")).hexdigest()[:10]
        return f"{name}-{digest}"


git_workspace_service = GitWorkspaceService()
