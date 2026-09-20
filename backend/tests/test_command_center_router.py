from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.command_center_router as router_module
from routers.auth_router import get_current_user
from services.command_center_service import CommandCenterService
from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService
from services.work_run_service import WorkRunService


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
    monkeypatch.setattr(router_module, "context_retrieval_service", context_service)
    monkeypatch.setattr(router_module, "memory_feedback_service", memory_service)
    monkeypatch.setattr(router_module, "work_run_service", WorkRunService(service.db_path))
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


def test_health_exposes_storage_backend_and_production_capabilities(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    service.register_worker("router-test-worker", role="embedded")

    response = client.get("/api/v3/command-center/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_of_truth"] == service.db_path
    assert payload["storage"] == {
        "backend": "sqlite",
        "source_of_truth": service.db_path,
        "capabilities": {
            "durable": True,
            "transactional_claims": True,
            "multi_instance": False,
            "runtime_schema_management": True,
        },
    }
    assert payload["storage_runtime"]["connection_mode"] == "direct"

    production = client.get("/api/v3/command-center/production-health")
    assert production.status_code == 200
    production_payload = production.json()
    assert production_payload["status"] == "ready"
    assert production_payload["work_runs"]["expired_active_leases"] == 0
    assert production_payload["workflow_runtime"]["checkpoint_storage"]["status"] == "local"
    assert production_payload["workers"]["status"] == "ready"
    assert production_payload["workers"]["live"] == 1
    assert production_payload["workers"]["required"] == 1


def test_agent_memory_context_resolves_bound_identity_and_3021_scope(tmp_path, monkeypatch):
    client, command_service, context_service, _memory_service = _client(tmp_path, monkeypatch)
    context_service.upsert_fact(
        user_id="1",
        fact_type="decision",
        fact_key="decision.single_entry",
        fact_value="擎天柱是唯一任务入口。",
        importance="critical",
        source_ref="router-test",
    )
    command_service.upsert_external_user_binding(
        channel="feishu",
        external_user_id="ou_test",
        internal_user_id="1",
        profile_user_id="1",
        display_name="管理员",
    )

    response = client.post(
        "/api/v3/command-center/agent/memory-context",
        headers={"X-Command-Center-Token": "test-secret"},
        json={
            "channel": "feishu",
            "external_user_id": "ou_test",
            "query": "你记住了哪些内容",
            "agent_id": "optimus",
            "persist": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["identity"] == {
        "channel": "feishu",
        "display_name": "管理员",
        "bound": True,
    }
    assert payload["authority"]["system"] == "3021-unified-memory"
    assert payload["counts"]["profile_facts"] == 1
    assert payload["remembered_items"][0]["content"] == "擎天柱是唯一任务入口。"


def test_agent_memory_context_isolates_users_on_same_channel(tmp_path, monkeypatch):
    client, command_service, context_service, _memory_service = _client(tmp_path, monkeypatch)
    context_service.upsert_profile(user_id="2", display_name="第二用户")
    context_service.upsert_fact(
        user_id="1",
        fact_type="preference",
        fact_key="preference.private_workspace",
        fact_value="仅用户一可见的私有工作偏好。",
        importance="critical",
        source_ref="cross-user-isolation-test",
    )
    command_service.upsert_external_user_binding(
        channel="feishu",
        external_user_id="ou_user_one",
        internal_user_id="1",
        profile_user_id="1",
        display_name="管理员",
    )
    command_service.upsert_external_user_binding(
        channel="feishu",
        external_user_id="ou_user_two",
        internal_user_id="2",
        profile_user_id="2",
        display_name="第二用户",
    )

    response = client.post(
        "/api/v3/command-center/agent/memory-context",
        headers={"X-Command-Center-Token": "test-secret"},
        json={
            "channel": "feishu",
            "external_user_id": "ou_user_two",
            "query": "私有工作偏好",
            "agent_id": "optimus",
            "persist": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["identity"] == {
        "channel": "feishu",
        "display_name": "第二用户",
        "bound": True,
    }
    assert payload["counts"]["profile_facts"] == 0
    assert all(
        "仅用户一可见" not in str(item.get("content") or "")
        for item in payload["remembered_items"]
    )


def test_agent_memory_context_rejects_unbound_identity(tmp_path, monkeypatch):
    client, _command_service, _context_service, _memory_service = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/v3/command-center/agent/memory-context",
        headers={"X-Command-Center-Token": "test-secret"},
        json={
            "channel": "feishu",
            "external_user_id": "ou_unknown",
            "query": "你记住了什么",
        },
    )

    assert response.status_code == 400
    assert "not mapped" in response.json()["detail"]


def test_memory_health_ingress_publishes_sanitized_transition(tmp_path, monkeypatch):
    client, _command_service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    captured = {}

    def publish(_db, payload):
        captured.update(payload)
        return {"status": "published", "notifications_created": 1}

    monkeypatch.setattr(router_module, "publish_memory_health_notification", publish)
    response = client.post(
        "/api/v3/command-center/agent/memory-health",
        headers={"X-Command-Center-Token": "test-secret"},
        json={
            "schema_version": "memory-system-health.v1",
            "checked_at": "2026-09-17T00:00:00+00:00",
            "healthy": False,
            "case_id": "optimus-memory-inventory-system-gate",
            "failures": [{"check": "identity.bound"}],
            "summary": {"channels": {"approved_graph_projection": "ready"}},
        },
    )

    assert response.status_code == 200
    assert response.json()["notifications_created"] == 1
    assert captured["healthy"] is False
    assert captured["failures"] == [{"check": "identity.bound"}]


def test_memory_health_ingress_rejects_invalid_token(tmp_path, monkeypatch):
    client, _command_service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/v3/command-center/agent/memory-health",
        headers={"X-Command-Center-Token": "wrong"},
        json={
            "checked_at": "2026-09-17T00:00:00+00:00",
            "healthy": True,
        },
    )

    assert response.status_code == 401


def test_command_center_capabilities_catalog(tmp_path, monkeypatch):
    client, _service, _context_service, _memory_service = _client(tmp_path, monkeypatch)

    response = client.get("/api/v3/command-center/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert any(agent["id"] == "optimus" for agent in payload["agents"])
    assert any(tool["id"] == "codex" for tool in payload["tools"])
    assert payload["task_agent_defaults"]["backend"] == "raphael"
    assert any(
        flow["flow_key"] == "software"
        for flow in payload["business_flow_contract"]["flows"]
    )
    assert payload["business_flow_contract"]["risk_levels"]["L3"]["step_approval"] is True
    assert payload["workflow_runtime"]["default_runtime"] == "legacy"
    assert payload["workflow_runtime"]["ownership"]["business_state"] == "command_center"
    assert payload["execution_evidence"]["schema_version"] == "1.0"
    assert payload["step_approval"]["single_use"] is True
    assert payload["compensation"]["policy"]["automatic_execution"] is False

    flow_response = client.get("/api/v3/command-center/business-flows")
    assert flow_response.status_code == 200
    assert "artifact" in flow_response.json()["contracts"]

    runtime_response = client.get("/api/v3/command-center/workflow-runtime")
    assert runtime_response.status_code == 200
    assert runtime_response.json()["langgraph"]["checkpoint_backend"] == "sqlite"


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

    delivery = client.get(
        f"/api/v3/command-center/missions/{mission_id}/delivery-evidence"
    )
    assert delivery.status_code == 200
    assert delivery.json()["summary"]["artifact_count"] == 0

    ledger = client.get(
        f"/api/v3/command-center/missions/{mission_id}/run-ledger"
    )
    assert ledger.status_code == 200
    assert ledger.json()["run"]["id"].startswith("mrun-")
    assert ledger.json()["run"]["correlation_id"].startswith("mission-")
    assert ledger.json()["summary"]["event_count"] >= 3

    listed = client.get("/api/v3/command-center/missions")
    assert listed.status_code == 200
    assert listed.json()["missions"][0]["id"] == mission_id

    summary = client.get("/api/v3/command-center/summary")
    assert summary.status_code == 200
    assert summary.json()["total"] == 1


def test_high_risk_step_approval_api_requires_current_contract(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    mission = service.create_mission(
        objective="执行生产发布",
        requested_by="admin",
        project_id="project-1",
        mission_type="software",
        profile_user_id="1",
    )
    service.claim_planning_mission("planner")
    service.save_plan(
        mission["id"],
        {
            "summary": "高风险发布",
            "steps": [
                {
                    "title": "生产发布",
                    "description": "发布至生产环境",
                    "agent_id": "optimus",
                    "task_type": "operations",
                    "risk_class": "L3",
                    "approval_required": True,
                    "side_effect": True,
                    "resources": ["production"],
                    "rollback_plan": "恢复上一稳定版本",
                    "depends_on": [],
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    assert service.claim_ready_steps("runner", limit=1) == []

    listed = client.get(
        f"/api/v3/command-center/missions/{mission['id']}/step-approvals"
    )
    assert listed.status_code == 200
    approval = listed.json()["current"][0]

    stale = client.post(
        f"/api/v3/command-center/missions/{mission['id']}/steps/{approval['step_id']}/approve",
        json={
            "approval_id": approval["id"],
            "contract_hash": "0" * 64,
            "comment": "错误快照",
        },
    )
    assert stale.status_code == 409

    approved = client.post(
        f"/api/v3/command-center/missions/{mission['id']}/steps/{approval['step_id']}/approve",
        json={
            "approval_id": approval["id"],
            "contract_hash": approval["contract_hash"],
            "comment": "批准当前合同快照",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["approval"]["status"] == "approved"


def test_compensation_api_requires_admin_contract_approval(tmp_path, monkeypatch):
    client, service, _context_service, _memory_service = _client(tmp_path, monkeypatch)
    mission = service.create_mission(
        objective="执行生产配置变更",
        requested_by="admin",
        project_id="project-1",
        mission_type="software",
        profile_user_id="1",
    )
    service.claim_planning_mission("planner")
    service.save_plan(
        mission["id"],
        {
            "summary": "生产变更",
            "steps": [
                {
                    "title": "生产配置变更",
                    "task_type": "operations",
                    "agent_id": "optimus",
                    "risk_class": "L3",
                    "approval_required": True,
                    "side_effect": True,
                    "resources": ["production-config"],
                    "rollback_plan": "恢复上一配置",
                    "depends_on": [],
                }
            ],
        },
    )
    service.approve(mission["id"], decided_by="admin")
    service.activate_approved_missions()
    service.claim_ready_steps("runner", limit=1)
    current = service.get_mission(mission["id"])
    step = current["steps"][0]
    approval = step["step_approval"]
    service.decide_step_approval(
        mission["id"],
        step["id"],
        approval_id=approval["id"],
        contract_hash=approval["contract_hash"],
        decision="approved",
        decided_by="admin",
    )
    running = service.claim_ready_steps("runner", limit=1)[0]
    service.complete_step(
        running["id"],
        result={
            "error": "健康检查失败",
            "side_effects": [
                {
                    "effect_key": "config-change",
                    "resource": "production-config",
                    "action": "更新配置",
                    "status": "applied",
                    "idempotency_key": running["idempotency_key"],
                    "receipt_ref": "ops:change-1",
                    "evidence_refs": ["health:failed"],
                }
            ],
        },
        success=False,
        actor="optimus",
        lease_token=running["lease_token"],
    )

    listed = client.get(
        f"/api/v3/command-center/missions/{mission['id']}/compensations"
    )
    assert listed.status_code == 200
    compensation = listed.json()["compensations"][0]

    stale = client.post(
        f"/api/v3/command-center/missions/{mission['id']}/compensations/{compensation['id']}/approve",
        json={"contract_hash": "0" * 64, "comment": "wrong"},
    )
    assert stale.status_code == 409

    approved = client.post(
        f"/api/v3/command-center/missions/{mission['id']}/compensations/{compensation['id']}/approve",
        json={
            "contract_hash": compensation["contract_hash"],
            "comment": "批准补偿",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["compensation"]["status"] == "ready"


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
