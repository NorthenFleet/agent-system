"""Evidence-aware writing workflow and durable cross-system run state."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import os
import re
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
    WritingResearchEvaluation,
    WritingResearchIteration,
    WritingResearchRunScope,
    WritingRetrievalRef,
    WritingScreeningDecision,
    WritingWordImport,
    WritingWordRelease,
)
from services.document_workspace_service import DocumentVersionConflict, DocumentWorkspaceError
from services.mission_planning_adapter import mission_planning_adapter


EVIDENCE_LEVELS = {"diagnostic": 0, "G1": 1, "G2": 2, "A": 3}
EVIDENCE_SCOPE_KEYS = {"claim", "claim_type", "section", "block"}
EVIDENCE_KINDS = {"literature", "simulation", "dataset", "policy", "system_record"}
SOURCE_QUALITIES = {"peer_reviewed", "official", "standard", "preprint", "secondary", "internal"}
SUPPORT_ROLES = {"supports", "contradicts", "contextualizes", "method_basis"}
DIRECTNESS_LEVELS = {"direct", "indirect", "metadata_only"}
ACCESS_STATUSES = {"metadata_only", "abstract", "fulltext", "unavailable"}
SCREENING_STATUSES = {"pending", "include", "exclude", "uncertain", "duplicate"}
GAP_TYPES = {"literature", "experiment", "mixed"}
LITERATURE_EVIDENCE_KINDS = {"literature", "policy"}
EXPERIMENT_EVIDENCE_KINDS = {"simulation", "dataset", "system_record"}
LITERATURE_SOURCES = {"local_knowledge", "bibliography", "semantic_scholar", "crossref"}
LITERATURE_RUN_STEPS = (
    "freeze_baseline",
    "extract_claims",
    "build_matrix",
    "retrieve_local",
    "retrieve_external",
    "deduplicate",
    "screen",
    "snapshot_sources",
    "promote_evidence",
    "bind_claims",
    "score_baseline",
)
EXTERNAL_SCREENING_POLICY_VERSION = "external-topic-phrase-v1"
LITERATURE_DIRECTIONS = (
    {
        "key": "command_authority",
        "title": "战术指挥控制、任务式指挥与人机权责配置",
        "keywords_zh": ["指挥控制", "任务式指挥", "人机权责", "动态授权", "认知负荷"],
        "keywords_en": ["command and control", "mission command", "human machine authority allocation"],
    },
    {
        "key": "intent_decomposition",
        "title": "指挥意图形式化、任务分析与层次化任务分解",
        "keywords_zh": ["指挥意图", "任务分析", "任务分解"],
        "keywords_en": ["commander intent", "mission analysis", "task decomposition"],
    },
    {
        "key": "coa_refinement",
        "title": "行动方案向任务级计划细化、可执行性校核与推演评估",
        "keywords_zh": ["行动方案", "计划细化", "可执行性校核", "推演评估"],
        "keywords_en": ["course of action", "plan refinement", "feasibility assessment"],
    },
    {
        "key": "force_allocation",
        "title": "任务编组、任务与资源分配及协同组织",
        "keywords_zh": ["任务编组", "任务分配", "资源分配", "协同组织"],
        "keywords_en": ["task organization", "task allocation", "resource allocation"],
    },
    {
        "key": "execution_replanning",
        "title": "计划执行控制、受扰通信与动态重规划",
        "keywords_zh": ["执行控制", "受扰通信", "动态重规划"],
        "keywords_en": ["execution control", "denied communications", "dynamic replanning"],
    },
    {
        "key": "autonomous_coordination",
        "title": "任务级自主决策与多平台协同机动",
        "keywords_zh": ["自主决策", "多平台协同", "协同机动"],
        "keywords_en": ["autonomous decision making", "multi platform coordination"],
    },
    {
        "key": "wargame_evaluation",
        "title": "任务规划系统、兵棋仿真与战术效能评估",
        "keywords_zh": ["任务规划系统", "兵棋仿真", "战术效能评估"],
        "keywords_en": ["mission planning system", "wargaming", "operational effectiveness"],
    },
)
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


def _normalized_literature_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", value.lower()))


def _external_topic_match(retrieval: dict[str, Any]) -> tuple[bool, str]:
    direction = next(
        (item for item in LITERATURE_DIRECTIONS if item["key"] == retrieval.get("query_id")),
        None,
    )
    if not direction:
        return False, "检索方向无法映射到研究矩阵"

    haystack = _normalized_literature_text(
        f"{retrieval.get('title') or ''} {retrieval.get('abstract_snapshot') or ''}"
    )
    matched_terms: list[str] = []
    for term in [*(direction.get("keywords_zh") or []), *(direction.get("keywords_en") or [])]:
        normalized = _normalized_literature_text(str(term))
        tokens = normalized.split()
        distinctive_suffix = " ".join(tokens[-2:]) if len(tokens) > 2 else normalized
        if normalized and (normalized in haystack or distinctive_suffix in haystack):
            matched_terms.append(str(term))
    if matched_terms:
        return True, f"主题术语命中：{', '.join(matched_terms[:3])}"
    return False, "题名和摘要未命中该研究方向的主题短语"


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def _payload_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DocumentWorkspaceError("时间字段必须使用 ISO-8601 格式") from exc


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


def _default_context_retriever(**payload: Any) -> dict[str, Any]:
    from services.context_retrieval_service import context_retrieval_service

    return context_retrieval_service.retrieve(**payload)


def _default_external_retriever(**payload: Any) -> dict[str, Any]:
    from services.writing_literature_sources import external_literature_registry

    return external_literature_registry.search(**payload)


def _node_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("text") or "") + "".join(
        _node_text(child) for child in (node.get("content") or [])
    )


def _citation_numbers(value: str) -> list[int]:
    numbers: set[int] = set()
    for start, end in re.findall(r"\[(\d+)(?:-(\d+))?\]", value):
        first = int(start)
        last = int(end or start)
        if last < first or last - first > 100:
            continue
        numbers.update(range(first, last + 1))
    return sorted(numbers)


def _reference_metadata(entry: str) -> dict[str, Any]:
    match = re.match(r"^\[(\d+)\]\s*(.+)$", entry.strip())
    if not match:
        return {}
    number = int(match.group(1))
    body = match.group(2).strip()
    doi_match = re.search(r"\bDOI:\s*([^\s]+)", body, flags=re.IGNORECASE)
    year_matches = re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", body)
    title = body
    if "." in body:
        parts = [part.strip() for part in body.split(".") if part.strip()]
        if len(parts) >= 2:
            title = parts[1]
    return {
        "number": number,
        "entry": entry.strip(),
        "title": title[:4000],
        "year": int(year_matches[-1]) if year_matches else None,
        "doi": (doi_match.group(1).rstrip(".") if doi_match else "")[:300],
    }


def _evidence_category(evidence_kind: str) -> str:
    if evidence_kind in LITERATURE_EVIDENCE_KINDS:
        return "literature"
    if evidence_kind in EXPERIMENT_EVIDENCE_KINDS:
        return "experiment"
    return ""


def _required_evidence_categories(gap_type: str) -> set[str]:
    if gap_type == "mixed":
        return {"literature", "experiment"}
    if gap_type in {"literature", "experiment"}:
        return {gap_type}
    return {"experiment"}


def _classify_gap(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("gap_type") or "").strip().lower()
    if explicit:
        if explicit not in GAP_TYPES:
            raise DocumentWorkspaceError("证据缺口类型必须为 literature、experiment 或 mixed")
        return explicit

    policy = payload.get("evidence_policy") or {}
    policy_type = str(policy.get("gap_type") or "").strip().lower() if isinstance(policy, dict) else ""
    if policy_type:
        if policy_type not in GAP_TYPES:
            raise DocumentWorkspaceError("证据策略中的缺口类型无效")
        return policy_type
    required_kinds = set(policy.get("required_evidence_kinds") or []) if isinstance(policy, dict) else set()
    required_categories = {_evidence_category(str(kind)) for kind in required_kinds} - {""}
    if required_categories == {"literature", "experiment"}:
        return "mixed"
    if required_categories:
        return next(iter(required_categories))

    matrix = payload.get("research_matrix") or {}
    searchable = json.dumps(matrix, ensure_ascii=False, sort_keys=True).lower()
    searchable = f"{searchable} {str(payload.get('claim_text') or '').lower()}"
    literature = any(token in searchable for token in (
        "writing.literature", "literature", "文献", "综述", "研究现状", "引用", "来源",
    ))
    experiment = any(token in searchable for token in (
        "one_sim", "one-sim", "simulation", "experiment", "training_plan",
        "仿真", "实验", "训练", "对照", "性能评估", "效能评估",
    ))
    if literature and experiment:
        return "mixed"
    if literature:
        return "literature"
    return "experiment"


class WritingResearchService:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        research_compiler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        context_retriever: Callable[..., dict[str, Any]] | None = None,
        external_retriever: Callable[..., dict[str, Any]] | None = None,
        allow_non_postgres_writes: bool | None = None,
        evidence_root: str | Path | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.research_compiler = research_compiler or _default_research_compiler
        self.context_retriever = context_retriever or _default_context_retriever
        self.external_retriever = external_retriever or _default_external_retriever
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
            "claim_key": row.claim_key,
            "claim_fingerprint": row.claim_fingerprint,
            "rhetorical_role": row.rhetorical_role,
            "evidence_policy": row.evidence_policy or {},
            "temporal_scope": row.temporal_scope,
            "geographic_scope": row.geographic_scope,
            "supersedes_claim_id": row.supersedes_claim_id or "",
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
            "evidence_kind": row.evidence_kind,
            "source_quality": row.source_quality,
            "support_role": row.support_role,
            "directness": row.directness,
            "published_at": row.published_at.isoformat() if row.published_at else "",
            "acquired_at": row.acquired_at.isoformat() if row.acquired_at else "",
            "license_or_access": row.license_or_access,
            "retrieval_ref_id": row.retrieval_ref_id or "",
            "locator": row.locator or {},
            "excerpt_sha256": row.excerpt_sha256,
            "allowed_claim_scope": row.allowed_claim_scope,
            "provenance": row.provenance or {},
            "immutable": row.immutable,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    @staticmethod
    def _retrieval_dict(row: WritingRetrievalRef) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "document_revision": row.document_revision,
            "run_id": row.run_id or "",
            "iteration_id": row.iteration_id or "",
            "provider": row.provider,
            "provider_record_id": row.provider_record_id,
            "query_id": row.query_id,
            "query_text": row.query_text,
            "rank": row.rank,
            "retrieval_score": row.retrieval_score,
            "title": row.title,
            "authors": row.authors or [],
            "year": row.year,
            "venue": row.venue,
            "doi": row.doi,
            "url": row.url,
            "abstract_snapshot": row.abstract_snapshot,
            "metadata_snapshot": row.metadata_snapshot or {},
            "metadata_sha256": row.metadata_sha256,
            "access_status": row.access_status,
            "screening_status": row.screening_status,
            "screening_reason": row.screening_reason,
            "canonical_ref_id": row.canonical_ref_id or "",
            "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else "",
            "created_by": row.created_by,
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

    @staticmethod
    def _iteration_dict(
        row: WritingResearchIteration,
        evaluation: WritingResearchEvaluation | None = None,
    ) -> dict[str, Any]:
        result = {
            "id": row.id,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "run_id": row.run_id,
            "iteration_no": row.iteration_no,
            "base_revision": row.base_revision,
            "base_section_sha256": row.base_section_sha256,
            "candidate_sha256": row.candidate_sha256,
            "candidate_payload": row.candidate_payload or {},
            "candidate_artifact_path": row.candidate_artifact_path or "",
            "status": row.status,
            "parent_iteration_id": row.parent_iteration_id or "",
            "change_set_id": row.change_set_id or "",
            "started_at": row.started_at.isoformat() if row.started_at else "",
            "finished_at": row.finished_at.isoformat() if row.finished_at else "",
        }
        if evaluation:
            result["evaluation"] = {
                "id": evaluation.id,
                "evaluator_version": evaluation.evaluator_version,
                "hard_gates": evaluation.hard_gates or {},
                "dimension_scores": evaluation.dimension_scores or {},
                "total_score": evaluation.total_score,
                "baseline_delta": evaluation.baseline_delta,
                "decision": evaluation.decision,
                "reasons": evaluation.reasons or [],
                "input_sha256": evaluation.input_sha256,
                "created_at": evaluation.created_at.isoformat() if evaluation.created_at else "",
            }
        return result

    @staticmethod
    def _section_snapshot(content_json: dict[str, Any], section_id: str) -> dict[str, Any]:
        nodes = list((content_json or {}).get("content") or [])
        selected: list[dict[str, Any]] = []
        heading_level = 0
        heading_title = ""
        heading_block_id = ""
        for node in nodes:
            node_type = str(node.get("type") or "")
            attrs = node.get("attrs") or {}
            title = _node_text(node).strip()
            level = int(attrs.get("level") or 0) if node_type == "heading" else 0
            block_id = str(attrs.get("blockId") or "")
            matches = node_type == "heading" and (
                block_id == section_id
                or title == section_id
                or title.startswith(f"{section_id} ")
            )
            if not selected and matches:
                heading_level = level
                heading_title = title
                heading_block_id = block_id
                selected.append(node)
                continue
            if selected:
                if node_type == "heading" and level and level <= heading_level:
                    break
                selected.append(node)
        if not selected:
            raise DocumentWorkspaceError("研究范围章节不存在")
        text = "\n".join(_node_text(node).strip() for node in selected if _node_text(node).strip())
        return {
            "section_id": section_id,
            "heading_block_id": heading_block_id,
            "heading_title": heading_title,
            "nodes": selected,
            "text": text,
            "sha256": _payload_sha256(selected),
        }

    @staticmethod
    def _bibliography(content_json: dict[str, Any]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        in_references = False
        for node in list((content_json or {}).get("content") or []):
            node_type = str(node.get("type") or "")
            value = _node_text(node).strip()
            if node_type == "heading" and value == "参考文献":
                in_references = True
                continue
            if not in_references:
                continue
            metadata = _reference_metadata(value)
            if metadata:
                result[metadata["number"]] = metadata
        return result

    @staticmethod
    def _claim_role(value: str) -> str:
        if any(token in value for token in ("缺乏", "不足", "尚未", "尚缺", "局限")):
            return "limitation"
        if any(token in value for token in ("相比", "一方面", "另一方面", "比较")):
            return "comparison"
        if re.search(r"20\d{2}年|近年来|逐步|开始", value):
            return "trend"
        if any(token in value for token in ("是指", "定义为", "核心不是")):
            return "definition"
        return "fact"

    @staticmethod
    def _claim_candidates(section: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for node in section["nodes"]:
            if str(node.get("type") or "") != "paragraph":
                continue
            attrs = node.get("attrs") or {}
            block_id = str(attrs.get("blockId") or "")
            paragraph = _node_text(node).strip()
            for index, sentence in enumerate(re.split(r"(?<=[。！？])", paragraph)):
                claim_text = sentence.strip()
                if len(claim_text) < 10:
                    continue
                candidates.append({
                    "claim_text": claim_text,
                    "block_id": block_id,
                    "sentence_index": index,
                    "citation_numbers": _citation_numbers(claim_text),
                    "rhetorical_role": WritingResearchService._claim_role(claim_text),
                })
        return candidates

    @staticmethod
    def _matrix_for(section: dict[str, Any]) -> dict[str, Any]:
        prefix = str(section["section_id"]).split()[0]
        directions = list(LITERATURE_DIRECTIONS)
        if prefix == "1.3.1":
            directions = directions[:1]
        return {
            "schema": "writing.literature_research_matrix.v1",
            "section_id": section["section_id"],
            "section_title": section["heading_title"],
            "directions": [
                {
                    **direction,
                    "research_question": f"{direction['title']}的研究进展、证据边界与未解决问题是什么？",
                    "date_range": {"from": 2000, "to": _now().year},
                    "source_types": ["local_knowledge", "bibliography"],
                    "minimum_source_count": 3,
                    "required_recent_sources": 1,
                    "inclusion_criteria": ["来源可定位", "内容或元数据可哈希", "与目标章节直接相关"],
                    "exclusion_criteria": ["命令或模板文件", "无来源占位内容", "无法定位原始记录"],
                }
                for direction in directions
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
        gap_type = _classify_gap(payload)
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            requested_revision = int(payload.get("document_revision") or state.document_revision)
            if requested_revision > state.document_revision:
                raise DocumentVersionConflict("主张引用了尚不存在的正文修订")
            claim_text = str(payload.get("claim_text") or "").strip()
            claim_fingerprint = _payload_sha256({"claim_text": " ".join(claim_text.split())})
            supersedes_claim_id = str(payload.get("supersedes_claim_id") or "").strip() or None
            if supersedes_claim_id:
                superseded = session.get(WritingClaim, supersedes_claim_id)
                if not superseded or superseded.project_id != project_id or superseded.document_id != document_id:
                    raise DocumentWorkspaceError("被替代的论文主张不存在")
            row = WritingClaim(
                id=_uuid("claim"),
                project_id=project_id,
                document_id=document_id,
                document_revision=requested_revision,
                section_id=str(payload.get("section_id") or "")[:128],
                block_id=str(payload.get("block_id") or "")[:96],
                claim_text=claim_text,
                claim_type=str(payload.get("claim_type") or "argument")[:32],
                claim_key=str(payload.get("claim_key") or claim_fingerprint)[:160],
                claim_fingerprint=claim_fingerprint,
                rhetorical_role=str(payload.get("rhetorical_role") or "fact")[:24],
                evidence_policy=payload.get("evidence_policy") or {},
                temporal_scope=str(payload.get("temporal_scope") or "")[:80],
                geographic_scope=str(payload.get("geographic_scope") or "global")[:24],
                supersedes_claim_id=supersedes_claim_id,
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
                gap_type=gap_type,
                reason="尚未绑定达到最低等级的不可变证据",
                research_matrix=payload.get("research_matrix") or {},
            )
            session.add_all([row, gap])
            session.commit()
            return self._claim_dict(row)

    def register_retrieval(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        provider = str(payload.get("provider") or "").strip().lower()
        provider_record_id = str(payload.get("provider_record_id") or "").strip()
        title = str(payload.get("title") or "").strip()
        idempotency_key = str(payload.get("idempotency_key") or "").strip()[:96]
        access_status = str(payload.get("access_status") or "metadata_only")
        if not provider or not provider_record_id or not title or not idempotency_key:
            raise DocumentWorkspaceError("RetrievalRef 必须包含来源、记录 ID、题名和幂等键")
        if access_status not in ACCESS_STATUSES:
            raise DocumentWorkspaceError("RetrievalRef 访问状态无效")
        metadata_snapshot = payload.get("metadata_snapshot") or {}
        if not isinstance(metadata_snapshot, dict):
            raise DocumentWorkspaceError("RetrievalRef 元数据快照必须是对象")
        abstract_snapshot = str(payload.get("abstract_snapshot") or "")
        metadata_sha256 = _payload_sha256({
            "metadata": metadata_snapshot,
            "abstract_snapshot": abstract_snapshot,
        })
        declared_sha256 = str(payload.get("metadata_sha256") or "").lower()
        if declared_sha256 and declared_sha256 != metadata_sha256:
            raise DocumentWorkspaceError("RetrievalRef 元数据哈希与快照不一致")
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            base_revision = int(payload.get("base_revision") or 0)
            if base_revision != state.document_revision:
                raise DocumentVersionConflict("RetrievalRef 必须绑定当前正文修订")
            existing = session.execute(select(WritingRetrievalRef).where(
                WritingRetrievalRef.project_id == project_id,
                WritingRetrievalRef.document_id == document_id,
                WritingRetrievalRef.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                result = self._retrieval_dict(existing)
                result["idempotent_replay"] = True
                return result
            run_id = str(payload.get("run_id") or "").strip() or None
            if run_id:
                run = session.get(WritingJarvisRun, run_id)
                if not run or run.project_id != project_id or run.document_id != document_id:
                    raise DocumentWorkspaceError("RetrievalRef 关联的 Jarvis 运行不存在")
            iteration_id = str(payload.get("iteration_id") or "").strip() or None
            if iteration_id:
                iteration = session.get(WritingResearchIteration, iteration_id)
                if not iteration or iteration.project_id != project_id or iteration.document_id != document_id:
                    raise DocumentWorkspaceError("RetrievalRef 关联的研究迭代不存在")
            year = payload.get("year")
            if year is not None and not 1000 <= int(year) <= 2100:
                raise DocumentWorkspaceError("RetrievalRef 年份无效")
            row = WritingRetrievalRef(
                id=_uuid("retrieval"),
                project_id=project_id,
                document_id=document_id,
                document_revision=base_revision,
                run_id=run_id,
                iteration_id=iteration_id,
                provider=provider[:48],
                provider_record_id=provider_record_id[:200],
                query_id=str(payload.get("query_id") or "")[:96],
                query_text=str(payload.get("query_text") or ""),
                rank=max(0, int(payload.get("rank") or 0)),
                retrieval_score=float(payload.get("retrieval_score") or 0),
                title=title,
                authors=payload.get("authors") or [],
                year=int(year) if year is not None else None,
                venue=str(payload.get("venue") or ""),
                doi=str(payload.get("doi") or "")[:300].lower(),
                url=str(payload.get("url") or ""),
                abstract_snapshot=abstract_snapshot,
                metadata_snapshot=metadata_snapshot,
                metadata_sha256=metadata_sha256,
                access_status=access_status,
                idempotency_key=idempotency_key,
                created_by=actor,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                row = session.execute(select(WritingRetrievalRef).where(
                    WritingRetrievalRef.project_id == project_id,
                    WritingRetrievalRef.document_id == document_id,
                    WritingRetrievalRef.provider == provider[:48],
                    WritingRetrievalRef.provider_record_id == provider_record_id[:200],
                    WritingRetrievalRef.metadata_sha256 == metadata_sha256,
                )).scalar_one()
            return self._retrieval_dict(row)

    def list_retrievals(
        self,
        project_id: str,
        document_id: str,
        *,
        screening_status: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            statement = select(WritingRetrievalRef).where(
                WritingRetrievalRef.project_id == project_id,
                WritingRetrievalRef.document_id == document_id,
            )
            if screening_status:
                if screening_status not in SCREENING_STATUSES:
                    raise DocumentWorkspaceError("RetrievalRef 筛选状态无效")
                statement = statement.where(WritingRetrievalRef.screening_status == screening_status)
            rows = session.execute(statement.order_by(
                WritingRetrievalRef.retrieved_at.desc(),
            ).limit(max(1, min(limit, 500)))).scalars().all()
            return [self._retrieval_dict(row) for row in rows]

    def _complete_literature_step(
        self,
        run_id: str,
        step_key: str,
        result_payload: dict[str, Any],
    ) -> None:
        with self.session_factory() as session:
            step = session.execute(select(WritingJarvisStep).where(
                WritingJarvisStep.run_id == run_id,
                WritingJarvisStep.step_key == step_key,
            )).scalar_one()
            step.status = "completed"
            step.attempt_count = max(1, step.attempt_count + 1)
            step.result_payload = result_payload
            step.error = ""
            session.commit()

    def _write_retrieval_snapshot(self, run_id: str, name: str, payload: dict[str, Any]) -> Path:
        snapshot_root = self.evidence_root.parent / "writing_retrieval_snapshots" / run_id
        snapshot_root.mkdir(parents=True, exist_ok=True)
        digest = _payload_sha256(payload)
        target = snapshot_root / f"{name}-{digest}.json"
        if not target.exists():
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, target)
            target.chmod(0o444)
        return target.resolve()

    def _write_candidate_snapshot(
        self,
        run_id: str,
        candidate_sha256: str,
        payload: dict[str, Any],
    ) -> Path:
        snapshot_root = self.evidence_root.parent / "writing_literature_candidates" / run_id
        snapshot_root.mkdir(parents=True, exist_ok=True)
        target = snapshot_root / f"{candidate_sha256}.json"
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        if target.is_file():
            if target.read_bytes() != encoded:
                raise DocumentWorkspaceError("候选快照哈希冲突")
            return target.resolve()
        temporary = snapshot_root / f".{candidate_sha256}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            target.chmod(0o444)
        finally:
            temporary.unlink(missing_ok=True)
        return target.resolve()

    def list_literature_runs(
        self,
        project_id: str,
        document_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.project_id == project_id,
                WritingJarvisRun.document_id == document_id,
                WritingJarvisRun.run_type == "literature_review_optimization",
            ).order_by(WritingJarvisRun.created_at.desc()).limit(max(1, min(limit, 200)))).scalars().all()
            result = []
            for row in rows:
                steps = session.execute(select(WritingJarvisStep).where(
                    WritingJarvisStep.run_id == row.id,
                ).order_by(WritingJarvisStep.updated_at.asc())).scalars().all()
                result.append(self._run_dict(row, steps))
            return result

    def list_research_iterations(
        self,
        project_id: str,
        document_id: str,
        *,
        run_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            statement = select(WritingResearchIteration).where(
                WritingResearchIteration.project_id == project_id,
                WritingResearchIteration.document_id == document_id,
            )
            if run_id:
                statement = statement.where(WritingResearchIteration.run_id == run_id)
            rows = session.execute(statement.order_by(
                WritingResearchIteration.started_at.desc(),
            ).limit(max(1, min(limit, 500)))).scalars().all()
            result = []
            for row in rows:
                evaluation = session.execute(select(WritingResearchEvaluation).where(
                    WritingResearchEvaluation.iteration_id == row.id,
                ).order_by(WritingResearchEvaluation.created_at.desc()).limit(1)).scalar_one_or_none()
                result.append(self._iteration_dict(row, evaluation))
            return result

    def evaluate_literature_candidate(
        self,
        project_id: str,
        document_id: str,
        run_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        operations = list(payload.get("operations") or [])
        idempotency_key = str(payload.get("idempotency_key") or "").strip()[:96]
        if not idempotency_key:
            raise DocumentWorkspaceError("候选修订必须包含幂等键")
        if not operations:
            raise DocumentWorkspaceError("候选修订至少包含一项文本替换")
        if len(operations) > 50:
            raise DocumentWorkspaceError("单轮候选最多包含 50 项文本替换")

        with self.session_factory() as session:
            run = session.get(WritingJarvisRun, run_id)
            if (
                not run
                or run.project_id != project_id
                or run.document_id != document_id
                or run.run_type != "literature_review_optimization"
            ):
                raise DocumentWorkspaceError("文献研究运行不存在")
            if run.status != "completed":
                raise DocumentWorkspaceError("文献研究基线尚未完成")
            state = self._state(session, project_id, document_id)
            base_revision = int(payload.get("base_revision") or 0)
            section_id = str((run.result_payload or {}).get("section_id") or "")
            section = self._section_snapshot(state.content_json or {}, section_id)
            baseline = session.execute(select(WritingResearchIteration).where(
                WritingResearchIteration.run_id == run_id,
                WritingResearchIteration.iteration_no == 0,
            )).scalar_one()
            baseline_evaluation = session.execute(select(WritingResearchEvaluation).where(
                WritingResearchEvaluation.iteration_id == baseline.id,
            ).order_by(WritingResearchEvaluation.created_at.desc()).limit(1)).scalar_one()

            normalized_operations = [
                {
                    "op": str(item.get("op") or ""),
                    "block_id": str(item.get("block_id") or ""),
                    "old_text": str(item.get("old_text") or ""),
                    "new_text": str(item.get("new_text") or ""),
                    "reason": str(item.get("reason") or "")[:1000],
                }
                for item in operations
            ]
            candidate_sha256 = _payload_sha256({
                "run_id": run_id,
                "idempotency_key": idempotency_key,
                "base_revision": base_revision,
                "base_section_sha256": baseline.base_section_sha256,
                "operations": normalized_operations,
            })
            existing = session.execute(select(WritingResearchIteration).where(
                WritingResearchIteration.run_id == run_id,
                WritingResearchIteration.candidate_sha256 == candidate_sha256,
            )).scalar_one_or_none()
            if existing:
                evaluation = session.execute(select(WritingResearchEvaluation).where(
                    WritingResearchEvaluation.iteration_id == existing.id,
                ).order_by(WritingResearchEvaluation.created_at.desc()).limit(1)).scalar_one_or_none()
                result = self._iteration_dict(existing, evaluation)
                result["idempotent_replay"] = True
                if existing.change_set_id:
                    change_set = session.get(WritingChangeSet, existing.change_set_id)
                    result["change_set"] = self._changeset_dict(change_set) if change_set else None
                return result

            section_nodes = copy.deepcopy(section["nodes"])
            section_block_ids = {
                str((node.get("attrs") or {}).get("blockId") or "")
                for node in section_nodes
            }
            scope_ok = True
            exact_match_ok = True
            nonempty_replacements = True
            no_new_citations = True
            no_new_numeric_facts = True
            changed_blocks: set[str] = set()

            def replace_once(node: dict[str, Any], old_text: str, new_text: str) -> int:
                for child in node.get("content") or []:
                    if child.get("type") == "text" and old_text in str(child.get("text") or ""):
                        child["text"] = str(child.get("text") or "").replace(old_text, new_text, 1)
                        return 1
                    if isinstance(child, dict) and replace_once(child, old_text, new_text):
                        return 1
                return 0

            for operation in normalized_operations:
                block_id = operation["block_id"]
                old_text = operation["old_text"]
                new_text = operation["new_text"]
                if operation["op"] != "replace_text" or block_id not in section_block_ids:
                    scope_ok = False
                    continue
                if not old_text or not new_text.strip():
                    nonempty_replacements = False
                    continue
                if not set(_citation_numbers(new_text)).issubset(set(_citation_numbers(old_text))):
                    no_new_citations = False
                old_numbers = set(re.findall(r"(?<!\w)(?:20\d{2}|\d+(?:\.\d+)?)(?!\w)", old_text))
                new_numbers = set(re.findall(r"(?<!\w)(?:20\d{2}|\d+(?:\.\d+)?)(?!\w)", new_text))
                if not new_numbers.issubset(old_numbers):
                    no_new_numeric_facts = False
                target = next(
                    (node for node in section_nodes if str((node.get("attrs") or {}).get("blockId") or "") == block_id),
                    None,
                )
                if not target or replace_once(target, old_text, new_text) != 1:
                    exact_match_ok = False
                    continue
                changed_blocks.add(block_id)

            evidence_ids = list(dict.fromkeys(str(value) for value in payload.get("evidence_ref_ids") or []))
            evidence_rows = session.execute(select(WritingEvidenceRef).where(
                WritingEvidenceRef.id.in_(evidence_ids),
                WritingEvidenceRef.project_id == project_id,
                WritingEvidenceRef.document_id == document_id,
            )).scalars().all() if evidence_ids else []
            evidence_valid = len(evidence_rows) == len(evidence_ids)
            if evidence_valid:
                try:
                    for evidence in evidence_rows:
                        self._verify_evidence_ref(evidence)
                except DocumentWorkspaceError:
                    evidence_valid = False

            scope_unchanged = section["sha256"] == baseline.base_section_sha256
            hard_gates = {
                "revision_unchanged": base_revision == state.document_revision == baseline.base_revision,
                "section_sha256_unchanged": scope_unchanged,
                "scope_confined_to_section": scope_ok,
                "exact_source_text_match": exact_match_ok,
                "nonempty_replacements": nonempty_replacements,
                "no_new_citations": no_new_citations,
                "no_new_numeric_facts": no_new_numeric_facts,
                "evidence_snapshots_verified": evidence_valid,
                "candidate_changes_content": bool(changed_blocks),
                "body_write_operations": 0,
            }
            claims = session.execute(select(WritingClaim).where(
                WritingClaim.project_id == project_id,
                WritingClaim.document_id == document_id,
                WritingClaim.section_id == section_id,
                WritingClaim.status == "active",
            )).scalars().all()
            targeted_claims = [
                claim for claim in claims
                if any(
                    operation["block_id"] == claim.block_id
                    and operation["old_text"] in claim.claim_text
                    for operation in normalized_operations
                )
            ]
            targeted_claim_ids = [claim.id for claim in targeted_claims]
            targeted_gaps = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.claim_id.in_(targeted_claim_ids),
            )).scalars().all() if targeted_claim_ids else []
            required_evidence_categories: set[str] = set()
            for gap in targeted_gaps:
                required_evidence_categories.update(_required_evidence_categories(gap.gap_type))
            required_experiment_level = max(
                (EVIDENCE_LEVELS[claim.minimum_evidence_level] for claim in targeted_claims),
                default=EVIDENCE_LEVELS["diagnostic"],
            )
            selected_evidence_categories = {
                _evidence_category(row.evidence_kind)
                for row in evidence_rows
                if row.support_role in {"supports", "method_basis"}
                and row.directness != "metadata_only"
                and row.perspective_scope in {"public", "project", "paper", "aggregate"}
                and (
                    _evidence_category(row.evidence_kind) != "experiment"
                    or EVIDENCE_LEVELS[row.evidence_level] >= required_experiment_level
                )
            } - {""}
            temporal_qualifications = sum(
                bool(re.search(r"20\d{2}年|近年来|最新", operation["old_text"]))
                and not bool(re.search(r"20\d{2}年|近年来|最新", operation["new_text"]))
                for operation in normalized_operations
            )
            conservative_qualification = bool(temporal_qualifications) and (
                no_new_citations and no_new_numeric_facts
            )
            evidence_policy_satisfied = conservative_qualification or (
                required_evidence_categories.issubset(selected_evidence_categories)
            )
            hard_gates["evidence_policy_satisfied"] = evidence_policy_satisfied
            all_gates_pass = all(
                value is True or (key == "body_write_operations" and value == 0)
                for key, value in hard_gates.items()
            )
            unsupported_targeted = sum(claim.evidence_status != "sufficient" for claim in targeted_claims)
            improvement = min(10.0, unsupported_targeted * 2.0 + temporal_qualifications * 3.0)
            candidate_score = round(min(100.0, baseline_evaluation.total_score + improvement), 2)
            baseline_delta = round(candidate_score - baseline_evaluation.total_score, 2)
            minimum_improvement = max(0.0, float(payload.get("minimum_improvement") or 2.0))
            kept = all_gates_pass and baseline_delta >= minimum_improvement
            dimensions = {
                "baseline_score": baseline_evaluation.total_score,
                "unsupported_claims_targeted": float(unsupported_targeted),
                "temporal_specificity_reduced": float(temporal_qualifications),
                "scope_integrity": 100.0 if scope_ok else 0.0,
                "citation_integrity": 100.0 if no_new_citations else 0.0,
                "numeric_fact_integrity": 100.0 if no_new_numeric_facts else 0.0,
            }
            candidate_payload = {
                "schema": "writing.literature_candidate.v1",
                "run_id": run_id,
                "section_id": section_id,
                "base_revision": base_revision,
                "base_section_sha256": baseline.base_section_sha256,
                "candidate_section_sha256": _payload_sha256(section_nodes),
                "operations": normalized_operations,
                "evidence_ref_ids": evidence_ids,
                "required_evidence_categories": sorted(required_evidence_categories),
                "selected_evidence_categories": sorted(selected_evidence_categories),
                "evidence_policy_mode": (
                    "conservative_qualification" if conservative_qualification else "evidence_bound"
                ),
                "candidate_section_nodes": section_nodes,
            }
            candidate_path = self._write_candidate_snapshot(run_id, candidate_sha256, candidate_payload)
            iteration_no = max(
                (value for (value,) in session.execute(select(WritingResearchIteration.iteration_no).where(
                    WritingResearchIteration.run_id == run_id,
                )).all()),
                default=0,
            ) + 1
            iteration = WritingResearchIteration(
                id=_uuid("iteration"),
                project_id=project_id,
                document_id=document_id,
                run_id=run_id,
                iteration_no=iteration_no,
                base_revision=base_revision,
                base_section_sha256=baseline.base_section_sha256,
                candidate_sha256=candidate_sha256,
                candidate_payload=candidate_payload,
                candidate_artifact_path=str(candidate_path),
                status="review_required" if kept else "discarded",
                parent_iteration_id=baseline.id,
                finished_at=_now(),
            )
            session.add(iteration)
            session.flush()
            evaluation = WritingResearchEvaluation(
                id=_uuid("evaluation"),
                iteration_id=iteration.id,
                evaluator_version=str(payload.get("evaluator_version") or "literature-candidate-v1")[:48],
                hard_gates=hard_gates,
                dimension_scores=dimensions,
                total_score=candidate_score,
                baseline_delta=baseline_delta,
                decision="kept" if kept else "discarded",
                reasons=(
                    ["候选通过硬门禁且达到最低提升阈值，已生成高风险待审 ChangeSet"]
                    if kept else
                    ["候选未通过全部硬门禁或未达到最低提升阈值，不生成可审批修改"]
                ),
                input_sha256=_payload_sha256({
                    "candidate_sha256": candidate_sha256,
                    "hard_gates": hard_gates,
                    "dimension_scores": dimensions,
                }),
            )
            session.add(evaluation)
            change_set = None
            if kept:
                change_set = WritingChangeSet(
                    id=_uuid("changeset"),
                    project_id=project_id,
                    document_id=document_id,
                    base_revision=base_revision,
                    operations=normalized_operations,
                    evidence_ref_ids=evidence_ids,
                    risk_level="high",
                    approval_policy="research_candidate",
                    status="review_required",
                    idempotency_key=f"literature-candidate:{candidate_sha256}"[:96],
                    summary=str(payload.get("summary") or f"第 {section_id} 节研究现状候选修订")[:4000],
                )
                session.add(change_set)
                session.flush()
                iteration.change_set_id = change_set.id
            session.commit()
            result = self._iteration_dict(iteration, evaluation)
            result["change_set"] = self._changeset_dict(change_set) if change_set else None
            result["body_changes"] = 0
            return result

    def start_literature_run(
        self,
        project_id: str,
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        scope_section_ids = list(payload.get("scope_section_ids") or [])
        section_id = str((scope_section_ids[0] if scope_section_ids else "") or payload.get("section_id") or "").strip()
        idempotency_key = str(payload.get("idempotency_key") or "").strip()[:96]
        source_whitelist = [
            str(value).strip().lower()
            for value in (payload.get("source_whitelist") or ["local_knowledge", "bibliography"])
            if str(value).strip()
        ]
        invalid_sources = sorted(set(source_whitelist) - LITERATURE_SOURCES)
        if not section_id or not idempotency_key:
            raise DocumentWorkspaceError("文献研究运行必须包含章节范围和幂等键")
        if invalid_sources:
            raise DocumentWorkspaceError(f"文献研究来源不在白名单：{', '.join(invalid_sources)}")
        external_request_budget = max(0, min(int(payload.get("external_request_budget") or 0), 10))

        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            base_revision = int(payload.get("base_revision") or 0)
            if base_revision != state.document_revision:
                raise DocumentVersionConflict("文献研究运行必须绑定当前正文修订")
            existing = session.execute(select(WritingJarvisRun).where(
                WritingJarvisRun.project_id == project_id,
                WritingJarvisRun.document_id == document_id,
                WritingJarvisRun.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                steps = session.execute(select(WritingJarvisStep).where(
                    WritingJarvisStep.run_id == existing.id,
                ).order_by(WritingJarvisStep.updated_at.asc())).scalars().all()
                result = self._run_dict(existing, steps)
                result["idempotent_replay"] = True
                return result
            section = self._section_snapshot(state.content_json or {}, section_id)
            bibliography = self._bibliography(state.content_json or {})
            matrix = json.loads(json.dumps(
                payload.get("research_matrix") or self._matrix_for(section),
                ensure_ascii=False,
            ))
            for direction in matrix.get("directions") or []:
                direction["source_types"] = source_whitelist
            run = WritingJarvisRun(
                id=_uuid("jrun"),
                project_id=project_id,
                document_id=document_id,
                run_type="literature_review_optimization",
                status="running",
                idempotency_key=idempotency_key,
                input_payload={
                    "base_revision": base_revision,
                    "scope_section_ids": [section_id],
                    "evaluator_version": str(payload.get("evaluator_version") or "literature-baseline-v1"),
                    "source_whitelist": source_whitelist,
                    "external_request_budget": external_request_budget,
                    "max_results_per_query": max(1, min(int(payload.get("max_results_per_query") or 12), 50)),
                },
                requested_by=actor,
                started_at=_now(),
                recovery_cursor={"next_step": "freeze_baseline"},
            )
            session.add(run)
            session.flush()
            iteration = WritingResearchIteration(
                id=_uuid("iteration"),
                project_id=project_id,
                document_id=document_id,
                run_id=run.id,
                iteration_no=0,
                base_revision=base_revision,
                base_section_sha256=section["sha256"],
                status="baseline",
            )
            scope = WritingResearchRunScope(
                id=_uuid("scope"),
                run_id=run.id,
                section_id=section_id,
                scope_role="target",
            )
            steps = []
            for index, step_key in enumerate(LITERATURE_RUN_STEPS):
                steps.append(WritingJarvisStep(
                    id=_uuid("jstep"),
                    run_id=run.id,
                    step_key=step_key,
                    status="running" if index == 0 else "pending",
                    depends_on=[] if index == 0 else [LITERATURE_RUN_STEPS[index - 1]],
                    input_payload={"section_id": section_id} if index == 0 else {},
                ))
            session.add_all([iteration, scope, *steps])
            session.commit()
            run_id = run.id
            iteration_id = iteration.id
            baseline_document_sha = state.content_sha256
            baseline_source_sha = state.source_markdown_sha256

        try:
            self._complete_literature_step(run_id, "freeze_baseline", {
                "document_revision": base_revision,
                "document_sha256": baseline_document_sha,
                "source_markdown_sha256": baseline_source_sha,
                "section_sha256": section["sha256"],
                "heading_block_id": section["heading_block_id"],
            })

            claims: list[dict[str, Any]] = []
            claims_by_reference: dict[int, list[str]] = {}
            for candidate in self._claim_candidates(section):
                claim_key = (
                    f"{section_id}:{candidate['block_id']}:{candidate['sentence_index']}:"
                    f"{_payload_sha256(candidate['claim_text'])[:16]}"
                )
                with self.session_factory() as session:
                    existing_claim = session.execute(select(WritingClaim).where(
                        WritingClaim.project_id == project_id,
                        WritingClaim.document_id == document_id,
                        WritingClaim.claim_key == claim_key,
                    )).scalar_one_or_none()
                claim = self._claim_dict(existing_claim) if existing_claim else self.create_claim(
                    project_id,
                    document_id,
                    {
                        "claim_text": candidate["claim_text"],
                        "claim_type": "argument",
                        "claim_key": claim_key,
                        "rhetorical_role": candidate["rhetorical_role"],
                        "minimum_evidence_level": "diagnostic",
                        "document_revision": base_revision,
                        "section_id": section_id,
                        "block_id": candidate["block_id"],
                        "research_matrix": matrix,
                    },
                    actor,
                )
                claims.append(claim)
                for number in candidate["citation_numbers"]:
                    claims_by_reference.setdefault(number, []).append(claim["id"])
            self._complete_literature_step(run_id, "extract_claims", {
                "claim_count": len(claims),
                "cited_reference_count": len(claims_by_reference),
            })
            self._complete_literature_step(run_id, "build_matrix", {
                "matrix_sha256": _payload_sha256(matrix),
                "direction_count": len(matrix.get("directions") or []),
                "research_matrix": matrix,
            })

            retrievals: list[dict[str, Any]] = []
            reference_evidence: dict[int, dict[str, Any]] = {}
            bibliography_numbers = sorted(claims_by_reference) if "bibliography" in source_whitelist else []
            for number in bibliography_numbers:
                reference = bibliography.get(number)
                if not reference:
                    continue
                retrieval = self.register_retrieval(project_id, document_id, {
                    "base_revision": base_revision,
                    "idempotency_key": f"{run_id}:bibliography:{number}",
                    "run_id": run_id,
                    "iteration_id": iteration_id,
                    "provider": "bibliography",
                    "provider_record_id": f"reference-{number}",
                    "query_id": f"{section_id}:citations",
                    "query_text": section["heading_title"],
                    "rank": number,
                    "retrieval_score": 1.0,
                    "title": reference["title"],
                    "year": reference["year"],
                    "doi": reference["doi"],
                    "abstract_snapshot": reference["entry"],
                    "metadata_snapshot": {
                        "reference_number": number,
                        "entry": reference["entry"],
                        "source_document_revision": base_revision,
                        "source_document_sha256": baseline_document_sha,
                    },
                    "access_status": "metadata_only",
                }, actor)
                retrievals.append(retrieval)

            local_items: list[dict[str, Any]] = []
            external_items: list[dict[str, Any]] = []
            health: dict[str, Any] = {"local_knowledge": [], "external": {}}
            remaining_external_budget = external_request_budget
            for direction in matrix.get("directions") or []:
                query = " ".join([
                    *(direction.get("keywords_zh") or []),
                    *(direction.get("keywords_en") or []),
                ])
                if "local_knowledge" in source_whitelist:
                    pack = self.context_retriever(
                        user_id=actor,
                        query=query,
                        project_id=project_id,
                        purpose="literature_review",
                        limit=int(payload.get("max_results_per_query") or 12),
                        persist=True,
                    )
                    health["local_knowledge"].append(pack.get("retrieval_health") or {})
                    for item in pack.get("items") or []:
                        if item.get("item_type") != "knowledge":
                            continue
                        metadata = item.get("metadata") or {}
                        if isinstance(metadata, str):
                            try:
                                metadata = json.loads(metadata)
                            except json.JSONDecodeError:
                                metadata = {}
                        source_ref = str(item.get("source_ref") or "")
                        if not metadata.get("path") and source_ref.startswith("knowledge:"):
                            relative_path = source_ref.removeprefix("knowledge:")
                            knowledge_root = Path(os.getenv(
                                "WRITING_KNOWLEDGE_ROOT",
                                str(Path.home() / "工作桌面" / "knowledge"),
                            )).expanduser()
                            candidate_path = (knowledge_root / relative_path).resolve()
                            if candidate_path.is_file():
                                metadata = {**metadata, "path": str(candidate_path)}
                        retrieval = self.register_retrieval(project_id, document_id, {
                            "base_revision": base_revision,
                            "idempotency_key": f"{run_id}:local:{_payload_sha256(item.get('source_ref') or item)[:32]}",
                            "run_id": run_id,
                            "iteration_id": iteration_id,
                            "provider": "local_knowledge",
                            "provider_record_id": str(item.get("source_ref") or item.get("title"))[:200],
                            "query_id": str(direction.get("key") or "local")[:96],
                            "query_text": query,
                            "rank": int(item.get("rank_index") or 0),
                            "retrieval_score": float(item.get("score") or 0),
                            "title": str(item.get("title") or item.get("source_ref")),
                            "abstract_snapshot": str(item.get("content") or ""),
                            "metadata_snapshot": {
                                **metadata,
                                "source_id": item.get("source_id"),
                                "source_ref": item.get("source_ref"),
                                "confidence": item.get("confidence"),
                            },
                            "access_status": "fulltext" if metadata.get("path") else "abstract",
                        }, actor)
                        retrievals.append(retrieval)
                        local_items.append({"retrieval": retrieval, "item": item})

                external_providers = [
                    provider for provider in source_whitelist
                    if provider in {"semantic_scholar", "crossref"}
                ]
                if external_providers and remaining_external_budget > 0:
                    external = self.external_retriever(
                        providers=external_providers,
                        query=query,
                        limit=int(payload.get("max_results_per_query") or 12),
                        year_from=int((direction.get("date_range") or {}).get("from") or 2000),
                        year_to=int((direction.get("date_range") or {}).get("to") or _now().year),
                        request_budget=remaining_external_budget,
                    )
                    remaining_external_budget = max(
                        0,
                        remaining_external_budget - int(external.get("requests_used") or 0),
                    )
                    health["external"][str(direction.get("key") or "external")] = external.get("health") or {}
                    for candidate in external.get("candidates") or []:
                        retrieval = self.register_retrieval(project_id, document_id, {
                            "base_revision": base_revision,
                            "idempotency_key": (
                                f"{run_id}:external:{candidate['provider']}:"
                                f"{_payload_sha256(candidate['provider_record_id'])[:24]}"
                            ),
                            "run_id": run_id,
                            "iteration_id": iteration_id,
                            "provider": candidate["provider"],
                            "provider_record_id": candidate["provider_record_id"],
                            "query_id": str(direction.get("key") or "external")[:96],
                            "query_text": query,
                            "rank": int(candidate.get("rank") or 0),
                            "retrieval_score": float(candidate.get("retrieval_score") or 0),
                            "title": candidate["title"],
                            "authors": candidate.get("authors") or [],
                            "year": candidate.get("year"),
                            "venue": candidate.get("venue") or "",
                            "doi": candidate.get("doi") or "",
                            "url": candidate.get("url") or "",
                            "abstract_snapshot": candidate.get("abstract_snapshot") or "",
                            "metadata_snapshot": {
                                **(candidate.get("metadata_snapshot") or {}),
                                "canonical_key": candidate.get("canonical_key") or "",
                                "screening_policy_version": EXTERNAL_SCREENING_POLICY_VERSION,
                            },
                            "access_status": candidate.get("access_status") or "metadata_only",
                        }, actor)
                        retrievals.append(retrieval)
                        external_items.append({"retrieval": retrieval, "candidate": candidate})
            self._complete_literature_step(run_id, "retrieve_local", {
                "retrieval_count": len(retrievals) - len(external_items),
                "bibliography_count": len(retrievals) - len(local_items) - len(external_items),
                "local_knowledge_count": len(local_items),
                "retrieval_ref_ids": [
                    item["id"] for item in retrievals
                    if item["provider"] in {"bibliography", "local_knowledge"}
                ],
                "source_health": health["local_knowledge"],
            })
            self._complete_literature_step(run_id, "retrieve_external", {
                "external_count": len(external_items),
                "retrieval_ref_ids": [item["retrieval"]["id"] for item in external_items],
                "source_health": health["external"],
                "request_budget": external_request_budget,
                "requests_remaining": remaining_external_budget,
            })
            duplicate_targets: dict[str, str] = {}
            external_canonical: dict[str, str] = {}
            for retrieval in retrievals:
                if retrieval["provider"] not in {"semantic_scholar", "crossref"}:
                    continue
                canonical_key = str((retrieval.get("metadata_snapshot") or {}).get("canonical_key") or "")
                if not canonical_key:
                    continue
                canonical_id = external_canonical.get(canonical_key)
                if canonical_id and canonical_id != retrieval["id"]:
                    duplicate_targets[retrieval["id"]] = canonical_id
                else:
                    external_canonical[canonical_key] = retrieval["id"]
            self._complete_literature_step(run_id, "deduplicate", {
                "canonical_count": len({item["id"] for item in retrievals}) - len(duplicate_targets),
                "duplicate_count": len(duplicate_targets),
            })

            included = excluded = uncertain = duplicate = 0
            promoted: list[dict[str, Any]] = []
            for retrieval in retrievals:
                canonical_ref_id = duplicate_targets.get(retrieval["id"])
                if canonical_ref_id:
                    decision = "duplicate"
                    reason = "DOI 或规范化题名与已登记外部来源重复"
                elif retrieval["provider"] == "bibliography":
                    decision = "include"
                    reason = "当前正文引用的书目记录；仅作为元数据证据"
                elif retrieval["provider"] == "local_knowledge":
                    metadata = retrieval["metadata_snapshot"]
                    source_path = Path(str(metadata.get("path") or "")).expanduser()
                    content = retrieval["abstract_snapshot"].strip()
                    lowered = f"{retrieval['title']} {source_path}".lower()
                    placeholder = any(token in content for token in (
                        "One-line conclusion -",
                        "Confidence: low/medium/high",
                        "Read the `",
                    ))
                    command_source = "/commands/" in str(source_path) or "commands/" in lowered
                    if placeholder or command_source:
                        decision = "exclude"
                        reason = "命令或未填充模板不能作为论文证据"
                    elif not source_path.is_absolute() or not source_path.is_file():
                        decision = "uncertain"
                        reason = "本地来源文件无法定位，不能生成不可变快照"
                    elif len(content) < 60:
                        decision = "uncertain"
                        reason = "本地内容过短，需要人工核验"
                    else:
                        decision = "include"
                        reason = "本地来源可定位且内容达到最低完整性门槛"
                else:
                    if not retrieval["title"] or not retrieval["provider_record_id"]:
                        decision = "exclude"
                        reason = "外部元数据缺少稳定记录标识或题名"
                    elif retrieval.get("year") is None:
                        decision = "uncertain"
                        reason = "外部元数据缺少年份，需要人工核验"
                    else:
                        topic_match, topic_reason = _external_topic_match(retrieval)
                        if topic_match:
                            decision = "include"
                            reason = (
                                "外部学术元数据具有稳定标识、题名和年份；"
                                f"{topic_reason}；仅按可用元数据升级"
                            )
                        else:
                            decision = "uncertain"
                            reason = f"{topic_reason}，需要人工核验"
                screened = self.decide_retrieval(project_id, document_id, retrieval["id"], {
                    "expected_revision": base_revision,
                    "decision": decision,
                    "reason": reason,
                    "canonical_ref_id": canonical_ref_id or "",
                    "actor_type": "agent",
                    "idempotency_key": f"{run_id}:screen:{retrieval['id']}",
                }, actor)
                if decision == "include":
                    included += 1
                    if retrieval["provider"] == "bibliography":
                        number = int(retrieval["metadata_snapshot"]["reference_number"])
                        snapshot_path = self._write_retrieval_snapshot(
                            run_id,
                            f"reference-{number}",
                            retrieval["metadata_snapshot"],
                        )
                        source_quality = "secondary"
                        locator = {"reference_number": number}
                        license_or_access = "local_project_access"
                        directness = "metadata_only"
                    elif retrieval["provider"] == "local_knowledge":
                        snapshot_path = Path(str(retrieval["metadata_snapshot"].get("path") or "")).resolve()
                        source_quality = "internal"
                        locator = {"path": str(snapshot_path)}
                        license_or_access = "local_project_access"
                        directness = "direct"
                    else:
                        snapshot_path = self._write_retrieval_snapshot(
                            run_id,
                            f"{retrieval['provider']}-{_payload_sha256(retrieval['provider_record_id'])[:16]}",
                            {
                                "provider": retrieval["provider"],
                                "provider_record_id": retrieval["provider_record_id"],
                                "title": retrieval["title"],
                                "authors": retrieval["authors"],
                                "year": retrieval["year"],
                                "venue": retrieval["venue"],
                                "doi": retrieval["doi"],
                                "url": retrieval["url"],
                                "abstract_snapshot": retrieval["abstract_snapshot"],
                                "metadata_snapshot": retrieval["metadata_snapshot"],
                            },
                        )
                        source_quality = "secondary"
                        locator = {"provider_record_id": retrieval["provider_record_id"]}
                        license_or_access = "provider_metadata_api"
                        directness = (
                            "indirect" if retrieval["access_status"] == "abstract" else "metadata_only"
                        )
                    evidence = self.promote_retrieval(project_id, document_id, retrieval["id"], {
                        "expected_revision": base_revision,
                        "artifact_path": str(snapshot_path),
                        "artifact_sha256": _file_sha256(snapshot_path),
                        "evidence_level": "diagnostic",
                        "evidence_kind": "literature",
                        "source_quality": source_quality,
                        "support_role": "contextualizes",
                        "directness": directness,
                        "license_or_access": license_or_access,
                        "locator": locator,
                        "allowed_claim_scope": f"section:{section_id}",
                        "provenance": {"run_id": run_id, "screening_status": screened["screening_status"]},
                    }, actor)
                    promoted.append(evidence)
                    if retrieval["provider"] == "bibliography":
                        reference_evidence[int(retrieval["metadata_snapshot"]["reference_number"])] = evidence
                elif decision == "exclude":
                    excluded += 1
                elif decision == "duplicate":
                    duplicate += 1
                else:
                    uncertain += 1
            self._complete_literature_step(run_id, "screen", {
                "included": included,
                "excluded": excluded,
                "uncertain": uncertain,
                "duplicate": duplicate,
            })
            self._complete_literature_step(run_id, "snapshot_sources", {
                "verified_snapshot_count": len(promoted),
            })
            self._complete_literature_step(run_id, "promote_evidence", {
                "evidence_ref_ids": [item["id"] for item in promoted],
            })

            binding_count = 0
            for number, claim_ids in claims_by_reference.items():
                evidence = reference_evidence.get(number)
                if not evidence:
                    continue
                for claim_id in claim_ids:
                    self.bind_evidence(project_id, document_id, {
                        "claim_id": claim_id,
                        "evidence_ref_id": evidence["id"],
                        "support_scope": f"section:{section_id}",
                    }, actor)
                    binding_count += 1
            self._complete_literature_step(run_id, "bind_claims", {
                "binding_count": binding_count,
                "unbound_claim_count": sum(
                    1 for claim in claims if not any(
                        claim["id"] in ids and number in reference_evidence
                        for number, ids in claims_by_reference.items()
                    )
                ),
            })

            with self.session_factory() as session:
                current_state = self._state(session, project_id, document_id)
                current_section = self._section_snapshot(current_state.content_json or {}, section_id)
                current_claims = session.execute(select(WritingClaim).where(
                    WritingClaim.project_id == project_id,
                    WritingClaim.document_id == document_id,
                    WritingClaim.section_id == section_id,
                    WritingClaim.status == "active",
                )).scalars().all()
                sufficient_claims = sum(1 for claim in current_claims if claim.evidence_status == "sufficient")
                hard_gates = {
                    "revision_unchanged": current_state.document_revision == base_revision,
                    "document_sha256_unchanged": current_state.content_sha256 == baseline_document_sha,
                    "source_markdown_sha256_unchanged": current_state.source_markdown_sha256 == baseline_source_sha,
                    "section_sha256_unchanged": current_section["sha256"] == section["sha256"],
                    "all_evidence_has_verified_snapshot": all(
                        Path(item["artifact_path"]).is_file()
                        and _file_sha256(Path(item["artifact_path"])) == item["artifact_sha256"]
                        for item in promoted
                    ),
                    "body_write_operations": 0,
                }
                claim_coverage = round(100 * sufficient_claims / max(1, len(current_claims)), 2)
                dimensions = {
                    "claim_traceability": claim_coverage,
                    "source_snapshot_integrity": 100.0 if promoted else 0.0,
                    "local_source_selectivity": round(100 * included / max(1, len(retrievals)), 2),
                    "recent_source_presence": 100.0 if any(
                        (item.get("year") or 0) >= _now().year - 3 for item in retrievals
                    ) else 0.0,
                    "fulltext_local_coverage": round(
                        100 * sum(1 for item in promoted if item["directness"] != "metadata_only") / max(1, len(promoted)),
                        2,
                    ),
                }
                total_score = round(sum(dimensions.values()) / len(dimensions), 2)
                evaluation_input = {
                    "hard_gates": hard_gates,
                    "dimension_scores": dimensions,
                    "claim_ids": [claim.id for claim in current_claims],
                    "evidence_ids": [item["id"] for item in promoted],
                }
                evaluation = WritingResearchEvaluation(
                    id=_uuid("evaluation"),
                    iteration_id=iteration_id,
                    evaluator_version=str(payload.get("evaluator_version") or "literature-baseline-v1")[:48],
                    hard_gates=hard_gates,
                    dimension_scores=dimensions,
                    total_score=total_score,
                    baseline_delta=0.0,
                    decision="baseline",
                    reasons=[
                        "本阶段仅建立审计基线，不生成正文候选",
                        "metadata_only 证据只证明书目记录存在，不能支持效果或结论",
                    ],
                    input_sha256=_payload_sha256(evaluation_input),
                )
                evaluation_id = evaluation.id
                session.add(evaluation)
                session.commit()
            self._complete_literature_step(run_id, "score_baseline", {
                "evaluation_id": evaluation_id,
                "total_score": total_score,
                "hard_gates": hard_gates,
            })

            with self.session_factory() as session:
                row = session.get(WritingJarvisRun, run_id)
                iteration = session.get(WritingResearchIteration, iteration_id)
                row.status = "completed"
                row.finished_at = _now()
                row.recovery_cursor = {"next_step": "audit_complete"}
                row.result_payload = {
                    "section_id": section_id,
                    "section_sha256": section["sha256"],
                    "research_matrix": matrix,
                    "claim_count": len(claims),
                    "retrieval_count": len(retrievals),
                    "retrieval_ref_ids": [item["id"] for item in retrievals],
                    "evidence_count": len(promoted),
                    "evidence_ref_ids": [item["id"] for item in promoted],
                    "binding_count": binding_count,
                    "evaluation_id": evaluation_id,
                    "baseline_score": total_score,
                    "body_changes": 0,
                    "audit_only": True,
                }
                iteration.finished_at = _now()
                session.commit()
                steps = session.execute(select(WritingJarvisStep).where(
                    WritingJarvisStep.run_id == run_id,
                ).order_by(WritingJarvisStep.updated_at.asc())).scalars().all()
                return self._run_dict(row, steps)
        except Exception as exc:
            with self.session_factory() as session:
                row = session.get(WritingJarvisRun, run_id)
                if row:
                    row.status = "failed"
                    row.error = str(exc)[:4000]
                    row.finished_at = _now()
                    session.commit()
            raise

    def decide_retrieval(
        self,
        project_id: str,
        document_id: str,
        retrieval_ref_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        decision = str(payload.get("decision") or "")
        if decision not in SCREENING_STATUSES - {"pending"}:
            raise DocumentWorkspaceError("筛选决定必须为 include、exclude、uncertain 或 duplicate")
        idempotency_key = str(payload.get("idempotency_key") or "").strip()[:96]
        if not idempotency_key:
            raise DocumentWorkspaceError("筛选决定缺少幂等键")
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            if int(payload.get("expected_revision") or 0) != state.document_revision:
                raise DocumentVersionConflict("筛选决定必须绑定当前正文修订")
            row = session.get(WritingRetrievalRef, retrieval_ref_id)
            if not row or row.project_id != project_id or row.document_id != document_id:
                raise DocumentWorkspaceError("RetrievalRef 不存在")
            existing = session.execute(select(WritingScreeningDecision).where(
                WritingScreeningDecision.retrieval_ref_id == retrieval_ref_id,
                WritingScreeningDecision.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                result = self._retrieval_dict(row)
                result["idempotent_replay"] = True
                return result
            canonical_ref_id = str(payload.get("canonical_ref_id") or "").strip() or None
            if decision == "duplicate":
                canonical = session.get(WritingRetrievalRef, canonical_ref_id) if canonical_ref_id else None
                if (
                    not canonical
                    or canonical.id == row.id
                    or canonical.project_id != project_id
                    or canonical.document_id != document_id
                ):
                    raise DocumentWorkspaceError("重复来源必须指向同一文档中的规范 RetrievalRef")
            else:
                canonical_ref_id = None
            reason = str(payload.get("reason") or "")[:4000]
            decision_row = WritingScreeningDecision(
                id=_uuid("screening"),
                retrieval_ref_id=row.id,
                decision=decision,
                reason=reason,
                decided_by=actor,
                actor_type=str(payload.get("actor_type") or "human")[:16],
                idempotency_key=idempotency_key,
            )
            row.screening_status = decision
            row.screening_reason = reason
            row.canonical_ref_id = canonical_ref_id
            session.add(decision_row)
            session.commit()
            return self._retrieval_dict(row)

    def promote_retrieval(
        self,
        project_id: str,
        document_id: str,
        retrieval_ref_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._require_mutation_backend()
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            if int(payload.get("expected_revision") or 0) != state.document_revision:
                raise DocumentVersionConflict("证据升级必须绑定当前正文修订")
            retrieval = session.get(WritingRetrievalRef, retrieval_ref_id)
            if not retrieval or retrieval.project_id != project_id or retrieval.document_id != document_id:
                raise DocumentWorkspaceError("RetrievalRef 不存在")
            if retrieval.screening_status != "include":
                raise DocumentWorkspaceError("只有已纳入的 RetrievalRef 可以升级为 EvidenceRef")
            if retrieval.access_status == "unavailable":
                raise DocumentWorkspaceError("不可访问的 RetrievalRef 不能升级为 EvidenceRef")
            retrieval_data = self._retrieval_dict(retrieval)
        directness = (
            "metadata_only"
            if retrieval_data["access_status"] == "metadata_only"
            else str(payload.get("directness") or "direct")
        )
        return self.register_evidence(project_id, document_id, {
            **payload,
            "source_system": retrieval_data["provider"],
            "source_record_id": retrieval_data["provider_record_id"],
            "retrieval_ref_id": retrieval_ref_id,
            "evidence_kind": payload.get("evidence_kind") or "literature",
            "directness": directness,
            "provenance": {
                **(payload.get("provenance") or {}),
                "retrieval_metadata_sha256": retrieval_data["metadata_sha256"],
                "retrieved_at": retrieval_data["retrieved_at"],
            },
        }, actor)

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
        evidence_kind = str(payload.get("evidence_kind") or "simulation")
        source_quality = str(payload.get("source_quality") or "internal")
        support_role = str(payload.get("support_role") or "supports")
        directness = str(payload.get("directness") or "direct")
        if evidence_kind not in EVIDENCE_KINDS:
            raise DocumentWorkspaceError("EvidenceRef 证据类型无效")
        if source_quality not in SOURCE_QUALITIES:
            raise DocumentWorkspaceError("EvidenceRef 来源质量无效")
        if support_role not in SUPPORT_ROLES:
            raise DocumentWorkspaceError("EvidenceRef 支持角色无效")
        if directness not in DIRECTNESS_LEVELS:
            raise DocumentWorkspaceError("EvidenceRef 直接性无效")
        with self.session_factory() as session:
            retrieval_ref_id = str(payload.get("retrieval_ref_id") or "").strip() or None
            if retrieval_ref_id:
                retrieval = session.get(WritingRetrievalRef, retrieval_ref_id)
                if not retrieval or retrieval.project_id != project_id or retrieval.document_id != document_id:
                    raise DocumentWorkspaceError("EvidenceRef 关联的 RetrievalRef 不存在")
                if retrieval.screening_status != "include":
                    raise DocumentWorkspaceError("EvidenceRef 只能关联已纳入的 RetrievalRef")
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
                evidence_kind=evidence_kind,
                source_quality=source_quality,
                support_role=support_role,
                directness=directness,
                published_at=_optional_datetime(payload.get("published_at")),
                acquired_at=_now(),
                license_or_access=str(payload.get("license_or_access") or ""),
                retrieval_ref_id=retrieval_ref_id,
                locator=payload.get("locator") or {},
                excerpt_sha256=str(payload.get("excerpt_sha256") or "").lower(),
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
            bound_evidence = session.execute(select(WritingEvidenceRef).join(
                WritingEvidenceBinding,
                WritingEvidenceBinding.evidence_ref_id == WritingEvidenceRef.id,
            ).where(
                WritingEvidenceBinding.claim_id == claim.id,
                WritingEvidenceBinding.status == "active",
                WritingEvidenceRef.support_role.in_(("supports", "method_basis")),
                WritingEvidenceRef.directness != "metadata_only",
            )).scalars().all()
            gaps = session.execute(select(WritingEvidenceGap).where(
                WritingEvidenceGap.claim_id == claim.id,
                WritingEvidenceGap.status != "resolved",
            ).with_for_update()).scalars().all()
            required_categories: set[str] = set()
            for gap in gaps:
                required_categories.update(_required_evidence_categories(gap.gap_type))
            if not required_categories:
                required_categories = _required_evidence_categories(_classify_gap({
                    "claim_text": claim.claim_text,
                    "evidence_policy": claim.evidence_policy or {},
                }))
            experiment_levels = [
                row.evidence_level
                for row in bound_evidence
                if _evidence_category(row.evidence_kind) == "experiment"
            ]
            strongest_level = max(
                experiment_levels,
                key=lambda value: EVIDENCE_LEVELS.get(value, -1),
                default="diagnostic",
            )
            allowed_source_qualities = set(
                (claim.evidence_policy or {}).get("allowed_source_qualities")
                or (claim.evidence_policy or {}).get("required_source_quality")
                or SOURCE_QUALITIES
            )
            invalid_source_qualities = allowed_source_qualities - SOURCE_QUALITIES
            if invalid_source_qualities:
                raise DocumentWorkspaceError("主张证据策略包含无效的文献来源质量")
            satisfied_categories = {
                "literature"
                for row in bound_evidence
                if _evidence_category(row.evidence_kind) == "literature"
                and row.source_quality in allowed_source_qualities
            }
            if experiment_levels and (
                EVIDENCE_LEVELS[strongest_level] >= EVIDENCE_LEVELS[claim.minimum_evidence_level]
            ):
                satisfied_categories.add("experiment")
            sufficient = required_categories.issubset(satisfied_categories)
            claim.evidence_status = "sufficient" if sufficient else "insufficient"
            missing_categories = sorted(required_categories - satisfied_categories)
            for gap in gaps:
                gap.status = "resolved" if sufficient else "open"
                gap.reason = (
                    "所需文献来源与实验证据约束均已满足"
                    if sufficient
                    else f"仍缺少满足约束的证据类别：{', '.join(missing_categories)}"
                )
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
                "required_evidence_categories": sorted(required_categories),
                "satisfied_evidence_categories": sorted(satisfied_categories),
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
            retrievals = session.execute(select(WritingRetrievalRef).where(
                WritingRetrievalRef.project_id == project_id,
                WritingRetrievalRef.document_id == document_id,
            ).order_by(WritingRetrievalRef.retrieved_at.desc()).limit(200)).scalars().all()
            return {
                "revision": state.document_revision,
                "approved_revision": state.approved_revision,
                "published_revision": state.published_revision,
                "claims": [self._claim_dict(row) for row in claims],
                "evidence_refs": [self._evidence_dict(row) for row in evidence],
                "retrieval_refs": [self._retrieval_dict(row) for row in retrievals],
                "gaps": [
                    {
                        "id": row.id,
                        "claim_id": row.claim_id,
                        "required_level": row.required_level,
                        "gap_type": row.gap_type,
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
            claim = session.get(WritingClaim, gap.claim_id)
            if not claim:
                raise DocumentWorkspaceError("证据缺口关联的论文主张不存在")
            gap_type = _classify_gap({
                "gap_type": gap.gap_type,
                "claim_text": claim.claim_text,
                "evidence_policy": claim.evidence_policy or {},
                "research_matrix": matrix,
            })
            gap.gap_type = gap_type
            section_id = str(claim.section_id or matrix.get("section_id") or "").strip()
            if gap_type in {"literature", "mixed"} and not section_id:
                raise DocumentWorkspaceError("文献证据缺口必须绑定可定位的章节")
            state = self._state(session, project_id, document_id)
            policy = payload.get("execution_policy") or {}
            approval_reason = self._requires_execution_approval(policy)
            next_step = (
                "run_literature_research"
                if gap_type in {"literature", "mixed"}
                else "compile_research_matrix"
            )
            run_type = {
                "literature": "literature_gap_dispatch",
                "experiment": "experiment_gap_dispatch",
                "mixed": "mixed_gap_dispatch",
            }[gap_type]
            run = WritingJarvisRun(
                id=_uuid("jrun"),
                project_id=project_id,
                document_id=document_id,
                run_type=run_type,
                status="awaiting_approval" if approval_reason else "queued",
                idempotency_key=idempotency_key,
                input_payload={
                    "gap_id": gap_id,
                    "gap_type": gap_type,
                    "claim_id": claim.id,
                    "section_id": section_id,
                    "base_revision": state.document_revision,
                    "research_matrix": matrix,
                    "execution_policy": policy,
                },
                approval_reason=approval_reason,
                requested_by=actor,
                recovery_cursor={} if approval_reason else {"next_step": next_step},
            )
            step = WritingJarvisStep(
                id=_uuid("jstep"),
                run_id=run.id,
                step_key=next_step,
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
                    gap_type = str((row.input_payload or {}).get("gap_type") or "experiment")
                    row.recovery_cursor = {
                        "next_step": (
                            "run_literature_research"
                            if gap_type in {"literature", "mixed"}
                            else "compile_research_matrix"
                        )
                    }
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

            if stage == "run_literature_research":
                matrix = input_payload.get("research_matrix") or {}
                literature_matrix = matrix.get("literature_matrix") or matrix
                source_whitelist = list(literature_matrix.get("source_whitelist") or [])
                if not source_whitelist:
                    source_whitelist = list(dict.fromkeys(
                        str(source).strip().lower()
                        for direction in literature_matrix.get("directions") or []
                        for source in direction.get("source_types") or []
                        if str(source).strip().lower() in LITERATURE_SOURCES
                    ))
                if not source_whitelist:
                    source_whitelist = ["local_knowledge", "bibliography"]
                policy = input_payload.get("execution_policy") or {}
                child_run = await asyncio.to_thread(
                    self.start_literature_run,
                    str(input_payload.get("project_id") or "") or row.project_id,
                    str(input_payload.get("document_id") or "") or row.document_id,
                    {
                        "base_revision": int(input_payload.get("base_revision") or 0),
                        "idempotency_key": f"jarvis:{run_id}:literature"[:96],
                        "scope_section_ids": [str(input_payload.get("section_id") or "")],
                        "source_whitelist": source_whitelist,
                        "external_request_budget": int(policy.get("external_request_budget") or 0),
                        "max_results_per_query": int(policy.get("max_results_per_query") or 12),
                        "research_matrix": literature_matrix,
                    },
                    str(row.requested_by or "jarvis"),
                )
                gap_type = str(input_payload.get("gap_type") or "literature")
                with self.session_factory() as session:
                    row = leased_run(session)
                    if not row:
                        return
                    step = session.execute(select(WritingJarvisStep).where(
                        WritingJarvisStep.run_id == run_id,
                        WritingJarvisStep.step_key == "run_literature_research",
                    )).scalar_one()
                    step.status = "completed"
                    step.attempt_count += 1
                    step.result_payload = {"literature_run_id": child_run["id"], "status": child_run["status"]}
                    current_result = dict(row.result_payload or {})
                    row.result_payload = {
                        **current_result,
                        "literature_run_id": child_run["id"],
                        "literature_run_status": child_run["status"],
                    }
                    gap = session.execute(select(WritingEvidenceGap).where(
                        WritingEvidenceGap.dispatched_run_id == run_id,
                    )).scalar_one_or_none()
                    if gap_type == "mixed":
                        compile_step = session.execute(select(WritingJarvisStep).where(
                            WritingJarvisStep.run_id == run_id,
                            WritingJarvisStep.step_key == "compile_research_matrix",
                        )).scalar_one_or_none()
                        if not compile_step:
                            session.add(WritingJarvisStep(
                                id=_uuid("jstep"),
                                run_id=run_id,
                                step_key="compile_research_matrix",
                                status="pending",
                                depends_on=["run_literature_research"],
                                input_payload=matrix.get("experiment_matrix") or matrix,
                            ))
                        row.recovery_cursor = {"next_step": "compile_research_matrix"}
                        row.status = "queued"
                        if gap:
                            gap.status = "queued"
                    else:
                        row.recovery_cursor = {}
                        row.status = "completed"
                        row.finished_at = _now()
                        if gap and gap.status != "resolved":
                            gap.status = "open"
                            gap.reason = "文献检索已完成，等待来源审查、证据升级与主张绑定"
                    row.lease_owner = ""
                    row.lease_expires_at = None
                    session.commit()
                return

            if stage == "compile_research_matrix":
                matrix = input_payload.get("research_matrix") or {}
                matrix = matrix.get("experiment_matrix") or matrix
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
