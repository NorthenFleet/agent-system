"""Public projections cannot leak or mutate the private cluster execution fence."""
from copy import deepcopy
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.projects_v3 as projects
import routers.command_center_router as command_router
from routers.auth_router import get_current_user
from services.work_run_service import public_work_run
from tests.test_cluster_step_authority import approved, harness  # noqa: F401
from tests.test_cluster_execution import request, PRINCIPAL


@pytest.mark.parametrize("executor", ["cluster-readonly-v1", "unexpected-legacy-name"])
def test_cluster_projection_is_allowlisted_and_does_not_mutate_private_state(executor):
    raw = {"id": "wrun-1", "executor": executor, "status": "running",
           "workspace": "/private/path", "prompt_path": "/private/prompt",
           "lease_owner": "private-owner", "unexpected": "private-extension",
           "input_context": {"request": {**request().model_dump(), "private_key": "/private/key"},
                             "_cluster_step_fence": {"lease_sha256": "private-fence"},
                             "_at_most_once": {"binding_sha256": "private-binding"}},
           "execution_result": {"status": "succeeded", "remote_outcome": "confirmed",
                                "approval_id": "approval-1", "contract_hash": "public-contract",
                                "log": "Linux 6.8 x86_64", "private_key": "/private/key",
                                "parameters_summary": {"private_key": "/private/key"}},
           "events": [{"id": "event-1", "metadata": {"attempt": 1, "binding_sha256": "private-binding"}}],
           "metrics": {"private_key": "/private/key"},
           "artifacts": [{"uri": "/private/artifact"}]}
    before = deepcopy(raw)
    view = public_work_run(raw)
    assert raw == before
    assert "private" not in json.dumps(view)
    assert view["input_context"] == {"request": request().model_dump()}
    assert view["execution_result"]["approval_id"] == "approval-1"
    assert view["execution_result"]["contract_hash"] == "public-contract"
    assert view["events"][0]["metadata"] == {"attempt": 1}


def test_generic_projection_preserves_existing_contract():
    raw = {"executor": "openclaw", "input_context": {"task": 3, "_legacy": [1]}, "workspace": "/work"}
    view = public_work_run(raw)
    assert view == raw and view is not raw
    view["input_context"]["_legacy"].append(2)
    assert raw["input_context"]["_legacy"] == [1]
    assert public_work_run(None) is None


@pytest.fixture()
def api(approved, monkeypatch):
    _make, ledger, _calls, service, mission_id, _step, authority = approved
    run, _ = authority.claim(request(), PRINCIPAL, "clusterprobe")
    monkeypatch.setattr(projects, "work_run_service", ledger)
    monkeypatch.setattr(command_router, "command_center_service", service)
    app = FastAPI()
    app.include_router(projects.router)
    app.include_router(command_router.router)
    app.dependency_overrides[get_current_user] = lambda: dict(PRINCIPAL)
    return TestClient(app, raise_server_exceptions=False), ledger, service, mission_id, run


def test_detail_and_list_hide_control_metadata_but_internal_ledger_retains_it(api):
    client, ledger, _, _, run = api
    detail = client.get(f"/api/v3/work-runs/{run['id']}")
    listing = client.get("/api/v3/work-runs")
    assert detail.status_code == listing.status_code == 200
    for response in (detail, listing):
        assert "_cluster_step_fence" not in response.text
        assert "_at_most_once" not in response.text and "binding_sha256" not in response.text
        assert "lease_sha256" not in response.text
    assert "_cluster_step_fence" in ledger.get(run["id"])["input_context"]


@pytest.mark.parametrize("status", ["running", "review", "completed", "blocked", "failed", "cancelled"])
def test_cluster_transition_returns_409_without_writing(api, status):
    client, ledger, service, mission_id, run = api
    before = ledger.get(run["id"])

    def snapshot():
        # get_mission refreshes canonical projection timestamps; inspect durable
        # rows directly so the assertion itself cannot manufacture a mutation.
        tables = ("orchestration_missions", "mission_runs", "mission_steps",
                  "mission_step_approvals", "mission_events", "workflow_runs")
        with service.connect() as conn:
            return {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                    for table in tables}

    mission_before = snapshot()
    response = client.post(f"/api/v3/work-runs/{run['id']}/transition", json={"status": status})
    assert response.status_code == 409
    assert response.json()["detail"] == "Work run is controlled by its active execution authority"
    assert ledger.get(run["id"]) == before
    assert snapshot() == mission_before


def test_generic_transition_and_not_found_remain_compatible(api):
    client, ledger, *_ = api
    run = ledger.claim(dispatch_id="generic", agent_id="worker", executor="openclaw")
    response = client.post(f"/api/v3/work-runs/{run['id']}/transition", json={"status": "running"})
    assert response.status_code == 200 and response.json()["status"] == "running"
    assert client.get("/api/v3/work-runs/missing").status_code == 404


def test_runner_summary_hides_cluster_fence_in_both_live_and_cached_records(api, monkeypatch):
    client, ledger, _, _, run = api
    monkeypatch.setattr(projects, "_load_runner_state", lambda: {"runs": [ledger.get(run["id"])]})
    monkeypatch.setattr(projects, "_load_dispatch_queue", lambda: {"tasks": []})
    monkeypatch.setattr(projects, "_runner_executor_status", lambda: {})
    monkeypatch.setattr(projects, "_elastic_runner_status", lambda: {})
    response = client.get("/api/v3/agents/runner/status")
    assert response.status_code == 200
    assert "_cluster_step_fence" not in response.text and "lease_sha256" not in response.text
    assert response.json()["canonical_runs"]["runs"][0]["id"] == run["id"]


def test_mission_run_ledger_links_and_projects_cluster_work_run(api):
    client, ledger, service, mission_id, run = api
    internal = service.get_mission_run_ledger(mission_id)
    assert [r["id"] for r in internal["step_runs"]] == [run["id"]]
    assert internal["step_runs"][0]["mission_run_id"] == internal["run"]["id"]
    assert internal["step_runs"][0]["correlation_id"] == internal["run"]["correlation_id"]
    response = client.get(f"/api/v3/command-center/missions/{mission_id}/run-ledger")
    assert response.status_code == 200
    assert response.json()["step_runs"][0]["id"] == run["id"]
    assert "_cluster_step_fence" not in response.text and "binding_sha256" not in response.text
    assert "_cluster_step_fence" in ledger.get(run["id"])["input_context"]


def test_completed_receipt_stays_auditable_in_public_projection(approved):
    make, ledger, calls, service, mission_id, step, authority = approved
    receipt = asyncio.run(make(authorize=None, step_authority=authority).execute(request(), PRINCIPAL))
    stored = ledger.get(receipt["run_id"])
    public = public_work_run(stored)
    assert public["status"] == "completed" and len(calls) == 1
    assert public["execution_result"] == receipt
    assert public["execution_result"]["approval_id"] == step["step_approval"]["id"]
    assert public["mission_run_id"] == service.get_mission_run_ledger(mission_id)["run"]["id"]
    assert "binding_sha256" not in json.dumps(public)
    assert "lease_sha256" not in json.dumps(public)
    assert "_cluster_step_fence" in stored["input_context"]
