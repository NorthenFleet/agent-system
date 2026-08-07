"""Read-only software project documentation workspace projection."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from codex_job_service import (
    CODEX_REMOTE_HOST,
    CODEX_REMOTE_PORT,
    CODEX_REMOTE_REPO,
    CODEX_REMOTE_USER,
)


_REMOTE_SCRIPT = r'''
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

root = Path(sys.argv[1]).expanduser().resolve()
action = sys.argv[2]
requested = sys.argv[3] if len(sys.argv) > 3 else ""
allowed_suffixes = {".md", ".mdx", ".yaml", ".yml", ".json"}
excluded_parts = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "coverage",
    "graphify-out", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

def allowed_path(path):
    try:
        rel = path.resolve().relative_to(root)
    except (ValueError, OSError):
        return None
    if any(part in excluded_parts or part.startswith(".") for part in rel.parts):
        return None
    if path.suffix.lower() not in allowed_suffixes:
        return None
    if path.name in {"AGENTS.md", "README.md", "README.zh-CN.md"}:
        return rel
    if not rel.parts:
        return None
    if rel.parts[0] == "docs":
        return rel
    if rel.parts[:2] in {("data_lake", "structure"), ("data_lake", "rules")}:
        return rel
    if "docs" in rel.parts[:4]:
        return rel
    if path.name.lower().startswith("readme") and len(rel.parts) <= 4:
        return rel
    return None

def category_for(rel):
    value = rel.as_posix().lower()
    name = rel.name.lower()
    if value in {"agents.md", "readme.md", "readme.zh-cn.md"} or "codex_development_map" in value:
        return "overview"
    if value.startswith("data_lake/structure/") or "schema" in name or "数据结构" in value:
        return "data"
    if "/api" in value or "api_" in name or "interface" in value or "contract" in value or "接口" in value:
        return "api"
    if "test" in value or "verification" in value or "验收" in value or "验证" in value:
        return "test"
    if "operation" in value or "deploy" in value or "topology" in value or "运维" in value or "部署" in value:
        return "operations"
    if "architecture" in value or "design" in value or "架构" in value or "设计" in value:
        return "design"
    return "logic"

def git(*args):
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=4, check=False
        ).stdout.strip()
    except Exception:
        return ""

def run_git(args, timeout=12):
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return None

def request_payload():
    if not requested:
        return {}
    try:
        value = json.loads(requested)
    except json.JSONDecodeError:
        raise SystemExit(json.dumps({"error": "invalid_git_request"}))
    if not isinstance(value, dict):
        raise SystemExit(json.dumps({"error": "invalid_git_request"}))
    return value

def safe_git_path(value):
    if not isinstance(value, str) or not value or len(value) > 500 or "\x00" in value:
        return None
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] == ".git":
        return None
    return rel.as_posix()

def status_name(code):
    return {
        "M": "modified", "A": "added", "D": "deleted", "R": "renamed",
        "C": "copied", "U": "conflicted", "?": "untracked", "!": "ignored",
    }.get(code, "unchanged")

def workspace_scope_prefix():
    top_level_value = git("rev-parse", "--show-toplevel")
    try:
        prefix = root.relative_to(Path(top_level_value).resolve()).as_posix().strip("/")
    except (ValueError, OSError):
        return ""
    if prefix in {"", "."}:
        return ""
    return f"{prefix}/" if prefix else ""

def git_status_payload():
    result = run_git(["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."])
    if result is None:
        return {"error": "git_status_timeout"}
    if result.returncode != 0:
        return {"error": (result.stderr or "git_status_failed").strip()}
    records = result.stdout.split("\x00")
    scope_prefix = workspace_scope_prefix()

    def relative_status_path(value):
        return value[len(scope_prefix):] if scope_prefix and value.startswith(scope_prefix) else value

    changes = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record or len(record) < 4:
            continue
        index_code, worktree_code = record[0], record[1]
        path = relative_status_path(record[3:])
        original_path = ""
        if index_code in {"R", "C"} and index < len(records):
            original_path = relative_status_path(records[index])
            index += 1
        changes.append({
            "path": path,
            "original_path": original_path,
            "index_status": status_name(index_code),
            "worktree_status": status_name(worktree_code),
            "index_code": index_code,
            "worktree_code": worktree_code,
            "staged": index_code not in {" ", "?", "!"},
            "unstaged": worktree_code not in {" ", "!"} or index_code == "?",
        })
    branch = git("branch", "--show-current")
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    ahead = behind = 0
    if upstream:
        counts = git("rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
        if len(counts) == 2:
            ahead, behind = int(counts[0]), int(counts[1])
    log_result = run_git(["log", "-10", "--pretty=format:%h%x1f%an%x1f%aI%x1f%s%x1e", "--", "."])
    commits = []
    if log_result and log_result.returncode == 0:
        for row in log_result.stdout.strip("\x1e\n").split("\x1e"):
            fields = row.strip().split("\x1f", 3)
            if len(fields) == 4:
                commits.append({"hash": fields[0], "author": fields[1], "date": fields[2], "subject": fields[3]})
    changes.sort(key=lambda item: (not item["staged"], item["path"].lower()))
    total_changes = len(changes)
    staged_count = sum(1 for item in changes if item["staged"])
    unstaged_count = sum(1 for item in changes if item["unstaged"])
    visible_changes = changes[:800]
    return {
        "repository": str(root),
        "branch": branch,
        "commit": git("rev-parse", "--short", "HEAD"),
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "changes": visible_changes,
        "total_changes": total_changes,
        "truncated": total_changes > len(visible_changes),
        "staged_count": staged_count,
        "unstaged_count": unstaged_count,
        "commits": commits,
    }

def requested_paths(payload):
    values = payload.get("paths")
    if not isinstance(values, list) or not values or len(values) > 200:
        raise SystemExit(json.dumps({"error": "invalid_git_paths"}))
    paths = []
    for value in values:
        path = safe_git_path(value)
        if path is None:
            raise SystemExit(json.dumps({"error": "invalid_git_path"}))
        paths.append(path)
    known = {item["path"] for item in git_status_payload().get("changes", [])}
    if any(path not in known for path in paths):
        raise SystemExit(json.dumps({"error": "git_path_not_changed"}))
    return list(dict.fromkeys(paths))

if not root.is_dir():
    raise SystemExit(json.dumps({"error": "repository_not_found", "repository": str(root)}))

if action == "scan":
    rows = []
    candidates = []
    for name in ("AGENTS.md", "README.md", "README.zh-CN.md"):
        path = root / name
        if path.is_file():
            candidates.append(path)
    scan_roots = [
        root / "docs",
        root / "data_lake" / "structure",
        root / "data_lake" / "rules" / "v4",
        root / "ai-planning" / "docs",
        root / "envs" / "wargame" / "docs",
    ]
    for scan_root in scan_roots:
        if scan_root.is_dir():
            candidates.extend(scan_root.rglob("*"))
    for path in candidates:
        if not path.is_file():
            continue
        rel = allowed_path(path)
        if rel is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append({
            "path": rel.as_posix(),
            "name": path.name,
            "extension": path.suffix.lower().lstrip("."),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "category": category_for(rel),
        })
        if len(rows) >= 800:
            break
    rows.sort(key=lambda row: row["path"].lower())
    dirty_lines = [line for line in git("status", "--porcelain", "--", ".").splitlines() if line.strip()]
    print(json.dumps({
        "repository": str(root),
        "branch": git("branch", "--show-current"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty_count": len(dirty_lines),
        "documents": rows,
    }, ensure_ascii=False))
elif action == "read":
    rel = PurePosixPath(requested)
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(json.dumps({"error": "invalid_document_path"}))
    path = root.joinpath(*rel.parts)
    safe_rel = allowed_path(path)
    if safe_rel is None or safe_rel.as_posix() != rel.as_posix() or not path.is_file():
        raise SystemExit(json.dumps({"error": "document_not_found"}))
    content = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(content) > 300000
    if truncated:
        content = content[:300000]
    print(json.dumps({
        "path": rel.as_posix(),
        "name": path.name,
        "extension": path.suffix.lower().lstrip("."),
        "category": category_for(rel),
        "content": content,
        "truncated": truncated,
        "size_bytes": path.stat().st_size,
    }, ensure_ascii=False))
elif action == "git_status":
    print(json.dumps(git_status_payload(), ensure_ascii=False))
elif action == "git_diff":
    payload = request_payload()
    path = safe_git_path(payload.get("path"))
    if path is None:
        raise SystemExit(json.dumps({"error": "invalid_git_path"}))
    item = next((row for row in git_status_payload().get("changes", []) if row["path"] == path), None)
    if item is None:
        raise SystemExit(json.dumps({"error": "git_path_not_changed"}))
    staged = bool(payload.get("staged"))
    if staged:
        args = ["diff", "--cached", "--no-ext-diff", "--", path]
    elif item["index_code"] == "?":
        args = ["diff", "--no-index", "--no-ext-diff", "--", "/dev/null", str(root / path)]
    else:
        args = ["diff", "--no-ext-diff", "--", path]
    result = run_git(args)
    if result is None:
        raise SystemExit(json.dumps({"error": "git_diff_timeout"}))
    if result.returncode not in {0, 1}:
        raise SystemExit(json.dumps({"error": (result.stderr or "git_diff_failed").strip()}))
    content = result.stdout
    truncated = len(content) > 400000
    print(json.dumps({
        "path": path, "staged": staged, "content": content[:400000],
        "truncated": truncated, "binary": "Binary files" in content,
    }, ensure_ascii=False))
elif action in {"git_stage", "git_unstage"}:
    payload = request_payload()
    paths = requested_paths(payload)
    args = (["add", "-A", "--"] if action == "git_stage" else ["restore", "--staged", "--"]) + paths
    result = run_git(args)
    if result is None:
        raise SystemExit(json.dumps({"error": "git_operation_timeout"}))
    if result.returncode != 0:
        raise SystemExit(json.dumps({"error": (result.stderr or "git_operation_failed").strip()}))
    response = git_status_payload()
    response["operation"] = "stage" if action == "git_stage" else "unstage"
    response["affected_paths"] = paths
    print(json.dumps(response, ensure_ascii=False))
elif action == "git_commit":
    payload = request_payload()
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > 2000 or "\x00" in message:
        raise SystemExit(json.dumps({"error": "invalid_commit_message"}))
    staged = run_git(["diff", "--cached", "--quiet"])
    if staged is None:
        raise SystemExit(json.dumps({"error": "git_operation_timeout"}))
    if staged.returncode == 0:
        raise SystemExit(json.dumps({"error": "nothing_staged"}))
    if staged.returncode != 1:
        raise SystemExit(json.dumps({"error": (staged.stderr or "git_status_failed").strip()}))
    scope_prefix = workspace_scope_prefix()
    if scope_prefix:
        all_staged = run_git(["diff", "--cached", "--name-only", "-z"])
        if all_staged is None:
            raise SystemExit(json.dumps({"error": "git_operation_timeout"}))
        staged_paths = [value for value in all_staged.stdout.split("\x00") if value]
        if any(not value.startswith(scope_prefix) for value in staged_paths):
            raise SystemExit(json.dumps({"error": "staged_changes_outside_workspace"}))
    result = run_git(["commit", "-m", message.strip()], timeout=30)
    if result is None:
        raise SystemExit(json.dumps({"error": "git_commit_timeout"}))
    if result.returncode != 0:
        raise SystemExit(json.dumps({"error": (result.stderr or result.stdout or "git_commit_failed").strip()}))
    response = git_status_payload()
    response["operation"] = "commit"
    response["message"] = message.strip()
    response["output"] = result.stdout.strip()
    print(json.dumps(response, ensure_ascii=False))
else:
    raise SystemExit(json.dumps({"error": "invalid_action"}))
'''


class SoftwareWorkspaceError(RuntimeError):
    pass


class SoftwareWorkspaceService:
    category_labels = {
        "overview": "项目总览",
        "design": "设计与架构",
        "data": "数据结构",
        "logic": "功能逻辑",
        "api": "接口与契约",
        "test": "测试与验证",
        "operations": "部署与运维",
    }

    def project_config(self, project: dict[str, Any]) -> dict[str, str]:
        context = project.get("context") if isinstance(project.get("context"), dict) else {}
        configured = context.get("software_workspace") if isinstance(context.get("software_workspace"), dict) else {}
        identity = f"{project.get('id', '')} {project.get('name', '')}".lower()
        repository = str(configured.get("repository") or "").strip()
        if not repository and ("one-sim" in identity or "one_sim" in identity):
            repository = CODEX_REMOTE_REPO
        if not repository:
            raise SoftwareWorkspaceError("该软件项目尚未配置代码仓库")
        host = str(configured.get("host") or CODEX_REMOTE_HOST or "").strip()
        user = str(configured.get("user") or CODEX_REMOTE_USER or "").strip()
        port = str(configured.get("port") or CODEX_REMOTE_PORT or "").strip()
        machine_name = str(configured.get("machine_name") or ("Mac Pro" if host else "Mac mini")).strip()
        return {
            "repository": os.path.abspath(os.path.expanduser(repository)),
            "host": host,
            "user": user,
            "port": port,
            "machine_name": machine_name,
        }

    def git_repository_configs(self, project: dict[str, Any]) -> list[dict[str, str]]:
        base = self.project_config(project)
        context = project.get("context") if isinstance(project.get("context"), dict) else {}
        configured = context.get("software_workspace") if isinstance(context.get("software_workspace"), dict) else {}
        configured_repositories = configured.get("repositories")
        identity = f"{project.get('id', '')} {project.get('name', '')}".lower()
        if isinstance(configured_repositories, list) and configured_repositories:
            definitions = configured_repositories
        elif "one-sim" in identity or "one_sim" in identity:
            definitions = [
                {"id": "ai-planning", "name": "AI Planning", "path": "ai-planning"},
                {"id": "data-lake", "name": "Data Lake", "path": "data_lake"},
                {"id": "wargame", "name": "Wargame", "path": "envs/wargame"},
            ]
        else:
            definitions = [{"id": "main", "name": project.get("name") or "主仓库", "path": "."}]

        base_path = os.path.abspath(base["repository"])
        repositories = []
        seen = set()
        for item in definitions:
            if not isinstance(item, dict):
                continue
            repository_id = str(item.get("id") or "").strip()
            relative_path = str(item.get("path") or ".").strip()
            if not repository_id or repository_id in seen or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", repository_id):
                continue
            candidate = os.path.abspath(os.path.join(base_path, relative_path))
            try:
                if os.path.commonpath([base_path, candidate]) != base_path:
                    continue
            except ValueError:
                continue
            repositories.append({
                **base,
                "repository_id": repository_id,
                "repository_name": str(item.get("name") or repository_id).strip(),
                "repository": candidate,
            })
            seen.add(repository_id)
        if not repositories:
            raise SoftwareWorkspaceError("该软件项目没有可用的 Git 仓库配置")
        return repositories

    def git_repository_config(self, project: dict[str, Any], repository_id: str) -> dict[str, str]:
        selected = next(
            (item for item in self.git_repository_configs(project) if item["repository_id"] == repository_id),
            None,
        )
        if selected is None:
            raise SoftwareWorkspaceError("未知的 Git 子项目仓库")
        return selected

    def list_workspace(self, project: dict[str, Any]) -> dict[str, Any]:
        config = self.project_config(project)
        payload = self._execute(config, "scan")
        documents = payload.get("documents") if isinstance(payload.get("documents"), list) else []
        counts = {key: 0 for key in self.category_labels}
        for document in documents:
            category = str(document.get("category") or "logic")
            if category in counts:
                counts[category] += 1
        coverage = [
            {
                "key": key,
                "label": label,
                "count": counts[key],
                "status": "available" if counts[key] else "missing",
            }
            for key, label in self.category_labels.items()
        ]
        return {
            "project_id": project.get("id"),
            "machine": {
                "name": config["machine_name"],
                "host": config["host"] or "localhost",
                "user": config["user"] or None,
                "status": "online",
            },
            "repository": {
                "path": payload.get("repository") or config["repository"],
                "branch": payload.get("branch") or "",
                "commit": payload.get("commit") or "",
                "dirty_count": int(payload.get("dirty_count") or 0),
            },
            "documents": documents,
            "tree": self._build_tree(documents),
            "coverage": coverage,
            "total_documents": len(documents),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def read_document(self, project: dict[str, Any], path: str) -> dict[str, Any]:
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
            raise SoftwareWorkspaceError("无效的文档路径")
        config = self.project_config(project)
        payload = self._execute(config, "read", normalized.as_posix())
        payload["project_id"] = project.get("id")
        return payload

    def list_git_repositories(self, project: dict[str, Any]) -> dict[str, Any]:
        repositories = []
        for config in self.git_repository_configs(project):
            try:
                payload = self._execute(config, "git_status")
                payload.update({
                    "project_id": project.get("id"),
                    "repository_id": config["repository_id"],
                    "repository_name": config["repository_name"],
                })
            except SoftwareWorkspaceError as exc:
                payload = {
                    "project_id": project.get("id"),
                    "repository_id": config["repository_id"],
                    "repository_name": config["repository_name"],
                    "repository": config["repository"],
                    "branch": "",
                    "commit": "",
                    "upstream": "",
                    "ahead": 0,
                    "behind": 0,
                    "staged_count": 0,
                    "unstaged_count": 0,
                    "total_changes": 0,
                    "truncated": False,
                    "changes": [],
                    "commits": [],
                    "error": str(exc),
                }
            repositories.append(payload)
        return {"project_id": project.get("id"), "repositories": repositories}

    def git_status(self, project: dict[str, Any], repository_id: str) -> dict[str, Any]:
        config = self.git_repository_config(project, repository_id)
        payload = self._execute(config, "git_status")
        payload.update({
            "project_id": project.get("id"),
            "repository_id": config["repository_id"],
            "repository_name": config["repository_name"],
        })
        return payload

    def git_diff(self, project: dict[str, Any], repository_id: str, path: str, staged: bool = False) -> dict[str, Any]:
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
            raise SoftwareWorkspaceError("无效的 Git 文件路径")
        request = json.dumps({"path": normalized.as_posix(), "staged": staged}, ensure_ascii=False)
        config = self.git_repository_config(project, repository_id)
        payload = self._execute(config, "git_diff", request)
        payload.update({"project_id": project.get("id"), "repository_id": repository_id})
        return payload

    def git_stage(self, project: dict[str, Any], repository_id: str, paths: list[str]) -> dict[str, Any]:
        return self._git_paths_action(project, repository_id, "git_stage", paths)

    def git_unstage(self, project: dict[str, Any], repository_id: str, paths: list[str]) -> dict[str, Any]:
        return self._git_paths_action(project, repository_id, "git_unstage", paths)

    def git_commit(self, project: dict[str, Any], repository_id: str, message: str) -> dict[str, Any]:
        request = json.dumps({"message": message}, ensure_ascii=False)
        config = self.git_repository_config(project, repository_id)
        payload = self._execute(config, "git_commit", request)
        payload.update({
            "project_id": project.get("id"),
            "repository_id": config["repository_id"],
            "repository_name": config["repository_name"],
        })
        return payload

    def _git_paths_action(self, project: dict[str, Any], repository_id: str, action: str, paths: list[str]) -> dict[str, Any]:
        normalized = []
        for path in paths:
            value = PurePosixPath(path)
            if value.is_absolute() or ".." in value.parts or not value.parts:
                raise SoftwareWorkspaceError("无效的 Git 文件路径")
            normalized.append(value.as_posix())
        request = json.dumps({"paths": normalized}, ensure_ascii=False)
        config = self.git_repository_config(project, repository_id)
        payload = self._execute(config, action, request)
        payload.update({
            "project_id": project.get("id"),
            "repository_id": config["repository_id"],
            "repository_name": config["repository_name"],
        })
        return payload

    def _execute(self, config: dict[str, str], action: str, path: str = "") -> dict[str, Any]:
        command = ["python3", "-c", _REMOTE_SCRIPT, config["repository"], action, path]
        stdin_payload = None
        if config["host"]:
            target = f"{config['user']}@{config['host']}" if config["user"] else config["host"]
            ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6"]
            if config["port"]:
                ssh.extend(["-p", config["port"]])
            remote_command = " ".join(shlex.quote(value) for value in ["python3", "-", config["repository"], action, path])
            command = [*ssh, target, remote_command]
            stdin_payload = _REMOTE_SCRIPT
        try:
            timeout = 50 if action == "git_commit" else 30
            result = subprocess.run(
                command,
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SoftwareWorkspaceError(f"无法连接研发仓库：{exc}") from exc
        raw = (result.stdout or result.stderr).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SoftwareWorkspaceError("研发仓库返回了无法解析的数据") from exc
        if result.returncode != 0 or payload.get("error"):
            raise SoftwareWorkspaceError(str(payload.get("error") or "研发仓库读取失败"))
        return payload

    def _build_tree(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        root: dict[str, Any] = {}
        for document in documents:
            current = root
            parts = PurePosixPath(str(document.get("path") or "")).parts
            if not parts:
                continue
            for index, part in enumerate(parts):
                node = current.setdefault(part, {"children": {}, "document": None})
                if index == len(parts) - 1:
                    node["document"] = document
                current = node["children"]

        def serialize(values: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[dict[str, Any]]:
            rows = []
            for name, value in values.items():
                path = "/".join((*prefix, name))
                children = serialize(value["children"], (*prefix, name))
                document = value["document"]
                rows.append({
                    "id": path,
                    "label": name,
                    "path": document.get("path") if document else "",
                    "kind": "file" if document else "folder",
                    "category": document.get("category") if document else "",
                    "extension": document.get("extension") if document else "",
                    "children": children,
                })
            rows.sort(key=lambda row: (row["kind"] == "file", row["label"].lower()))
            return rows

        return serialize(root)


software_workspace_service = SoftwareWorkspaceService()
