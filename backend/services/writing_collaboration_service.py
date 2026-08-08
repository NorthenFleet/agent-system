"""Transactional human-AI collaboration over structured document JSON."""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent_messenger import agent_messenger
from database import SessionLocal
from models.writing_collaboration import (
    WritingAiJob,
    WritingAiMessage,
    WritingAiProposal,
    WritingChangeSet,
    WritingChangeEvent,
    WritingDocumentState,
    WritingDocumentVersion,
    WritingEvidenceRef,
)
from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceError,
    DocumentWorkspaceService,
    document_workspace_service,
)
from services.multi_document_service import MultiDocumentService, multi_document_service
from services.structured_document_service import (
    SCHEMA_VERSION,
    StructuredDocumentCodec,
    structured_document_codec,
)


AiRequester = Callable[[str, str], Awaitable[str]]
TERMINAL_JOB_STATUSES = {
    "partially_applied",
    "applied",
    "conflicted",
    "review_required",
    "failed",
    "cancelled",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _feature_enabled() -> bool:
    return os.getenv("WRITING_COLLABORATION_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


LOW_RISK_INSTRUCTION = re.compile(r"(润色|措辞|语法|标点|格式|排版|压缩冗余|结构整理|错别字)")
EVIDENCE_SENSITIVE_TEXT = re.compile(
    r"(研究表明|实验|结果|结论|显著|提升|降低|准确率|胜率|证据|引用|文献|图\s*\d|表\s*\d|式\s*\d|公式|\[[0-9]+\]|\d+(?:\.\d+)?\s*%)",
    flags=re.IGNORECASE,
)


class WritingCollaborationDisabled(DocumentWorkspaceError):
    pass


class WritingCollaborationService:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        codec: StructuredDocumentCodec = structured_document_codec,
        workspace_service: DocumentWorkspaceService = document_workspace_service,
        documents_service: MultiDocumentService = multi_document_service,
        ai_requester: AiRequester | None = None,
        allow_non_postgres_writes: bool | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.codec = codec
        self.workspace_service = workspace_service
        self.documents_service = documents_service
        self.ai_requester = ai_requester or agent_messenger.request_agent
        self.allow_non_postgres_writes = (
            os.getenv("WRITING_COLLABORATION_ALLOW_NON_POSTGRES", "0").strip().lower()
            in {"1", "true", "on", "yes"}
            if allow_non_postgres_writes is None
            else allow_non_postgres_writes
        )

    def _sync_job_message(self, session: Session, job: WritingAiJob) -> None:
        if not job.response_message_id:
            return
        message = session.get(WritingAiMessage, job.response_message_id)
        if not message:
            return
        message.job_kind = "document"
        message.job_id = job.id
        message.status = job.status
        message.error = job.error or ""
        message.content = job.summary or job.error or {
            "queued": "任务已排队",
            "running": "正在生成修改建议……",
            "cancelled": "任务已取消",
        }.get(job.status, "AI写作任务已更新")
        message.proposal_ids = [proposal.id for proposal in job.proposals or []]

    def _require_enabled(self) -> None:
        if not _feature_enabled():
            raise WritingCollaborationDisabled("人机双写功能当前未启用")

    def _require_mutation_backend(self) -> None:
        self._require_enabled()
        with self.session_factory() as session:
            dialect = session.get_bind().dialect.name
        if dialect != "postgresql" and not self.allow_non_postgres_writes:
            raise WritingCollaborationDisabled(
                "人机双写仅允许在 PostgreSQL 上写入；SQLite 仅用于显式测试模式"
            )

    def _context(self, project: dict[str, Any], document_id: str) -> dict[str, Any]:
        return self.documents_service.rich_project(project, document_id)

    def _state_query(self, project_id: str, document_id: str):
        return select(WritingDocumentState).where(
            WritingDocumentState.project_id == project_id,
            WritingDocumentState.document_id == document_id,
        )

    def _load_state(
        self,
        session: Session,
        project_id: str,
        document_id: str,
        *,
        lock: bool = False,
    ) -> WritingDocumentState | None:
        statement = self._state_query(project_id, document_id)
        if lock:
            statement = statement.with_for_update()
        return session.execute(statement).scalar_one_or_none()

    def _validate_round_trip(self, markdown: str, document: dict[str, Any]) -> None:
        projected = self.codec.to_markdown(document)
        reparsed = self.codec.from_markdown(projected, namespace="roundtrip-validation")
        before = self.codec.metrics(document)
        after = self.codec.metrics(reparsed)
        keys = (
            "heading_count",
            "table_count",
            "image_count",
            "citation_count",
            "plain_text_sha256",
        )
        differences = [key for key in keys if before[key] != after[key]]
        if differences:
            raise DocumentWorkspaceError(
                "结构化迁移往返校验失败，未切换正文权威：" + "、".join(differences)
            )
        if markdown.strip() and not projected.strip():
            raise DocumentWorkspaceError("结构化迁移生成了空投影，未切换正文权威")

    def ensure_state(
        self,
        project: dict[str, Any],
        document_id: str,
    ) -> WritingDocumentState:
        self._require_mutation_backend()
        project_id = str(project.get("id") or "")
        if not project_id:
            raise DocumentWorkspaceError("项目标识不能为空")
        with self.session_factory() as session:
            existing = self._load_state(session, project_id, document_id)
            if existing:
                return existing

        context = self._context(project, document_id)
        fulltext = self.workspace_service.fulltext(context)
        markdown = str(fulltext.get("content") or "")
        revision = max(int(fulltext.get("version") or 1), 1)
        document = self.codec.from_markdown(
            markdown,
            namespace=f"{project_id}/{document_id}",
        )
        self._validate_round_trip(markdown, document)
        content_sha = self.codec.document_sha256(document)
        source_sha = _sha256(markdown)
        state = WritingDocumentState(
            project_id=project_id,
            document_id=document_id,
            schema_version=SCHEMA_VERSION,
            document_revision=revision,
            content_json=document,
            content_sha256=content_sha,
            source_markdown_sha256=source_sha,
            projection_revision=revision,
            projection_status="current",
        )
        initial_version = WritingDocumentVersion(
            id=_uuid("wver"),
            project_id=project_id,
            document_id=document_id,
            document_revision=revision,
            label="结构化正文迁移",
            reason="migration",
            content_json=copy.deepcopy(document),
            content_sha256=content_sha,
            markdown_snapshot=markdown,
            actor_type="system",
            actor_id="migration",
        )
        try:
            with self.session_factory() as session:
                session.add(state)
                session.add(initial_version)
                session.commit()
        except IntegrityError:
            with self.session_factory() as session:
                existing = self._load_state(session, project_id, document_id)
                if existing:
                    return existing
            raise

        try:
            self.workspace_service.apply_structured_projection(
                context,
                self.codec.to_markdown(document),
                revision,
                "structured-migration",
                checkpoint_label="before-structured-authority",
            )
        except Exception as exc:
            self._mark_projection_stale(project, document_id, revision, exc)
        with self.session_factory() as session:
            return self._load_state(session, project_id, document_id)  # type: ignore[return-value]

    def _block_text(self, node: dict[str, Any]) -> str:
        if node.get("type") == "text":
            return str(node.get("text") or "")
        return "".join(self._block_text(child) for child in node.get("content") or [])

    def _section_range(
        self,
        context: dict[str, Any],
        document: dict[str, Any],
        section_id: str,
    ) -> tuple[int, int, dict[str, Any]]:
        blocks = document.get("content") or []
        if not section_id:
            return 0, len(blocks), {
                "id": "",
                "title": str(context.get("_document_title") or context.get("name") or "全文"),
            }
        heading_positions = [
            index
            for index, block in enumerate(blocks)
            if block.get("type") == "heading"
            and int((block.get("attrs") or {}).get("level") or 1) == 1
        ]
        stable_position = next(
            (
                index
                for index in heading_positions
                if str((blocks[index].get("attrs") or {}).get("blockId") or "")
                == section_id
            ),
            None,
        )
        if stable_position is not None:
            order_index = heading_positions.index(stable_position)
            section = {
                "id": "",
                "title": self._block_text(blocks[stable_position]),
                "order_index": order_index,
                "kind": "chapter",
            }
        else:
            section = self.workspace_service.section(context, section_id)
            order_index = int(section.get("order_index") or 0)
        if order_index >= len(heading_positions):
            raise DocumentWorkspaceError("结构化正文无法定位所选章节")
        start = heading_positions[order_index]
        end = heading_positions[order_index + 1] if order_index + 1 < len(heading_positions) else len(blocks)
        stable_section_id = str((blocks[start].get("attrs") or {}).get("blockId") or "")
        if not stable_section_id:
            raise DocumentWorkspaceError("所选章节缺少稳定标识")
        return start, end, {
            "id": stable_section_id,
            "legacy_id": str(section.get("id") or ""),
            "title": self._block_text(blocks[start]) or section.get("title") or "未命名章节",
            "kind": section.get("kind") or "",
            "order_index": order_index,
        }

    def _agents(self) -> list[dict[str, Any]]:
        return [
            {"id": "ultra-magnus", "name": "通天晓 · 文档写作", "role": "写作", "available": True},
            {"id": "perceptor", "name": "感知器 · 审稿", "role": "审稿", "available": True},
            {"id": "ratchet", "name": "救护车 · 资料核查", "role": "资料核查", "available": True},
            {"id": "michelangelo", "name": "米开朗基罗 · 格式检查", "role": "格式", "available": True},
        ]

    def _proposal_dict(self, proposal: WritingAiProposal) -> dict[str, Any]:
        job = proposal.job
        return {
            "id": proposal.id,
            "job_id": proposal.job_id,
            "agent_id": job.agent_id if job else "",
            "block_id": proposal.block_id,
            "operation_type": proposal.operation_type,
            "scope": job.scope if job else "block",
            "title": proposal.summary or "AI 修改建议",
            "summary": proposal.summary,
            "rationale": proposal.rationale,
            "instruction": job.instruction if job else "",
            "diff": proposal.diff,
            "replacement_markdown": proposal.replacement_markdown,
            "status": proposal.status,
            "risk_level": proposal.risk_level,
            "approval_required": proposal.approval_required,
            "evidence_ref_ids": proposal.evidence_ref_ids or [],
            "concurrency_status": proposal.concurrency_status,
            "requires_rebase": proposal.status == "pending" and proposal.concurrency_status == "conflicted",
            "created_at": proposal.created_at.isoformat() if proposal.created_at else "",
        }

    def _pending_proposals(
        self,
        session: Session,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, Any]]:
        proposals = session.execute(
            select(WritingAiProposal)
            .where(
                WritingAiProposal.project_id == project_id,
                WritingAiProposal.document_id == document_id,
                WritingAiProposal.status == "pending",
            )
            .order_by(WritingAiProposal.created_at.desc())
            .limit(50)
        ).scalars().all()
        return [self._proposal_dict(row) for row in proposals]

    def _state_dict(
        self,
        session: Session,
        state: WritingDocumentState,
        context: dict[str, Any],
        section_id: str,
    ) -> dict[str, Any]:
        full_document = copy.deepcopy(state.content_json)
        start, end, section = self._section_range(context, full_document, section_id)
        section_document = {
            "type": "doc",
            "attrs": copy.deepcopy(full_document.get("attrs") or {}),
            "content": copy.deepcopy((full_document.get("content") or [])[start:end]),
        }
        section["block_ids"] = [
            str((block.get("attrs") or {}).get("blockId") or "")
            for block in section_document["content"]
        ]
        return {
            "feature_enabled": True,
            "schema_version": state.schema_version,
            "revision": state.document_revision,
            "document_revision": state.document_revision,
            "approved_revision": state.approved_revision,
            "published_revision": state.published_revision,
            "document": section_document,
            "draft": {"revision": state.document_revision, "document": section_document},
            "section": section,
            "projection": {
                "revision": state.projection_revision,
                "status": state.projection_status,
                "error": state.projection_error,
            },
            "agents": self._agents(),
            "proposals": self._pending_proposals(
                session,
                state.project_id,
                state.document_id,
            ),
        }

    def get_state(
        self,
        project: dict[str, Any],
        document_id: str,
        section_id: str = "",
    ) -> dict[str, Any]:
        self._require_enabled()
        context = self._context(project, document_id)
        with self.session_factory() as session:
            current = self._load_state(session, str(project.get("id")), document_id)
            if not current:
                raise DocumentWorkspaceError(
                    "该文档尚未启用人机双写，请由管理员先执行结构化迁移"
                )
            return self._state_dict(session, current, context, section_id)

    def _validate_document(self, document: Any, namespace: str) -> dict[str, Any]:
        if not isinstance(document, dict) or document.get("type") != "doc":
            raise DocumentWorkspaceError("正文必须是 Tiptap JSON 文档")
        if not isinstance(document.get("content"), list):
            raise DocumentWorkspaceError("正文 content 必须是数组")
        value = copy.deepcopy(document)
        try:
            self.codec.validate_document(value, require_block_ids=True)
        except ValueError as exc:
            raise DocumentWorkspaceError(f"正文 JSON 不符合编辑器契约：{exc}") from exc
        return value

    def _find_block(self, document: dict[str, Any], block_id: str) -> tuple[int, dict[str, Any]] | None:
        for index, block in enumerate(document.get("content") or []):
            if str((block.get("attrs") or {}).get("blockId") or "") == block_id:
                return index, block
        return None

    def _assert_section_boundaries(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        protected = {
            str((block.get("attrs") or {}).get("blockId") or "")
            for block in before.get("content") or []
            if block.get("type") == "heading"
            and int((block.get("attrs") or {}).get("level") or 1) == 1
        }
        current = {
            str((block.get("attrs") or {}).get("blockId") or "")
            for block in after.get("content") or []
            if block.get("type") == "heading"
            and int((block.get("attrs") or {}).get("level") or 1) == 1
        }
        if not protected.issubset(current):
            raise DocumentWorkspaceError(
                "章节一级标题不能在正文编辑器中删除或降级，请在项目文档结构中调整章节"
            )

    def _apply_operations(
        self,
        document: dict[str, Any],
        operations: list[dict[str, Any]],
        *,
        namespace: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        applied: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        for operation in operations:
            kind = str(operation.get("op") or operation.get("action") or "upsert")
            block_id = str(operation.get("block_id") or operation.get("blockId") or "")
            expected = operation.get("expected_block_revision")
            if expected is None:
                expected = operation.get("block_revision")
            expected_revision = int(expected or 0)
            found = self._find_block(document, block_id) if block_id else None
            if kind in {"delete", "replace", "upsert"} and found:
                index, current = found
                current_revision = int((current.get("attrs") or {}).get("blockRevision") or 1)
                if expected_revision != current_revision:
                    conflicts.append({
                        "block_id": block_id,
                        "expected_block_revision": expected_revision,
                        "current_block_revision": current_revision,
                        "reason": "block_revision_changed",
                    })
                    continue
                if kind == "delete":
                    document["content"].pop(index)
                    applied.append({"op": "delete", "block_id": block_id})
                    continue
                node = operation.get("node") or operation.get("content")
                if not isinstance(node, dict):
                    conflicts.append({"block_id": block_id, "reason": "missing_node"})
                    continue
                node = copy.deepcopy(node)
                attrs = node.setdefault("attrs", {})
                attrs["blockId"] = block_id
                attrs["blockRevision"] = current_revision + 1
                document["content"][index] = node
                applied.append({"op": "upsert", "block_id": block_id, "node": copy.deepcopy(node)})
                continue
            if kind == "move_after" and found:
                index, current = found
                current_revision = int((current.get("attrs") or {}).get("blockRevision") or 1)
                if expected_revision != current_revision:
                    conflicts.append({
                        "block_id": block_id,
                        "expected_block_revision": expected_revision,
                        "current_block_revision": current_revision,
                        "reason": "block_revision_changed",
                    })
                    continue
                after_id = str(operation.get("after_block_id") or "")
                before_id = str(operation.get("before_block_id") or "")
                if after_id == block_id or before_id == block_id:
                    conflicts.append({"block_id": block_id, "reason": "invalid_move_anchor"})
                    continue
                moving = document["content"].pop(index)
                after = self._find_block(document, after_id) if after_id else None
                before = self._find_block(document, before_id) if before_id else None
                if after_id and not after:
                    document["content"].insert(index, moving)
                    conflicts.append({"block_id": block_id, "reason": "move_anchor_missing"})
                    continue
                if before_id and not before:
                    document["content"].insert(index, moving)
                    conflicts.append({"block_id": block_id, "reason": "move_anchor_missing"})
                    continue
                insert_at = after[0] + 1 if after else before[0] if before else 0
                document["content"].insert(insert_at, moving)
                applied.append({
                    "op": "move_after",
                    "block_id": block_id,
                    "after_block_id": after_id,
                    "before_block_id": before_id,
                })
                continue
            if kind in {"insert", "insert_after"} and not found:
                node = operation.get("node") or operation.get("content")
                if not isinstance(node, dict):
                    conflicts.append({"block_id": block_id, "reason": "missing_node"})
                    continue
                node = copy.deepcopy(node)
                temporary = {"type": "doc", "content": [node]}
                self.codec.ensure_block_ids(temporary, namespace=f"{namespace}/{len(document.get('content') or [])}")
                node = temporary["content"][0]
                attrs = node.setdefault("attrs", {})
                if block_id:
                    attrs["blockId"] = block_id
                attrs["blockRevision"] = 1
                after_id = str(operation.get("after_block_id") or "")
                before_id = str(operation.get("before_block_id") or "")
                after = self._find_block(document, after_id) if after_id else None
                before = self._find_block(document, before_id) if before_id else None
                insert_at = (
                    after[0] + 1
                    if after
                    else before[0]
                    if before
                    else len(document.get("content") or [])
                )
                document.setdefault("content", []).insert(insert_at, node)
                applied.append({"op": "insert_after", "block_id": attrs["blockId"], "after_block_id": after_id, "node": copy.deepcopy(node)})
                continue
            if kind == "upsert" and not found:
                conflicts.append({
                    "block_id": block_id,
                    "expected_block_revision": expected_revision,
                    "reason": "block_deleted",
                })
                continue
            conflicts.append({"block_id": block_id, "reason": "block_missing"})
        return applied, conflicts

    def _operations_from_section_document(
        self,
        current_document: dict[str, Any],
        incoming_document: dict[str, Any],
        context: dict[str, Any],
        section_id: str,
        expected_document_revision: int,
        current_document_revision: int,
    ) -> list[dict[str, Any]]:
        start, end, _ = self._section_range(context, current_document, section_id)
        current_blocks = current_document.get("content") or []
        section_blocks = current_blocks[start:end]
        incoming_blocks = incoming_document.get("content") or []
        current_by_id = {
            str((block.get("attrs") or {}).get("blockId") or ""): block
            for block in section_blocks
        }
        incoming_ids = {
            str((block.get("attrs") or {}).get("blockId") or "")
            for block in incoming_blocks
        }
        operations: list[dict[str, Any]] = []
        previous_id = ""
        for block in incoming_blocks:
            block_id = str((block.get("attrs") or {}).get("blockId") or "")
            existing = current_by_id.get(block_id)
            if existing:
                if self.codec.block_sha256(existing) != self.codec.block_sha256(block):
                    operations.append({
                        "op": "upsert",
                        "block_id": block_id,
                        "expected_block_revision": int((block.get("attrs") or {}).get("blockRevision") or 0),
                        "node": block,
                    })
            else:
                operations.append({
                    "op": "insert_after",
                    "block_id": block_id,
                    "expected_block_revision": 0,
                    "after_block_id": previous_id,
                    "node": block,
                })
            previous_id = block_id
        current_existing_order = [
            str((block.get("attrs") or {}).get("blockId") or "")
            for block in section_blocks
            if str((block.get("attrs") or {}).get("blockId") or "") in incoming_ids
        ]
        desired_existing_order = [
            str((block.get("attrs") or {}).get("blockId") or "")
            for block in incoming_blocks
            if str((block.get("attrs") or {}).get("blockId") or "") in current_by_id
        ]
        if current_existing_order != desired_existing_order:
            previous_id = ""
            for block_id in desired_existing_order:
                block = current_by_id[block_id]
                operations.append({
                    "op": "move_after",
                    "block_id": block_id,
                    "expected_block_revision": int((block.get("attrs") or {}).get("blockRevision") or 1),
                    "after_block_id": previous_id,
                })
                previous_id = block_id
        if expected_document_revision == current_document_revision:
            for block in section_blocks:
                block_id = str((block.get("attrs") or {}).get("blockId") or "")
                if block_id not in incoming_ids:
                    operations.append({
                        "op": "delete",
                        "block_id": block_id,
                        "expected_block_revision": int((block.get("attrs") or {}).get("blockRevision") or 1),
                    })
        return operations

    def patch_draft(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        project_id = str(project.get("id"))
        section_id = str(payload.get("section_id") or "")
        expected_revision = int(
            payload.get("base_document_revision")
            or payload.get("expected_revision")
            or 0
        )
        client_change_id = str(payload.get("client_change_id") or _uuid("change"))[:96]
        context = self._context(project, document_id)
        conflicts: list[dict[str, Any]] = []
        applied: list[dict[str, Any]] = []
        next_revision = 0
        response_section_id = section_id
        with self.session_factory() as session:
            previous_event = session.execute(
                select(WritingChangeEvent).where(
                    WritingChangeEvent.project_id == project_id,
                    WritingChangeEvent.document_id == document_id,
                    WritingChangeEvent.client_change_id == client_change_id,
                )
            ).scalar_one_or_none()
            if previous_event:
                state = self._load_state(session, project_id, document_id)
                if not state:
                    raise DocumentWorkspaceError("结构化正文状态不存在")
                event_data = (
                    previous_event.operations
                    if isinstance(previous_event.operations, dict)
                    else {}
                )
                response_section_id = str(event_data.get("section_id") or section_id)
                response = self._state_dict(session, state, context, response_section_id)
                response["idempotent_replay"] = True
                return response

            state = self._load_state(session, project_id, document_id, lock=True)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            if expected_revision < 1 or expected_revision > state.document_revision:
                raise DocumentVersionConflict(
                    f"正文修订不匹配，当前为 {state.document_revision}"
                )
            document = copy.deepcopy(state.content_json)
            if section_id:
                _, _, resolved_section = self._section_range(context, document, section_id)
                response_section_id = str(resolved_section.get("id") or section_id)
            operations = payload.get("changes") or payload.get("operations") or []
            if payload.get("content") is not None:
                incoming = self._validate_document(
                    payload.get("content"),
                    f"{project_id}/{document_id}/client",
                )
                operations = self._operations_from_section_document(
                    document,
                    incoming,
                    context,
                    section_id,
                    expected_revision,
                    state.document_revision,
                )
            if not isinstance(operations, list) or not operations:
                response = self._state_dict(session, state, context, response_section_id)
                response["conflicts"] = []
                return response
            if any(str(row.get("op") or "") == "move_after" for row in operations):
                if expected_revision != state.document_revision:
                    raise DocumentVersionConflict(
                        "段落顺序已发生变化，请刷新后重新排序"
                    )
            before_sha = state.content_sha256
            applied, conflicts = self._apply_operations(
                document,
                operations,
                namespace=f"{project_id}/{document_id}/draft",
            )
            if not applied:
                raise DocumentVersionConflict(
                    "目标段落已发生变化，未覆盖当前正文；请基于最新内容重新修改"
                )
            try:
                self.codec.validate_document(document, require_block_ids=True)
            except ValueError as exc:
                raise DocumentWorkspaceError(f"正文 JSON 不符合编辑器契约：{exc}") from exc
            self._assert_section_boundaries(state.content_json, document)
            state.document_revision += 1
            state.content_json = document
            state.content_sha256 = self.codec.document_sha256(document)
            state.projection_status = "stale"
            state.projection_error = ""
            state.updated_at = _now()
            next_revision = state.document_revision
            session.add(WritingChangeEvent(
                id=_uuid("wevt"),
                project_id=project_id,
                document_id=document_id,
                document_revision=next_revision,
                client_change_id=client_change_id,
                actor_type="human",
                actor_id=actor,
                source="draft",
                operations={
                    "section_id": response_section_id,
                    "applied": applied,
                    "conflicts": conflicts,
                },
                before_sha256=before_sha,
                after_sha256=state.content_sha256,
            ))
            session.commit()

        self._refresh_projection(project, document_id)
        self._maybe_checkpoint(project, document_id, actor)
        response = self.get_state(project, document_id, response_section_id)
        response["conflicts"] = conflicts
        response["applied_operations"] = len(applied)
        response["revision"] = next_revision
        return response

    def _mark_projection_stale(
        self,
        project: dict[str, Any],
        document_id: str,
        revision: int,
        error: Exception,
    ) -> None:
        message = str(error)[:2000]
        project_id = str(project.get("id"))
        with self.session_factory() as session:
            state = self._load_state(session, project_id, document_id, lock=True)
            if state:
                state.projection_status = "stale"
                state.projection_error = message
                session.commit()
        try:
            self.workspace_service.mark_structured_projection_stale(
                self._context(project, document_id), revision, message
            )
        except Exception:
            pass

    def _refresh_projection(
        self,
        project: dict[str, Any],
        document_id: str,
        *,
        checkpoint_label: str = "",
    ) -> bool:
        project_id = str(project.get("id"))
        with self.session_factory() as session:
            state = self._load_state(session, project_id, document_id)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            revision = state.document_revision
            markdown = self.codec.to_markdown(state.content_json)
        try:
            self.workspace_service.apply_structured_projection(
                self._context(project, document_id),
                markdown,
                revision,
                "structured-projection",
                checkpoint_label=checkpoint_label,
            )
        except Exception as exc:
            self._mark_projection_stale(project, document_id, revision, exc)
            return False
        with self.session_factory() as session:
            state = self._load_state(session, project_id, document_id, lock=True)
            if state and state.document_revision == revision:
                state.projection_revision = revision
                state.projection_status = "current"
                state.projection_error = ""
                session.commit()
        return True

    def ensure_projection_current(self, project: dict[str, Any], document_id: str) -> None:
        if not _feature_enabled():
            return
        with self.session_factory() as session:
            state = self._load_state(session, str(project.get("id")), document_id)
        if not state:
            return
        if state.projection_status != "current" or state.projection_revision != state.document_revision:
            if not self._refresh_projection(project, document_id):
                raise DocumentWorkspaceError("Markdown 投影重建失败，暂不能导出")

    def _create_version_row(
        self,
        session: Session,
        state: WritingDocumentState,
        *,
        label: str,
        reason: str,
        actor_type: str,
        actor_id: str,
    ) -> WritingDocumentVersion:
        existing = session.execute(
            select(WritingDocumentVersion).where(
                WritingDocumentVersion.project_id == state.project_id,
                WritingDocumentVersion.document_id == state.document_id,
                WritingDocumentVersion.document_revision == state.document_revision,
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        parent_revision = session.execute(
            select(func.max(WritingDocumentVersion.document_revision)).where(
                WritingDocumentVersion.project_id == state.project_id,
                WritingDocumentVersion.document_id == state.document_id,
                WritingDocumentVersion.document_revision < state.document_revision,
            )
        ).scalar_one_or_none() or 0
        row = WritingDocumentVersion(
            id=_uuid("wver"),
            project_id=state.project_id,
            document_id=state.document_id,
            document_revision=state.document_revision,
            label=label[:160],
            reason=reason,
            content_json=copy.deepcopy(state.content_json),
            content_sha256=state.content_sha256,
            markdown_snapshot=self.codec.to_markdown(state.content_json),
            actor_type=actor_type,
            actor_id=actor_id,
            parent_revision=parent_revision,
            lifecycle_status="working",
        )
        session.add(row)
        return row

    def create_version(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        requested_revision = int(payload.get("revision") or 0)
        label = str(payload.get("name") or payload.get("label") or "人工版本")
        with self.session_factory() as session:
            state = self._load_state(session, str(project.get("id")), document_id, lock=True)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            if requested_revision and requested_revision != state.document_revision:
                raise DocumentVersionConflict(
                    f"只能为当前修订 {state.document_revision} 创建版本"
                )
            row = self._create_version_row(
                session,
                state,
                label=label,
                reason="manual",
                actor_type="human",
                actor_id=actor,
            )
            session.commit()
            version_id = row.id
            revision = row.document_revision
        self._refresh_projection(
            project,
            document_id,
            checkpoint_label=f"version-{revision}",
        )
        return {"id": version_id, "revision": revision, "label": label, "status": "created"}

    def list_versions(
        self,
        project: dict[str, Any],
        document_id: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        project_id = str(project.get("id"))
        with self.session_factory() as session:
            state = self._load_state(session, project_id, document_id)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            rows = session.execute(
                select(WritingDocumentVersion)
                .where(
                    WritingDocumentVersion.project_id == project_id,
                    WritingDocumentVersion.document_id == document_id,
                )
                .order_by(
                    WritingDocumentVersion.document_revision.desc(),
                    WritingDocumentVersion.created_at.desc(),
                )
            ).scalars().all()
            return {
                "current_revision": state.document_revision,
                "versions": [
                    {
                        "id": row.id,
                        "revision": row.document_revision,
                        "label": row.label,
                        "reason": row.reason,
                        "actor_type": row.actor_type,
                        "actor_id": row.actor_id,
                        "content_sha256": row.content_sha256,
                        "created_at": row.created_at.isoformat() if row.created_at else "",
                    }
                    for row in rows
                ],
            }

    def restore_version(
        self,
        project: dict[str, Any],
        document_id: str,
        version_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        project_id = str(project.get("id"))
        expected_revision = int(payload.get("expected_revision") or 0)
        restored_from_revision = 0
        next_revision = 0
        with self.session_factory() as session:
            state = self._load_state(session, project_id, document_id, lock=True)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            if expected_revision and expected_revision != state.document_revision:
                raise DocumentVersionConflict(
                    f"正文修订不匹配，当前为 {state.document_revision}"
                )
            version = session.execute(
                select(WritingDocumentVersion).where(
                    WritingDocumentVersion.id == version_id,
                    WritingDocumentVersion.project_id == project_id,
                    WritingDocumentVersion.document_id == document_id,
                )
            ).scalar_one_or_none()
            if not version:
                raise DocumentWorkspaceError("文档版本不存在")
            restored_document = self._validate_document(
                copy.deepcopy(version.content_json),
                f"{project_id}/{document_id}/restore",
            )
            self._create_version_row(
                session,
                state,
                label=f"恢复前 v{state.document_revision}",
                reason="pre_restore",
                actor_type="human",
                actor_id=actor,
            )
            before_sha = state.content_sha256
            restored_from_revision = version.document_revision
            state.document_revision += 1
            next_revision = state.document_revision
            state.content_json = restored_document
            state.content_sha256 = self.codec.document_sha256(restored_document)
            state.projection_status = "stale"
            state.projection_error = ""
            state.updated_at = _now()
            session.add(WritingChangeEvent(
                id=_uuid("wevt"),
                project_id=project_id,
                document_id=document_id,
                document_revision=next_revision,
                client_change_id=_uuid("restore")[:96],
                actor_type="human",
                actor_id=actor,
                source="version_restore",
                operations={
                    "version_id": version.id,
                    "restored_from_revision": restored_from_revision,
                },
                before_sha256=before_sha,
                after_sha256=state.content_sha256,
            ))
            session.commit()
        self._refresh_projection(
            project,
            document_id,
            checkpoint_label=f"restore-{restored_from_revision}-as-{next_revision}",
        )
        response = self.get_state(project, document_id)
        response["restored_from_version_id"] = version_id
        response["restored_from_revision"] = restored_from_revision
        return response

    def _maybe_checkpoint(self, project: dict[str, Any], document_id: str, actor: str) -> None:
        with self.session_factory() as session:
            state = self._load_state(session, str(project.get("id")), document_id, lock=True)
            if not state:
                return
            latest = session.execute(
                select(WritingDocumentVersion)
                .where(
                    WritingDocumentVersion.project_id == state.project_id,
                    WritingDocumentVersion.document_id == state.document_id,
                )
                .order_by(WritingDocumentVersion.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest and latest.created_at:
                created = latest.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if _now() - created < timedelta(minutes=10):
                    return
            self._create_version_row(
                session,
                state,
                label="自动恢复检查点",
                reason="automatic",
                actor_type="human",
                actor_id=actor,
            )
            session.commit()

    def _target_blocks(
        self,
        project: dict[str, Any],
        document_id: str,
        state: WritingDocumentState,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        scope = str(payload.get("scope") or "section")
        document = state.content_json
        blocks = document.get("content") or []
        target_ids: list[str] = []
        if scope == "document":
            target_ids = [str((row.get("attrs") or {}).get("blockId") or "") for row in blocks]
        elif scope == "section":
            context = self._context(project, document_id)
            start, end, _ = self._section_range(context, document, str(payload.get("section_id") or ""))
            target_ids = [str((row.get("attrs") or {}).get("blockId") or "") for row in blocks[start:end]]
        elif scope == "block":
            target_ids = [str(payload.get("block_id") or "")]
        elif scope == "selection":
            selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
            selected_text = str(selection.get("text") or "").strip()
            explicit_id = str(selection.get("block_id") or payload.get("block_id") or "")
            if explicit_id:
                target_ids = [explicit_id]
            elif selected_text:
                match = next((row for row in blocks if selected_text in self._block_text(row)), None)
                if match:
                    target_ids = [str((match.get("attrs") or {}).get("blockId") or "")]
        else:
            raise DocumentWorkspaceError("AI 作用范围无效")
        target_ids = [value for value in dict.fromkeys(target_ids) if value]
        if not target_ids:
            raise DocumentWorkspaceError("没有可供 AI 处理的目标段落")
        targets = []
        for block_id in target_ids:
            found = self._find_block(document, block_id)
            if not found:
                raise DocumentWorkspaceError(f"AI 目标段落不存在：{block_id}")
            _, block = found
            targets.append({
                "block_id": block_id,
                "block_revision": int((block.get("attrs") or {}).get("blockRevision") or 1),
                "block_sha256": self.codec.block_sha256(block),
                "markdown": self.codec.block_markdown(block),
            })
        return targets

    def submit_ai_job(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        instruction = str(payload.get("instruction") or "").strip()
        if not instruction:
            raise DocumentWorkspaceError("AI 写作指令不能为空")
        agent_id = str(payload.get("agent_id") or "ultra-magnus").strip()
        scope = str(payload.get("scope") or "section")
        selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
        selection = copy.deepcopy(selection)
        selection["text_sha256"] = _sha256(str(selection.get("text") or ""))
        project_id = str(project.get("id"))
        client_request_id = str(payload.get("client_request_id") or _uuid("request"))[:96]
        evidence_ref_ids = [str(value) for value in payload.get("evidence_ref_ids") or []]
        with self.session_factory() as session:
            existing = session.execute(
                select(WritingAiJob).where(
                    WritingAiJob.project_id == project_id,
                    WritingAiJob.document_id == document_id,
                    WritingAiJob.client_request_id == client_request_id,
                )
            ).scalar_one_or_none()
            if existing:
                result = self._job_dict(existing)
                result["idempotent_replay"] = True
                return result
            state = self._load_state(session, project_id, document_id)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            if evidence_ref_ids:
                available = session.execute(select(WritingEvidenceRef.id).where(
                    WritingEvidenceRef.project_id == project_id,
                    WritingEvidenceRef.document_id == document_id,
                    WritingEvidenceRef.id.in_(evidence_ref_ids),
                    WritingEvidenceRef.immutable.is_(True),
                    WritingEvidenceRef.perspective_scope.in_({"public", "project", "paper", "aggregate"}),
                )).scalars().all()
                if set(available) != set(evidence_ref_ids):
                    raise DocumentWorkspaceError("AI 任务引用了不存在或无权进入正文的 EvidenceRef")
            canonical_payload = copy.deepcopy(payload)
            section_id = str(canonical_payload.get("section_id") or "")
            if section_id:
                context = self._context(project, document_id)
                _, _, resolved_section = self._section_range(
                    context,
                    state.content_json,
                    section_id,
                )
                section_id = str(resolved_section.get("id") or section_id)
                canonical_payload["section_id"] = section_id
            targets = self._target_blocks(project, document_id, state, canonical_payload)
            job = WritingAiJob(
                id=_uuid("wjob"),
                project_id=project_id,
                document_id=document_id,
                client_request_id=client_request_id,
                section_id=section_id,
                agent_id=agent_id,
                instruction=instruction,
                scope=scope,
                base_document_revision=state.document_revision,
                target_blocks=targets,
                selection=selection,
                evidence_ref_ids=evidence_ref_ids,
                risk_policy=copy.deepcopy(payload.get("risk_policy") or {}),
                status="queued",
                requested_by=actor,
                conversation_id=str(payload.get("conversation_id") or "")[:64],
                request_message_id=str(payload.get("request_message_id") or "")[:64],
                response_message_id=str(payload.get("response_message_id") or "")[:64],
            )
            session.add(job)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(
                    select(WritingAiJob).where(
                        WritingAiJob.project_id == project_id,
                        WritingAiJob.document_id == document_id,
                        WritingAiJob.client_request_id == client_request_id,
                    )
                ).scalar_one_or_none()
                if not existing:
                    raise
                result = self._job_dict(existing)
                result["idempotent_replay"] = True
                return result
            return self._job_dict(job)

    def _ai_prompt(self, job: WritingAiJob) -> str:
        targets = list(job.target_blocks or [])
        source = "\n\n".join(
            f"--- BLOCK {row['block_id']} REV {row['block_revision']} ---\n{row['markdown']}"
            for row in targets
        )
        if len(source) > 120_000:
            raise DocumentWorkspaceError("AI 处理范围过大，请改为章节或段落")
        return f"""你是结构化文档协作智能体。只处理下面列出的块，不得修改未列出的正文，也不得虚构事实或引用。

用户指令：{job.instruction}
作用范围：{job.scope}
基础文档修订：{job.base_document_revision}

请只返回一个 JSON 对象，不要使用 Markdown 代码围栏：
{{
  "summary": "本次处理摘要",
  "operations": [
    {{
      "block_id": "原块 ID",
      "action": "replace|delete|insert_after",
      "replacement_markdown": "替换或插入的 Markdown；delete 时为空",
      "summary": "建议标题",
      "rationale": "修改理由"
    }}
  ]
}}

绑定证据引用：{json.dumps(job.evidence_ref_ids or [], ensure_ascii=False)}

规则：
1. 不得返回完整文档 JSON，只返回上述结构化操作。
2. replace/delete 的 block_id 必须来自输入；insert_after 使用锚点 block_id。
3. 保留事实限定、引用编号和图片路径；资料不足时在 rationale 中说明，不要补造。
4. replacement_markdown 必须是完整可解析的 Markdown 块。

目标正文：
{source}
"""

    def _operation_risk(
        self,
        job: WritingAiJob,
        action: str,
        current_markdown: str,
        replacement_markdown: str,
        current_block: dict[str, Any] | None,
        replacement_nodes: list[dict[str, Any]],
    ) -> tuple[str, bool]:
        """Separate concurrency safety from authorization to enter the draft."""
        sensitive = bool(EVIDENCE_SENSITIVE_TEXT.search(replacement_markdown))
        low_risk_instruction = bool(LOW_RISK_INSTRUCTION.search(job.instruction))
        structural = action in {"delete", "insert_after"}
        same_shape = bool(
            action == "replace"
            and current_block
            and len(replacement_nodes) == 1
            and self._semantic_shape(current_block) == self._semantic_shape(replacement_nodes[0])
        )
        if sensitive or structural or not same_shape:
            return ("high", True)
        def formatting_baseline(value: str) -> str:
            compact = re.sub(r"\s+", "", value, flags=re.UNICODE)
            return re.sub(r"[，。！？；：、,.!?;:]+$", "", compact).casefold()

        semantic_before = formatting_baseline(current_markdown)
        semantic_after = formatting_baseline(replacement_markdown)
        formatting_only = bool(semantic_before) and semantic_before == semantic_after
        if (
            action == "replace"
            and formatting_only
            and low_risk_instruction
            and bool((job.risk_policy or {}).get("allow_auto_draft", True))
        ):
            return ("low", False)
        return ("medium", True)

    @classmethod
    def _semantic_shape(cls, value: Any) -> Any:
        """Keep node/mark structure while ignoring text and stable block identity."""
        if isinstance(value, list):
            return [cls._semantic_shape(item) for item in value]
        if not isinstance(value, dict):
            return value
        shaped: dict[str, Any] = {}
        for key, item in value.items():
            if key == "text":
                shaped[key] = "<text>"
            elif key == "attrs" and isinstance(item, dict):
                shaped[key] = {
                    name: cls._semantic_shape(attribute)
                    for name, attribute in item.items()
                    if name not in {"blockId", "blockRevision"}
                }
            else:
                shaped[key] = cls._semantic_shape(item)
        return shaped

    def _parse_ai_response(self, response: str) -> dict[str, Any]:
        value = response.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            value = fence.group(1)
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise DocumentWorkspaceError("AI 返回内容不是有效 JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("operations"), list):
            raise DocumentWorkspaceError("AI 返回缺少 operations 数组")
        if len(payload["operations"]) > 200:
            raise DocumentWorkspaceError("AI 返回操作数量超过限制")
        return payload

    def _replacement_nodes(
        self,
        markdown: str,
        *,
        namespace: str,
        target_block_id: str,
        target_revision: int,
    ) -> list[dict[str, Any]]:
        document = self.codec.from_markdown(markdown, namespace=namespace)
        nodes = copy.deepcopy(document.get("content") or [])
        if not nodes:
            raise DocumentWorkspaceError("AI 替换内容不能为空")
        first_attrs = nodes[0].setdefault("attrs", {})
        first_attrs["blockId"] = target_block_id
        first_attrs["blockRevision"] = target_revision + 1
        return nodes

    async def process_ai_job(
        self,
        project: dict[str, Any],
        document_id: str,
        job_id: str,
        *,
        worker_id: str = "inline-worker",
    ) -> None:
        project_id = str(project.get("id"))
        try:
            with self.session_factory() as session:
                now = _now()
                claim = session.execute(
                    update(WritingAiJob)
                    .where(
                        WritingAiJob.id == job_id,
                        WritingAiJob.project_id == project_id,
                        WritingAiJob.document_id == document_id,
                        or_(
                            WritingAiJob.status == "queued",
                            and_(
                                WritingAiJob.status == "running",
                                WritingAiJob.lease_expires_at.is_not(None),
                                WritingAiJob.lease_expires_at < now,
                            ),
                        ),
                    )
                    .values(
                        status="running",
                        started_at=now,
                        worker_id=worker_id[:128],
                        lease_expires_at=now + timedelta(minutes=10),
                        attempt_count=WritingAiJob.attempt_count + 1,
                        error="",
                    )
                )
                if claim.rowcount != 1:
                    session.rollback()
                    return
                job = session.get(WritingAiJob, job_id)
                if not job:
                    session.rollback()
                    return
                self._sync_job_message(session, job)
                session.commit()
                prompt = self._ai_prompt(job)
                agent_id = job.agent_id
            response = await self.ai_requester(agent_id, prompt)
            payload = self._parse_ai_response(response)
            with self.session_factory() as session:
                job = session.execute(
                    select(WritingAiJob)
                    .where(WritingAiJob.id == job_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if not job or job.status == "cancelled" or job.worker_id != worker_id[:128]:
                    return
                state = self._load_state(session, project_id, document_id, lock=True)
                if not state:
                    raise DocumentWorkspaceError("结构化正文状态不存在")
                targets = {row["block_id"]: row for row in job.target_blocks or []}
                proposed_operations: list[dict[str, Any]] = []
                proposals: list[WritingAiProposal] = []
                applied_count = 0
                conflict_count = 0
                review_count = 0
                before_sha = state.content_sha256
                for index, operation in enumerate(payload.get("operations") or []):
                    if not isinstance(operation, dict):
                        raise DocumentWorkspaceError("AI 操作必须是对象")
                    block_id = str(operation.get("block_id") or "")
                    action = str(operation.get("action") or "replace")
                    if action not in {"replace", "delete", "insert_after"}:
                        raise DocumentWorkspaceError(f"AI 操作类型无效：{action}")
                    target = targets.get(block_id)
                    if not target:
                        raise DocumentWorkspaceError(f"AI 尝试修改未授权段落：{block_id}")
                    found = self._find_block(state.content_json, block_id)
                    current_block = found[1] if found else None
                    unchanged = bool(
                        current_block
                        and int((current_block.get("attrs") or {}).get("blockRevision") or 1)
                        == int(target["block_revision"])
                        and self.codec.block_sha256(current_block) == target["block_sha256"]
                    )
                    replacement_markdown = str(operation.get("replacement_markdown") or "")
                    current_markdown = self.codec.block_markdown(current_block) if current_block else ""
                    replacement_nodes: list[dict[str, Any]] = []
                    if action != "delete":
                        replacement_nodes = self._replacement_nodes(
                            replacement_markdown,
                            namespace=f"{project_id}/{document_id}/{job_id}/{index}",
                            target_block_id=block_id if action == "replace" else _uuid("block"),
                            target_revision=int(target["block_revision"]) if action == "replace" else 0,
                        )
                    risk_level, approval_required = self._operation_risk(
                        job,
                        action,
                        current_markdown,
                        replacement_markdown,
                        current_block,
                        replacement_nodes,
                    )
                    diff = "\n".join(difflib.unified_diff(
                        current_markdown.splitlines(),
                        replacement_markdown.splitlines(),
                        fromfile="当前正文",
                        tofile="AI 建议",
                        lineterm="",
                    ))
                    proposal = WritingAiProposal(
                        id=_uuid("wprop"),
                        job_id=job.id,
                        project_id=project_id,
                        document_id=document_id,
                        block_id=block_id,
                        operation_type=action,
                        base_block_revision=int(target["block_revision"]),
                        base_block_sha256=str(target["block_sha256"]),
                        replacement_markdown=replacement_markdown,
                        replacement_json=replacement_nodes,
                        diff=diff,
                        summary=str(operation.get("summary") or "AI 修改建议")[:1000],
                        rationale=str(operation.get("rationale") or "")[:4000],
                        risk_level=risk_level,
                        approval_required=approval_required,
                        evidence_ref_ids=list(job.evidence_ref_ids or []),
                        concurrency_status="unchanged" if unchanged else "conflicted",
                        status="applied" if unchanged and not approval_required else "pending",
                        decided_at=_now() if unchanged and not approval_required else None,
                        decided_by=job.agent_id if unchanged and not approval_required else "",
                    )
                    session.add(proposal)
                    session.flush()
                    proposals.append(proposal)
                    if unchanged and not approval_required:
                        if action == "delete":
                            proposed_operations.append({
                                "op": "delete",
                                "block_id": block_id,
                                "expected_block_revision": target["block_revision"],
                            })
                        elif action == "insert_after":
                            anchor = block_id
                            for node in replacement_nodes:
                                proposed_operations.append({
                                    "op": "insert_after",
                                    "after_block_id": anchor,
                                    "block_id": str((node.get("attrs") or {}).get("blockId") or ""),
                                    "node": node,
                                })
                                anchor = str((node.get("attrs") or {}).get("blockId") or anchor)
                        else:
                            first, *extras = replacement_nodes
                            proposed_operations.append({
                                "op": "upsert",
                                "block_id": block_id,
                                "expected_block_revision": target["block_revision"],
                                "node": first,
                            })
                            anchor = block_id
                            for node in extras:
                                proposed_operations.append({
                                    "op": "insert_after",
                                    "after_block_id": anchor,
                                    "block_id": str((node.get("attrs") or {}).get("blockId") or ""),
                                    "node": node,
                                })
                                anchor = str((node.get("attrs") or {}).get("blockId") or anchor)
                        applied_count += 1
                    else:
                        session.add(WritingChangeSet(
                            id=_uuid("changeset"),
                            project_id=project_id,
                            document_id=document_id,
                            base_revision=job.base_document_revision,
                            proposal_id=proposal.id,
                            operations=[{
                                "op": action,
                                "block_id": block_id,
                                "replacement_markdown": replacement_markdown,
                            }],
                            evidence_ref_ids=list(job.evidence_ref_ids or []),
                            risk_level=risk_level,
                            approval_policy="risk_driven",
                            status="conflicted" if not unchanged else "review_required",
                            idempotency_key=f"proposal:{proposal.id}",
                            summary=proposal.summary,
                        ))
                        if unchanged:
                            review_count += 1
                        else:
                            conflict_count += 1
                if proposed_operations:
                    document = copy.deepcopy(state.content_json)
                    applied, apply_conflicts = self._apply_operations(
                        document,
                        proposed_operations,
                        namespace=f"{project_id}/{document_id}/{job_id}/apply",
                    )
                    if apply_conflicts:
                        raise DocumentVersionConflict("AI 自动合并期间正文再次发生变化")
                    self._assert_section_boundaries(state.content_json, document)
                    state.document_revision += 1
                    state.content_json = document
                    state.content_sha256 = self.codec.document_sha256(document)
                    state.projection_status = "stale"
                    session.add(WritingChangeEvent(
                        id=_uuid("wevt"),
                        project_id=project_id,
                        document_id=document_id,
                        document_revision=state.document_revision,
                        client_change_id=f"ai:{job.id}",
                        actor_type="ai",
                        actor_id=job.agent_id,
                        source="ai-auto-merge",
                        operations=applied,
                        before_sha256=before_sha,
                        after_sha256=state.content_sha256,
                    ))
                    self._create_version_row(
                        session,
                        state,
                        label=f"AI 合并：{str(payload.get('summary') or job.instruction)[:100]}",
                        reason="ai_merge",
                        actor_type="ai",
                        actor_id=job.agent_id,
                    )
                job.summary = str(payload.get("summary") or "")[:4000]
                job.raw_response = response[:100_000]
                job.finished_at = _now()
                job.lease_expires_at = None
                job.worker_id = ""
                if applied_count and (conflict_count or review_count):
                    job.status = "partially_applied"
                elif applied_count:
                    job.status = "applied"
                elif conflict_count:
                    job.status = "conflicted"
                elif review_count:
                    job.status = "review_required"
                else:
                    job.status = "failed"
                    job.error = "AI 未返回可执行操作"
                self._sync_job_message(session, job)
                session.commit()
            if applied_count:
                self._refresh_projection(
                    project,
                    document_id,
                    checkpoint_label=f"ai-{job_id}",
                )
        except Exception as exc:
            with self.session_factory() as session:
                job = session.get(WritingAiJob, job_id)
                if job and job.status != "cancelled" and job.worker_id == worker_id[:128]:
                    job.status = "failed"
                    job.error = str(exc)[:4000]
                    job.finished_at = _now()
                    job.lease_expires_at = None
                    job.worker_id = ""
                    self._sync_job_message(session, job)
                    session.commit()

    def next_runnable_ai_job(self) -> dict[str, str] | None:
        """Return one durable queued or expired job for the database worker."""
        self._require_mutation_backend()
        now = _now()
        with self.session_factory() as session:
            job = session.execute(
                select(WritingAiJob)
                .where(
                    or_(
                        WritingAiJob.status == "queued",
                        and_(
                            WritingAiJob.status == "running",
                            WritingAiJob.lease_expires_at.is_not(None),
                            WritingAiJob.lease_expires_at < now,
                        ),
                    )
                )
                .order_by(WritingAiJob.created_at.asc())
                .limit(1)
            ).scalar_one_or_none()
            if not job:
                return None
            return {
                "id": job.id,
                "project_id": job.project_id,
                "document_id": job.document_id,
            }

    def next_stale_projection(self) -> dict[str, str] | None:
        """Return one stale projection after a short retry backoff."""
        self._require_mutation_backend()
        retry_before = _now() - timedelta(seconds=30)
        with self.session_factory() as session:
            state = session.execute(
                select(WritingDocumentState)
                .where(
                    WritingDocumentState.projection_status == "stale",
                    WritingDocumentState.updated_at < retry_before,
                )
                .order_by(WritingDocumentState.updated_at.asc())
                .limit(1)
            ).scalar_one_or_none()
            if not state:
                return None
            return {
                "project_id": state.project_id,
                "document_id": state.document_id,
            }

    def refresh_projection(
        self,
        project: dict[str, Any],
        document_id: str,
    ) -> bool:
        self._require_mutation_backend()
        return self._refresh_projection(project, document_id)

    def fail_ai_job(self, job_id: str, error: str) -> None:
        with self.session_factory() as session:
            job = session.get(WritingAiJob, job_id)
            if job and job.status in {"queued", "running"}:
                job.status = "failed"
                job.error = error[:4000]
                job.finished_at = _now()
                job.lease_expires_at = None
                job.worker_id = ""
                self._sync_job_message(session, job)
            session.commit()

    def _job_dict(self, job: WritingAiJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "project_id": job.project_id,
            "document_id": job.document_id,
            "client_request_id": job.client_request_id,
            "agent_id": job.agent_id,
            "scope": job.scope,
            "status": job.status,
            "summary": job.summary,
            "error": job.error,
            "base_document_revision": job.base_document_revision,
            "attempt_count": job.attempt_count,
            "evidence_ref_ids": job.evidence_ref_ids or [],
            "risk_policy": job.risk_policy or {},
            "created_at": job.created_at.isoformat() if job.created_at else "",
            "started_at": job.started_at.isoformat() if job.started_at else "",
            "finished_at": job.finished_at.isoformat() if job.finished_at else "",
            "proposals": [self._proposal_dict(row) for row in job.proposals],
        }

    def get_ai_job(
        self,
        project: dict[str, Any],
        document_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            job = session.get(WritingAiJob, job_id)
            if (
                not job
                or job.project_id != str(project.get("id"))
                or job.document_id != document_id
            ):
                raise DocumentWorkspaceError("AI 写作任务不存在")
            anchor = job.started_at or job.created_at
            if job.status == "running" and anchor and job.lease_expires_at is None:
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                if _now() - anchor > timedelta(minutes=10):
                    job.status = "failed"
                    job.error = "AI 写作任务超时或服务已重启，请重新提交"
                    job.finished_at = _now()
                    self._sync_job_message(session, job)
                    session.commit()
            return self._job_dict(job)

    def cancel_ai_job(
        self,
        project: dict[str, Any],
        document_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            job = session.get(WritingAiJob, job_id)
            if (
                not job
                or job.project_id != str(project.get("id"))
                or job.document_id != document_id
            ):
                raise DocumentWorkspaceError("AI 写作任务不存在")
            if job.status not in TERMINAL_JOB_STATUSES:
                job.status = "cancelled"
                job.finished_at = _now()
                job.lease_expires_at = None
                job.worker_id = ""
                self._sync_job_message(session, job)
                session.commit()
            return self._job_dict(job)

    def _proposal(
        self,
        session: Session,
        project: dict[str, Any],
        document_id: str,
        proposal_id: str,
        *,
        lock: bool = False,
    ) -> WritingAiProposal:
        statement = select(WritingAiProposal).where(WritingAiProposal.id == proposal_id)
        if lock:
            statement = statement.with_for_update()
        proposal = session.execute(statement).scalar_one_or_none()
        if (
            not proposal
            or proposal.project_id != str(project.get("id"))
            or proposal.document_id != document_id
        ):
            raise DocumentWorkspaceError("AI 修订建议不存在")
        return proposal

    def accept_proposal(
        self,
        project: dict[str, Any],
        document_id: str,
        proposal_id: str,
        actor: str,
    ) -> dict[str, Any]:
        project_id = str(project.get("id"))
        section_id = ""
        with self.session_factory() as session:
            proposal = self._proposal(session, project, document_id, proposal_id, lock=True)
            section_id = proposal.job.section_id if proposal.job else ""
            if proposal.status != "pending":
                raise DocumentWorkspaceError("该建议已处理")
            if EVIDENCE_SENSITIVE_TEXT.search(proposal.replacement_markdown) and not proposal.evidence_ref_ids:
                raise DocumentWorkspaceError("证据敏感修改未绑定 EvidenceRef，只能保留为证据缺口")
            state = self._load_state(session, project_id, document_id, lock=True)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            found = self._find_block(state.content_json, proposal.block_id)
            if not found:
                raise DocumentVersionConflict("建议目标段落已删除，请重新生成建议")
            current = found[1]
            if (
                int((current.get("attrs") or {}).get("blockRevision") or 1)
                != proposal.base_block_revision
                or self.codec.block_sha256(current) != proposal.base_block_sha256
            ):
                raise DocumentVersionConflict(
                    "目标段落在 AI 生成后已变化，不能覆盖；请基于当前正文重新生成建议"
                )
            operations: list[dict[str, Any]] = []
            if proposal.operation_type == "delete":
                operations.append({
                    "op": "delete",
                    "block_id": proposal.block_id,
                    "expected_block_revision": proposal.base_block_revision,
                })
            elif proposal.operation_type == "insert_after":
                anchor = proposal.block_id
                for node in copy.deepcopy(proposal.replacement_json or []):
                    block_id = str((node.get("attrs") or {}).get("blockId") or "")
                    operations.append({
                        "op": "insert_after",
                        "after_block_id": anchor,
                        "block_id": block_id,
                        "node": node,
                    })
                    anchor = block_id or anchor
            else:
                replacement_nodes = copy.deepcopy(proposal.replacement_json or [])
                if not replacement_nodes:
                    raise DocumentWorkspaceError("AI 建议缺少替换内容")
                first, *extras = replacement_nodes
                operations.append({
                    "op": "upsert",
                    "block_id": proposal.block_id,
                    "expected_block_revision": proposal.base_block_revision,
                    "node": first,
                })
                anchor = proposal.block_id
                for node in extras:
                    block_id = str((node.get("attrs") or {}).get("blockId") or "")
                    operations.append({
                        "op": "insert_after",
                        "after_block_id": anchor,
                        "block_id": block_id,
                        "node": node,
                    })
                    anchor = block_id or anchor
            document = copy.deepcopy(state.content_json)
            applied, conflicts = self._apply_operations(
                document,
                operations,
                namespace=f"{project_id}/{document_id}/{proposal_id}/accept",
            )
            if conflicts:
                raise DocumentVersionConflict("建议目标段落已变化，请重新生成建议")
            self._assert_section_boundaries(state.content_json, document)
            before_sha = state.content_sha256
            state.document_revision += 1
            state.content_json = document
            state.content_sha256 = self.codec.document_sha256(document)
            state.projection_status = "stale"
            proposal.status = "applied"
            proposal.decided_at = _now()
            proposal.decided_by = actor
            change_set = session.execute(select(WritingChangeSet).where(
                WritingChangeSet.proposal_id == proposal.id
            ).with_for_update()).scalar_one_or_none()
            if change_set:
                change_set.status = "approved"
                change_set.result_revision = state.document_revision
                change_set.decided_at = _now()
                change_set.decided_by = actor
            session.add(WritingChangeEvent(
                id=_uuid("wevt"),
                project_id=project_id,
                document_id=document_id,
                document_revision=state.document_revision,
                client_change_id=f"proposal:{proposal.id}",
                actor_type="human",
                actor_id=actor,
                source="proposal-accept",
                operations=applied,
                before_sha256=before_sha,
                after_sha256=state.content_sha256,
            ))
            self._create_version_row(
                session,
                state,
                label=f"接受 AI 建议：{proposal.summary[:100]}",
                reason="ai_accept",
                actor_type="human",
                actor_id=actor,
            )
            session.commit()
        self._refresh_projection(
            project,
            document_id,
            checkpoint_label=f"proposal-{proposal_id}",
        )
        return self.get_state(project, document_id, section_id)

    def reject_proposal(
        self,
        project: dict[str, Any],
        document_id: str,
        proposal_id: str,
        actor: str,
    ) -> dict[str, Any]:
        section_id = ""
        with self.session_factory() as session:
            proposal = self._proposal(session, project, document_id, proposal_id, lock=True)
            section_id = proposal.job.section_id if proposal.job else ""
            if proposal.status == "pending":
                proposal.status = "rejected"
                proposal.decided_at = _now()
                proposal.decided_by = actor
                change_set = session.execute(select(WritingChangeSet).where(
                    WritingChangeSet.proposal_id == proposal.id
                ).with_for_update()).scalar_one_or_none()
                if change_set:
                    change_set.status = "rejected"
                    change_set.decided_at = _now()
                    change_set.decided_by = actor
                session.commit()
        return self.get_state(project, document_id, section_id)


writing_collaboration_service = WritingCollaborationService()
