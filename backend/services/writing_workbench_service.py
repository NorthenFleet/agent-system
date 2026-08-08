"""Persistent state for the dual-pane writing workbench."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from models.writing_collaboration import (
    PresentationAiJob,
    WritingAiConversation,
    WritingAiJob,
    WritingAiMessage,
    WritingWorkspacePreference,
)
from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import MultiDocumentService, multi_document_service
from services.writing_collaboration_service import (
    WritingCollaborationService,
    writing_collaboration_service,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _response_client_id(client_message_id: str) -> str:
    return f"reply:{client_message_id}"[:96]


DEFAULT_PREFERENCE: dict[str, Any] = {
    "schema_version": 2,
    "preset": "writing",
    "split_percent": 42,
    "maximized_pane": None,
    "panes": {
        "left": {"module": "ai", "ai_target_locked": False},
        "right": {"module": "document", "ai_target_locked": False},
    },
}


class WritingWorkbenchConflict(DocumentWorkspaceError):
    pass


class WritingWorkbenchService:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        collaboration_service: WritingCollaborationService = writing_collaboration_service,
        documents_service: MultiDocumentService = multi_document_service,
    ) -> None:
        self.session_factory = session_factory
        self.collaboration_service = collaboration_service
        self.documents_service = documents_service

    def _preference_dict(self, row: WritingWorkspacePreference | None) -> dict[str, Any]:
        preference = copy.deepcopy(DEFAULT_PREFERENCE)
        if row:
            preference.update(copy.deepcopy(row.preference_json or {}))
            if preference.get("preset") == "comparison":
                preference["preset"] = "document_presentation"
            preference["schema_version"] = 2
            preference["revision"] = row.revision
            preference["updated_at"] = row.updated_at.isoformat() if row.updated_at else ""
        else:
            preference["revision"] = 0
            preference["updated_at"] = ""
        return preference

    def get_preference(self, project_id: str, owner_user_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.execute(select(WritingWorkspacePreference).where(
                WritingWorkspacePreference.project_id == project_id,
                WritingWorkspacePreference.owner_user_id == owner_user_id,
            )).scalar_one_or_none()
            return self._preference_dict(row)

    def update_preference(
        self,
        project_id: str,
        owner_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        expected_revision = int(payload.pop("expected_revision", 0) or 0)
        preference = copy.deepcopy(DEFAULT_PREFERENCE)
        preference.update(copy.deepcopy(payload))
        if preference.get("preset") == "comparison":
            preference["preset"] = "document_presentation"
        preference["schema_version"] = 2
        preference.pop("revision", None)
        preference.pop("updated_at", None)
        with self.session_factory() as session:
            row = session.execute(
                select(WritingWorkspacePreference)
                .where(
                    WritingWorkspacePreference.project_id == project_id,
                    WritingWorkspacePreference.owner_user_id == owner_user_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            current_revision = row.revision if row else 0
            if expected_revision != current_revision:
                raise WritingWorkbenchConflict(
                    f"工作台布局已在其他设备更新：当前修订 {current_revision}"
                )
            if row:
                row.preference_json = preference
                row.schema_version = 2
                row.revision += 1
                row.updated_at = _now()
            else:
                row = WritingWorkspacePreference(
                    id=_uuid("wpref"),
                    project_id=project_id,
                    owner_user_id=owner_user_id,
                    schema_version=2,
                    revision=1,
                    preference_json=preference,
                )
                session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                current = session.execute(select(WritingWorkspacePreference).where(
                    WritingWorkspacePreference.project_id == project_id,
                    WritingWorkspacePreference.owner_user_id == owner_user_id,
                )).scalar_one_or_none()
                current_revision = current.revision if current else 0
                raise WritingWorkbenchConflict(
                    f"工作台布局已在其他设备更新：当前修订 {current_revision}"
                ) from exc
            session.refresh(row)
            return self._preference_dict(row)

    def _conversation(
        self,
        session,
        project_id: str,
        owner_user_id: str,
        conversation_id: str,
    ) -> WritingAiConversation:
        row = session.get(WritingAiConversation, conversation_id)
        if (
            not row
            or row.project_id != project_id
            or row.owner_user_id != owner_user_id
        ):
            raise DocumentWorkspaceError("AI 协作会话不存在")
        return row

    def _conversation_dict(self, row: WritingAiConversation) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "agent_id": row.agent_id,
            "title": row.title,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    def _message_dict(self, row: WritingAiMessage) -> dict[str, Any]:
        return {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "role": row.role,
            "content": row.content,
            "target_context": copy.deepcopy(row.target_context or {}),
            "job_kind": row.job_kind,
            "job_id": row.job_id,
            "proposal_ids": list(row.proposal_ids or []),
            "status": row.status,
            "error": row.error,
            "client_message_id": row.client_message_id,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    def list_conversations(self, project_id: str, owner_user_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.execute(select(WritingAiConversation).where(
                WritingAiConversation.project_id == project_id,
                WritingAiConversation.owner_user_id == owner_user_id,
                WritingAiConversation.status != "archived",
            ).order_by(WritingAiConversation.updated_at.desc())).scalars().all()
            return [self._conversation_dict(row) for row in rows]

    def create_conversation(
        self,
        project_id: str,
        owner_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = WritingAiConversation(
            id=_uuid("wconv"),
            project_id=project_id,
            owner_user_id=owner_user_id,
            agent_id=str(payload.get("agent_id") or "ultra-magnus")[:64],
            title=str(payload.get("title") or "协作会话")[:200],
            status="active",
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._conversation_dict(row)

    def list_messages(
        self,
        project_id: str,
        owner_user_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            self._conversation(session, project_id, owner_user_id, conversation_id)
            rows = session.execute(select(WritingAiMessage).where(
                WritingAiMessage.conversation_id == conversation_id,
            ).order_by(WritingAiMessage.created_at.asc())).scalars().all()
            return [self._message_dict(row) for row in rows]

    def _create_message_pair(
        self,
        project_id: str,
        owner_user_id: str,
        conversation_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any], bool]:
        target = copy.deepcopy(payload.get("target") or {})
        content = str(payload.get("content") or "").strip()
        if not content:
            raise DocumentWorkspaceError("AI 协作指令不能为空")
        client_message_id = str(payload.get("client_message_id") or _uuid("client"))[:80]
        response_client_id = _response_client_id(client_message_id)
        request_id = _uuid("wmsg")
        response_id = _uuid("wmsg")
        with self.session_factory() as session:
            conversation = self._conversation(
                session, project_id, owner_user_id, conversation_id
            )
            existing = session.execute(select(WritingAiMessage).where(
                WritingAiMessage.conversation_id == conversation_id,
                WritingAiMessage.client_message_id == client_message_id,
            )).scalar_one_or_none()
            if existing:
                response = session.execute(select(WritingAiMessage).where(
                    WritingAiMessage.conversation_id == conversation_id,
                    WritingAiMessage.client_message_id == response_client_id,
                )).scalar_one_or_none()
                return existing.id, response.id if response else "", target, True
            session.add(WritingAiMessage(
                id=request_id,
                conversation_id=conversation_id,
                project_id=project_id,
                role="user",
                content=content,
                target_context=target,
                status="completed",
                client_message_id=client_message_id,
            ))
            session.add(WritingAiMessage(
                id=response_id,
                conversation_id=conversation_id,
                project_id=project_id,
                role="assistant",
                content="正在生成修改建议……",
                target_context=target,
                status="queued",
                client_message_id=response_client_id,
            ))
            conversation.updated_at = _now()
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(select(WritingAiMessage).where(
                    WritingAiMessage.conversation_id == conversation_id,
                    WritingAiMessage.client_message_id == client_message_id,
                )).scalar_one_or_none()
                response = session.execute(select(WritingAiMessage).where(
                    WritingAiMessage.conversation_id == conversation_id,
                    WritingAiMessage.client_message_id == response_client_id,
                )).scalar_one_or_none()
                if existing:
                    return existing.id, response.id if response else "", target, True
                raise
        return request_id, response_id, target, False

    def submit_message(
        self,
        project: dict[str, Any],
        owner_user_id: str,
        conversation_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(project.get("id") or "")
        request_id, response_id, target, idempotent_replay = self._create_message_pair(
            project_id, owner_user_id, conversation_id, payload
        )
        if idempotent_replay:
            return {
                "request_message_id": request_id,
                "response_message_id": response_id,
                "idempotent_replay": True,
            }
        target_kind = str(target.get("kind") or "")
        document_id = str(target.get("document_id") or "")
        content = str(payload.get("content") or "").strip()
        try:
            if not document_id:
                raise DocumentWorkspaceError("AI目标缺少文档资源")
            if target_kind == "document":
                self.documents_service.assert_writable(project, document_id)
                job_payload = {
                    "client_request_id": str(payload.get("client_message_id") or request_id),
                    "agent_id": str(payload.get("agent_id") or "ultra-magnus"),
                    "scope": str(target.get("scope") or "section"),
                    "instruction": content,
                    "section_id": str(target.get("section_id") or ""),
                    "selection": target.get("selection"),
                    "block_id": target.get("block_id"),
                    "block_revision": target.get("block_revision"),
                    "risk_policy": {"allow_auto_draft": True},
                    "conversation_id": conversation_id,
                    "request_message_id": request_id,
                    "response_message_id": response_id,
                }
                job = self.collaboration_service.submit_ai_job(
                    project, document_id, job_payload, owner_user_id
                )
                with self.session_factory() as session:
                    job_row = session.get(WritingAiJob, job["id"])
                    response = session.get(WritingAiMessage, response_id)
                    if response:
                        response.job_kind = "document"
                        response.job_id = str(job.get("id") or "")
                        response.status = str(job.get("status") or "queued")
                        if job_row:
                            job_row.conversation_id = conversation_id
                            job_row.request_message_id = request_id
                            job_row.response_message_id = response_id
                        session.commit()
                return {"job": job, "response_message_id": response_id}
            if target_kind == "presentation":
                job = self.submit_presentation_job(
                    project,
                    document_id,
                    {
                        "slide": int(target.get("slide") or 1),
                        "draft": copy.deepcopy(target.get("draft") or {}),
                        "instruction": content,
                        "agent_id": str(payload.get("agent_id") or "presentation-editor"),
                        "client_request_id": str(payload.get("client_message_id") or request_id),
                    },
                    owner_user_id,
                    conversation_id=conversation_id,
                    request_message_id=request_id,
                    response_message_id=response_id,
                )
                return {"job": job, "response_message_id": response_id}
            raise DocumentWorkspaceError("AI目标必须是文档或PPT")
        except Exception as exc:
            with self.session_factory() as session:
                response = session.get(WritingAiMessage, response_id)
                if response:
                    response.status = "failed"
                    response.content = "任务提交失败"
                    response.error = str(exc)[:4000]
                    session.commit()
            raise

    def submit_presentation_job(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
        *,
        conversation_id: str = "",
        request_message_id: str = "",
        response_message_id: str = "",
    ) -> dict[str, Any]:
        project_id = str(project.get("id") or "")
        client_request_id = str(payload.get("client_request_id") or _uuid("request"))[:96]
        with self.session_factory() as session:
            existing = session.execute(select(PresentationAiJob).where(
                PresentationAiJob.project_id == project_id,
                PresentationAiJob.document_id == document_id,
                PresentationAiJob.client_request_id == client_request_id,
            )).scalar_one_or_none()
            if existing:
                return self._presentation_job_dict(existing)
            row = PresentationAiJob(
                id=_uuid("pptjob"),
                project_id=project_id,
                document_id=document_id,
                slide=max(1, int(payload.get("slide") or 1)),
                client_request_id=client_request_id,
                agent_id=str(payload.get("agent_id") or "presentation-editor")[:64],
                instruction=str(payload.get("instruction") or "").strip(),
                draft=copy.deepcopy(payload.get("draft") or {}),
                status="running",
                requested_by=actor,
                conversation_id=conversation_id,
                request_message_id=request_message_id,
                response_message_id=response_message_id,
                started_at=_now(),
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(select(PresentationAiJob).where(
                    PresentationAiJob.project_id == project_id,
                    PresentationAiJob.document_id == document_id,
                    PresentationAiJob.client_request_id == client_request_id,
                )).scalar_one_or_none()
                if existing:
                    return self._presentation_job_dict(existing)
                raise
            job_id = row.id
        try:
            proposal = self.documents_service.presentation_slide_proposal(
                project,
                document_id,
                max(1, int(payload.get("slide") or 1)),
                copy.deepcopy(payload.get("draft") or {}),
                str(payload.get("instruction") or ""),
                str(payload.get("agent_id") or "presentation-editor"),
            )
            with self.session_factory() as session:
                row = session.get(PresentationAiJob, job_id)
                row.status = "succeeded"
                row.proposal = proposal
                row.finished_at = _now()
                if row.response_message_id:
                    message = session.get(WritingAiMessage, row.response_message_id)
                    if message:
                        message.job_kind = "presentation"
                        message.job_id = row.id
                        message.status = "succeeded"
                        message.content = str(proposal.get("summary") or "已生成PPT修改建议")
                        proposal_id = str(proposal.get("id") or "")
                        message.proposal_ids = [proposal_id] if proposal_id else []
                session.commit()
                return self._presentation_job_dict(row)
        except Exception as exc:
            with self.session_factory() as session:
                row = session.get(PresentationAiJob, job_id)
                if row:
                    row.status = "failed"
                    row.error = str(exc)[:4000]
                    row.finished_at = _now()
                    if row.response_message_id:
                        message = session.get(WritingAiMessage, row.response_message_id)
                        if message:
                            message.status = "failed"
                            message.content = "PPT建议生成失败"
                            message.error = row.error
                    session.commit()
            raise

    def _presentation_job_dict(self, row: PresentationAiJob) -> dict[str, Any]:
        return {
            "id": row.id,
            "status": row.status,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "slide": row.slide,
            "agent_id": row.agent_id,
            "instruction": row.instruction,
            "proposal": copy.deepcopy(row.proposal or None),
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    def get_presentation_job(
        self,
        project_id: str,
        document_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(PresentationAiJob, job_id)
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("PPT页面AI任务不存在")
            return self._presentation_job_dict(row)

    def cancel_presentation_job(
        self,
        project_id: str,
        document_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(PresentationAiJob, job_id)
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("PPT页面AI任务不存在")
            if row.status not in {"succeeded", "failed", "cancelled"}:
                row.status = "cancelled"
                row.finished_at = _now()
                if row.response_message_id:
                    response = session.get(WritingAiMessage, row.response_message_id)
                    if response:
                        response.status = "cancelled"
                        response.content = "任务已取消"
                session.commit()
            return self._presentation_job_dict(row)

    def cancel_message(
        self,
        project: dict[str, Any],
        owner_user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, Any]:
        project_id = str(project.get("id") or "")
        with self.session_factory() as session:
            self._conversation(session, project_id, owner_user_id, conversation_id)
            message = session.get(WritingAiMessage, message_id)
            if not message or message.conversation_id != conversation_id:
                raise DocumentWorkspaceError("AI消息不存在")
            job_kind = message.job_kind
            job_id = message.job_id
            target = copy.deepcopy(message.target_context or {})
        if job_kind == "document" and job_id:
            self.collaboration_service.cancel_ai_job(
                project, str(target.get("document_id") or ""), job_id
            )
        elif job_kind == "presentation" and job_id:
            self.cancel_presentation_job(
                project_id, str(target.get("document_id") or ""), job_id
            )
        with self.session_factory() as session:
            message = session.get(WritingAiMessage, message_id)
            if message and message.status not in {
                "succeeded",
                "applied",
                "partially_applied",
                "conflicted",
                "review_required",
                "failed",
                "cancelled",
            }:
                message.status = "cancelled"
                message.content = "任务已取消"
                session.commit()
            return self._message_dict(message)


writing_workbench_service = WritingWorkbenchService()
