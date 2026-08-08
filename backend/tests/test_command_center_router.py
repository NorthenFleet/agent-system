from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.command_center_router as router_module
from routers.auth_router import get_current_user
from services.command_center_service import CommandCenterService
from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService


def _projects():
    return [
        {
            "id": "project-1",
            "name": "OpenClaw 团队信息看板",
            "project_type": "software",
            "status": "active",
        },
        {
            "id": "document-1",
            "name": "博士论文",
            "project_type": "document",
            "status": "active",
        },
    ]


class _FinanceIntakeStub:
    def __init__(self):
        self.calls = []

    def stage_command(self, **payload):
        replayed = any(
            item["command_message_id"] == payload["command_message_id"]
            for item in self.calls
        )
        self.calls.append(payload)
        return {
            "job": {
                "id": f"finance-job-{payload['command_message_id']}",
                "command_message_id": payload["command_message_id"],
                "target_agent_id": payload["target_agent_id"],
                "operation_type": "reimbursement",
                "mode": "shadow",
                "status": "shadow_read",
            },
            "replayed": replayed,
        }

    def submit_extraction(self, job_id, **payload):
        return {
            "job": {
                "id": job_id,
                "target_agent_id": payload["agent_id"],
                "mode": "shadow",
                "status": "needs_review",
                "lock_version": 2,
            },
            "validation": {"valid": True, "errors": [], "warnings": []},
            "replayed": False,
        }

    def submit_review(self, job_id, **payload):
        return {
            "job": {
                "id": job_id,
                "target_agent_id": "soundwave",
                "mode": "shadow",
                "status": "validated" if payload["decision"] == "approve" else "rejected",
                "lock_version": 3,
            },
            "review": {
                "reviewer_agent_id": payload["reviewer_agent_id"],
                "decision": payload["decision"],
            },
            "replayed": False,
        }

    def list_agent_jobs(self, **_filters):
        return []

    def get_agent_job(self, job_id, *, agent_id):
        return {"id": job_id, "reader_agent_id": agent_id, "status": "needs_review"}


class _FinanceReviewOrchestratorStub:
    def __init__(self):
        self.calls = []

    async def review_job(self, job_id):
        self.calls.append(job_id)
        return {"status": "completed", "job_id": job_id}


def _client(tmp_path, monkeypatch):
    service = CommandCenterService(
        str(tmp_path / "router.db"),
        project_provider=_projects,
    )
    context_service = ContextRetrievalService(
        service.db_path,
        memory_root=str(tmp_path / "memory"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
    )
    memory_service = MemoryFeedbackService(service.db_path)
    context_service.upsert_profile(user_id="1", display_name="管理员")
    monkeypatch.setattr(router_module, "command_center_service", service)
    monkeypatch.setattr(router_module, "memory_feedback_service", memory_service)
    monkeypatch.setattr(router_module, "finance_intake_coordinator", _FinanceIntakeStub())
    monkeypatch.setattr(router_module, "finance_review_orchestrator", _FinanceReviewOrchestratorStub())
    monkeypatch.setenv("COMMAND_CENTER_INGRESS_TOKEN", "test-secret")
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "1",
        "username": "admin",
        "role": "admin",
    }
    return TestClient(app), service, context_service, memory_service


def test_dashboard_mission_crud_and_approval_contract(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v3/command-center/missions",
        json={
            "title": "自动化测试",
            "objective": "开发一个审批功能",
            "project_id": "project-1",
            "mission_type": "software",
        },
    )
    assert created.status_code == 201
    mission_id = created.json()["mission"]["id"]
    assert created.json()["mission"]["project_id"] == "project-1"
    assert created.json()["mission"]["context"]["profile_user_id"] == "1"

    service.claim_planning_mission("test")
    service.save_plan(
        mission_id,
        {
            "summary": "单步",
            "steps": [
                {
                    "title": "实现",
                    "agent_id": "raphael",
                    "task_type": "backend",
                    "depends_on": [],
                }
            ],
        },
    )
    approved = client.post(
        f"/api/v3/command-center/missions/{mission_id}/approve",
        json={"comment": "按计划执行"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "dispatching"

    listed = client.get("/api/v3/command-center/missions")
    assert listed.status_code == 200
    assert listed.json()["missions"][0]["id"] == mission_id

    summary = client.get("/api/v3/command-center/summary")
    assert summary.status_code == 200
    assert summary.json()["total"] == 1


def test_normalized_inbox_requires_secret_and_is_idempotent(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    service.upsert_external_user_binding(
        channel="feishu",
        external_user_id="ou_test",
        internal_user_id="1",
        profile_user_id="1",
    )
    payload = {
        "channel": "feishu",
        "external_conversation_id": "oc_test",
        "user_external_id": "ou_test",
        "content": "讨论一下资料整理方式",
        "external_message_id": "om_test",
        "metadata": {"target": "oc_test"},
    }
    denied = client.post("/api/v3/command-center/inbox", json=payload)
    assert denied.status_code == 401

    headers = {"X-Command-Center-Token": "test-secret"}
    created = client.post("/api/v3/command-center/inbox", json=payload, headers=headers)
    duplicate = client.post("/api/v3/command-center/inbox", json=payload, headers=headers)
    assert created.status_code == 200
    assert created.json()["action"] == "discussion"
    assert duplicate.json()["action"] == "duplicate"
    assert created.json()["mission"] is None
    response = client.post(
        f"/api/v3/command-center/agent/messages/{created.json()['message']['id']}/response",
        json={"content": "这是一般讨论，不创建任务。"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["action"] == "recorded"

    mission_payload = {
        **payload,
        "content": "开发 OpenClaw 审批功能",
        "external_message_id": "om_mission",
        "intent_type": "software_project",
        "intent_confidence": 0.97,
        "intent_reason": "明确的软件开发交付",
        "execution_requested": True,
        "project_id": "project-1",
    }
    mission_result = client.post(
        "/api/v3/command-center/inbox",
        json=mission_payload,
        headers=headers,
    )
    assert mission_result.status_code == 200
    assert mission_result.json()["action"] == "mission_created"
    mission_id = mission_result.json()["mission"]["id"]
    agent_status = client.get(
        f"/api/v3/command-center/agent/missions/{mission_id}",
        headers=headers,
    )
    assert agent_status.status_code == 200
    assert agent_status.json()["id"] == mission_id

    recent = client.get("/api/v3/command-center/messages")
    assert recent.status_code == 200
    assert recent.json()["total"] == 2
    assert recent.json()["messages"][1]["response"]["content"].startswith("这是一般讨论")


def test_dashboard_mission_rejects_missing_or_mismatched_project(tmp_path, monkeypatch):
    client, _service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    missing = client.post(
        "/api/v3/command-center/missions",
        json={"objective": "执行开发", "mission_type": "software"},
    )
    assert missing.status_code == 422

    mismatch = client.post(
        "/api/v3/command-center/missions",
        json={
            "objective": "执行开发",
            "project_id": "document-1",
            "mission_type": "software",
        },
    )
    assert mismatch.status_code == 400


def test_admin_can_manage_external_user_bindings(tmp_path, monkeypatch):
    client, _service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v3/command-center/external-user-bindings",
        json={
            "channel": "feishu",
            "external_user_id": "ou-admin-mapped",
            "internal_user_id": "1",
            "profile_user_id": "1",
            "display_name": "孙总",
        },
    )
    assert created.status_code == 200
    assert created.json()["binding"]["status"] == "active"
    listed = client.get("/api/v3/command-center/external-user-bindings")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_lark_challenge_and_text_event_are_normalized(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    service.upsert_external_user_binding(
        channel="feishu",
        external_user_id="ou-1",
        internal_user_id="1",
        profile_user_id="1",
    )
    headers = {"X-Command-Center-Token": "test-secret"}
    challenge = client.post(
        "/api/v2/lark/events",
        json={"type": "url_verification", "challenge": "abc"},
        headers=headers,
    )
    assert challenge.json() == {"challenge": "abc"}

    event = client.post(
        "/api/v2/lark/events",
        json={
            "header": {"event_id": "evt-1", "event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou-1"}},
                "message": {
                    "message_id": "om-1",
                    "chat_id": "oc-1",
                    "content": '{"text":"开发 OpenClaw 团队信息看板测试接口"}',
                },
            },
        },
        headers=headers,
    )
    assert event.status_code == 200
    assert event.json()["action"] == "mission_created"
    assert event.json()["mission"]["conversation"]["external_conversation_id"] == "oc-1"


def test_finance_message_routes_to_soundwave_without_creating_mission(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    service.upsert_external_user_binding(
        channel="feishu",
        external_user_id="ou-finance",
        internal_user_id="1",
        profile_user_id="1",
    )
    headers = {"X-Command-Center-Token": "test-secret"}
    payload = {
        "channel": "feishu",
        "external_conversation_id": "oc-finance",
        "user_external_id": "ou-finance",
        "content": "请登记这张项目报销发票，金额428.60元",
        "external_message_id": "om-finance-1",
        "intent_type": "finance_operation",
        "intent_confidence": 0.99,
        "intent_reason": "明确的财务作业",
        "execution_requested": True,
        "metadata": {"account_id": "soundwave", "target": "oc-finance"},
    }

    routed = client.post("/api/v3/command-center/inbox", json=payload, headers=headers)
    duplicate = client.post("/api/v3/command-center/inbox", json=payload, headers=headers)

    assert routed.status_code == 200
    assert routed.json()["action"] == "finance_intake"
    assert routed.json()["target_agent_id"] == "soundwave"
    assert routed.json()["mission"] is None
    assert routed.json()["message"]["target_agent_id"] == "soundwave"
    assert routed.json()["finance_job"]["mode"] == "shadow"
    assert routed.json()["finance_job"]["status"] == "shadow_read"
    assert routed.json()["finance_job_replayed"] is False
    assert duplicate.json()["action"] == "duplicate"
    assert duplicate.json()["finance_job"]["id"] == routed.json()["finance_job"]["id"]
    assert duplicate.json()["finance_job_replayed"] is True
    assert service.list_missions() == []

    wrong_agent = client.post(
        f"/api/v3/command-center/agent/messages/{routed.json()['message']['id']}/response",
        json={"content": "错误代理响应", "sender_id": "optimus"},
        headers=headers,
    )
    assert wrong_agent.status_code == 400

    response = client.post(
        f"/api/v3/command-center/agent/messages/{routed.json()['message']['id']}/response",
        json={"content": "已生成财务录入草稿，尚未写入正式财务表。", "sender_id": "soundwave"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message"]["sender_id"] == "soundwave"
    assert response.json()["message"]["target_agent_id"] == "soundwave"


def test_finance_agent_extraction_and_independent_review_endpoints(tmp_path, monkeypatch):
    client, _service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    headers = {"X-Command-Center-Token": "test-secret"}

    extracted = client.post(
        "/api/v3/command-center/agent/finance-jobs/job-1/extraction",
        json={
            "agent_id": "soundwave",
            "payload": {"project_id": "project-1", "total_amount": 100},
            "evidence": ["用户消息"],
            "confidence": 0.9,
            "expected_version": 1,
        },
        headers=headers,
    )
    reviewed = client.post(
        "/api/v3/command-center/agent/finance-jobs/job-1/review",
        json={
            "reviewer_agent_id": "inspector",
            "decision": "approve",
            "summary": "结构和金额一致",
            "findings": [],
            "confidence": 0.95,
            "expected_version": 2,
        },
        headers=headers,
    )

    assert extracted.status_code == 200
    assert extracted.json()["job"]["status"] == "needs_review"
    assert extracted.json()["validation"]["valid"] is True
    assert extracted.json()["review_scheduled"] is True
    assert reviewed.status_code == 200
    assert reviewed.json()["job"]["status"] == "validated"
    assert reviewed.json()["review"]["reviewer_agent_id"] == "inspector"


def test_memory_candidate_review_requires_admin_and_publishes_fact(tmp_path, monkeypatch):
    client, service, context_service, memory_service = _client(tmp_path, monkeypatch)
    mission = service.create_mission(
        objective="验证长期记忆审核",
        requested_by="admin",
        profile_user_id="1",
    )
    candidates = memory_service.create_candidates(
        user_id="1",
        mission_id=mission["id"],
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "decision",
                "memory_key": "decision.review_gate",
                "title": "长期记忆审核门禁",
                "content": "长期记忆必须由管理员审核后发布。",
                "importance": "critical",
                "confidence": 0.99,
            },
            {
                "target_scope": "profile",
                "memory_type": "lesson",
                "memory_key": "lesson.reject",
                "title": "不应长期保存",
                "content": "这是一条一次性状态。",
            },
        ],
    )

    listed = client.get("/api/v3/command-center/memory-candidates")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert listed.json()["can_review"] is True

    published = client.post(
        f"/api/v3/command-center/memory-candidates/{candidates[0]['id']}/approve",
        json={"comment": "确认作为长期规则"},
    )
    assert published.status_code == 200
    assert published.json()["candidate"]["status"] == "published"
    assert context_service.get_profile("1")["facts"][0]["fact_key"] == "decision.review_gate"
    repeated = client.post(
        f"/api/v3/command-center/memory-candidates/{candidates[0]['id']}/approve",
        json={"comment": "重复提交"},
    )
    assert repeated.status_code == 200

    rejected_without_reason = client.post(
        f"/api/v3/command-center/memory-candidates/{candidates[1]['id']}/reject",
        json={},
    )
    assert rejected_without_reason.status_code == 400
    rejected = client.post(
        f"/api/v3/command-center/memory-candidates/{candidates[1]['id']}/reject",
        json={"comment": "一次性状态，不保存"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["candidate"]["status"] == "rejected"

    events = service.get_mission(mission["id"])["events"]
    assert sum(
        event["event_type"] == "memory_candidate_published" for event in events
    ) == 1
    assert any(event["event_type"] == "memory_candidate_rejected" for event in events)

    client.app.dependency_overrides[get_current_user] = lambda: {
        "sub": "1",
        "username": "viewer",
        "role": "viewer",
    }
    denied = client.post(
        f"/api/v3/command-center/memory-candidates/{candidates[0]['id']}/approve",
        json={},
    )
    assert denied.status_code == 403


def test_non_admin_users_only_see_and_mutate_their_own_missions(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    own = service.create_mission(
        objective="用户一任务",
        requested_by="user-one",
        profile_user_id="1",
    )
    other = service.create_mission(
        objective="用户二任务",
        requested_by="user-two",
        profile_user_id="2",
    )
    client.app.dependency_overrides[get_current_user] = lambda: {
        "sub": "1",
        "username": "user-one",
        "role": "viewer",
    }

    listed = client.get("/api/v3/command-center/missions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["missions"]] == [own["id"]]
    assert client.get(
        f"/api/v3/command-center/missions/{other['id']}"
    ).status_code == 404
    assert client.post(
        f"/api/v3/command-center/missions/{other['id']}/cancel",
        json={"comment": "越权取消"},
    ).status_code == 404
    assert client.get("/api/v3/command-center/summary").json()["total"] == 1


def test_task_workbench_endpoint(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "_load_task_ledger", lambda: [])
    created = client.post(
        "/api/v3/command-center/missions",
        json={
            "title": "统一任务工作台",
            "objective": "完善任务列表",
            "project_id": "project-1",
            "mission_type": "software",
        },
    )
    assert created.status_code == 201

    listed = client.get("/api/v3/command-center/task-workbench", params={"mission_type": "software"})

    assert listed.status_code == 200
    data = listed.json()
    assert data["total"] == 1
    assert data["items"][0]["mission_title"] == "统一任务工作台"
    assert data["items"][0]["project_name"] == "OpenClaw 团队信息看板"
