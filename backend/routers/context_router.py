"""Authenticated APIs for user profiles and versioned context packs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.auth_router import get_current_user
from services.auth_service import require_role
from services.context_retrieval_service import (
    ContextRetrievalError,
    context_retrieval_service,
)
from services.graph_memory_evaluation_service import (
    GraphMemoryEvaluationError,
    GraphMemoryEvaluationService,
)
from services.graph_memory_operations_service import GraphMemoryOperationsService
from services.memory_awareness_service import MemoryAwarenessService
from services.memory_effectiveness_service import MemoryEffectivenessError
from services.memory_retrieval_evaluation_service import (
    MemoryRetrievalEvaluationError,
    MemoryRetrievalEvaluationService,
)


router = APIRouter(prefix="/api/v3/context", tags=["v3-context"])


class ProfileUpdate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=160)
    preferred_name: str = Field("", max_length=160)
    timezone: str = Field("Asia/Shanghai", max_length=80)
    summary: str = Field("", max_length=12000)
    work_context: dict[str, Any] = Field(default_factory=dict)
    business_context: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class FactUpsert(BaseModel):
    fact_type: str = Field("general", max_length=80)
    fact_key: str = Field(..., min_length=1, max_length=200)
    fact_value: str = Field(..., min_length=1, max_length=12000)
    importance: str = Field("normal", pattern="^(critical|high|normal|low)$")
    confidence: float = Field(1.0, ge=0, le=1)
    source_type: str = Field("manual", max_length=80)
    source_ref: str = Field("", max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20000)
    project_id: str = Field("", max_length=160)
    mission_id: str = Field("", max_length=160)
    task_id: str = Field("", max_length=160)
    agent_id: str = Field("optimus", max_length=160)
    purpose: str = Field("planning", max_length=80)
    limit: int = Field(12, ge=1, le=50)
    persist: bool = True


class MemoryEffectObservation(BaseModel):
    event_type: str = Field(..., pattern="^(used|task_outcome|correction)$")
    source_refs: list[str] = Field(default_factory=list, max_length=50)
    task_id: str = Field("", max_length=160)
    outcome: str = Field(
        "unknown",
        pattern="^(unknown|accepted|rejected|success|partial|failure|corrected|forgotten)$",
    )
    reason_code: str = Field("", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field("", max_length=240)


class MemoryIntrospectionRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20000)
    project_id: str = Field("", max_length=160)
    agent_id: str = Field("optimus", pattern=r"^[A-Za-z0-9_.-]{1,160}$")
    limit: int = Field(12, ge=1, le=50)
    persist: bool = True


class GraphMemoryEvaluationCase(BaseModel):
    id: str = Field("", max_length=160)
    query: str = Field(..., min_length=1, max_length=20000)
    project_id: str = Field("", max_length=160)
    agent_id: str = Field("optimus", max_length=160)
    limit: int = Field(12, ge=1, le=50)
    expected_source_refs: list[str] = Field(default_factory=list, max_length=50)
    forbidden_source_refs: list[str] = Field(default_factory=list, max_length=50)
    task_outcomes: dict[str, bool] = Field(default_factory=dict)


class GraphMemoryEvaluationRequest(BaseModel):
    cases: list[GraphMemoryEvaluationCase] = Field(..., min_length=1, max_length=100)
    modes: list[str] = Field(default_factory=lambda: ["disabled", "retrieval", "rerank"], max_length=3)
    persist: bool = True


class GraphMemoryRolloutUpdate(BaseModel):
    graph_mode: str = Field(..., pattern="^(disabled|retrieval|rerank)$")
    project_id: str = Field("", max_length=160)


class RetrievalEvaluationCaseUpsert(BaseModel):
    id: str = Field("", max_length=160)
    subject_user_id: str = Field("", max_length=160)
    origin: str = Field("manual", max_length=80)
    source_memory_ref: str = Field("", max_length=500)
    variant_key: str = Field("canonical", max_length=80)
    query: str = Field(..., min_length=1, max_length=20000)
    project_id: str = Field("", max_length=160)
    agent_id: str = Field("optimus", max_length=160)
    limit: int = Field(10, ge=1, le=50)
    expected_source_refs: list[str] = Field(default_factory=list, max_length=50)
    forbidden_source_refs: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field("", max_length=4000)
    review_checks: dict[str, bool] = Field(default_factory=dict)
    reviewer_confidence: str = Field(
        "unreviewed", pattern="^(unreviewed|medium|high)$"
    )
    status: str = Field("draft", pattern="^(draft|active|archived)$")


class RetrievalEvaluationRunRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list, max_length=100)


class RetrievalEvaluationBatchCreate(BaseModel):
    target_count: int = Field(30, ge=1, le=100)
    name: str = Field("", max_length=200)


class RetrievalEvaluationProposal(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=160)
    suggested_query: str = Field(..., min_length=1, max_length=20000)
    suggested_forbidden_source_refs: list[str] = Field(
        default_factory=list, max_length=50
    )
    rationale: str = Field(..., min_length=1, max_length=1000)


class RetrievalEvaluationProposalSet(BaseModel):
    proposals: list[RetrievalEvaluationProposal] = Field(
        ..., min_length=1, max_length=100
    )


def _user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(401, "登录身份缺少用户标识")
    return user_id


def _translate_error(exc: ContextRetrievalError) -> HTTPException:
    message = str(exc)
    if message.startswith("profile not found"):
        return HTTPException(404, message)
    return HTTPException(400, message)


@router.get("/profile/me")
def get_my_profile(user: dict = Depends(get_current_user)):
    profile = context_retrieval_service.get_profile(_user_id(user))
    if not profile:
        raise HTTPException(404, "尚未建立用户上下文档案")
    return profile


@router.put("/profile/me")
def update_my_profile(
    body: ProfileUpdate,
    user: dict = Depends(get_current_user),
):
    try:
        return context_retrieval_service.upsert_profile(
            user_id=_user_id(user),
            display_name=body.display_name,
            preferred_name=body.preferred_name,
            timezone_name=body.timezone,
            summary=body.summary,
            work_context=body.work_context,
            business_context=body.business_context,
            preferences=body.preferences,
            constraints=body.constraints,
            source="dashboard",
        )
    except ContextRetrievalError as exc:
        raise _translate_error(exc) from exc


@router.post("/profile/me/facts", status_code=201)
def upsert_my_fact(
    body: FactUpsert,
    user: dict = Depends(get_current_user),
):
    try:
        return context_retrieval_service.upsert_fact(
            user_id=_user_id(user),
            fact_type=body.fact_type,
            fact_key=body.fact_key,
            fact_value=body.fact_value,
            importance=body.importance,
            confidence=body.confidence,
            source_type=body.source_type,
            source_ref=body.source_ref,
            metadata=body.metadata,
        )
    except ContextRetrievalError as exc:
        raise _translate_error(exc) from exc


@router.delete("/profile/me/facts/{fact_id}")
def archive_my_fact(
    fact_id: str,
    user: dict = Depends(get_current_user),
):
    archived = context_retrieval_service.archive_fact(_user_id(user), fact_id)
    if not archived:
        raise HTTPException(404, "档案事实不存在")
    return {"success": True, "fact_id": fact_id, "status": "archived"}


@router.post("/retrieve")
def retrieve_context(
    body: RetrieveRequest,
    user: dict = Depends(get_current_user),
):
    try:
        return context_retrieval_service.retrieve(
            user_id=_user_id(user),
            query=body.query,
            project_id=body.project_id,
            mission_id=body.mission_id,
            task_id=body.task_id,
            agent_id=body.agent_id,
            purpose=body.purpose,
            limit=body.limit,
            persist=body.persist,
        )
    except ContextRetrievalError as exc:
        raise _translate_error(exc) from exc


@router.post("/packs/{pack_id}/effect", status_code=201)
def record_memory_effect(
    pack_id: str,
    body: MemoryEffectObservation,
    user: dict = Depends(get_current_user),
):
    try:
        return context_retrieval_service.record_memory_effect(
            pack_id=pack_id,
            user_id=_user_id(user),
            event_type=body.event_type,
            source_refs=body.source_refs,
            task_id=body.task_id,
            outcome=body.outcome,
            reason_code=body.reason_code,
            metadata=body.metadata,
            idempotency_key=body.idempotency_key,
        )
    except MemoryEffectivenessError as exc:
        message = str(exc)
        hidden = message in {
            "context pack not found",
            "context pack belongs to another user",
        }
        raise HTTPException(404 if hidden else 400, message) from exc


@router.get("/effectiveness/summary")
def memory_effectiveness_summary(user: dict = Depends(get_current_user)):
    return context_retrieval_service.memory_effectiveness_summary(
        user_id=_user_id(user)
    )


@router.post("/introspect")
def introspect_memory(
    body: MemoryIntrospectionRequest,
    user: dict = Depends(get_current_user),
):
    try:
        return MemoryAwarenessService(context_retrieval_service).inspect(
            user_id=_user_id(user),
            query=body.query,
            project_id=body.project_id,
            agent_id=body.agent_id,
            limit=body.limit,
            persist=body.persist,
        )
    except (ContextRetrievalError, ValueError) as exc:
        raise _translate_error(ContextRetrievalError(str(exc))) from exc


@router.post("/evaluations/graph-memory")
def evaluate_graph_memory(
    body: GraphMemoryEvaluationRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        evaluator = GraphMemoryEvaluationService(context_retrieval_service)
        return evaluator.evaluate(
            user_id=_user_id(user),
            requested_by=str(user.get("username") or user.get("sub") or "admin"),
            cases=[case.model_dump() for case in body.cases],
            modes=body.modes,
            persist=body.persist,
        )
    except GraphMemoryEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


def _retrieval_evaluator() -> MemoryRetrievalEvaluationService:
    return MemoryRetrievalEvaluationService(
        context_retrieval_service,
        context_retrieval_service.db_path,
    )


@router.post("/evaluations/retrieval/cases", status_code=201)
def create_retrieval_evaluation_case(
    body: RetrievalEvaluationCaseUpsert,
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().upsert_case(
            owner_user_id=_user_id(user),
            reviewed_by=str(user.get("username") or user.get("sub") or "admin"),
            payload=body.model_dump(),
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/evaluations/retrieval/cases/generate-drafts")
def generate_retrieval_evaluation_drafts(
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().generate_drafts_from_approved_memories(
            owner_user_id=_user_id(user),
            requested_by=str(user.get("username") or user.get("sub") or "admin"),
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/evaluations/retrieval/cases/generate-variants")
def generate_retrieval_evaluation_variants(
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().generate_variant_drafts(
            owner_user_id=_user_id(user),
            requested_by=str(user.get("username") or user.get("sub") or "admin"),
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/evaluations/retrieval/cases/{case_id}")
def update_retrieval_evaluation_case(
    case_id: str,
    body: RetrievalEvaluationCaseUpsert,
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().upsert_case(
            owner_user_id=_user_id(user),
            reviewed_by=str(user.get("username") or user.get("sub") or "admin"),
            payload=body.model_dump(),
            case_id=case_id,
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/evaluations/retrieval/cases")
def list_retrieval_evaluation_cases(
    status: str = Query("", pattern="^(|draft|active|archived)$"),
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_role("admin")),
):
    try:
        cases = _retrieval_evaluator().list_cases(
            _user_id(user), status=status, limit=limit
        )
        return {"cases": cases, "total": len(cases)}
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/evaluations/retrieval/coverage")
def retrieval_evaluation_coverage(
    user: dict = Depends(require_role("admin")),
):
    return _retrieval_evaluator().coverage(_user_id(user))


@router.get("/evaluations/retrieval/review-queue")
def retrieval_evaluation_review_queue(
    user: dict = Depends(require_role("admin")),
):
    return _retrieval_evaluator().review_queue(_user_id(user))


@router.get("/evaluations/retrieval/cases/{case_id}/events")
def retrieval_evaluation_case_events(
    case_id: str,
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(require_role("admin")),
):
    try:
        events = _retrieval_evaluator().list_case_events(
            _user_id(user), case_id, limit=limit
        )
        return {"events": events, "total": len(events)}
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/evaluations/retrieval/batches", status_code=201)
def create_retrieval_evaluation_batch(
    body: RetrievalEvaluationBatchCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().create_review_batch(
            owner_user_id=_user_id(user),
            requested_by=str(user.get("username") or user.get("sub") or "admin"),
            target_count=body.target_count,
            name=body.name,
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/evaluations/retrieval/batches/latest")
def latest_retrieval_evaluation_batch(
    user: dict = Depends(require_role("admin")),
):
    return {"batch": _retrieval_evaluator().latest_review_batch(_user_id(user))}


@router.put("/evaluations/retrieval/batches/{batch_id}/proposals")
def set_retrieval_evaluation_batch_proposals(
    batch_id: str,
    body: RetrievalEvaluationProposalSet,
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().set_review_proposals(
            owner_user_id=_user_id(user),
            batch_id=batch_id,
            proposed_by=str(user.get("username") or user.get("sub") or "admin"),
            proposals=[proposal.model_dump() for proposal in body.proposals],
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/evaluations/retrieval/run")
def run_retrieval_evaluation(
    body: RetrievalEvaluationRunRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        return _retrieval_evaluator().run(
            owner_user_id=_user_id(user),
            requested_by=str(user.get("username") or user.get("sub") or "admin"),
            case_ids=body.case_ids,
        )
    except MemoryRetrievalEvaluationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/evaluations/retrieval/latest")
def latest_retrieval_evaluation(
    user: dict = Depends(require_role("admin")),
):
    return {"run": _retrieval_evaluator().latest_run(_user_id(user))}


@router.get("/graph-memory/operations")
def graph_memory_operations(
    project_id: str = Query("", max_length=160),
    reconcile_projection: bool = Query(False),
    user: dict = Depends(require_role("admin")),
):
    return GraphMemoryOperationsService(context_retrieval_service).status(
        user_id=_user_id(user),
        project_id=project_id,
        reconcile_projection=reconcile_projection,
    )


@router.put("/graph-memory/rollout")
def update_graph_memory_rollout(
    body: GraphMemoryRolloutUpdate,
    user: dict = Depends(require_role("admin")),
):
    try:
        return context_retrieval_service.set_graph_memory_mode(
            user_id=_user_id(user),
            project_id=body.project_id,
            graph_mode=body.graph_mode,
            updated_by=str(user.get("username") or user.get("sub") or "admin"),
        )
    except ContextRetrievalError as exc:
        raise _translate_error(exc) from exc


@router.get("/vector-memory/operations")
def vector_memory_operations(
    _user: dict = Depends(require_role("admin")),
):
    return context_retrieval_service.vector_memory_operations()


@router.get("/vector-memory/shadow-metrics")
def vector_memory_shadow_metrics(
    window_hours: int = Query(168, ge=1, le=24 * 90),
    _user: dict = Depends(require_role("admin")),
):
    return context_retrieval_service.retrieval_shadow_metrics(
        window_hours=window_hours
    )


@router.get("/vector-memory/rollout-gate")
def vector_memory_rollout_gate(
    window_hours: int = Query(168, ge=1, le=24 * 90),
    user: dict = Depends(require_role("admin")),
):
    return _retrieval_evaluator().rollout_gate(
        owner_user_id=_user_id(user),
        window_hours=window_hours,
    )


@router.post("/vector-memory/backfill")
def backfill_vector_memory(
    _user: dict = Depends(require_role("admin")),
):
    try:
        return context_retrieval_service.enqueue_vector_memory_backfill()
    except ContextRetrievalError as exc:
        raise _translate_error(exc) from exc


@router.post("/vector-memory/process")
def process_vector_memory_jobs(
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(require_role("admin")),
):
    try:
        return context_retrieval_service.process_vector_memory_jobs(
            owner=f"api:{user.get('sub') or 'admin'}",
            limit=limit,
        )
    except ContextRetrievalError as exc:
        raise _translate_error(exc) from exc


@router.get("/packs")
def list_my_context_packs(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    packs = context_retrieval_service.list_packs(_user_id(user), limit=limit)
    return {"packs": packs, "total": len(packs)}


@router.get("/packs/{pack_id}")
def get_my_context_pack(
    pack_id: str,
    user: dict = Depends(get_current_user),
):
    pack = context_retrieval_service.get_pack(pack_id)
    if not pack or pack["user_id"] != _user_id(user):
        raise HTTPException(404, "上下文快照不存在")
    return pack


@router.get("/sources")
def list_context_sources(_user: dict = Depends(get_current_user)):
    sources = context_retrieval_service.list_sources()
    return {"sources": sources, "total": len(sources)}


@router.get("/health")
def context_health(
    agent_id: str = Query("optimus", max_length=160),
    _user: dict = Depends(get_current_user),
):
    return context_retrieval_service.health(agent_id)
