"""Candidate-only bridge between Word native edits and 3021 ChangeSets."""

from __future__ import annotations

import copy
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import SessionLocal
from models.writing_collaboration import (
    WritingAiJob,
    WritingAiProposal,
    WritingChangeSet,
    WritingDocumentState,
)
from services.auth_service import ALGORITHM, SECRET_KEY
from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceError,
)


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
APPLY_TOKEN_TYPE = "word_addin_candidate_apply"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain_paragraph_text(nodes: Any) -> str:
    if not isinstance(nodes, list) or len(nodes) != 1:
        raise DocumentWorkspaceError("Word PoC 仅允许单个普通段落候选")
    paragraph = nodes[0]
    if not isinstance(paragraph, dict) or paragraph.get("type") != "paragraph":
        raise DocumentWorkspaceError("Word PoC 暂不写入标题、列表、表格或其他复杂对象")
    chunks: list[str] = []
    for node in paragraph.get("content") or []:
        if not isinstance(node, dict):
            raise DocumentWorkspaceError("Word 候选包含无法识别的节点")
        if node.get("type") == "hardBreak":
            chunks.append("\n")
            continue
        if node.get("type") != "text" or node.get("marks"):
            raise DocumentWorkspaceError("Word PoC 暂不写入带格式、公式、链接或嵌入对象的段落")
        chunks.append(str(node.get("text") or ""))
    value = "".join(chunks)
    if not value:
        raise DocumentWorkspaceError("Word 候选替换文本不能为空")
    return value


def _structured_paragraph_text(block: Any) -> str:
    if not isinstance(block, dict) or block.get("type") != "paragraph":
        return ""
    chunks: list[str] = []
    for node in block.get("content") or []:
        if not isinstance(node, dict):
            return ""
        if node.get("type") == "hardBreak":
            chunks.append("\n")
        elif node.get("type") == "text":
            chunks.append(str(node.get("text") or ""))
        else:
            return ""
    return "".join(chunks)


class WordAddinBridgeService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        token_secret: str = SECRET_KEY,
        token_ttl_seconds: int = 300,
    ):
        self.session_factory = session_factory
        self.token_secret = token_secret
        self.token_ttl_seconds = max(30, token_ttl_seconds)

    def context(self, project_id: str, document_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            return {
                "mode": "candidate_only",
                "project_id": project_id,
                "document_id": document_id,
                "revision": state.document_revision,
                "content_sha256": state.content_sha256,
                "approved_revision": state.approved_revision,
                "published_revision": state.published_revision,
                "allowed_operations": ["replace_plain_paragraph"],
                "requires_word_import": True,
                "structured_authority_unchanged": True,
            }

    def resolve_paragraph(
        self,
        project_id: str,
        document_id: str,
        *,
        text: str,
        text_sha256: str,
    ) -> dict[str, Any]:
        if not text or _sha256(text) != text_sha256:
            raise DocumentWorkspaceError("Word 段落内容与指纹不一致")
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            if not state:
                raise DocumentWorkspaceError("结构化正文状态不存在")
            matches = []
            for block in (state.content_json or {}).get("content") or []:
                if _structured_paragraph_text(block) != text:
                    continue
                attrs = block.get("attrs") or {}
                block_id = str(attrs.get("blockId") or "")
                if block_id:
                    matches.append({
                        "block_id": block_id,
                        "block_revision": int(attrs.get("blockRevision") or 1),
                    })
            if not matches:
                raise DocumentWorkspaceError("Word 段落在3021当前正文中没有精确匹配")
            if len(matches) > 1:
                raise DocumentWorkspaceError("Word 段落在3021正文中不唯一，请改用块标识定位")
            return {
                **matches[0],
                "revision": state.document_revision,
                "content_sha256": state.content_sha256,
                "match_count": 1,
                "match_mode": "exact_unique_plain_paragraph",
            }

    def validate_apply(
        self,
        project_id: str,
        document_id: str,
        change_set_id: str,
        *,
        base_revision: int,
        current_paragraph_sha256: str,
        office_session_id: str,
        document_session_fingerprint: str,
    ) -> dict[str, Any]:
        if not SHA256_PATTERN.fullmatch(current_paragraph_sha256):
            raise DocumentWorkspaceError("Word 段落指纹不是有效 SHA-256")
        if not office_session_id.strip():
            raise DocumentWorkspaceError("Word 会话标识不能为空")
        if not SHA256_PATTERN.fullmatch(document_session_fingerprint):
            raise DocumentWorkspaceError("Word 候选文档指纹不是有效 SHA-256")
        with self.session_factory() as session:
            state, change_set, proposal, job = self._load_candidate(
                session,
                project_id,
                document_id,
                change_set_id,
            )
            if state.document_revision != base_revision or change_set.base_revision != base_revision:
                raise DocumentVersionConflict(
                    f"正文修订已变化，当前为 {state.document_revision}，请重新生成建议"
                )
            if job.base_document_revision != base_revision:
                raise DocumentVersionConflict("AI 任务基础修订与 ChangeSet 不一致")
            if change_set.status != "review_required":
                raise DocumentWorkspaceError("该 ChangeSet 当前不可应用到 Word 候选")
            if proposal.status != "pending" or proposal.concurrency_status != "unchanged":
                raise DocumentVersionConflict("AI 建议已处理或目标段落已发生冲突")
            if proposal.operation_type != "replace" or job.scope != "selection":
                raise DocumentWorkspaceError("Word PoC 仅接受选区触发的段落替换建议")
            selected_block_id = str((job.selection or {}).get("block_id") or "")
            if not selected_block_id or selected_block_id != proposal.block_id:
                raise DocumentWorkspaceError("Word 候选缺少已验证的稳定块映射")
            expected_sha = str((job.selection or {}).get("text_sha256") or "")
            if not SHA256_PATTERN.fullmatch(expected_sha):
                raise DocumentWorkspaceError("AI 建议缺少原始 Word 段落指纹")
            if expected_sha != current_paragraph_sha256:
                raise DocumentVersionConflict("Word 段落在建议生成后已变化，拒绝覆盖")
            replacement_text = _plain_paragraph_text(proposal.replacement_json)
            replacement_sha = _sha256(replacement_text)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=self.token_ttl_seconds)
            receipt_id = f"word-receipt-{uuid.uuid4().hex}"
            token = jwt.encode(
                {
                    "type": APPLY_TOKEN_TYPE,
                    "jti": receipt_id,
                    "project_id": project_id,
                    "document_id": document_id,
                    "change_set_id": change_set.id,
                    "proposal_id": proposal.id,
                    "base_revision": base_revision,
                    "before_sha256": expected_sha,
                    "after_sha256": replacement_sha,
                    "office_session_id": office_session_id[:96],
                    "document_session_fingerprint": document_session_fingerprint,
                    "iat": now,
                    "exp": expires_at,
                },
                self.token_secret,
                algorithm=ALGORITHM,
            )
            return {
                "allowed": True,
                "mode": "candidate_only",
                "change_set_id": change_set.id,
                "proposal_id": proposal.id,
                "base_revision": base_revision,
                "expected_paragraph_sha256": expected_sha,
                "replacement_text": replacement_text,
                "replacement_sha256": replacement_sha,
                "apply_token": token,
                "expires_at": expires_at.isoformat(),
                "requires_word_import": True,
            }

    def record_receipt(
        self,
        project_id: str,
        document_id: str,
        change_set_id: str,
        *,
        apply_token: str,
        before_sha256: str,
        after_sha256: str,
        office_session_id: str,
        document_session_fingerprint: str,
        actor: str,
    ) -> dict[str, Any]:
        payload = self._decode_token(apply_token)
        expected = {
            "project_id": project_id,
            "document_id": document_id,
            "change_set_id": change_set_id,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "office_session_id": office_session_id,
            "document_session_fingerprint": document_session_fingerprint,
        }
        if any(str(payload.get(key) or "") != str(value) for key, value in expected.items()):
            raise DocumentVersionConflict("Word 应用回执与已验证候选不一致")
        receipt_id = str(payload.get("jti") or "")
        if not receipt_id:
            raise DocumentWorkspaceError("Word 应用令牌缺少回执标识")

        with self.session_factory() as session:
            state, change_set, proposal, _job = self._load_candidate(
                session,
                project_id,
                document_id,
                change_set_id,
                lock=True,
            )
            existing_receipt = next(
                (
                    operation
                    for operation in change_set.operations or []
                    if isinstance(operation, dict)
                    and operation.get("op") == "word_application_receipt"
                    and operation.get("receipt_id") == receipt_id
                ),
                None,
            )
            if existing_receipt:
                return self._receipt_response(state, change_set, receipt_id, idempotent=True)
            base_revision = int(payload.get("base_revision") or 0)
            if state.document_revision != base_revision or change_set.base_revision != base_revision:
                raise DocumentVersionConflict("3021 正文在 Word 应用期间发生变化，候选不得回流")
            if change_set.status != "review_required" or proposal.status != "pending":
                raise DocumentWorkspaceError("该 Word 候选已处理或不可登记")
            operations = copy.deepcopy(change_set.operations or [])
            operations.append(
                {
                    "op": "word_application_receipt",
                    "receipt_id": receipt_id,
                    "before_sha256": before_sha256,
                    "after_sha256": after_sha256,
                    "office_session_id": office_session_id[:96],
                    "document_session_fingerprint": document_session_fingerprint[:128],
                    "actor": actor[:64],
                }
            )
            change_set.operations = operations
            change_set.status = "word_candidate_applied"
            proposal.status = "word_candidate_applied"
            session.commit()
            return self._receipt_response(state, change_set, receipt_id, idempotent=False)

    def _decode_token(self, value: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(value, self.token_secret, algorithms=[ALGORITHM])
        except JWTError as exc:
            raise DocumentWorkspaceError("Word 应用令牌无效或已过期") from exc
        if payload.get("type") != APPLY_TOKEN_TYPE:
            raise DocumentWorkspaceError("Word 应用令牌类型无效")
        return payload

    @staticmethod
    def _state(
        session: Session,
        project_id: str,
        document_id: str,
    ) -> WritingDocumentState | None:
        return session.query(WritingDocumentState).filter(
            WritingDocumentState.project_id == project_id,
            WritingDocumentState.document_id == document_id,
        ).one_or_none()

    @staticmethod
    def _receipt_response(
        state: WritingDocumentState,
        change_set: WritingChangeSet,
        receipt_id: str,
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "status": change_set.status,
            "change_set_id": change_set.id,
            "receipt_id": receipt_id,
            "base_revision": change_set.base_revision,
            "current_revision": state.document_revision,
            "structured_authority_unchanged": state.document_revision == change_set.base_revision,
            "requires_word_import": True,
            "idempotent_replay": idempotent,
        }

    @staticmethod
    def _load_candidate(
        session: Session,
        project_id: str,
        document_id: str,
        change_set_id: str,
        *,
        lock: bool = False,
    ) -> tuple[WritingDocumentState, WritingChangeSet, WritingAiProposal, WritingAiJob]:
        state = WordAddinBridgeService._state(session, project_id, document_id)
        statement = session.query(WritingChangeSet).filter(WritingChangeSet.id == change_set_id)
        if lock:
            statement = statement.with_for_update()
        change_set = statement.one_or_none()
        if (
            not state
            or not change_set
            or change_set.project_id != project_id
            or change_set.document_id != document_id
            or not change_set.proposal_id
        ):
            raise DocumentWorkspaceError("Word 候选 ChangeSet 不存在")
        proposal = session.get(WritingAiProposal, change_set.proposal_id)
        job = session.get(WritingAiJob, proposal.job_id) if proposal else None
        if not proposal or not job:
            raise DocumentWorkspaceError("Word 候选缺少 AI 建议映射")
        if (
            proposal.project_id != project_id
            or proposal.document_id != document_id
            or job.project_id != project_id
            or job.document_id != document_id
        ):
            raise DocumentWorkspaceError("Word 候选的 AI 建议映射越界")
        return state, change_set, proposal, job


word_addin_bridge_service = WordAddinBridgeService()
