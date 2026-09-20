from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from services.command_center_service import CommandCenterService, _iso, _now


def test_worker_registry_requires_live_instances_and_tracks_shutdown(tmp_path):
    service = CommandCenterService(str(tmp_path / "worker-registry.db"))

    initial = service.worker_runtime_status(required_workers=2, stale_after_seconds=20)
    assert initial["status"] == "degraded"
    assert initial["live"] == 0

    service.register_worker("worker-a", role="embedded", metadata={"pid": 101})
    service.register_worker("worker-b", role="dedicated", metadata={"pid": 202})
    ready = service.worker_runtime_status(required_workers=2, stale_after_seconds=20)
    assert ready["status"] == "ready"
    assert ready["live"] == 2
    assert {item["role"] for item in ready["workers"]} == {"embedded", "dedicated"}

    service.stop_worker("worker-b")
    stopped = service.worker_runtime_status(required_workers=2, stale_after_seconds=20)
    assert stopped["status"] == "degraded"
    assert stopped["live"] == 1

    with service.connect(immediate=True) as connection:
        connection.execute(
            "UPDATE command_center_workers SET state='running', last_seen_at=? WHERE id=?",
            (_iso(_now() - timedelta(seconds=60)), "worker-b"),
        )
    stale = service.worker_runtime_status(required_workers=2, stale_after_seconds=20)
    assert stale["status"] == "degraded"
    assert stale["stale"] == 1


def test_concurrent_workers_claim_a_ready_step_exactly_once(tmp_path):
    service = CommandCenterService(str(tmp_path / "concurrent-claim.db"))
    mission = service.create_mission(
        objective="验证并发 worker 不会重复执行步骤",
        requested_by="admin",
    )
    assert service.claim_planning_mission("planner")["id"] == mission["id"]
    service.save_plan(
        mission["id"],
        {
            "summary": "单步骤并发领取测试",
            "risk_level": "low",
            "steps": [
                {
                    "order_index": 1,
                    "title": "唯一执行步骤",
                    "description": "多个 worker 同时争抢",
                    "task_type": "coordination",
                    "agent_id": "optimus",
                    "depends_on": [],
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()

    def claim(index: int):
        return service.claim_ready_steps(f"worker-{index}", limit=1)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(claim, range(32)))

    claimed = [step for result in results for step in result]
    assert len(claimed) == 1
    assert claimed[0]["title"] == "唯一执行步骤"
    assert claimed[0]["lease_token"]

    with service.connect() as conn:
        row = conn.execute(
            "SELECT status, attempt_count, lease_owner FROM mission_steps WHERE id=?",
            (claimed[0]["id"],),
        ).fetchone()
    assert dict(row) == {
        "status": "running",
        "attempt_count": 1,
        "lease_owner": claimed[0]["lease_owner"],
    }
