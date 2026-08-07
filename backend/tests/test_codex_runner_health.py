from types import SimpleNamespace

import codex_job_service as module
from codex_job_service import CodexJobService


def configure_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(module, "INDEX_FILE", str(tmp_path / "jobs.json"))
    monkeypatch.setattr(module, "LOOP_INDEX_FILE", str(tmp_path / "loops.json"))


def test_local_runner_health_executes_codex_version_and_checks_repo(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\n", encoding="utf-8")
    codex.chmod(0o755)
    monkeypatch.setattr(module, "CODEX_RUNNER_MODE", "local")
    monkeypatch.setattr(module, "CODEX_BIN", str(codex))
    monkeypatch.setattr(module, "DEFAULT_REPO", str(repo))

    def fake_run(command, **_kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="codex-cli 1.2.3\n", stderr="")
        if command[-1] == "--show-prefix":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout=f"{repo}\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    service = CodexJobService()

    health = service.runner_health(force=True)

    assert health["available"] is True
    assert health["reachable"] is True
    assert health["codex_version"] == "codex-cli 1.2.3"
    assert health["repo_exists"] is True
    assert health["repo_writable"] is True
    assert health["git_root"] == str(repo)
    assert health["repo_relative_path"] == "."
    assert health["repo_is_git_root"] is True


def test_ssh_runner_health_parses_remote_probe(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "CODEX_RUNNER_MODE", "ssh")
    monkeypatch.setattr(module, "CODEX_REMOTE_HOST", "192.0.2.10")
    monkeypatch.setattr(module, "CODEX_REMOTE_USER", "codex")
    monkeypatch.setattr(module, "CODEX_REMOTE_REPO", "/srv/one-sim")
    monkeypatch.setattr(module, "CODEX_REMOTE_SSH_KEY", "")

    def fake_run(command, **_kwargs):
        assert command[0] == "ssh"
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "CODEX_RC:0\n"
                "CODEX_VERSION:codex-cli 2.0\n"
                "REPO_EXISTS:yes\n"
                "REPO_WRITABLE:yes\n"
                "GIT_ROOT:/srv\n"
                "GIT_PREFIX:one-sim/\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    service = CodexJobService()

    health = service.runner_health(force=True)

    assert health["available"] is True
    assert health["reachable"] is True
    assert health["codex_executable"] is True
    assert health["repo"] == "/srv/one-sim"
    assert health["git_root"] == "/srv"
    assert health["repo_relative_path"] == "one-sim"
    assert health["repo_is_git_root"] is False
