import pytest
from fastapi import HTTPException

from routers import codex_jobs_router


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        ("software_requires_plan", "必须先生成自动化计划"),
        ("document_forbidden", "文档任务不能进入"),
    ],
)
def test_managed_project_targets_cannot_bypass_codex_runner(monkeypatch, policy, message):
    monkeypatch.setattr(
        codex_jobs_router.development_automation_service,
        "target_execution_policy",
        lambda _task_id: policy,
    )

    with pytest.raises(HTTPException) as exc:
        codex_jobs_router._enforce_target_policy("target-1")

    assert exc.value.status_code == 409
    assert message in str(exc.value.detail)


def test_unmanaged_compatibility_target_keeps_legacy_route(monkeypatch):
    monkeypatch.setattr(
        codex_jobs_router.development_automation_service,
        "target_execution_policy",
        lambda _task_id: "unmanaged_compatibility",
    )

    assert codex_jobs_router._enforce_target_policy("legacy-target") is None
