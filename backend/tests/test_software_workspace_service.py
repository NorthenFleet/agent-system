import json
import subprocess
from types import SimpleNamespace

import pytest

from services.software_workspace_service import SoftwareWorkspaceError, SoftwareWorkspaceService


def test_workspace_projection_builds_tree_and_coverage(monkeypatch):
    service = SoftwareWorkspaceService()
    payload = {
        "repository": "/repo/one-sim",
        "branch": "main",
        "commit": "abc1234",
        "dirty_count": 2,
        "documents": [
            {"path": "README.md", "name": "README.md", "extension": "md", "category": "overview", "size_bytes": 20},
            {"path": "docs/architecture/system.md", "name": "system.md", "extension": "md", "category": "design", "size_bytes": 40},
            {"path": "data_lake/structure/schema.yaml", "name": "schema.yaml", "extension": "yaml", "category": "data", "size_bytes": 60},
        ],
    }
    monkeypatch.setattr(service, "_execute", lambda config, action, path="": payload)

    result = service.list_workspace({
        "id": "one-sim",
        "name": "one-sim 仿真",
        "context": {"software_workspace": {"repository": "/repo/one-sim", "host": "192.168.31.144", "machine_name": "Mac Pro"}},
    })

    assert result["total_documents"] == 3
    assert result["machine"]["name"] == "Mac Pro"
    assert result["repository"]["commit"] == "abc1234"
    assert next(item for item in result["coverage"] if item["key"] == "design")["count"] == 1
    docs = next(item for item in result["tree"] if item["label"] == "docs")
    assert docs["children"][0]["label"] == "architecture"


def test_read_document_rejects_parent_traversal():
    service = SoftwareWorkspaceService()
    with pytest.raises(SoftwareWorkspaceError, match="无效的文档路径"):
        service.read_document({"id": "one-sim", "name": "one-sim"}, "../secrets.txt")


def test_remote_error_is_exposed_as_workspace_error(monkeypatch):
    service = SoftwareWorkspaceService()
    monkeypatch.setattr(
        "services.software_workspace_service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=json.dumps({"error": "document_not_found"}), stderr=""),
    )
    config = {"repository": "/repo", "host": "", "user": "", "port": "", "machine_name": "Mac mini"}
    with pytest.raises(SoftwareWorkspaceError, match="document_not_found"):
        service._execute(config, "read", "missing.md")


def test_git_workflow_is_scoped_and_commits_only_staged_files(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
    (repository / "tracked.md").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "tracked.md"], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-qm", "initial"], check=True)
    (repository / "tracked.md").write_text("after\n", encoding="utf-8")
    (repository / "new file.md").write_text("new\n", encoding="utf-8")

    service = SoftwareWorkspaceService()
    config = {"repository": str(repository), "host": "", "user": "", "port": "", "machine_name": "test"}
    status = service._execute(config, "git_status")

    assert status["unstaged_count"] == 2
    assert {item["path"] for item in status["changes"]} == {"tracked.md", "new file.md"}

    staged = service._execute(config, "git_stage", json.dumps({"paths": ["new file.md"]}))
    assert staged["staged_count"] == 1
    assert staged["unstaged_count"] == 1

    result = service._execute(config, "git_commit", json.dumps({"message": "add selected file"}))
    assert result["operation"] == "commit"
    assert result["unstaged_count"] == 1
    assert result["staged_count"] == 0


def test_git_paths_reject_parent_traversal():
    service = SoftwareWorkspaceService()
    with pytest.raises(SoftwareWorkspaceError, match="无效的 Git 文件路径"):
        service.git_diff({"id": "one-sim", "name": "one-sim"}, "wargame", "../outside", False)


def test_one_sim_exposes_independent_git_repositories():
    service = SoftwareWorkspaceService()
    repositories = service.git_repository_configs({
        "id": "one-sim",
        "name": "one-sim 仿真",
        "context": {
            "software_workspace": {
                "repository": "/repo/one-sim",
                "host": "192.168.31.144",
                "user": "sunyi",
            },
        },
    })

    assert [item["repository_id"] for item in repositories] == ["ai-planning", "data-lake", "wargame"]
    assert [item["repository_name"] for item in repositories] == ["AI Planning", "Data Lake", "Wargame"]
    assert [item["repository"] for item in repositories] == [
        "/repo/one-sim/ai-planning",
        "/repo/one-sim/data_lake",
        "/repo/one-sim/envs/wargame",
    ]


def test_git_repository_config_rejects_unknown_repository():
    service = SoftwareWorkspaceService()
    project = {
        "id": "one-sim",
        "name": "one-sim",
        "context": {"software_workspace": {"repository": "/repo/one-sim"}},
    }
    with pytest.raises(SoftwareWorkspaceError, match="未知的 Git 子项目仓库"):
        service.git_repository_config(project, "missing")


def test_git_commit_rejects_staged_files_outside_workspace(tmp_path):
    repository = tmp_path / "parent"
    workspace = repository / "one-sim"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
    (workspace / "inside.md").write_text("initial\n", encoding="utf-8")
    (repository / "outside.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-qm", "initial"], check=True)
    (workspace / "inside.md").write_text("inside\n", encoding="utf-8")
    (repository / "outside.md").write_text("outside\n", encoding="utf-8")

    service = SoftwareWorkspaceService()
    config = {"repository": str(workspace), "host": "", "user": "", "port": "", "machine_name": "test"}
    status = service._execute(config, "git_status")
    assert [item["path"] for item in status["changes"]] == ["inside.md"]
    service._execute(config, "git_stage", json.dumps({"paths": ["inside.md"]}))
    subprocess.run(["git", "-C", str(repository), "add", "outside.md"], check=True)

    with pytest.raises(SoftwareWorkspaceError, match="staged_changes_outside_workspace"):
        service._execute(config, "git_commit", json.dumps({"message": "scoped commit"}))
