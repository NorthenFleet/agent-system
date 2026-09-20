"""Authenticated API for the discussion-to-research workspace."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.auth_router import get_current_user
from agent_messenger import agent_messenger
from services.discussion_service import DiscussionError, discussion_service


router = APIRouter(prefix="/api/v3/discussions", tags=["discussions"])


class DiscussionPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    status: str = "captured"
    summary: str = Field("", max_length=2000)
    question: str = Field("", max_length=6000)
    body: str = Field("", max_length=30000)
    current_conclusion: str = Field("", max_length=6000)
    open_questions: list[str] = Field(default_factory=list, max_length=50)
    topics: list[str] = Field(default_factory=list, max_length=50)
    agent_ids: list[str] = Field(default_factory=list, max_length=50)


class DiscussionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    status: str | None = None
    summary: str | None = Field(None, max_length=2000)
    question: str | None = Field(None, max_length=6000)
    body: str | None = Field(None, max_length=30000)
    current_conclusion: str | None = Field(None, max_length=6000)
    open_questions: list[str] | None = Field(None, max_length=50)
    topics: list[str] | None = Field(None, max_length=50)
    agent_ids: list[str] | None = Field(None, max_length=50)


class DiscussionLink(BaseModel):
    target_type: str = Field(..., pattern="^(project|agent|knowledge|discussion)$")
    target_id: str = Field(..., min_length=1, max_length=500)
    relation: str = Field("related", max_length=100)


class PromotionPayload(BaseModel):
    project_name: str = Field("", max_length=160)
    description: str = Field("", max_length=6000)
    hypothesis: str = Field("", max_length=6000)
    owner_agent: str = Field("optimus", max_length=80)


class ConversationPayload(BaseModel):
    agent_id: str = Field("optimus", min_length=1, max_length=80)


class MessagePayload(BaseModel):
    content: str = Field(..., min_length=1, max_length=12000)


def _owner(user: dict[str, Any]) -> str:
    return str(user.get("sub") or user.get("user_id") or "")


def _translate(exc: DiscussionError) -> HTTPException:
    message = str(exc)
    return HTTPException(404 if message == "discussion not found" else 400, message)


@router.get("")
def list_discussions(
    status: str = Query(""),
    q: str = Query("", max_length=500),
    topic: str = Query("", max_length=120),
    limit: int = Query(100, ge=1, le=300),
    user: dict = Depends(get_current_user),
):
    try:
        return discussion_service.list(owner_user_id=_owner(user), status=status, query=q, topic=topic, limit=limit)
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.post("", status_code=201)
def create_discussion(body: DiscussionPayload, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.create(body.model_dump(), owner_user_id=_owner(user))
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationPayload, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.create_conversation(owner_user_id=_owner(user), agent_id=body.agent_id)
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.get("/{discussion_id}")
def get_discussion(discussion_id: str, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.get(discussion_id, owner_user_id=_owner(user))
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.post("/{discussion_id}/messages")
async def send_message(discussion_id: str, body: MessagePayload, user: dict = Depends(get_current_user)):
    owner = _owner(user)
    try:
        prompt = discussion_service.conversation_prompt(discussion_id, body.content, owner_user_id=owner)
        raw_reply = await agent_messenger.request_agent("optimus", prompt, timeout_seconds=120)
        reply, generated = discussion_service.parse_agent_reply(raw_reply)
        return discussion_service.add_turn(discussion_id, body.content, reply, generated, owner_user_id=owner)
    except DiscussionError as exc:
        raise _translate(exc) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, f"研究助手暂时不可用：{exc}") from exc


@router.post("/{discussion_id}/archive")
def archive_conversation(discussion_id: str, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.archive(discussion_id, owner_user_id=_owner(user))
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.put("/{discussion_id}")
def update_discussion(discussion_id: str, body: DiscussionUpdate, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.update(
            discussion_id,
            body.model_dump(exclude_unset=True),
            owner_user_id=_owner(user),
        )
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.post("/{discussion_id}/links")
def add_discussion_link(discussion_id: str, body: DiscussionLink, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.add_link(discussion_id, body.model_dump(), owner_user_id=_owner(user))
    except DiscussionError as exc:
        raise _translate(exc) from exc


@router.post("/{discussion_id}/promote")
def promote_discussion(discussion_id: str, body: PromotionPayload, user: dict = Depends(get_current_user)):
    try:
        return discussion_service.promote(discussion_id, body.model_dump(), owner_user_id=_owner(user))
    except DiscussionError as exc:
        raise _translate(exc) from exc
