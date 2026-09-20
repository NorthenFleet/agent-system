"""Optimus command-center APIs and normalized Feishu ingress."""

from __future__ import annotations

import hmac
import json
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from database import get_db
from routers.auth_router import get_current_user, require_role
from services.agent_capability_registry import agent_capability_registry
from services.business_flow_service import business_flow_registry
from services.execution_evidence_service import execution_evidence_service
from services.compensation_service import compensation_service
from services.command_center_service import (
    CommandCenterError,
    InvalidMissionTransition,
    MissionNotFound,
    command_center_service,
)
from services.finance_intake_service import FinanceIntakeError, finance_intake_coordinator
from services.finance_review_orchestrator import finance_review_orchestrator
from services.memory_feedback_service import (
    MemoryFeedbackError,
    memory_feedback_service,
)
from services.context_retrieval_service import context_retrieval_service
from services.memory_awareness_service import MemoryAwarenessService
from services.work_run_service import WorkRunService, work_run_service
from services.memory_system_health_status import (
    MemorySystemHealthStatusError,
    publish_memory_health_notification,
)


router = APIRouter(tags=["v3-command-center"])


class InboxRequest(BaseModel):
    channel: str = "feishu"
    external_conversation_id: str
    user_external_id: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    external_message_id: str = ""
    reply_to_external_message_id: str = ""
    intent_type: str = Field(
        "",
        pattern="^(|discussion|software_project|document_project|finance_operation|mission_control|clarification_required)$",
    )
    intent_confidence: float = Field(0.0, ge=0.0, le=1.0)
    intent_reason: str = Field("", max_length=1000)
    execution_requested: bool = False
    project_id: str = Field("", max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionCreateRequest(BaseModel):
    objective: str = Field(..., min_length=1, max_length=20000)
    title: str = Field("", max_length=160)
    project_id: str = Field(..., min_length=1, max_length=160)
    mission_type: str = Field(..., pattern="^(software|document)$")
    flow_key: str = Field(
        "",
        pattern="^(|general|software|document|finance|research|operations)$",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class ConversationResponseRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)
    external_message_id: str = Field("", max_length=200)
    sender_id: str = Field("optimus", pattern="^(optimus|soundwave)$")


class FinanceExtractionRequest(BaseModel):
    agent_id: str = Field("soundwave", pattern="^soundwave$")
    payload: dict[str, Any]
    evidence: list[str] = Field(default_factory=list, max_length=50)
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_version: int = Field(..., ge=1)


class FinanceReviewRequest(BaseModel):
    reviewer_agent_id: str = Field("inspector", pattern="^inspector$")
    decision: str = Field(..., pattern="^(approve|reject)$")
    summary: str = Field(..., min_length=1, max_length=4000)
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_version: int = Field(..., ge=1)


class DashboardMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)
    intent_type: str = Field(
        "",
        pattern="^(|discussion|software_project|document_project|finance_operation|mission_control|clarification_required)$",
    )
    intent_confidence: float = Field(0.0, ge=0.0, le=1.0)
    intent_reason: str = Field("", max_length=1000)
    execution_requested: bool = False
    project_id: str = Field("", max_length=160)


class DecisionRequest(BaseModel):
    comment: str = Field("", max_length=4000)


class StepApprovalDecisionRequest(BaseModel):
    approval_id: str = Field(..., min_length=1, max_length=160)
    contract_hash: str = Field(..., pattern="^[a-f0-9]{64}$")
    comment: str = Field("", max_length=4000)


class CompensationDecisionRequest(BaseModel):
    contract_hash: str = Field(..., pattern="^[a-f0-9]{64}$")
    comment: str = Field("", max_length=4000)


class FeedbackRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class MemoryCandidateReviewRequest(BaseModel):
    comment: str = Field("", max_length=4000)
    title: str = Field("", max_length=300)
    content: str = Field("", max_length=12000)
    memory_key: str = Field("", max_length=200)
    importance: str = Field("", pattern="^(|critical|high|normal|low)$")


class ExternalUserBindingRequest(BaseModel):
    channel: str = Field(..., min_length=1, max_length=80)
    external_user_id: str = Field(..., min_length=1, max_length=200)
    internal_user_id: str = Field(..., min_length=1, max_length=160)
    profile_user_id: str = Field(..., min_length=1, max_length=160)
    display_name: str = Field("", max_length=200)
    status: str = Field("active", pattern="^(active|disabled)$")


class AgentMemoryContextRequest(BaseModel):
    channel: str = Field("feishu", min_length=1, max_length=80)
    external_user_id: str = Field(..., min_length=1, max_length=200)
    query: str = Field(..., min_length=1, max_length=20000)
    agent_id: str = Field("optimus", pattern=r"^[A-Za-z0-9_.-]{1,160}$")
    project_id: str = Field("", max_length=160)
    limit: int = Field(12, ge=1, le=50)
    persist: bool = True


class MemoryHealthEventRequest(BaseModel):
    monitor_key: str = Field("primary", pattern="^(primary|matrix)$")
    schema_version: str = Field("memory-system-health.v1", max_length=80)
    checked_at: str = Field(..., min_length=1, max_length=80)
    healthy: bool
    case_id: str = Field("", max_length=160)
    failures: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    summary: dict[str, Any] = Field(default_factory=dict)


def _actor(user: dict) -> str:
    return str(user.get("username") or user.get("sub") or "dashboard-user")


def _profile_user_id(user: dict) -> str:
    return str(user.get("sub") or "").strip()


def _is_admin(user: dict) -> bool:
    return str(user.get("role") or "") == "admin"


def _owner_scope(user: dict) -> str:
    return "" if _is_admin(user) else _profile_user_id(user)


def _assert_mission_access(mission_id: str, user: dict) -> None:
    command_center_service.get_mission(
        mission_id,
        owner_user_id=_owner_scope(user),
    )


def _verify_ingress(request: Request, token: str = "") -> None:
    configured = os.getenv("COMMAND_CENTER_INGRESS_TOKEN", "").strip()
    if configured:
        if not token or not hmac.compare_digest(configured, token):
            raise HTTPException(401, "指挥中心接入令牌无效")
        return
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(
            403,
            "未配置 COMMAND_CENTER_INGRESS_TOKEN 时，仅允许本机 OpenClaw 接入",
        )


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MissionNotFound):
        return HTTPException(404, f"任务不存在: {exc}")
    if isinstance(exc, InvalidMissionTransition):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


@router.post("/api/v3/command-center/agent/memory-context")
def agent_memory_context(
    body: AgentMemoryContextRequest,
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    """Resolve a bound external identity before returning scoped memory."""
    _verify_ingress(request, x_command_center_token)
    try:
        binding = command_center_service.get_external_user_binding(
            channel=body.channel,
            external_user_id=body.external_user_id,
        )
        if str(binding.get("status") or "") != "active":
            raise CommandCenterError("external user binding is disabled")
        result = MemoryAwarenessService(context_retrieval_service).inspect(
            user_id=str(binding["profile_user_id"]),
            query=body.query,
            agent_id=body.agent_id,
            project_id=body.project_id,
            limit=body.limit,
            persist=body.persist,
        )
        result["identity"] = {
            "channel": body.channel,
            "display_name": binding.get("display_name") or "",
            "bound": True,
        }
        return result
    except (CommandCenterError, ValueError) as exc:
        raise _translate_error(exc) from exc


@router.post("/api/v3/command-center/agent/memory-health")
def ingest_memory_health(
    body: MemoryHealthEventRequest,
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
    db=Depends(get_db),
):
    """Turn memory gate state changes into deduplicated administrator notifications."""
    _verify_ingress(request, x_command_center_token)
    try:
        return publish_memory_health_notification(db, body.model_dump())
    except MemorySystemHealthStatusError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/api/v3/command-center/inbox")
def ingest_command(
    body: InboxRequest,
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        metadata = dict(body.metadata)
        if body.intent_type:
            metadata.update(
                {
                    "intent_type": body.intent_type,
                    "intent_confidence": body.intent_confidence,
                    "intent_reason": body.intent_reason,
                    "execution_requested": body.execution_requested,
                }
            )
        if body.project_id:
            metadata["project_id"] = body.project_id
        result = command_center_service.process_inbound(
            channel=body.channel,
            external_conversation_id=body.external_conversation_id,
            user_external_id=body.user_external_id,
            content=body.content,
            external_message_id=body.external_message_id,
            reply_to_external_message_id=body.reply_to_external_message_id,
            metadata=metadata,
        )
        message = result.get("message") or {}
        if message.get("intent_type") == "finance_operation":
            binding = command_center_service.get_external_user_binding(
                channel=body.channel,
                external_user_id=body.user_external_id,
            )
            staged = finance_intake_coordinator.stage_command(
                command_message_id=message["id"],
                external_message_id=message.get("external_message_id") or body.external_message_id,
                source_channel=body.channel,
                source_account_id=str(body.metadata.get("account_id") or "soundwave"),
                external_conversation_id=body.external_conversation_id,
                external_user_id=body.user_external_id,
                requested_by_user_id=int(binding["internal_user_id"]),
                target_agent_id=message.get("target_agent_id") or "soundwave",
                request_text=body.content,
                request_metadata=metadata,
            )
            result["finance_job"] = staged["job"]
            result["finance_job_replayed"] = staged["replayed"]
        return result
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc
    except FinanceIntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/v3/command-center/agent/messages/{message_id}/response")
def record_agent_response(
    message_id: str,
    body: ConversationResponseRequest,
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        return command_center_service.record_conversation_response(
            message_id,
            content=body.content,
            sender_id=body.sender_id,
            external_message_id=body.external_message_id,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/agent/finance-jobs")
def agent_list_finance_jobs(
    request: Request,
    agent_id: str = Query(..., pattern="^(soundwave|inspector)$"),
    status: str = Query("", pattern="^(|shadow_read|needs_review|validated|rejected|failed|cancelled)$"),
    limit: int = Query(100, ge=1, le=500),
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        jobs = finance_intake_coordinator.list_agent_jobs(
            agent_id=agent_id,
            status=status,
            limit=limit,
        )
        return {"jobs": jobs, "total": len(jobs)}
    except FinanceIntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/api/v3/command-center/agent/finance-jobs/{job_id}")
def agent_get_finance_job(
    job_id: str,
    request: Request,
    agent_id: str = Query(..., pattern="^(soundwave|inspector)$"),
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        return finance_intake_coordinator.get_agent_job(job_id, agent_id=agent_id)
    except FinanceIntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/v3/command-center/agent/finance-jobs/{job_id}/extraction")
def agent_submit_finance_extraction(
    job_id: str,
    body: FinanceExtractionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        result = finance_intake_coordinator.submit_extraction(
            job_id,
            agent_id=body.agent_id,
            payload=body.payload,
            evidence=body.evidence,
            confidence=body.confidence,
            expected_version=body.expected_version,
        )
        if result["job"]["status"] == "needs_review":
            background_tasks.add_task(finance_review_orchestrator.review_job, job_id)
            result["review_scheduled"] = True
        return result
    except FinanceIntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/v3/command-center/agent/finance-jobs/{job_id}/review")
def agent_submit_finance_review(
    job_id: str,
    body: FinanceReviewRequest,
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        return finance_intake_coordinator.submit_review(
            job_id,
            reviewer_agent_id=body.reviewer_agent_id,
            decision=body.decision,
            summary=body.summary,
            findings=body.findings,
            confidence=body.confidence,
            expected_version=body.expected_version,
        )
    except FinanceIntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/api/v3/command-center/agent/missions")
def agent_list_missions(
    request: Request,
    status: str = Query("", description="按状态筛选"),
    limit: int = Query(50, ge=1, le=200),
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    missions = command_center_service.list_missions(status=status, limit=limit)
    return {
        "missions": missions,
        "total": len(missions),
        "summary": command_center_service.summary(),
    }


@router.get("/api/v3/command-center/agent/missions/{mission_id}")
def agent_get_mission(
    mission_id: str,
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    _verify_ingress(request, x_command_center_token)
    try:
        return command_center_service.get_mission(mission_id)
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post("/api/v2/lark/events")
async def ingest_lark_event(
    request: Request,
    x_command_center_token: str = Header("", alias="X-Command-Center-Token"),
):
    """Compatibility endpoint for ``backend/lark_event_bridge.py``."""
    _verify_ingress(request, x_command_center_token)
    payload = await request.json()
    if payload.get("type") == "url_verification" or payload.get("challenge"):
        return {"challenge": payload.get("challenge", "")}

    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    content_value: Any = message.get("content") or event.get("content") or ""
    if isinstance(content_value, str):
        try:
            content_payload = json.loads(content_value)
            content = str(content_payload.get("text") or content_payload.get("content") or content_value)
        except json.JSONDecodeError:
            content = content_value
    elif isinstance(content_value, dict):
        content = str(content_value.get("text") or content_value.get("content") or "")
    else:
        content = str(content_value or "")

    chat_id = str(
        message.get("chat_id")
        or event.get("chat_id")
        or payload.get("chat_id")
        or ""
    )
    user_id = str(
        sender_id.get("open_id")
        or sender_id.get("user_id")
        or sender.get("open_id")
        or payload.get("open_id")
        or ""
    )
    message_id = str(message.get("message_id") or event.get("message_id") or "")
    reply_to = str(
        message.get("parent_id")
        or message.get("root_id")
        or event.get("parent_id")
        or ""
    )
    if not chat_id or not content.strip():
        return {"success": True, "ignored": True, "reason": "event has no text message"}

    try:
        result = command_center_service.process_inbound(
            channel="feishu",
            external_conversation_id=chat_id,
            user_external_id=user_id,
            content=content,
            external_message_id=message_id,
            reply_to_external_message_id=reply_to,
            metadata={
                "target": chat_id,
                "event_id": payload.get("event_id") or payload.get("header", {}).get("event_id"),
                "raw_type": payload.get("type") or payload.get("header", {}).get("event_type"),
            },
        )
        return {"success": True, **result}
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/summary")
def command_center_summary(_user: dict = Depends(get_current_user)):
    return {
        **command_center_service.summary(owner_user_id=_owner_scope(_user)),
        "memory_candidates": memory_feedback_service.stats(
            user_id=_owner_scope(_user)
        ),
    }


@router.get("/api/v3/command-center/messages")
def list_routed_messages(
    intent_type: str = Query("", max_length=40),
    limit: int = Query(30, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    messages = command_center_service.list_routed_messages(
        owner_user_id=_owner_scope(user),
        intent_type=intent_type,
        limit=limit,
    )
    return {"messages": messages, "total": len(messages)}


@router.post("/api/v3/command-center/messages")
def route_dashboard_message(
    body: DashboardMessageRequest,
    user: dict = Depends(get_current_user),
):
    try:
        return command_center_service.process_inbound(
            channel="dashboard",
            external_conversation_id=f"dashboard:{_profile_user_id(user)}",
            user_external_id=_actor(user),
            content=body.content,
            external_message_id=f"dashboard-{uuid.uuid4().hex}",
            metadata={
                "profile_user_id": _profile_user_id(user),
                "source": "dashboard-command-center",
                "suppress_notification": True,
                **(
                    {
                        "intent_type": body.intent_type,
                        "intent_confidence": body.intent_confidence,
                        "intent_reason": body.intent_reason,
                        "execution_requested": body.execution_requested,
                    }
                    if body.intent_type
                    else {}
                ),
                **({"project_id": body.project_id} if body.project_id else {}),
            },
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/memory-candidates")
def list_memory_candidates(
    status: str = Query("pending_review", max_length=40),
    mission_id: str = Query("", max_length=160),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    try:
        candidates = memory_feedback_service.list_candidates(
            user_id=_owner_scope(user),
            status=status,
            mission_id=mission_id,
            limit=limit,
        )
        return {
            "candidates": candidates,
            "total": len(candidates),
            "summary": memory_feedback_service.stats(
                user_id=_owner_scope(user)
            ),
            "can_review": _is_admin(user),
        }
    except MemoryFeedbackError as exc:
        raise HTTPException(400, str(exc)) from exc


def _review_memory_candidate(
    candidate_id: str,
    *,
    decision: str,
    body: MemoryCandidateReviewRequest,
    user: dict,
):
    try:
        candidate = memory_feedback_service.review_candidate(
            candidate_id,
            decision=decision,
            reviewed_by=_actor(user),
            comment=body.comment,
            title=body.title,
            content=body.content,
            memory_key=body.memory_key,
            importance=body.importance,
        )
        event_warning = ""
        if candidate.pop("review_changed", False):
            try:
                command_center_service.record_memory_event(
                    candidate["mission_id"],
                    event_type=(
                        "memory_candidate_published"
                        if decision == "approve"
                        else "memory_candidate_rejected"
                    ),
                    actor=_actor(user),
                    detail=(
                        f"长期记忆候选“{candidate['title']}”已审核发布"
                        if decision == "approve"
                        else f"长期记忆候选“{candidate['title']}”已驳回"
                    ),
                    metadata={
                        "candidate_id": candidate["id"],
                        "target_scope": candidate["target_scope"],
                        "published_ref": candidate.get("published_ref"),
                        "comment": body.comment,
                    },
                )
            except CommandCenterError as exc:
                event_warning = f"记忆已发布，任务时间线暂未同步：{str(exc)[:300]}"
        return {
            "success": True,
            "candidate": candidate,
            "event_warning": event_warning,
        }
    except MemoryFeedbackError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message else 409 if "already" in message else 400
        raise HTTPException(status_code, message) from exc


@router.post("/api/v3/command-center/memory-candidates/{candidate_id}/approve")
def approve_memory_candidate(
    candidate_id: str,
    body: MemoryCandidateReviewRequest,
    user: dict = Depends(require_role("admin")),
):
    return _review_memory_candidate(
        candidate_id,
        decision="approve",
        body=body,
        user=user,
    )


@router.post("/api/v3/command-center/memory-candidates/{candidate_id}/reject")
def reject_memory_candidate(
    candidate_id: str,
    body: MemoryCandidateReviewRequest,
    user: dict = Depends(require_role("admin")),
):
    if not body.comment.strip():
        raise HTTPException(400, "驳回长期记忆候选必须填写原因")
    return _review_memory_candidate(
        candidate_id,
        decision="reject",
        body=body,
        user=user,
    )


@router.get("/api/v3/command-center/capabilities")
def command_center_capabilities(_user: dict = Depends(get_current_user)):
    return {
        **agent_capability_registry.catalog(),
        "business_flow_contract": business_flow_registry.catalog(),
        "workflow_runtime": command_center_service.workflow_runtime_status(),
        "execution_evidence": execution_evidence_service.catalog(),
        "step_approval": command_center_service.step_approval_policy(),
        "compensation": compensation_service.catalog(),
    }


@router.get("/api/v3/command-center/business-flows")
def command_center_business_flows(_user: dict = Depends(get_current_user)):
    """Expose versioned flow, lifecycle and risk contracts to planners and UI."""
    return business_flow_registry.catalog()


@router.get("/api/v3/command-center/workflow-runtime")
def command_center_workflow_runtime(_user: dict = Depends(get_current_user)):
    """Expose rollout configuration and durable workflow-run health."""
    return command_center_service.workflow_runtime_status()


@router.get("/api/v3/command-center/task-workbench")
def task_workbench(
    status: str = Query("", description="按 mission 状态筛选"),
    mission_type: str = Query("", description="software 或 document"),
    project_id: str = Query("", description="按项目筛选"),
    agent_id: str = Query("", description="按当前或关联智能体筛选"),
    source: str = Query("", description="按生产任务来源筛选"),
    search: str = Query("", description="搜索标题、目标、项目或智能体"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    return command_center_service.list_task_workbench(
        status=status,
        mission_type=mission_type,
        project_id=project_id,
        agent_id=agent_id,
        source=source,
        search=search,
        limit=limit,
        offset=offset,
        owner_user_id=_owner_scope(user),
    )


@router.get("/api/v3/command-center/space")
def command_center_agent_space(
    mission_id: str = Query("", description="按任务聚焦空间态势"),
    user: dict = Depends(get_current_user),
):
    return command_center_service.agent_space(
        mission_id=mission_id,
        owner_user_id=_owner_scope(user),
    )


@router.get("/api/v3/command-center/missions")
def list_missions(
    status: str = Query("", description="按状态筛选"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user: dict = Depends(get_current_user),
):
    missions = command_center_service.list_missions(
        status=status,
        limit=limit,
        offset=offset,
        owner_user_id=_owner_scope(_user),
    )
    return {"missions": missions, "total": len(missions)}


@router.post("/api/v3/command-center/missions", status_code=201)
def create_mission(
    body: MissionCreateRequest,
    user: dict = Depends(get_current_user),
):
    try:
        command_center_service.validate_project_target(
            body.project_id,
            body.mission_type,
        )
        mission = command_center_service.create_mission(
            objective=body.objective,
            requested_by=_actor(user),
            project_id=body.project_id,
            mission_type=body.mission_type,
            title=body.title,
            context={
                **body.context,
                "mission_type": body.mission_type,
                "business_flow_key": body.flow_key or body.mission_type,
            },
            profile_user_id=_profile_user_id(user),
        )
        return {"success": True, "mission": mission}
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/missions/{mission_id}")
def get_mission(
    mission_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        return command_center_service.get_mission(
            mission_id,
            owner_user_id=_owner_scope(user),
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/missions/{mission_id}/delivery-evidence")
def get_mission_delivery_evidence(
    mission_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        return command_center_service.get_delivery_evidence(
            mission_id,
            owner_user_id=_owner_scope(user),
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/missions/{mission_id}/run-ledger")
def get_mission_run_ledger(
    mission_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        return command_center_service.get_mission_run_ledger(
            mission_id,
            owner_user_id=_owner_scope(user),
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/missions/{mission_id}/step-approvals")
def get_mission_step_approvals(
    mission_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        return command_center_service.list_step_approvals(
            mission_id,
            owner_user_id=_owner_scope(user),
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/api/v3/command-center/missions/{mission_id}/steps/{step_id}/approve"
)
def approve_mission_step(
    mission_id: str,
    step_id: str,
    body: StepApprovalDecisionRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.decide_step_approval(
            mission_id,
            step_id,
            approval_id=body.approval_id,
            contract_hash=body.contract_hash,
            decision="approved",
            decided_by=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/api/v3/command-center/missions/{mission_id}/steps/{step_id}/reject"
)
def reject_mission_step(
    mission_id: str,
    step_id: str,
    body: StepApprovalDecisionRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.decide_step_approval(
            mission_id,
            step_id,
            approval_id=body.approval_id,
            contract_hash=body.contract_hash,
            decision="rejected",
            decided_by=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/missions/{mission_id}/compensations")
def get_mission_compensations(
    mission_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        return command_center_service.list_compensations(
            mission_id,
            owner_user_id=_owner_scope(user),
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/api/v3/command-center/missions/{mission_id}/compensations/{compensation_id}/approve"
)
def approve_mission_compensation(
    mission_id: str,
    compensation_id: str,
    body: CompensationDecisionRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.decide_compensation(
            compensation_id,
            expected_mission_id=mission_id,
            contract_hash=body.contract_hash,
            decision="approved",
            decided_by=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/api/v3/command-center/missions/{mission_id}/compensations/{compensation_id}/reject"
)
def reject_mission_compensation(
    mission_id: str,
    compensation_id: str,
    body: CompensationDecisionRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.decide_compensation(
            compensation_id,
            expected_mission_id=mission_id,
            contract_hash=body.contract_hash,
            decision="rejected",
            decided_by=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post("/api/v3/command-center/missions/{mission_id}/approve")
def approve_mission(
    mission_id: str,
    body: DecisionRequest,
    user: dict = Depends(get_current_user),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.approve(
            mission_id,
            decided_by=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post("/api/v3/command-center/missions/{mission_id}/reject")
def reject_mission(
    mission_id: str,
    body: DecisionRequest,
    user: dict = Depends(get_current_user),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.reject(
            mission_id,
            decided_by=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post("/api/v3/command-center/missions/{mission_id}/cancel")
def cancel_mission(
    mission_id: str,
    body: DecisionRequest,
    user: dict = Depends(get_current_user),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.cancel(
            mission_id,
            actor=_actor(user),
            comment=body.comment,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.post("/api/v3/command-center/missions/{mission_id}/feedback")
def mission_feedback(
    mission_id: str,
    body: FeedbackRequest,
    user: dict = Depends(get_current_user),
):
    try:
        _assert_mission_access(mission_id, user)
        return command_center_service.add_feedback(
            mission_id,
            actor=_actor(user),
            content=body.content,
        )
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc


@router.get("/api/v3/command-center/health")
def command_center_health(_user: dict = Depends(get_current_user)):
    summary = command_center_service.summary(owner_user_id=_owner_scope(_user))
    storage = command_center_service.storage_info()
    return {
        "status": "ready",
        "source_of_truth": storage["source_of_truth"],
        "storage": storage,
        "storage_runtime": command_center_service.storage_runtime_metrics(),
        "optimus_entry": True,
        **summary,
    }


@router.get("/api/v3/command-center/production-health")
def command_center_production_health(_user: dict = Depends(require_role("admin"))):
    """Expose sanitized persistence, lease and checkpoint reliability indicators."""
    storage = command_center_service.storage_info()
    workflow = command_center_service.workflow_runtime_status()
    runtime_work_runs = work_run_service
    if (
        command_center_service.repository.backend == "postgresql"
        and work_run_service.repository.backend != "postgresql"
    ):
        runtime_work_runs = WorkRunService(repository=command_center_service.repository)
    work_runs = runtime_work_runs.operational_metrics()
    pool = command_center_service.storage_runtime_metrics()
    workers = command_center_service.worker_runtime_status()
    degraded = bool(
        workflow.get("checkpoint_storage", {}).get("status") == "degraded"
        or int(work_runs.get("expired_active_leases") or 0) > 0
        or pool.get("status") == "degraded"
        or workers.get("status") == "degraded"
    )
    return {
        "status": "degraded" if degraded else "ready",
        "storage": storage,
        "storage_runtime": pool,
        "work_runs": work_runs,
        "workflow_runtime": workflow,
        "workers": workers,
    }


@router.get("/api/v3/command-center/external-user-bindings")
def list_external_user_bindings(_user: dict = Depends(require_role("admin"))):
    bindings = command_center_service.list_external_user_bindings()
    return {"bindings": bindings, "total": len(bindings)}


@router.post("/api/v3/command-center/external-user-bindings")
def upsert_external_user_binding(
    body: ExternalUserBindingRequest,
    _user: dict = Depends(require_role("admin")),
):
    try:
        binding = command_center_service.upsert_external_user_binding(
            channel=body.channel,
            external_user_id=body.external_user_id,
            internal_user_id=body.internal_user_id,
            profile_user_id=body.profile_user_id,
            display_name=body.display_name,
            status=body.status,
        )
        return {"success": True, "binding": binding}
    except CommandCenterError as exc:
        raise _translate_error(exc) from exc
