"""Stage-1 Agent Team domain APIs.

Writes are disabled by default and do not dispatch WorkRuns.  The endpoints
exist to validate the persistence contract before shared-task execution is
enabled in a later phase.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth_router import get_current_user
from services.agent_team_service import (
    AgentTeamConflict,
    AgentTeamError,
    AgentTeamNotFound,
    agent_team_service,
)
from services.command_center_service import MissionNotFound


router = APIRouter(prefix="/api/v3/agent-teams", tags=["v3-agent-teams"])


def _enabled() -> bool:
    return os.getenv("AGENT_TEAM_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _owner(user: dict[str, Any]) -> str:
    return "" if str(user.get("role") or "") == "admin" else str(user.get("sub") or "")


def _actor(user: dict[str, Any]) -> str:
    return str(user.get("username") or user.get("sub") or "agent-team-api")


def _write_guard() -> None:
    if not _enabled():
        raise HTTPException(503, "Agent Team 写入尚未启用；当前仅完成持久化契约")


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, (AgentTeamNotFound, MissionNotFound)):
        return HTTPException(404, str(exc))
    if isinstance(exc, AgentTeamConflict):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


class TeamCreateRequest(BaseModel):
    mission_id: str = Field(..., min_length=1, max_length=160)
    name: str = Field(..., min_length=1, max_length=200)
    idempotency_key: str = Field(..., min_length=1, max_length=240)
    leader_agent_id: str = Field("optimus", min_length=1, max_length=160)
    max_members: int = Field(8, ge=1, le=100)
    max_parallel_tasks: int = Field(4, ge=1, le=100)
    policy_version: str = Field("agent-team-v1", min_length=1, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoleCreateRequest(BaseModel):
    role_key: str = Field(..., min_length=1, max_length=120)
    display_name: str = Field(..., min_length=1, max_length=200)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    required_tools: list[str] = Field(default_factory=list, max_length=100)
    min_instances: int = Field(0, ge=0, le=100)
    max_instances: int = Field(1, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InstanceCreateRequest(BaseModel):
    role_id: str = Field(..., min_length=1, max_length=160)
    instance_key: str = Field(..., min_length=1, max_length=160)
    base_agent_id: str = Field(..., min_length=1, max_length=160)
    capacity: int = Field(1, ge=1, le=100)
    context_thread_id: str = Field("", max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreateRequest(BaseModel):
    task_key: str = Field(..., min_length=1, max_length=160)
    title: str = Field(..., min_length=1, max_length=300)
    objective: str = Field(..., min_length=1, max_length=20000)
    idempotency_key: str = Field(..., min_length=1, max_length=240)
    mission_step_id: str = Field("", max_length=160)
    task_type: str = Field("general", max_length=80)
    priority: int = Field(50, ge=0, le=1000)
    risk_class: str = Field("L1", pattern="^L[0-3]$")
    dependency_ids: list[str] = Field(default_factory=list, max_length=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    required_tools: list[str] = Field(default_factory=list, max_length=100)
    input_contract: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    evidence_required: list[str] = Field(default_factory=list, max_length=100)
    max_claims: int = Field(3, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCreateRequest(BaseModel):
    from_instance_id: str = Field(..., min_length=1, max_length=160)
    to_instance_id: str = Field("", max_length=160)
    to_role_id: str = Field("", max_length=160)
    shared_task_id: str = Field("", max_length=160)
    message_type: str = Field(..., min_length=1, max_length=80)
    content: str = Field(..., min_length=1, max_length=20000)
    artifact_refs: list[str] = Field(default_factory=list, max_length=100)
    requires_ack: bool = False
    correlation_id: str = Field("", max_length=200)
    idempotency_key: str = Field(..., min_length=1, max_length=240)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("")
def create_team(body: TeamCreateRequest, user: dict = Depends(get_current_user)):
    _write_guard()
    try:
        return agent_team_service.create_team(
            **body.model_dump(), actor=_actor(user), owner_user_id=_owner(user)
        )
    except (AgentTeamError, MissionNotFound) as exc:
        raise _translate(exc) from exc


@router.post("/{team_id}/roles")
def create_role(team_id: str, body: RoleCreateRequest, user: dict = Depends(get_current_user)):
    _write_guard()
    try:
        return agent_team_service.define_role(
            team_id=team_id, **body.model_dump(), actor=_actor(user), owner_user_id=_owner(user)
        )
    except (AgentTeamError, MissionNotFound) as exc:
        raise _translate(exc) from exc


@router.post("/{team_id}/instances")
def create_instance(team_id: str, body: InstanceCreateRequest, user: dict = Depends(get_current_user)):
    _write_guard()
    try:
        return agent_team_service.register_instance(
            team_id=team_id, **body.model_dump(), actor=_actor(user), owner_user_id=_owner(user)
        )
    except (AgentTeamError, MissionNotFound) as exc:
        raise _translate(exc) from exc


@router.post("/{team_id}/tasks")
def create_task(team_id: str, body: TaskCreateRequest, user: dict = Depends(get_current_user)):
    _write_guard()
    try:
        return agent_team_service.create_task(
            team_id=team_id, **body.model_dump(), actor=_actor(user), owner_user_id=_owner(user)
        )
    except (AgentTeamError, MissionNotFound) as exc:
        raise _translate(exc) from exc


@router.post("/{team_id}/messages")
def create_message(team_id: str, body: MessageCreateRequest, user: dict = Depends(get_current_user)):
    _write_guard()
    try:
        return agent_team_service.send_message(
            team_id=team_id, **body.model_dump(), owner_user_id=_owner(user)
        )
    except (AgentTeamError, MissionNotFound) as exc:
        raise _translate(exc) from exc


@router.get("/{team_id}")
def get_team(team_id: str, user: dict = Depends(get_current_user)):
    try:
        return agent_team_service.snapshot(team_id, owner_user_id=_owner(user))
    except (AgentTeamError, MissionNotFound) as exc:
        raise _translate(exc) from exc
