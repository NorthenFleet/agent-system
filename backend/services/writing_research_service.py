"""Evidence-aware writing workflow and durable cross-system run state."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zipfile import BadZipFile, ZipFile

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models.writing_collaboration import (
    WritingChangeSet,
    WritingClaim,
    WritingDocumentState,
    WritingDocumentVersion,
    WritingEvidenceBinding,
    WritingEvidenceGap,
    WritingEvidenceRef,
    WritingJarvisRun,
    WritingJarvisStep,
    WritingWordImport,
    WritingWordRelease,
)
from services.document_workspace_service import DocumentVersionConflict, DocumentWorkspaceError
from services.mission_planning_adapter import mission_planning_adapter


EVIDENCE_LEVELS = {"diagnostic": 0, "G1": 1, "G2": 2, "A": 3}
EVIDENCE_SCOPE_KEYS = {"claim", "claim_type", "section", "block"}
REMOTE_TERMINAL_STATUSES = {
    "cancelled",
    "canceled",
    "stopped",
    "failed",
    "completed",
    "done",
    "error",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_docx(content: bytes) -> None:
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except BadZipFile as exc:
        raise DocumentWorkspaceError("Word 回流文件不是有效 DOCX") from exc
    required = {"[Content_Types].xml", "word/document.xml"}
    if not required.issubset(names):
        raise DocumentWorkspaceError("Word 回流文件缺少必要 OOXML 部件")


def _parse_evidence_scope(value: str, *, field_name: str) -> list[tuple[str, str]]:
    raw = value.strip()
    if not raw:
        return []
    selectors: list[tuple[str, str]] = []
    for item in raw.replace(";", ",").split(","):
        token = item.strip()
        if not token or ":" not in token:
            raise DocumentWorkspaceError(f"{field_name} 必须使用 key:value 结构化选择器")
        key, selected = (part.strip() for part in token.split(":", 1))
        if key not in EVIDENCE_SCOPE_KEYS or not selected:
            raise DocumentWorkspaceError(f"{field_name} 包含无效的主张范围选择器")
        selectors.append((key, selected))
    return selectors


def _default_research_compiler(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(mission_planning_adapter.compile_research_matrix(payload))


class WritingResearchService:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        research_compiler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        allow_non_postgres_writes: bool | None = None,
        evidence_root: str | Path | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.research_compiler = research_compiler or _default_research_compiler
        self.evidence_root = Path(evidence_root or os.getenv(
            "WRITING_EVIDENCE_ROOT",
            str(Path(__file__).resolve().parents[1] / "data" / "writing_evidence"),
        ))
        self.allow_non_postgres_writes = (
            os.getenv("WRITING_RESEARCH_ALLOW_NON_POSTGRES", "0").strip().lower()
            in {"1", "true", "on", "yes"}
            if allow_non_postgres_writes is None
            else allow_non_postgres_writes
        )

    def _require_mutation_backend(self) -> None:
        with self.session_factory() as session:
            dialect = session.get_bind().dialect.name
        if dialect != "postgresql" and not self.allow_non_postgres_writes:
            raise DocumentWorkspaceError("研究写作运行状态仅允许写入 PostgreSQL")

    @staticmethod
    def _state(session, project_id: str, document_id: str, *, lock: bool = False) -> WritingDocumentState:
        statement = select(WritingDocumentState).where(
            WritingDocumentState.project_id == project_id,
            WritingDocumentState.document_id == document_id,
        )
        if lock:
            statement = statement.with_for_update()
        state = session.execute(statement).scalar_one_or_none()
        if not state:
            raise DocumentWorkspaceError("结构化正文状态不存在")
        return state

    def _snapshot_evidence(self, source: Path, expected_sha256: str) -> Path:
        target_dir = self.evidence_root / expected_sha256[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / expected_sha256
        if target.is_file():
            if _file_sha256(target) != expected_sha256:
                raise DocumentWorkspaceError("内容寻址证据快照已损坏")
            return target.resolve()
        temporary = target_dir / f".{expected_sha256}.{uuid.uuid4().hex}.tmp"
        try:
            with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
                for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                    output_handle.write(chunk)
                output_handle.flush()
                os.fsync(output_handle.fileno())
            if _file_sha256(temporary) != expected_sha256:
                raise DocumentWorkspaceError("证据快照复制后的 SHA-256 校验失败")
            try:
                os.replace(temporary, target)
            except FileExistsError:
                pass
            target.chmod(0o444)
        finally:
            temporary.unlink(missing_ok=True)
        if not target.is_file() or _file_sha256(target) != expected_sha256:
            raise DocumentWorkspaceError("内容寻址证据快照提交失败")
        return target.resolve()

    @staticmethod
    def _verify_evidence_ref(evidence: WritingEvidenceRef) -> None:
        path = Path(evidence.artifact_path)
        if not path.is_file() or _file_sha256(path) != evidence.artifact_sha256:
            raise DocumentWorkspaceError("EvidenceRef 内容寻址快照缺失或哈希校验失败")

    @staticmethod
    def _claim_dict(row: WritingClaim) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "document_revision": row.document_revision,
            "section_id": row.section_id,
            "block_id": row.block_id,
            "claim_text": row.claim_text,
            "claim_type": row.claim_type,
            "minimum_evidence_level": row.minimum_evidence_level,
            "evidence_status": row.evidence_status,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    @staticmethod
    def _evidence_dict(row: WritingEvidenceRef) -> dict[str, Any]:
        return {
            "id": row.id,
            "source_system": row.source_system,
            "source_record_id": row.source_record_id,
            "artifact_path": row.artifact_path,
            "artifact_sha256": row.artifact_sha256,
            "perspective_scope": row.perspective_scope,
            "evidence_level": row.evidence_level,
            "allowed_claim_scope": row.allowed_claim_scope,
            "provenance": row.provenance or {},
            "immutable": row.immutable,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    @staticmethod
    def _changeset_dict(row: WritingChangeSet) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "base_revision": row.base_revision,
            "result_revision": row.result_revision,
            "proposal_id": row.proposal_id or "",
            "operations": row.operations or [],
            "evidence_ref_ids": row.evidence_ref_ids or [],
            "risk_level": row.risk_level,
            "approval_policy": row.approval_policy,
            "status": row.status,
            "summary": row.summary,
            "decided_by": row.decided_by,
            "decided_at": row.decided_at.isoformat() if row.decided_at else "",
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    @staticmethod
    def _run_dict(row: WritingJarvisRun, steps: list[WritingJarvisStep] | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "run_type": row.run_type,
            "status": row.status,
            "input_payload": row.input_payload or {},
            "result_payload": row.result_payload or {},
            "approval_reason": row.approval_reason,
            "error": row.error,
            "lease_owner": row.lease_owner,
            "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else "",
            "recovery_cursor": row.recovery_cursor or {},
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "steps": [
                {
                    "id": step.id,
                    "step_key": step.step_key,
                    "status": step.status,
                    "depends_on": step.depends_on or [],
                    "attempt_count": step.attempt_count,
                    "result_payload": step.result_payload or {},
                    "error": step.error,
                }
                for step in (steps or [])
            ],
        }

    def create_claim(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        minimum = str(payload.get("minimum_evidence_level") or "diagnostic")
        if minimum not in EVIDENCE_LEVELS:
            raise DocumentWorkspaceError("证据等级必须为 diagnostic、G1、G2 或 A")
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            requested_revision = int(payload.get("document_revision") or state.document_revision)
            if requested_revision > state.document_revision:
                raise DocumentVersionConflict("主张引用了尚不存在的正文修订")
            row = WritingClaim(
                id=_uuid("claim"),
                project_id=project_id,
                document_id=document_id,
                document_revision=requested_revision,
                section_id=str(payload.get("section_id") or "")[:128],
                block_id=str(payload.get("block_id") or "")[:96],
                claim_text=str(payload.get("claim_text") or "").strip(),
                claim_type=str(payload.get("claim_type") or "argument")[:32],
                minimum_evidence_level=minimum,
                created_by=actor,
            )
            if not row.claim_text:
                raise DocumentWorkspaceError("论文主张不能为空")
            gap = WritingEvidenceGap(
                id=_uuid("gap"),
                claim_id=row.id,
                project_id=project_id,
                document_id=document_id,
                required_level=minimum,
                reason="尚未绑定达到最低等级的不可变证据",
                research_matrix=payload.get("research_matrix") or {},
            )
            session.add_all([row, gap])
            session.commit()
            return self._claim_dict(row)

    def register_evidence(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        source_system = str(payload.get("source_system") or "").strip()
        if source_system.lower() in {"retrieval", "search", "search_result"}:
            raise DocumentWorkspaceError("检索结果只能登记为 RetrievalRef；请先保存原始快照并登记哈希")
        level = str(payload.get("evidence_level") or "diagnostic")
        if level not in EVIDENCE_LEVELS:
            raise DocumentWorkspaceError("证据等级必须为 diagnostic、G1、G2 或 A")
        sha256 = str(payload.get("artifact_sha256") or "").lower()
        artifact_path = str(payload.get("artifact_path") or "").strip()
        if not source_system or not artifact_path or not _valid_sha256(sha256):
            raise DocumentWorkspaceError("EvidenceRef 必须包含来源系统、快照路径和有效 SHA-256")
        snapshot = Path(artifact_path).expanduser()
        if not snapshot.is_absolute() or not snapshot.is_file():
            raise DocumentWorkspaceError("EvidenceRef 快照必须是 3021 可读取的本地绝对路径")
        resolved_path = snapshot.resolve()
        if _file_sha256(resolved_path) != sha256:
            raise DocumentWorkspaceError("EvidenceRef 快照 SHA-256 与登记值不一致")
        immutable_path = self._snapshot_evidence(resolved_path, sha256)
        allowed_claim_scope = str(payload.get("allowed_claim_scope") or "").strip()
        _parse_evidence_scope(allowed_claim_scope, field_name="allowed_claim_scope")
        with self.session_factory() as session:
            row = WritingEvidenceRef(
                id=_uuid("evidence"),
                project_id=project_id,
                document_id=document_id,
                source_system=source_system[:48],
                source_record_id=str(payload.get("source_record_id") or "")[:160],
                artifact_path=str(immutable_path),
                artifact_sha256=sha256,
                perspective_scope=str(payload.get("perspective_scope") or "project")[:64],
                evidence_level=level,
                allowed_claim_scope=allowed_claim_scope,
                provenance=payload.get("provenance") or {},
                immutable=True,
                created_by=actor,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                row = session.execute(select(WritingEvidenceRef).where(
                    WritingEvidenceRef.project_id == project_id,
                    WritingEvidenceRef.document_id == document_id,
                    WritingEvidenceRef.source_system == source_system[:48],
                    WritingEvidenceRef.source_record_id == str(payload.get("source_record_id") or "")[:160],
                    WritingEvidenceRef.artifact_sha256 == sha256,
                )).scalar_one()
            return self._evidence_dict(row)

    def bind_evidence(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        compensation: tuple[str, list[str]] | None = None
        with self.session_factory() as session:
            claim = session.execute(select(WritingClaim).where(
                WritingClaim.id == str(payload.get("claim_id") or ""),
            ).with_for_update()).scalar_one_or_none()
            evidence = session.get(WritingEvidenceRef, str(payload.get("evidence_ref_id") or ""))
            if not claim or claim.project_id != project_id or claim.document_id != document_id:
                raise DocumentWorkspaceError("论文主张不存在")
            if not evidence or evidence.project_id != project_id or evidence.document_id != document_id:
                raise DocumentWorkspaceError("证据引用不存在")
            self._verify_evidence_ref(evidence)
            if evidence.perspective_scope not in {"public", "project", "paper", "aggregate"}:
                raise DocumentWorkspaceError("该仿真视角包含受限态势，不能绑定到论文正文")
            selectors = {
                "claim": claim.id,
                "claim_type": claim.claim_type,
                "section": claim.section_id,
                "block": claim.block_id,
            }
            declared_scope = str(evidence.allowed_claim_scope or "").strip()
            declared_selectors = _parse_evidence_scope(
                declared_scope,
                field_name="allowed_claim_scope",
            )
            if declared_selectors and not any(
                selectors.get(key) == value for key, value in declared_selectors
            ):
                raise DocumentWorkspaceError("EvidenceRef 允许支持的主张范围与当前主张不匹配")
            support_scope = str(payload.get("support_scope") or declared_scope).strip()
            support_selectors = _parse_evidence_scope(support_scope, field_name="support_scope")
            if support_selectors and not declared_selectors:
                raise DocumentWorkspaceError("support_scope 不能超出 EvidenceRef 声明范围")
            if any(item not in declared_selectors for item in support_selectors):
                raise DocumentWorkspaceError("support_scope 不能超出 EvidenceRef 声明范围")
            if support_selectors and not any(
                selectors.get(key) == value for key, value in support_selectors
            ):
                raise DocumentWorkspaceError("support_scope 与当前主张不匹配")
            binding = session.execute(select(WritingEvidenceBinding).where(
                WritingEvidenceBinding.claim_id == claim.id,
                WritingEvidenceBinding.evidence_ref_id == evidence.id,
            )).scalar_one_or_none()
            if not binding:
                binding = WritingEvidenceBinding(
                    id=_uuid("binding"),
                    claim_id=claim.id,
                    evidence_ref_id=evidence.id,
                    support_scope=support_scope,
                    created_by=actor,
                )
                session.add(binding)
                session.flush()
            bound_levels = session.execute(select(WritingEvidenceRef.evidence_level).join(
                WritingEvidenceBinding,
                WritingEvidenceBinding.evidence_ref_id == WritingEvidenceRef.id,
            ).where(
                WritingEvidenceBinding.claim_id == claim.id,
                WritingEvidenceBinding.status == "active",
            )).scalars().all()
            strongest_level = max(
                bound_levels,
                key=lambda value: EVIDENCE_LEVELS.get(value, -1),
                default="diagnostic",
            )
            sufficient = EVIDENCE_LEVELS[strongest_level] >= EVIDENCE_LEVELS[claim.minimum_evidence_level]
            claim.evidence_status = "sufficient" if sufficient else "insufficient"
            gaps = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.claim_id == claim.id,
                WritingEvidenceGap.status != "resolved",
            ).with_for_update()).scalars().all()
            for gap in gaps:
                gap.status = "resolved" if sufficient else "open"
                gap.reason = "证据等级满足最低要求" if sufficient else "已绑定证据低于最低等级"
                if sufficient and gap.dispatched_run_id:
                    run = session.execute(select(WritingJarvisRun).where(
                        WritingJarvisRun.id == gap.dispatched_run_id,
                    ).with_for_update()).scalar_one_or_none()
                    origin_run_id = str(payload.get("origin_run_id") or "")
                    if run and run.id != origin_run_id:
                        next_step = str((run.recovery_cursor or {}).get("next_step") or "")
                        if next_step == "starting_remote" and run.status in {
                            "queued",
                            "running",
                            "cancellation_requested",
                        }:
                            run.status = "cancellation_requested"
                            run.error = "证据缺口已解决，等待重放远端启动并确认停止"
                        elif run.status in {"queued", "awaiting_approval"}:
                            run.status = "cancelled"
                            run.finished_at = _now()
                            run.error = "证据缺口已由其他不可变证据解决"
                        elif run.status == "running":
                            if next_step in {"publish_and_start", "starting_remote"}:
                                run.status = "cancellation_requested"
                                run.error = "证据缺口已解决，等待工作步骤安全停止"
                            else:
                                run.status = "cancelled"
                                run.finished_at = _now()
                                run.lease_owner = ""
                                run.lease_expires_at = None
                                run.error = "证据缺口已解决，未进入外部执行阶段"
                        elif run.status == "waiting_evidence":
                            remote_run_ids = self._remote_run_ids(
                                (run.result_payload or {}).get("start_result") or {}
                            )
                            if remote_run_ids:
                                run.status = "compensating"
                                run.error = "证据缺口已解决，正在停止 One-Sim 运行"
                                run.recovery_cursor = {
                                    "next_step": "compensate_remote_runs",
                                    "remote_run_ids": remote_run_ids,
                                }
                                compensation = (run.id, remote_run_ids)
                            else:
                                result_payload = dict(run.result_payload or {})
                                run.result_payload = {
                                    **result_payload,
                                    "compensation": {
                                        "remote_run_ids": [],
                                        "attempts": [],
                                        "confirmed": True,
                                        "confirmed_at": _now().isoformat(),
                                        "reason": "no_remote_runs_created",
                                    },
                                }
                                run.status = "cancelled"
                                run.recovery_cursor = {}
                                run.finished_at = _now()
                                run.lease_owner = ""
                                run.lease_expires_at = None
                                run.error = "One-Sim 未创建本次运行，无需停止"
            session.commit()
            result = {
                "id": binding.id,
                "claim": self._claim_dict(claim),
                "evidence": self._evidence_dict(evidence),
                "strongest_evidence_level": strongest_level,
                "sufficient": sufficient,
            }
        if compensation:
            run_id, remote_run_ids = compensation
            result["compensation_pending"] = not asyncio.run(
                self._attempt_run_compensation(run_id, remote_run_ids)
            )
        return result

    @staticmethod
    def _remote_run_ids(start_result: dict[str, Any]) -> list[str]:
        rows = start_result.get("started") if isinstance(start_result.get("started"), list) else []
        values = [
            str(row.get("train_id") or row.get("run_id") or row.get("id") or "")
            for row in rows
            if isinstance(row, dict)
        ]
        fallback = str(start_result.get("train_id") or start_result.get("run_id") or "")
        if fallback:
            values.append(fallback)
        return list(dict.fromkeys(value for value in values if value))

    def _stop_requested_before_external_call(self, run_id: str) -> bool:
        with self.session_factory() as session:
            gap = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            run = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
            ).with_for_update()).scalar_one_or_none()
            if not run:
                return True
            requested = bool(
                (gap and gap.status == "resolved")
                or run.status in {"cancellation_requested", "compensating", "cancelled"}
            )
            if requested and run.status not in {"compensating", "cancelled"}:
                run.status = "cancelled"
                run.finished_at = _now()
                run.lease_owner = ""
                run.lease_expires_at = None
                run.error = "证据缺口已解决，外部执行已在下一步骤前停止"
                session.commit()
            return requested

    async def _attempt_run_compensation(self, run_id: str, remote_run_ids: list[str]) -> bool:
        if not remote_run_ids:
            self._complete_run_compensation(run_id, [])
            return True
        results: list[dict[str, Any]] = []
        all_confirmed = True
        for remote_run_id in remote_run_ids:
            try:
                cancel_result = await mission_planning_adapter.cancel_training_run(remote_run_id)
                status = str(cancel_result.get("status") or "").lower()
                observed = cancel_result
                for _ in range(5):
                    if status in REMOTE_TERMINAL_STATUSES:
                        break
                    await asyncio.sleep(0.5)
                    observed = await mission_planning_adapter.get_training_run(remote_run_id)
                    status = str(observed.get("status") or "").lower()
                confirmed = status in REMOTE_TERMINAL_STATUSES
                all_confirmed = all_confirmed and confirmed
                results.append({
                    "remote_run_id": remote_run_id,
                    "cancel_result": cancel_result,
                    "observed": observed,
                    "confirmed": confirmed,
                })
            except Exception as exc:
                all_confirmed = False
                results.append({
                    "remote_run_id": remote_run_id,
                    "confirmed": False,
                    "error": str(exc)[:2000],
                })
        if all_confirmed:
            self._complete_run_compensation(run_id, results)
        else:
            self._schedule_run_compensation(run_id, remote_run_ids, results)
        return all_confirmed

    def _schedule_run_compensation(
        self,
        run_id: str,
        remote_run_ids: list[str],
        results: list[dict[str, Any]],
    ) -> None:
        with self.session_factory() as session:
            session.execute(select(WritingEvidenceGap.id).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            run = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
            ).with_for_update()).scalar_one_or_none()
            if not run:
                return
            result_payload = dict(run.result_payload or {})
            run.result_payload = {
                **result_payload,
                "compensation": {
                    "remote_run_ids": remote_run_ids,
                    "attempts": results,
                    "confirmed": False,
                },
            }
            run.recovery_cursor = {
                "next_step": "compensate_remote_runs",
                "remote_run_ids": remote_run_ids,
            }
            run.status = "compensating"
            run.lease_owner = ""
            run.lease_expires_at = _now() + timedelta(seconds=30)
            run.error = "One-Sim 运行停止尚未全部确认，将自动重试"
            session.commit()

    async def _start_remote_and_finalize(
        self,
        run_id: str,
        lease_owner: str,
        *,
        plan_id: str,
        active_revision: int,
        idempotency_key: str,
        published: dict[str, Any],
        synchronized: dict[str, Any],
    ) -> None:
        started = await mission_planning_adapter.start_training_plan(
            plan_id,
            expected_revision=active_revision,
            idempotency_key=idempotency_key,
        )
        remote_run_ids = self._remote_run_ids(started)
        compensation_required = False
        with self.session_factory() as session:
            gap = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            row = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
            ).with_for_update()).scalar_one_or_none()
            if not row:
                return
            result_payload = dict(row.result_payload or {})
            row.result_payload = {**result_payload, "start_result": started}
            cancellation_requested = bool(
                (gap and gap.status == "resolved")
                or row.status in {"cancellation_requested", "compensating", "cancelled"}
            )
            if cancellation_requested and remote_run_ids:
                row.status = "compensating"
                row.error = "外部运行已启动，正在执行停止补偿"
                row.recovery_cursor = {
                    "next_step": "compensate_remote_runs",
                    "remote_run_ids": remote_run_ids,
                }
                row.lease_owner = ""
                row.lease_expires_at = None
                compensation_required = True
            elif cancellation_requested:
                row.result_payload = {
                    **row.result_payload,
                    "compensation": {
                        "remote_run_ids": [],
                        "attempts": [],
                        "confirmed": True,
                        "confirmed_at": _now().isoformat(),
                        "reason": "no_remote_runs_created",
                    },
                }
                row.status = "cancelled"
                row.recovery_cursor = {}
                row.finished_at = _now()
                row.lease_owner = ""
                row.lease_expires_at = None
                row.error = "One-Sim 未创建本次运行，无需停止"
            elif row.status != "running" or row.lease_owner != lease_owner:
                return
            else:
                step = session.execute(select(WritingJarvisStep).where(
                    WritingJarvisStep.run_id == run_id,
                    WritingJarvisStep.step_key == "publish_and_start",
                )).scalar_one_or_none()
                if not step:
                    step = WritingJarvisStep(
                        id=_uuid("jstep"),
                        run_id=run_id,
                        step_key="publish_and_start",
                        depends_on=["queue_experiment_plan"],
                        input_payload={"plan_id": plan_id, "expected_revision": active_revision},
                        attempt_count=1,
                    )
                    session.add(step)
                else:
                    step.attempt_count += 1
                step.status = "completed"
                step.result_payload = {
                    "published": published,
                    "synchronized": synchronized,
                    "started": started,
                }
                row.recovery_cursor = {"next_step": "wait_for_evidence_bundle"}
                row.status = "waiting_evidence"
                row.lease_owner = ""
                row.lease_expires_at = None
                if gap and gap.status != "resolved":
                    gap.status = "running"
            session.commit()
        if compensation_required:
            await self._attempt_run_compensation(run_id, remote_run_ids)

    def _complete_run_compensation(
        self,
        run_id: str,
        results: list[dict[str, Any]],
    ) -> None:
        with self.session_factory() as session:
            session.execute(select(WritingEvidenceGap.id).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            run = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
            ).with_for_update()).scalar_one_or_none()
            if not run:
                return
            result_payload = dict(run.result_payload or {})
            run.result_payload = {
                **result_payload,
                "compensation": {
                    "remote_run_ids": [row["remote_run_id"] for row in results],
                    "attempts": results,
                    "confirmed": True,
                    "confirmed_at": _now().isoformat(),
                },
            }
            run.status = "cancelled"
            run.finished_at = _now()
            run.lease_owner = ""
            run.lease_expires_at = None
            run.error = "One-Sim 运行已确认停止"
            session.commit()

    def workspace_summary(self, project_id: str, document_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            claims = session.execute(select(WritingClaim).where(
                WritingClaim.project_id == project_id,
                WritingClaim.document_id == document_id,
                WritingClaim.status == "active",
            ).order_by(WritingClaim.created_at.desc())).scalars().all()
            evidence = session.execute(select(WritingEvidenceRef).where(
                WritingEvidenceRef.project_id == project_id,
                WritingEvidenceRef.document_id == document_id,
            ).order_by(WritingEvidenceRef.created_at.desc())).scalars().all()
            gaps = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.project_id == project_id,
                WritingEvidenceGap.document_id == document_id,
                WritingEvidenceGap.status != "resolved",
            ).order_by(WritingEvidenceGap.created_at.asc())).scalars().all()
            changesets = session.execute(select(WritingChangeSet).where(
                WritingChangeSet.project_id == project_id,
                WritingChangeSet.document_id == document_id,
                WritingChangeSet.status.in_({"review_required", "conflicted"}),
            ).order_by(WritingChangeSet.created_at.asc())).scalars().all()
            runs = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.project_id == project_id,
                WritingJarvisRun.document_id == document_id,
            ).order_by(WritingJarvisRun.created_at.desc()).limit(20)).scalars().all()
            state = self._state(session, project_id, document_id)
            return {
                "revision": state.document_revision,
                "approved_revision": state.approved_revision,
                "published_revision": state.published_revision,
                "claims": [self._claim_dict(row) for row in claims],
                "evidence_refs": [self._evidence_dict(row) for row in evidence],
                "gaps": [
                    {
                        "id": row.id,
                        "claim_id": row.claim_id,
                        "required_level": row.required_level,
                        "reason": row.reason,
                        "research_matrix": row.research_matrix or {},
                        "status": row.status,
                        "dispatched_run_id": row.dispatched_run_id,
                    }
                    for row in gaps
                ],
                "change_sets": [self._changeset_dict(row) for row in changesets],
                "runs": [self._run_dict(row) for row in runs],
            }

    @staticmethod
    def _requires_execution_approval(policy: dict[str, Any]) -> str:
        if policy.get("uses_paid_service"):
            return "任务将调用付费服务"
        if policy.get("physical_device"):
            return "任务将控制物理设备"
        if policy.get("protocol_change"):
            return "任务将改变正式实验协议"
        budget = float(policy.get("estimated_cost") or 0)
        limit = float(policy.get("preauthorized_cost_limit") or 0)
        if budget > limit:
            return "任务预计成本超过预授权额度"
        return ""

    def dispatch_gap(
        self,
        project_id: str,
        document_id: str,
        gap_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        base_idempotency_key = str(payload.get("idempotency_key") or f"gap:{gap_id}")[:96]
        retry = bool(payload.get("retry"))
        retry_request_id = str(payload.get("retry_request_id") or "").strip()
        if retry and not retry_request_id:
            raise DocumentWorkspaceError("显式重试必须提供稳定的 retry_request_id")
        with self.session_factory() as session:
            gap = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.id == gap_id,
            ).with_for_update()).scalar_one_or_none()
            if not gap or gap.project_id != project_id or gap.document_id != document_id:
                raise DocumentWorkspaceError("证据缺口不存在")
            if gap.status == "resolved":
                raise DocumentWorkspaceError("证据缺口已解决，不能再次派发")
            if retry:
                retry_token = hashlib.sha256(retry_request_id.encode("utf-8")).hexdigest()[:24]
                idempotency_key = f"{base_idempotency_key[:64]}:retry:{retry_token}"
                existing = session.execute(select(WritingJarvisRun).where(
                    WritingJarvisRun.project_id == project_id,
                    WritingJarvisRun.document_id == document_id,
                    WritingJarvisRun.idempotency_key == idempotency_key,
                )).scalar_one_or_none()
                if existing:
                    steps = session.execute(select(WritingJarvisStep).where(WritingJarvisStep.run_id == existing.id)).scalars().all()
                    result = self._run_dict(existing, steps)
                    result["idempotent_replay"] = True
                    return result
                latest = session.get(WritingJarvisRun, gap.dispatched_run_id) if gap.dispatched_run_id else None
                if not latest or latest.status not in {"failed", "cancelled"}:
                    raise DocumentWorkspaceError("该证据缺口已有活跃运行，不能并发重试")
            else:
                idempotency_key = base_idempotency_key
                existing = session.execute(select(WritingJarvisRun).where(
                    WritingJarvisRun.project_id == project_id,
                    WritingJarvisRun.document_id == document_id,
                    WritingJarvisRun.idempotency_key == idempotency_key,
                )).scalar_one_or_none()
            if existing:
                steps = session.execute(select(WritingJarvisStep).where(WritingJarvisStep.run_id == existing.id)).scalars().all()
                result = self._run_dict(existing, steps)
                result["idempotent_replay"] = True
                return result
            latest = session.get(WritingJarvisRun, gap.dispatched_run_id) if gap.dispatched_run_id else None
            if latest and latest.status in {"queued", "running", "awaiting_approval", "waiting_evidence"}:
                raise DocumentWorkspaceError("该证据缺口已有活跃运行，不能重复派发")
            if latest and not retry:
                raise DocumentWorkspaceError("失败或已取消的运行必须通过显式重试恢复")
            matrix = payload.get("research_matrix") or gap.research_matrix
            if not isinstance(matrix, dict) or not matrix:
                raise DocumentWorkspaceError("证据缺口尚未形成 Research Matrix")
            policy = payload.get("execution_policy") or {}
            approval_reason = self._requires_execution_approval(policy)
            run = WritingJarvisRun(
                id=_uuid("jrun"),
                project_id=project_id,
                document_id=document_id,
                run_type="evidence_gap_dispatch",
                status="awaiting_approval" if approval_reason else "queued",
                idempotency_key=idempotency_key,
                input_payload={"gap_id": gap_id, "research_matrix": matrix, "execution_policy": policy},
                approval_reason=approval_reason,
                requested_by=actor,
                recovery_cursor={} if approval_reason else {"next_step": "compile_research_matrix"},
            )
            step = WritingJarvisStep(
                id=_uuid("jstep"),
                run_id=run.id,
                step_key="compile_research_matrix",
                status="waiting_approval" if approval_reason else "pending",
                input_payload=matrix,
                attempt_count=0,
            )
            gap.status = "awaiting_approval" if approval_reason else "queued"
            gap.dispatched_run_id = run.id
            session.add_all([run, step])
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(select(WritingJarvisRun).where(
                    WritingJarvisRun.project_id == project_id,
                    WritingJarvisRun.document_id == document_id,
                    WritingJarvisRun.idempotency_key == idempotency_key,
                )).scalar_one_or_none()
                if not existing:
                    raise
                steps = session.execute(select(WritingJarvisStep).where(
                    WritingJarvisStep.run_id == existing.id,
                )).scalars().all()
                result = self._run_dict(existing, steps)
                result["idempotent_replay"] = True
                return result
            return self._run_dict(run, [step])

    def get_run(self, project_id: str, document_id: str, run_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(WritingJarvisRun, run_id)
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("Jarvis 运行不存在")
            steps = session.execute(select(WritingJarvisStep).where(
                WritingJarvisStep.run_id == run_id,
            ).order_by(WritingJarvisStep.updated_at.asc())).scalars().all()
            return self._run_dict(row, steps)

    def decide_run(
        self,
        project_id: str,
        document_id: str,
        run_id: str,
        decision: str,
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        if decision not in {"approve", "reject"}:
            raise DocumentWorkspaceError("运行审批决定必须为 approve 或 reject")
        with self.session_factory() as session:
            gap = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            row = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
                WritingJarvisRun.project_id == project_id,
                WritingJarvisRun.document_id == document_id,
            ).with_for_update()).scalar_one_or_none()
            if not row:
                raise DocumentWorkspaceError("Jarvis 运行不存在")
            if row.status != "awaiting_approval":
                return self._run_dict(row)
            if decision == "reject":
                row.status = "cancelled"
                row.finished_at = _now()
                row.approval_reason = f"{row.approval_reason}；由 {actor} 拒绝"
                if gap and gap.status != "resolved":
                    gap.status = "open"
                    gap.reason = "Jarvis 运行审批已拒绝，可调整 Research Matrix 后重新派发"
            else:
                if not (row.recovery_cursor or {}).get("next_step"):
                    row.recovery_cursor = {"next_step": "compile_research_matrix"}
                row.status = "queued"
                row.approval_reason = ""
                if gap and gap.status != "resolved":
                    gap.status = "queued"
            session.commit()
            return self._run_dict(row)

    async def process_run(self, run_id: str, worker_id: str) -> None:
        lease_owner = worker_id[:128]

        def leased_run(session):
            session.execute(select(WritingEvidenceGap.id).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            return session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
                WritingJarvisRun.status == "running",
                WritingJarvisRun.lease_owner == lease_owner,
            ).with_for_update()).scalar_one_or_none()

        with self.session_factory() as session:
            row = leased_run(session)
            if not row:
                return
            stage = str((row.recovery_cursor or {}).get("next_step") or "")
            recovery_cursor = dict(row.recovery_cursor or {})
            input_payload = dict(row.input_payload or {})
            result_payload = dict(row.result_payload or {})

        try:
            if stage == "compensate_remote_runs":
                remote_run_ids = [
                    str(value)
                    for value in recovery_cursor.get("remote_run_ids", [])
                    if str(value)
                ]
                await self._attempt_run_compensation(run_id, remote_run_ids)
                return

            if stage == "starting_remote":
                await self._start_remote_and_finalize(
                    run_id,
                    lease_owner,
                    plan_id=str(recovery_cursor.get("plan_id") or ""),
                    active_revision=int(recovery_cursor.get("expected_revision") or 1),
                    idempotency_key=str(
                        recovery_cursor.get("idempotency_key") or f"jarvis:{run_id}:start"
                    ),
                    published=result_payload.get("publish_result") or {},
                    synchronized=result_payload.get("synchronize_result") or {},
                )
                return

            if stage == "compile_research_matrix":
                matrix = input_payload.get("research_matrix") or {}
                compile_request = matrix if "matrix" in matrix else {"matrix": matrix}
                compiled_response = await asyncio.to_thread(self.research_compiler, compile_request)
                with self.session_factory() as session:
                    row = leased_run(session)
                    if not row:
                        return
                    step = session.execute(select(WritingJarvisStep).where(
                        WritingJarvisStep.run_id == run_id,
                        WritingJarvisStep.step_key == "compile_research_matrix",
                    )).scalar_one()
                    step.status = "completed"
                    step.attempt_count += 1
                    step.result_payload = compiled_response
                    row.result_payload = {**result_payload, "compiled_matrix": compiled_response}
                    row.recovery_cursor = {"next_step": "queue_experiment_plan"}
                    row.status = "queued"
                    row.lease_owner = ""
                    row.lease_expires_at = None
                    gap = session.execute(select(WritingEvidenceGap).where(
                        WritingEvidenceGap.dispatched_run_id == run_id
                    )).scalar_one_or_none()
                    if gap:
                        gap.status = "queued"
                    session.commit()

                return

            if stage == "queue_experiment_plan":
                compiled_response = result_payload.get("compiled_matrix") or {}
                compiled = compiled_response.get("compiled") if isinstance(compiled_response, dict) else None
                compiled = compiled if isinstance(compiled, dict) else compiled_response
                plan_request = compiled.get("training_plan_request") if isinstance(compiled, dict) else None
                if not isinstance(plan_request, dict):
                    raise DocumentWorkspaceError("One-Sim 编译结果缺少 training_plan_request")
                draft = await mission_planning_adapter.create_training_plan(plan_request)
                plan_id = str(plan_request.get("id") or "")
                if not plan_id:
                    raise DocumentWorkspaceError("One-Sim 训练计划草案缺少 ID")
                policy = input_payload.get("execution_policy") or {}
                auto_start = bool(policy.get("auto_start"))
                with self.session_factory() as session:
                    row = leased_run(session)
                    if not row:
                        return
                    step = session.execute(select(WritingJarvisStep).where(
                        WritingJarvisStep.run_id == run_id,
                        WritingJarvisStep.step_key == "queue_experiment_plan",
                    )).scalar_one_or_none()
                    if not step:
                        step = WritingJarvisStep(
                            id=_uuid("jstep"),
                            run_id=run_id,
                            step_key="queue_experiment_plan",
                            status="completed",
                            depends_on=["compile_research_matrix"],
                            attempt_count=1,
                            input_payload=plan_request,
                            result_payload=draft,
                        )
                        session.add(step)
                    row.result_payload = {
                        **result_payload,
                        "training_plan_id": plan_id,
                        "training_plan_draft": draft,
                    }
                    row.recovery_cursor = {"next_step": "publish_and_start"}
                    row.status = "queued" if auto_start else "awaiting_approval"
                    row.approval_reason = "" if auto_start else "训练计划草案已创建，等待发布与执行审批"
                    row.lease_owner = ""
                    row.lease_expires_at = None
                    gap = session.execute(select(WritingEvidenceGap).where(
                        WritingEvidenceGap.dispatched_run_id == run_id,
                    )).scalar_one_or_none()
                    if gap and gap.status != "resolved":
                        gap.status = "queued" if auto_start else "awaiting_approval"
                    session.commit()
                return

            if stage == "publish_and_start":
                plan_id = str(result_payload.get("training_plan_id") or "")
                draft = result_payload.get("training_plan_draft") or {}
                revision = int(draft.get("revision") or 1) if isinstance(draft, dict) else 1
                if self._stop_requested_before_external_call(run_id):
                    return
                published = await mission_planning_adapter.publish_training_plan(
                    plan_id,
                    expected_revision=revision,
                )
                if self._stop_requested_before_external_call(run_id):
                    return
                published_revision = int(published.get("revision") or revision)
                synchronized = await mission_planning_adapter.synchronize_training_plan(
                    plan_id,
                    expected_revision=published_revision,
                    idempotency_key=f"jarvis:{run_id}:sync",
                )
                if self._stop_requested_before_external_call(run_id):
                    return
                active_revision = int(synchronized.get("revision") or published_revision)
                with self.session_factory() as session:
                    gap = session.execute(select(WritingEvidenceGap).where(
                        WritingEvidenceGap.dispatched_run_id == run_id,
                    ).with_for_update()).scalar_one_or_none()
                    row = session.execute(select(WritingJarvisRun).where(
                        WritingJarvisRun.id == run_id,
                    ).with_for_update()).scalar_one_or_none()
                    if not row:
                        return
                    result_payload = dict(row.result_payload or {})
                    if row.status != "running" or row.lease_owner != lease_owner:
                        return
                    start_idempotency_key = f"jarvis:{run_id}:start"
                    row.result_payload = {
                        **result_payload,
                        "publish_result": published,
                        "synchronize_result": synchronized,
                    }
                    row.recovery_cursor = {
                        "next_step": "starting_remote",
                        "plan_id": plan_id,
                        "expected_revision": active_revision,
                        "idempotency_key": start_idempotency_key,
                    }
                    session.commit()
                stage = "starting_remote"
                await self._start_remote_and_finalize(
                    run_id,
                    lease_owner,
                    plan_id=plan_id,
                    active_revision=active_revision,
                    idempotency_key=start_idempotency_key,
                    published=published,
                    synchronized=synchronized,
                )
                return

            with self.session_factory() as session:
                row = leased_run(session)
                if row:
                    row.status = "completed"
                    row.finished_at = _now()
                    row.lease_owner = ""
                    row.lease_expires_at = None
                    session.commit()
        except Exception as exc:
            with self.session_factory() as session:
                row = leased_run(session)
                if row:
                    current_stage = str((row.recovery_cursor or {}).get("next_step") or stage)
                    if current_stage == "starting_remote":
                        row.status = "queued"
                        row.error = (
                            "One-Sim 启动结果未确认，将使用同一幂等键恢复："
                            f"{str(exc)[:3500]}"
                        )
                        row.lease_owner = ""
                        row.lease_expires_at = None
                        gap = session.execute(select(WritingEvidenceGap).where(
                            WritingEvidenceGap.dispatched_run_id == run_id,
                        )).scalar_one_or_none()
                        if gap and gap.status != "resolved":
                            gap.status = "queued"
                    else:
                        row.status = "failed"
                        row.error = str(exc)[:4000]
                        row.finished_at = _now()
                        row.lease_owner = ""
                        row.lease_expires_at = None
                        gap = session.execute(select(WritingEvidenceGap).where(
                            WritingEvidenceGap.dispatched_run_id == run_id,
                        )).scalar_one_or_none()
                        if gap:
                            gap.status = "open"
                    step = session.execute(select(WritingJarvisStep).where(
                        WritingJarvisStep.run_id == run_id,
                        WritingJarvisStep.step_key == stage,
                    )).scalar_one_or_none()
                    if step and current_stage != "starting_remote":
                        step.status = "failed"
                        step.attempt_count += 1
                        step.error = row.error
                    session.commit()

    def ingest_evidence_bundle(
        self,
        project_id: str,
        document_id: str,
        run_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        run = self.get_run(project_id, document_id, run_id)
        if run["status"] not in {
            "waiting_evidence",
            "running",
            "queued",
            "cancellation_requested",
            "compensating",
            "cancelled",
        }:
            raise DocumentWorkspaceError("Jarvis 运行当前不接受证据包回传")
        evidence = self.register_evidence(
            project_id,
            document_id,
            {
                "source_system": payload.get("source_system") or "one-sim",
                "source_record_id": payload.get("source_record_id") or payload.get("bundle_id") or "",
                "artifact_path": payload.get("artifact_path") or "",
                "artifact_sha256": payload.get("artifact_sha256") or "",
                "perspective_scope": payload.get("perspective_scope") or "project",
                "evidence_level": payload.get("evidence_level") or "diagnostic",
                "allowed_claim_scope": payload.get("allowed_claim_scope") or "",
                "provenance": {
                    **(payload.get("provenance") or {}),
                    "simulation_record_id": payload.get("simulation_record_id") or "",
                    "paper_evidence_packet": payload.get("paper_evidence_packet") or {},
                    "jarvis_run_id": run_id,
                },
            },
            actor,
        )
        with self.session_factory() as session:
            gap = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.dispatched_run_id == run_id
            )).scalar_one_or_none()
        binding = None
        if gap:
            binding = self.bind_evidence(
                project_id,
                document_id,
                {"claim_id": gap.claim_id, "evidence_ref_id": evidence["id"], "origin_run_id": run_id},
                actor,
            )
        with self.session_factory() as session:
            session.execute(select(WritingEvidenceGap.id).where(
                WritingEvidenceGap.dispatched_run_id == run_id,
            ).with_for_update()).scalar_one_or_none()
            row = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == run_id,
                WritingJarvisRun.project_id == project_id,
                WritingJarvisRun.document_id == document_id,
            ).with_for_update()).scalar_one()
            result_payload = dict(row.result_payload or {})
            row.result_payload = {
                **result_payload,
                "evidence_ref_id": evidence["id"],
                "paper_evidence_packet": payload.get("paper_evidence_packet") or {},
            }
            compensation_active = row.status in {
                "cancellation_requested",
                "compensating",
                "cancelled",
            }
            if not compensation_active:
                row.recovery_cursor = {"next_step": "propose_evidence_bound_revision"}
                row.status = "completed"
                row.finished_at = _now()
                step = session.execute(select(WritingJarvisStep).where(
                    WritingJarvisStep.run_id == run_id,
                    WritingJarvisStep.step_key == "wait_for_evidence_bundle",
                )).scalar_one_or_none()
                if not step:
                    step = WritingJarvisStep(
                        id=_uuid("jstep"),
                        run_id=run_id,
                        step_key="wait_for_evidence_bundle",
                        status="completed",
                        depends_on=["publish_and_start"],
                        attempt_count=1,
                        input_payload={"bundle_id": payload.get("bundle_id") or ""},
                        result_payload={"evidence_ref_id": evidence["id"]},
                    )
                    session.add(step)
            session.commit()
            steps = session.execute(select(WritingJarvisStep).where(
                WritingJarvisStep.run_id == run_id
            )).scalars().all()
            result = self._run_dict(row, steps)
            result["evidence"] = evidence
            result["binding"] = binding
            return result

    def claim_next_run(self, worker_id: str, lease_seconds: int = 300) -> dict[str, Any] | None:
        self._require_mutation_backend()
        now = _now()
        with self.session_factory() as session:
            eligible_run = or_(
                WritingJarvisRun.status == "queued",
                and_(
                    WritingJarvisRun.status == "compensating",
                    or_(
                        WritingJarvisRun.lease_expires_at.is_(None),
                        WritingJarvisRun.lease_expires_at < now,
                    ),
                ),
                and_(
                    WritingJarvisRun.status == "cancellation_requested",
                    or_(
                        WritingJarvisRun.lease_expires_at.is_(None),
                        WritingJarvisRun.lease_expires_at < now,
                    ),
                ),
                and_(
                    WritingJarvisRun.status == "running",
                    WritingJarvisRun.lease_expires_at.is_not(None),
                    WritingJarvisRun.lease_expires_at < now,
                ),
            )
            gap = session.execute(select(WritingEvidenceGap).join(
                WritingJarvisRun,
                WritingJarvisRun.id == WritingEvidenceGap.dispatched_run_id,
            ).where(
                eligible_run,
            ).order_by(WritingJarvisRun.created_at.asc()).with_for_update(
                of=WritingEvidenceGap,
                skip_locked=True,
            ).limit(1)).scalar_one_or_none()
            if not gap:
                return None
            row = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.id == gap.dispatched_run_id,
                or_(
                    WritingJarvisRun.status == "queued",
                    and_(
                        WritingJarvisRun.status == "compensating",
                        or_(
                            WritingJarvisRun.lease_expires_at.is_(None),
                            WritingJarvisRun.lease_expires_at < now,
                        ),
                    ),
                    and_(
                        WritingJarvisRun.status == "cancellation_requested",
                        or_(
                            WritingJarvisRun.lease_expires_at.is_(None),
                            WritingJarvisRun.lease_expires_at < now,
                        ),
                    ),
                    and_(
                        WritingJarvisRun.status == "running",
                        WritingJarvisRun.lease_expires_at.is_not(None),
                        WritingJarvisRun.lease_expires_at < now,
                    ),
                ),
            ).with_for_update(skip_locked=True)).scalar_one_or_none()
            if not row:
                return None
            recovery_step = str((row.recovery_cursor or {}).get("next_step") or "")
            external_recovery_required = recovery_step in {
                "starting_remote",
                "compensate_remote_runs",
            }
            if gap.status == "resolved" and not external_recovery_required:
                row.status = "cancelled"
                row.finished_at = now
                row.error = "证据缺口已解决，运行未被领取"
                session.commit()
                return None
            row.status = "running"
            row.lease_owner = worker_id[:128]
            row.lease_expires_at = now + timedelta(seconds=max(30, lease_seconds))
            row.started_at = row.started_at or now
            if gap.status != "resolved":
                gap.status = "running"
            session.commit()
            return self._run_dict(row)

    def create_change_set(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        idempotency_key = str(payload.get("idempotency_key") or _uuid("changeset"))[:96]
        with self.session_factory() as session:
            existing = session.execute(select(WritingChangeSet).where(
                WritingChangeSet.project_id == project_id,
                WritingChangeSet.document_id == document_id,
                WritingChangeSet.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                return self._changeset_dict(existing)
            state = self._state(session, project_id, document_id)
            row = WritingChangeSet(
                id=_uuid("changeset"),
                project_id=project_id,
                document_id=document_id,
                base_revision=int(payload.get("base_revision") or state.document_revision),
                operations=payload.get("operations") or [],
                evidence_ref_ids=payload.get("evidence_ref_ids") or [],
                risk_level=str(payload.get("risk_level") or "high")[:16],
                approval_policy=str(payload.get("approval_policy") or "risk_driven")[:32],
                idempotency_key=idempotency_key,
                summary=str(payload.get("summary") or "待审修改")[:4000],
                status="review_required",
            )
            session.add(row)
            session.commit()
            return self._changeset_dict(row)

    def get_change_set(self, project_id: str, document_id: str, change_set_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(WritingChangeSet, change_set_id)
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("WritingChangeSet 不存在")
            return self._changeset_dict(row)

    def decide_change_set(
        self,
        project_id: str,
        document_id: str,
        change_set_id: str,
        decision: str,
        actor: str,
        *,
        result_revision: int = 0,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        if decision not in {"approve", "reject"}:
            raise DocumentWorkspaceError("审批决定必须为 approve 或 reject")
        with self.session_factory() as session:
            row = session.get(WritingChangeSet, change_set_id)
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("WritingChangeSet 不存在")
            if row.status in {"approved", "rejected"}:
                return self._changeset_dict(row)
            if decision == "approve" and not row.proposal_id and result_revision <= 0:
                raise DocumentWorkspaceError("该 ChangeSet 尚无可执行映射，不能标记为已应用")
            row.status = "approved" if decision == "approve" else "rejected"
            row.result_revision = result_revision
            row.decided_by = actor
            row.decided_at = _now()
            session.commit()
            return self._changeset_dict(row)

    def approve_revision(
        self,
        project_id: str,
        document_id: str,
        revision: int,
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id, lock=True)
            if revision != state.document_revision:
                raise DocumentVersionConflict("只能审批当前正文修订；请先处理后续修改")
            version = session.execute(select(WritingDocumentVersion).where(
                WritingDocumentVersion.project_id == project_id,
                WritingDocumentVersion.document_id == document_id,
                WritingDocumentVersion.document_revision == revision,
            )).scalar_one_or_none()
            if not version:
                raise DocumentWorkspaceError("当前修订缺少不可变版本快照")
            state.approved_revision = revision
            version.lifecycle_status = "approved"
            approval = session.execute(select(WritingChangeSet).where(
                WritingChangeSet.project_id == project_id,
                WritingChangeSet.document_id == document_id,
                WritingChangeSet.idempotency_key == f"revision-approval:{revision}",
            )).scalar_one_or_none()
            if not approval:
                approval = WritingChangeSet(
                    id=_uuid("changeset"),
                    project_id=project_id,
                    document_id=document_id,
                    base_revision=revision,
                    result_revision=revision,
                    operations=[{"op": "approve_revision", "revision": revision}],
                    evidence_ref_ids=[],
                    risk_level="high",
                    approval_policy="chapter_approval",
                    status="approved",
                    idempotency_key=f"revision-approval:{revision}",
                    summary=f"审批正文修订 {revision}",
                    decided_by=actor,
                    decided_at=_now(),
                )
                session.add(approval)
            session.commit()
            return {"document_revision": state.document_revision, "approved_revision": state.approved_revision}

    def register_word_import(
        self,
        project_id: str,
        document_id: str,
        *,
        filename: str,
        content: bytes,
        base_revision: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        if not filename.lower().endswith(".docx"):
            raise DocumentWorkspaceError("Word 回流仅接受 DOCX 文件")
        _validate_docx(content)
        sha256 = hashlib.sha256(content).hexdigest()
        import_root = Path(os.getenv(
            "WRITING_IMPORT_ROOT",
            str(Path(__file__).resolve().parents[1] / "data" / "writing_imports"),
        ))
        target_dir = import_root / project_id / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = target_dir / f"{sha256}.docx"
        if not artifact_path.exists():
            temporary_path = target_dir / f".{sha256}.{uuid.uuid4().hex}.tmp"
            try:
                temporary_path.write_bytes(content)
                os.replace(temporary_path, artifact_path)
            finally:
                temporary_path.unlink(missing_ok=True)
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            if base_revision > state.document_revision:
                raise DocumentVersionConflict("Word 回流引用了尚不存在的正文修订")
            existing = session.execute(select(WritingWordImport).join(
                WritingChangeSet, WritingWordImport.change_set_id == WritingChangeSet.id
            ).where(
                WritingWordImport.project_id == project_id,
                WritingWordImport.document_id == document_id,
                WritingChangeSet.idempotency_key == idempotency_key[:96],
            )).scalar_one_or_none()
            if existing:
                return {"id": existing.id, "change_set_id": existing.change_set_id, "mapping_status": existing.mapping_status, "idempotent_replay": True}
            change_set = WritingChangeSet(
                id=_uuid("changeset"),
                project_id=project_id,
                document_id=document_id,
                base_revision=base_revision,
                operations=[{
                    "op": "word_import_compare",
                    "filename": filename,
                    "file_sha256": sha256,
                    "artifact_path": str(artifact_path),
                }],
                evidence_ref_ids=[],
                risk_level="high",
                approval_policy="word_roundtrip",
                status="review_required",
                idempotency_key=idempotency_key[:96],
                summary="Word 修改已登记，需完成块映射与人工比较后方可回流",
            )
            row = WritingWordImport(
                id=_uuid("wordimport"),
                project_id=project_id,
                document_id=document_id,
                base_revision=base_revision,
                filename=filename[:255],
                file_sha256=sha256,
                file_size=len(content),
                mapping_status="manual_review",
                change_set_id=change_set.id,
                created_by=actor,
            )
            session.add_all([change_set, row])
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(select(WritingWordImport).join(
                    WritingChangeSet, WritingWordImport.change_set_id == WritingChangeSet.id
                ).where(
                    WritingWordImport.project_id == project_id,
                    WritingWordImport.document_id == document_id,
                    WritingChangeSet.idempotency_key == idempotency_key[:96],
                )).scalar_one_or_none()
                if not existing:
                    raise
                return {
                    "id": existing.id,
                    "change_set_id": existing.change_set_id,
                    "mapping_status": existing.mapping_status,
                    "idempotent_replay": True,
                }
            return {
                "id": row.id,
                "base_revision": row.base_revision,
                "filename": row.filename,
                "file_sha256": row.file_sha256,
                "file_size": row.file_size,
                "artifact_path": str(artifact_path),
                "mapping_status": row.mapping_status,
                "change_set_id": row.change_set_id,
            }

    def create_release(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        idempotency_key = str(payload.get("idempotency_key") or _uuid("release"))[:96]
        template_sha = str(payload.get("template_sha256") or "").lower()
        if not _valid_sha256(template_sha):
            raise DocumentWorkspaceError("WordRelease 必须登记有效模板 SHA-256")
        with self.session_factory() as session:
            existing = session.execute(select(WritingWordRelease).where(
                WritingWordRelease.project_id == project_id,
                WritingWordRelease.document_id == document_id,
                WritingWordRelease.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                return self._release_dict(existing)
            state = self._state(session, project_id, document_id)
            revision = int(payload.get("document_revision") or state.approved_revision)
            if revision <= 0 or revision != state.approved_revision:
                raise DocumentWorkspaceError("正式 Word 只能从当前已审批修订生成")
            if revision < state.published_revision:
                raise DocumentWorkspaceError("不能为早于当前已发布修订的正文创建 WordRelease")
            row = WritingWordRelease(
                id=_uuid("release"),
                project_id=project_id,
                document_id=document_id,
                document_revision=revision,
                template_sha256=template_sha,
                idempotency_key=idempotency_key,
                created_by=actor,
            )
            session.add(row)
            session.commit()
            return self._release_dict(row)

    @staticmethod
    def _release_dict(row: WritingWordRelease) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "document_revision": row.document_revision,
            "template_sha256": row.template_sha256,
            "docx_path": row.docx_path,
            "docx_sha256": row.docx_sha256,
            "pdf_path": row.pdf_path,
            "pdf_sha256": row.pdf_sha256,
            "field_refresh_status": row.field_refresh_status,
            "page_check": row.page_check or {},
            "status": row.status,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at.isoformat() if row.approved_at else "",
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    def update_release(
        self,
        project_id: str,
        document_id: str,
        release_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        with self.session_factory() as session:
            row = session.execute(select(WritingWordRelease).where(
                WritingWordRelease.id == release_id,
            ).with_for_update()).scalar_one_or_none()
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("WordRelease 不存在")
            mutable_fields = ("docx_path", "docx_sha256", "pdf_path", "pdf_sha256", "field_refresh_status")
            terminal_statuses = {"approved", "rejected", "failed"}
            if row.status in terminal_statuses:
                requested_status = str(payload.get("status") or row.status)
                changed = requested_status != row.status or any(
                    field in payload and str(payload[field] or "") != str(getattr(row, field) or "")
                    for field in mutable_fields
                )
                if "page_check" in payload and (payload["page_check"] or {}) != (row.page_check or {}):
                    changed = True
                if changed:
                    raise DocumentWorkspaceError("已终结的 WordRelease 不可修改")
                return self._release_dict(row)
            requested_status = str(payload.get("status") or row.status)
            if requested_status not in {"candidate", "approved", "rejected", "failed"}:
                raise DocumentWorkspaceError("WordRelease 状态无效")
            for field in mutable_fields:
                if field in payload:
                    setattr(row, field, str(payload[field] or ""))
            if "page_check" in payload:
                row.page_check = payload["page_check"] or {}
            if requested_status == "approved":
                state = self._state(session, project_id, document_id, lock=True)
                if row.document_revision != state.approved_revision:
                    raise DocumentWorkspaceError("WordRelease 不再对应当前已审批正文修订")
                if row.document_revision < state.published_revision:
                    raise DocumentWorkspaceError("不能将正式发布修订回退到更早版本")
                if not (_valid_sha256(row.docx_sha256) and _valid_sha256(row.pdf_sha256)):
                    raise DocumentWorkspaceError("发布审批前必须登记 DOCX 与 PDF 哈希")
                if row.field_refresh_status != "completed" or not bool((row.page_check or {}).get("passed")):
                    raise DocumentWorkspaceError("发布审批前必须完成字段刷新和全页检查")
                for label, path_value, expected_sha in (
                    ("DOCX", row.docx_path, row.docx_sha256),
                    ("PDF", row.pdf_path, row.pdf_sha256),
                ):
                    path = Path(path_value)
                    if not path.is_file() or _file_sha256(path) != expected_sha:
                        raise DocumentWorkspaceError(f"{label} 文件不存在或哈希与登记值不一致")
                state.published_revision = row.document_revision
                row.approved_by = actor
                row.approved_at = _now()
            row.status = requested_status
            session.commit()
            return self._release_dict(row)

    def require_formal_release(
        self,
        project_id: str,
        document_id: str,
        format: str = "docx",
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            unresolved_gaps = session.execute(select(WritingEvidenceGap.id).where(
                WritingEvidenceGap.project_id == project_id,
                WritingEvidenceGap.document_id == document_id,
                WritingEvidenceGap.status != "resolved",
            ).limit(1)).scalar_one_or_none()
            if unresolved_gaps:
                raise DocumentWorkspaceError("正式发布前必须解决全部论文主张证据缺口")
            active_run = session.execute(select(WritingJarvisRun.id).where(
                WritingJarvisRun.project_id == project_id,
                WritingJarvisRun.document_id == document_id,
                WritingJarvisRun.status.in_({
                    "queued",
                    "running",
                    "awaiting_approval",
                    "waiting_evidence",
                    "cancellation_requested",
                    "compensating",
                }),
            ).limit(1)).scalar_one_or_none()
            if active_run:
                raise DocumentWorkspaceError("正式发布前必须等待全部 Jarvis 研究运行结束或取消")
            pending_change_set = session.execute(select(WritingChangeSet.id).where(
                WritingChangeSet.project_id == project_id,
                WritingChangeSet.document_id == document_id,
                WritingChangeSet.status.in_({"review_required", "conflicted"}),
            ).limit(1)).scalar_one_or_none()
            if pending_change_set:
                raise DocumentWorkspaceError("正式发布前必须处理全部待审 WritingChangeSet")
            bound_evidence = session.execute(select(WritingEvidenceRef).join(
                WritingEvidenceBinding,
                WritingEvidenceBinding.evidence_ref_id == WritingEvidenceRef.id,
            ).join(
                WritingClaim,
                WritingClaim.id == WritingEvidenceBinding.claim_id,
            ).where(
                WritingClaim.project_id == project_id,
                WritingClaim.document_id == document_id,
                WritingClaim.status == "active",
                WritingEvidenceBinding.status == "active",
            )).scalars().all()
            for evidence in bound_evidence:
                self._verify_evidence_ref(evidence)
            release = session.execute(select(WritingWordRelease).where(
                WritingWordRelease.project_id == project_id,
                WritingWordRelease.document_id == document_id,
                WritingWordRelease.document_revision == state.approved_revision,
                WritingWordRelease.status == "approved",
            ).order_by(WritingWordRelease.created_at.desc()).limit(1)).scalar_one_or_none()
            if not release or state.approved_revision <= 0:
                raise DocumentWorkspaceError("正式导出需要当前已审批修订对应的已批准 WordRelease")
            if state.published_revision != release.document_revision:
                raise DocumentWorkspaceError("WordRelease 与当前正式发布修订不一致")
            if release.field_refresh_status != "completed" or not bool((release.page_check or {}).get("passed")):
                raise DocumentWorkspaceError("WordRelease 尚未完成字段刷新和全页检查")
            for label, path_value, expected_sha in (
                ("DOCX", release.docx_path, release.docx_sha256),
                ("PDF", release.pdf_path, release.pdf_sha256),
            ):
                path = Path(path_value)
                if not _valid_sha256(expected_sha) or not path.is_file() or _file_sha256(path) != expected_sha:
                    raise DocumentWorkspaceError(f"{label} 发布件不存在或哈希校验失败")
            if format.lower() not in {"docx", "pdf"}:
                raise DocumentWorkspaceError("正式发布仅支持 DOCX 或 PDF")
            return self._release_dict(release)


writing_research_service = WritingResearchService()
