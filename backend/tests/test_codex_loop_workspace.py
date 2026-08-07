import codex_job_service as module
from codex_job_service import CodexJobService


class FakeWorkspace:
    def __init__(self, integration_error=None):
        self.integration_error = integration_error
        self.released = False

    def prepare(self, repo, loop_id):
        return {
            "source_repo": repo, "source_branch": "main", "base_commit": "a" * 40,
            "execution_repo": f"{repo}/worktree", "execution_branch": f"codex/{loop_id}",
            "integration_branch": "codex/integration", "workspace_status": "ready",
        }

    def checkpoint(self, workspace, loop_id, round_index):
        return {"round": round_index, "commit_sha": "b" * 40, "created_commit": True, "changed_files": ["app.py"], "clean": True}

    def integrate(self, workspace, loop_id):
        if self.integration_error:
            raise RuntimeError(self.integration_error)
        return {"merge_commit": "c" * 40, "result_commit": "b" * 40, "workspace_status": "integrated"}

    def release_execution_worktree(self, workspace):
        self.released = True


def make_service(tmp_path, monkeypatch, workspace):
    monkeypatch.setattr(module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(module, "INDEX_FILE", str(tmp_path / "jobs.json"))
    monkeypatch.setattr(module, "LOOP_INDEX_FILE", str(tmp_path / "loops.json"))
    service = CodexJobService()
    service.workspace_service = workspace
    jobs = []

    def create_job(agent_id, instruction, **kwargs):
        job = {"id": f"job-{len(jobs) + 1}", "status": "queued", "agent_id": agent_id, "instruction": instruction}
        jobs.append(job)
        return job

    def wait_for_job(job_id):
        stage = jobs[int(job_id.split("-")[-1]) - 1]["instruction"]
        summary = "评估结论：通过\n测试通过" if "测试评估" in stage else "阶段完成"
        return {"id": job_id, "status": "succeeded", "summary": summary}

    service.create_job = create_job
    service._wait_for_job = wait_for_job
    return service


def append_loop(service, repo):
    service._append_loop({
        "id": "loop-test", "task_id": "task-1", "title": "测试 Loop", "instruction": "实现并验证",
        "repo": repo, "source_repo": repo, "status": "queued", "current_round": 0,
        "current_stage": "queued", "max_rounds": 1, "planner_agent_id": "wheeljack",
        "developer_agent_id": "raphael", "evaluator_agent_id": "michelangelo", "rounds": [],
        "created_at": service._now(), "updated_at": service._now(), "finished_at": None,
        "summary": "", "error": None,
    })


def test_loop_integrates_after_evaluation_passes(tmp_path, monkeypatch):
    workspace = FakeWorkspace()
    service = make_service(tmp_path, monkeypatch, workspace)
    append_loop(service, str(tmp_path / "repo"))

    service._run_loop("loop-test")

    loop = service._find_loop("loop-test")
    assert loop["status"] == "succeeded"
    assert loop["merge_commit"] == "c" * 40
    assert loop["result_commit"] == "b" * 40
    assert loop["rounds"][0]["checkpoint"]["changed_files"] == ["app.py"]
    assert loop["rounds"][0]["evaluation"]["passed"] is True
    assert workspace.released is True


def test_loop_preserves_workspace_when_integration_conflicts(tmp_path, monkeypatch):
    workspace = FakeWorkspace("merge conflict")
    service = make_service(tmp_path, monkeypatch, workspace)
    append_loop(service, str(tmp_path / "repo"))

    service._run_loop("loop-test")

    loop = service._find_loop("loop-test")
    assert loop["status"] == "needs_attention"
    assert loop["workspace_status"] == "retained_for_handoff"
    assert loop["evaluation_passed"] is True
    assert "merge conflict" in loop["handoff_reason"]
    assert workspace.released is False
