"""Authenticated APIs for user profiles and versioned context packs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.auth_router import get_current_user
from services.context_retrieval_service import (
    ContextRetrievalError,
    context_retrieval_service,
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
