import subprocess
from pathlib import Path

import pytest

from services.git_workspace_service import GitWorkspaceError, GitWorkspaceService


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout.strip()


def make_repo(path):
    path.mkdir()
    git(path, "init", "-b", "main")
    (path / "app.txt").write_text("base\n", encoding="utf-8")
    git(path, "add", "app.txt")
    git(path, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")


def test_worktree_checkpoint_and_integration_branch(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    service = GitWorkspaceService(str(tmp_path / "worktrees"), "codex/integration-test")

    workspace = service.prepare(str(repo), "loop-1")
    worktree = tmp_path / "worktrees" / next((tmp_path / "worktrees").iterdir()).name / "loop-1"
    assert workspace["execution_repo"] == str(worktree)
    assert git(repo, "branch", "--show-current") == "main"

    (worktree / "app.txt").write_text("base\nfeature\n", encoding="utf-8")
    evidence = service.checkpoint(workspace, "loop-1", 1)
    assert evidence["created_commit"] is True
    assert "app.txt" in evidence["changed_files"]
    assert git(repo, "show", f"{workspace['execution_branch']}:app.txt") == "base\nfeature"

    integrated = service.integrate(workspace, "loop-1")
    assert integrated["integration_branch"] == "codex/integration-test"
    assert git(repo, "show", "codex/integration-test:app.txt") == "base\nfeature"
    assert git(repo, "show", "main:app.txt") == "base"

    service.release_execution_worktree(workspace)
    assert not worktree.exists()


def test_integration_conflict_retains_execution_worktree(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    service = GitWorkspaceService(str(tmp_path / "worktrees"), "codex/integration-test")

    first = service.prepare(str(repo), "loop-a")
    first_path = tmp_path / "worktrees" / next((tmp_path / "worktrees").iterdir()).name / "loop-a"
    (first_path / "app.txt").write_text("first\n", encoding="utf-8")
    service.checkpoint(first, "loop-a", 1)
    service.integrate(first, "loop-a")

    second = service.prepare(str(repo), "loop-b")
    second_path = tmp_path / "worktrees" / next((tmp_path / "worktrees").iterdir()).name / "loop-b"
    (second_path / "app.txt").write_text("second\n", encoding="utf-8")
    service.checkpoint(second, "loop-b", 1)
    with pytest.raises(GitWorkspaceError):
        service.integrate(second, "loop-b")
    assert second_path.exists()


def test_monorepo_subdirectory_is_execution_boundary(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    target = repo / "one-sim"
    target.mkdir()
    (target / "sim.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "one-sim/sim.txt")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "add one-sim")
    service = GitWorkspaceService(str(tmp_path / "worktrees"), "codex/integration-test")

    workspace = service.prepare(str(target), "loop-subdir")

    assert workspace["source_repo"] == str(repo)
    assert workspace["source_working_directory"] == str(target)
    assert workspace["repo_relative_path"] == "one-sim"
    assert workspace["execution_repo"] == str(
        tmp_path / "worktrees" / next((tmp_path / "worktrees").iterdir()).name / "loop-subdir" / "one-sim"
    )

    execution_target = Path(workspace["execution_repo"])
    (execution_target / "sim.txt").write_text("base\nfeature\n", encoding="utf-8")
    evidence = service.checkpoint(workspace, "loop-subdir", 1)
    assert evidence["created_commit"] is True
    assert evidence["changed_files"] == ["one-sim/sim.txt"]


def test_monorepo_checkpoint_rejects_out_of_boundary_changes(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    target = repo / "one-sim"
    target.mkdir()
    (target / "sim.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "one-sim/sim.txt")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "add one-sim")
    service = GitWorkspaceService(str(tmp_path / "worktrees"), "codex/integration-test")
    workspace = service.prepare(str(target), "loop-boundary")

    worktree_root = Path(workspace["execution_worktree_root"])
    (worktree_root / "app.txt").write_text("base\noutside\n", encoding="utf-8")

    with pytest.raises(GitWorkspaceError, match="目标项目目录之外"):
        service.checkpoint(workspace, "loop-boundary", 1)
