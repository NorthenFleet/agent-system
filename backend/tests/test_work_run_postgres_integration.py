"""Opt-in PostgreSQL integration gate for canonical WorkRun leases."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.work_run_service import WorkRunLeaseConflict, WorkRunService


POSTGRES_URL = os.getenv("WORK_RUN_POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="WORK_RUN_POSTGRES_TEST_URL is not configured",
)


def _service() -> WorkRunService:
    return WorkRunService(database_url=POSTGRES_URL)


def test_postgres_concurrent_claim_is_single_attempt_and_auditable():
    dispatch_id = f"pg-work-run-{uuid.uuid4().hex}"
    service = _service()
    run_id = ""
    try:
        def claim(owner: str):
            try:
                return _service().claim(
                    dispatch_id=dispatch_id,
                    idempotency_key=dispatch_id,
                    agent_id=owner,
                    executor="postgres-integration-gate",
                    lease_seconds=300,
                )
            except WorkRunLeaseConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = list(pool.map(claim, ("agent-a", "agent-b")))

        successful = [item for item in claimed if item]
        assert len(successful) == 1
        run = successful[0]
        run_id = run["id"]
        assert run["attempt"] == 1
        assert run["status"] == "claimed"

        with service.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count, MAX(attempt) AS max_attempt "
                "FROM work_runs WHERE idempotency_key=?",
                (dispatch_id,),
            ).fetchone()
        assert row["count"] == 1
        assert row["max_attempt"] == 1

        service.transition(run_id, "running", actor=run["lease_owner"])
        service.transition(
            run_id,
            "review",
            actor=run["lease_owner"],
            result_summary="PostgreSQL execution complete",
            execution_result={"success": True},
        )
        artifact = service.add_artifact(
            run_id,
            artifact_type="integration-evidence",
            title="PostgreSQL WorkRun gate",
            uri="urn:test:work-run-postgres",
        )
        completed = service.transition(run_id, "completed", actor="reviewer")

        assert completed["status"] == "completed"
        assert completed["ended_at"]
        assert any(item["id"] == artifact["id"] for item in completed["artifacts"])
        assert [event["to_status"] for event in completed["events"]][-3:] == [
            "review",
            "review",
            "completed",
        ]
    finally:
        if run_id:
            with service.connect(immediate=True) as connection:
                connection.execute("DELETE FROM work_runs WHERE id=?", (run_id,))
