import sqlite3

import pytest

from services.work_run_service import (
    InvalidWorkTransition,
    WorkRunLeaseConflict,
    WorkRunService,
)
from unified_data_manager import UnifiedDataManager


def _project_document(*, title: str = "Canonical task", include_task: bool = True) -> dict:
    task = {
        "id": "task-1",
        "title": title,
        "status": "ready",
        "priority": "high",
        "development_points": [
            {"id": "point-1", "title": "Acceptance", "status": "ready", "weight": 1}
        ],
    }
    return {
        "projects": [
            {
                "id": "project-1",
                "name": "Company OS",
                "status": "active",
                "created_at": "2026-07-14T00:00:00+00:00",
                "updated_at": "2026-07-14T00:00:00+00:00",
                "tasks": [task] if include_task else [],
            }
        ],
        "logs": [],
    }


def test_claim_transition_artifact_and_retry_use_canonical_store(tmp_path):
    db_path = str(tmp_path / "unified.db")
    manager = UnifiedDataManager(db_path)
    manager.save_projects_document(_project_document())
    service = WorkRunService(db_path)

    run = service.claim(
        dispatch_id="elastic-task-1",
        project_id="project-1",
        task_id="task-1",
        development_point_id="point-1",
        agent_id="raphael-1",
        executor="codex-cli",
        workspace="/tmp/workspace",
    )
    assert run["status"] == "claimed"
    assert run["attempt"] == 1

    same_run = service.claim(
        dispatch_id="elastic-task-1",
        project_id="project-1",
        task_id="task-1",
        agent_id="raphael-1",
        executor="codex-cli",
    )
    assert same_run["id"] == run["id"]

    running = service.transition(run["id"], "running", actor="raphael-1")
    assert running["started_at"]
    review = service.transition(
        run["id"],
        "review",
        actor="raphael-1",
        result_summary="implementation ready",
        execution_result={"returncode": 0},
    )
    artifact = service.add_artifact(
        run["id"],
        artifact_type="runner-output",
        title="Codex output",
        uri="/tmp/workspace/RUNNER_OUTPUT.log",
    )
    assert artifact["run_id"] == run["id"]
    assert service.get(run["id"])["artifacts"][0]["artifact_type"] == "runner-output"

    with pytest.raises(InvalidWorkTransition):
        service.transition(run["id"], "claimed")

    completed = service.transition(review["id"], "completed", actor="reviewer")
    assert completed["ended_at"]

    retry = service.claim(
        dispatch_id="elastic-task-1",
        project_id="project-1",
        task_id="task-1",
        agent_id="raphael-1",
        executor="codex-cli",
    )
    assert retry["attempt"] == 2
    assert retry["id"] != run["id"]

    with sqlite3.connect(db_path) as conn:
        task_status = conn.execute("SELECT status FROM project_tasks WHERE id='task-1'").fetchone()[0]
    assert task_status == "claimed"


def test_active_lease_rejects_a_different_agent(tmp_path):
    service = WorkRunService(str(tmp_path / "lease.db"))
    service.claim(
        dispatch_id="dispatch-1",
        agent_id="agent-a",
        executor="codex-cli",
        lease_seconds=300,
    )

    with pytest.raises(WorkRunLeaseConflict):
        service.claim(
            dispatch_id="dispatch-1",
            agent_id="agent-b",
            executor="codex-cli",
            lease_seconds=300,
        )


def test_incremental_project_save_preserves_row_identity_and_work_runs(tmp_path):
    db_path = str(tmp_path / "incremental.db")
    manager = UnifiedDataManager(db_path)
    manager.save_projects_document(_project_document())
    service = WorkRunService(db_path)
    run = service.claim(
        dispatch_id="dispatch-1",
        project_id="project-1",
        task_id="task-1",
        agent_id="agent-a",
        executor="codex-cli",
    )

    with sqlite3.connect(db_path) as conn:
        project_rowid = conn.execute("SELECT rowid FROM projects WHERE id='project-1'").fetchone()[0]

    manager.save_projects_document(_project_document(title="Updated title"))

    with sqlite3.connect(db_path) as conn:
        updated_rowid = conn.execute("SELECT rowid FROM projects WHERE id='project-1'").fetchone()[0]
        title = conn.execute("SELECT title FROM project_tasks WHERE id='task-1'").fetchone()[0]
        run_count = conn.execute("SELECT COUNT(*) FROM work_runs WHERE id=?", (run["id"],)).fetchone()[0]
    assert updated_rowid == project_rowid
    assert title == "Updated title"
    assert run_count == 1

    manager.save_projects_document(_project_document(include_task=False))
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM project_tasks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM work_runs WHERE id=?", (run["id"],)).fetchone()[0] == 1


def test_unbound_document_asset_uses_null_foreign_key(tmp_path):
    db_path = str(tmp_path / "document.db")
    manager = UnifiedDataManager(db_path)
    manager.save_projects_document({
        "projects": [{
            "id": "document-1",
            "name": "Document",
            "project_type": "document",
            "document_spec": {
                "chapters": [],
                "assets": [{"id": "asset-1", "title": "Cover"}],
            },
            "tasks": [],
        }],
        "logs": [],
    })

    with sqlite3.connect(db_path) as conn:
        section_id = conn.execute(
            "SELECT section_id FROM document_assets WHERE id='asset-1'"
        ).fetchone()[0]
    assert section_id is None
