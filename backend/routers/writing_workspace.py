"""Long-form writing workspace API."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from project_manager import project_manager
from services.auth_service import get_current_user, require_role
from services.document_workspace_service import (
    DocumentProductionBlocked,
    DocumentVersionConflict,
    DocumentWorkspaceError,
    document_workspace_service,
)
from services.course_production_service import course_production_service
from services.document_evaluation_service import (
    DocumentEvaluationError,
    document_evaluation_service,
)
from services.document_layout_service import document_layout_service
from services.multi_document_service import multi_document_service
from services.product_delivery_service import register_document_export
from services.product_service import product_registry_service
from services.writing_collaboration_service import (
    WritingCollaborationDisabled,
    writing_collaboration_service,
)
from services.writing_workbench_service import (
    WritingWorkbenchConflict,
    writing_workbench_service,
)
from services.writing_research_service import writing_research_service


router = APIRouter(prefix="/api/v3/writing", tags=["writing-workspace"])


class SectionUpdate(BaseModel):
    content: str = Field(min_length=1)
    expected_version: int = Field(ge=1)
    actor: str = "human-editor"


class ExportRequest(BaseModel):
    format: str = "docx"
    release_mode: str = Field(default="candidate", pattern="^(candidate|formal)$")


class CollaborationDraftPatch(BaseModel):
    content: dict[str, Any] | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    base_document_revision: int | None = Field(default=None, ge=1)
    client_change_id: str = Field(default="", max_length=96)
    section_id: str = Field(default="", max_length=128)
    changes: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class CollaborationAiJobCreate(BaseModel):
    client_request_id: str = Field(default="", max_length=96)
    agent_id: str = Field(default="ultra-magnus", min_length=1, max_length=64)
    scope: str = Field(default="section", pattern="^(selection|block|section|document)$")
    instruction: str = Field(min_length=1, max_length=12000)
    section_id: str = Field(default="", max_length=128)
    selection: dict[str, Any] | None = None
    block_id: str | None = Field(default=None, max_length=96)
    block_revision: int | None = Field(default=None, ge=1)
    evidence_ref_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_policy: dict[str, Any] = Field(default_factory=dict)


class WritingClaimCreate(BaseModel):
    claim_text: str = Field(min_length=1, max_length=20000)
    claim_type: str = Field(default="argument", max_length=32)
    minimum_evidence_level: str = Field(default="diagnostic", pattern="^(diagnostic|G1|G2|A)$")
    document_revision: int | None = Field(default=None, ge=1)
    section_id: str = Field(default="", max_length=128)
    block_id: str = Field(default="", max_length=96)
    research_matrix: dict[str, Any] = Field(default_factory=dict)


class WritingEvidenceRefCreate(BaseModel):
    source_system: str = Field(min_length=1, max_length=48)
    source_record_id: str = Field(default="", max_length=160)
    artifact_path: str = Field(min_length=1, max_length=4000)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    perspective_scope: str = Field(default="project", max_length=64)
    evidence_level: str = Field(default="diagnostic", pattern="^(diagnostic|G1|G2|A)$")
    allowed_claim_scope: str = Field(default="", max_length=12000)
    provenance: dict[str, Any] = Field(default_factory=dict)


class WritingEvidenceBindingCreate(BaseModel):
    claim_id: str = Field(min_length=1, max_length=64)
    evidence_ref_id: str = Field(min_length=1, max_length=64)
    support_scope: str = Field(default="", max_length=12000)


class WritingEvidenceGapDispatch(BaseModel):
    research_matrix: dict[str, Any] | None = None
    execution_policy: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=96)
    retry: bool = False
    retry_request_id: str = Field(default="", max_length=64)


class WritingChangeSetCreate(BaseModel):
    base_revision: int | None = Field(default=None, ge=1)
    operations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    evidence_ref_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_level: str = Field(default="high", pattern="^(low|medium|high)$")
    approval_policy: str = Field(default="risk_driven", max_length=32)
    idempotency_key: str = Field(default="", max_length=96)
    summary: str = Field(default="", max_length=4000)


class WritingChangeSetDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str = Field(default="", max_length=4000)


class WritingJarvisRunDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str = Field(default="", max_length=4000)


class WritingEvidenceBundleReady(BaseModel):
    source_system: str = Field(default="one-sim", max_length=48)
    bundle_id: str = Field(min_length=1, max_length=160)
    source_record_id: str = Field(default="", max_length=160)
    simulation_record_id: str = Field(default="", max_length=160)
    artifact_path: str = Field(min_length=1, max_length=4000)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    perspective_scope: str = Field(default="project", max_length=64)
    evidence_level: str = Field(pattern="^(diagnostic|G1|G2|A)$")
    allowed_claim_scope: str = Field(default="", max_length=12000)
    provenance: dict[str, Any] = Field(default_factory=dict)
    paper_evidence_packet: dict[str, Any] = Field(default_factory=dict)


class WritingWordReleaseCreate(BaseModel):
    document_revision: int | None = Field(default=None, ge=1)
    template_sha256: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(default="", max_length=96)


class WritingWordReleaseUpdate(BaseModel):
    docx_path: str | None = Field(default=None, max_length=4000)
    docx_sha256: str | None = Field(default=None, max_length=64)
    pdf_path: str | None = Field(default=None, max_length=4000)
    pdf_sha256: str | None = Field(default=None, max_length=64)
    field_refresh_status: str | None = Field(default=None, pattern="^(pending|running|completed|failed)$")
    page_check: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(candidate|approved|rejected|failed)$")


class CollaborationVersionCreate(BaseModel):
    name: str = Field(default="人工版本", max_length=160)
    message: str = Field(default="", max_length=2000)
    revision: int | None = Field(default=None, ge=1)


class CollaborationVersionRestore(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)


class PresentationSlideProposalCreate(BaseModel):
    slide: int = Field(ge=1)
    instruction: str = Field(min_length=1, max_length=4000)
    agent_id: str = Field(default="presentation-editor", min_length=1, max_length=64)
    draft: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str = Field(default="", max_length=96)


class WorkbenchPaneState(BaseModel):
    module: str = Field(pattern="^(document|presentation|ai)$")
    resource_id: str | None = Field(default=None, max_length=64)
    section_id: str | None = Field(default=None, max_length=128)
    slide: int | None = Field(default=None, ge=1)
    ai_conversation_id: str | None = Field(default=None, max_length=64)
    ai_target_locked: bool = False


class WorkbenchPanePair(BaseModel):
    left: WorkbenchPaneState
    right: WorkbenchPaneState


class WorkbenchPreferenceUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    schema_version: int = Field(default=1, ge=1, le=1)
    preset: str = Field(pattern="^(writing|presentation|comparison|custom)$")
    split_percent: int = Field(ge=25, le=75)
    maximized_pane: str | None = Field(default=None, pattern="^(left|right)$")
    panes: WorkbenchPanePair


class WritingAiConversationCreate(BaseModel):
    title: str = Field(default="协作会话", min_length=1, max_length=200)
    agent_id: str = Field(default="ultra-magnus", min_length=1, max_length=64)


class WritingAiTarget(BaseModel):
    kind: str = Field(pattern="^(document|presentation)$")
    document_id: str = Field(min_length=1, max_length=64)
    document_title: str = Field(default="", max_length=200)
    scope: str = Field(default="section", pattern="^(selection|block|section|document)$")
    section_id: str = Field(default="", max_length=128)
    section_title: str = Field(default="", max_length=300)
    block_id: str | None = Field(default=None, max_length=96)
    block_revision: int | None = Field(default=None, ge=1)
    revision: int | None = Field(default=None, ge=1)
    selection: dict[str, Any] | None = None
    slide: int | None = Field(default=None, ge=1)
    structure_revision: int | None = Field(default=None, ge=1)
    draft: dict[str, Any] = Field(default_factory=dict)


class WritingAiConversationMessageCreate(BaseModel):
    client_message_id: str = Field(default="", max_length=80)
    agent_id: str = Field(default="ultra-magnus", min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=12000)
    target: WritingAiTarget


class DocumentLayoutUpdate(BaseModel):
    profile_id: str | None = None
    layout_revision: str | None = Field(default=None, max_length=20)
    cover: dict[str, str] | None = None


class WritingProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    document_type: str = "研究报告"
    writing_goal: str = ""
    target_audience: str = ""
    output_format: str = "Markdown / Word / PDF"
    outline: list[str] = Field(default_factory=list)
    owner_agent: str = "ultra-magnus"
    priority: str = "medium"
    product_id: str = ""


class ProjectDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str = Field(pattern="^(rich_text|workbook|presentation)$")
    outline: list[str] = Field(default_factory=list)
    source_path: str = ""
    is_primary: bool = False
    is_output_product: bool | None = None
    output_format: str = ""
    data_source_ids: list[str] = Field(default_factory=list)
    product_type: str = ""
    course_unit_ids: list[str] = Field(default_factory=list)
    quality_profile: str = ""
    required_for_release: bool = False
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    print_profile: str = ""
    publication_status: str = ""
    rules_version: str = ""
    data_version: str = ""


class ProjectDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = Field(default=None, pattern="^(active|archived)$")
    sort_order: int | None = Field(default=None, ge=0)
    is_primary: bool | None = None
    is_output_product: bool | None = None
    output_format: str | None = None
    data_source_ids: list[str] | None = None
    product_type: str | None = None
    course_unit_ids: list[str] | None = None
    quality_profile: str | None = None
    required_for_release: bool | None = None
    source_refs: list[dict[str, Any]] | None = None
    print_profile: str | None = None
    publication_status: str | None = None
    rules_version: str | None = None
    data_version: str | None = None


class ProjectDocumentOrder(BaseModel):
    document_ids: list[str] = Field(min_length=1)


class CourseBaselineUpdate(BaseModel):
    template_key: str = "surface_wargame_course_v1"
    version: str = "1.1"
    canonical_title: str = "水面舰艇作战软件与兵棋推演"
    course_code: str = "YJZT503"
    target_audience: str = "本科军兵种作战指挥专业"
    course_nature: str = "选修课"
    total_hours: int = 20
    unit_hours: int = 2
    theory_hours: int = 4
    practice_hours: int = 14
    assessment_hours: int = 2
    theory_sessions: int = 2
    practice_sessions: int = 7
    assessment_sessions: int = 1
    units: list[dict[str, Any]] = Field(default_factory=list)


class CourseTemplateApply(BaseModel):
    dry_run: bool = False


class CourseWorkPlanApply(BaseModel):
    dry_run: bool = False


class CourseIterationRun(BaseModel):
    rounds: int = Field(default=1, ge=1, le=10)
    parallelism: int = Field(default=3, ge=1, le=4)
    dry_run: bool = False


class CoursePointReview(BaseModel):
    decision: str = Field(pattern="^(approve|reject|retry)$")
    comment: str = Field(default="", max_length=2000)


class WorkbookCellPatch(BaseModel):
    coordinate: str = Field(min_length=2, max_length=8)
    value: Any = None


class WorkbookCellsUpdate(BaseModel):
    cells: list[WorkbookCellPatch] = Field(min_length=1, max_length=1000)
    expected_revision: int = Field(ge=1)
    actor: str = "human-editor"


class WorkbookSheetRename(BaseModel):
    new_name: str = Field(min_length=1, max_length=31)
    expected_revision: int = Field(ge=1)


class VersionRestoreRequest(BaseModel):
    actor: str = "human-editor"


class DocumentStructureBindingUpdate(BaseModel):
    mode: str = Field(pattern="^(canonical|derived|mapped)$")
    source_document_id: str = Field(min_length=1)
    source_version: str = ""
    source_sha256: str = ""
    status: str = Field(
        default="missing",
        pattern="^(aligned|diverged|stale|missing)$",
    )
    mapped_items: int = Field(default=0, ge=0)
    unmapped_items: list[Any] = Field(default_factory=list)
    changed_sections: list[Any] = Field(default_factory=list)
    manifest: dict[str, Any] | None = None


class EvaluationRunRequest(BaseModel):
    mode: str = Field(default="full", pattern="^(technical|full)$")


class EvaluationPolicyUpdate(BaseModel):
    profile_id: str = Field(min_length=1)
    overrides: dict[str, Any] = Field(default_factory=dict)
    actor: str = "human-editor"


class EvaluationConfirmationRequest(BaseModel):
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    gate_statuses: dict[str, str] = Field(default_factory=dict)
    comment: str = ""
    actor: str = "expert-reviewer"


def _project(project_id: str) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if "writing" not in (project.get("enabled_modules") or []):
        raise HTTPException(status_code=400, detail="Project has not enabled the writing module")
    return project


def _actor(user: dict[str, Any]) -> str:
    return str(
        user.get("username")
        or user.get("name")
        or user.get("user_id")
        or user.get("id")
        or "project-manager"
    )


def _owner_id(user: dict[str, Any]) -> str:
    return str(user.get("sub") or _actor(user))


def _handle(error: DocumentWorkspaceError) -> HTTPException:
    if isinstance(error, WritingWorkbenchConflict):
        return HTTPException(
            status_code=409,
            detail={"code": "workbench_revision_conflict", "message": str(error)},
        )
    if isinstance(error, WritingCollaborationDisabled):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, DocumentProductionBlocked):
        return HTTPException(
            status_code=409,
            detail={
                "code": "production_blocked",
                "message": str(error),
                "blockers": error.blockers,
            },
        )
    if isinstance(error, DocumentVersionConflict):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


def _handle_evaluation(error: DocumentEvaluationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def _refresh_technical_evaluation(project: dict[str, Any], document_id: str) -> None:
    try:
        document_evaluation_service.run_technical(project, document_id)
    except (DocumentWorkspaceError, DocumentEvaluationError, OSError):
        # Saving document content must not fail only because an auxiliary
        # evaluation profile or report store is temporarily unavailable.
        return


@router.get("/projects/{project_id}/workbench-preference")
def get_writing_workbench_preference(
    project_id: str,
    user: dict = Depends(get_current_user),
):
    _project(project_id)
    return writing_workbench_service.get_preference(project_id, _owner_id(user))


@router.patch("/projects/{project_id}/workbench-preference")
def update_writing_workbench_preference(
    project_id: str,
    req: WorkbenchPreferenceUpdate,
    user: dict = Depends(get_current_user),
):
    try:
        _project(project_id)
        return writing_workbench_service.update_preference(
            project_id,
            _owner_id(user),
            req.model_dump(),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/ai-conversations")
def list_writing_ai_conversations(
    project_id: str,
    user: dict = Depends(get_current_user),
):
    _project(project_id)
    return writing_workbench_service.list_conversations(project_id, _owner_id(user))


@router.post("/projects/{project_id}/ai-conversations", status_code=201)
def create_writing_ai_conversation(
    project_id: str,
    req: WritingAiConversationCreate,
    user: dict = Depends(get_current_user),
):
    _project(project_id)
    return writing_workbench_service.create_conversation(
        project_id,
        _owner_id(user),
        req.model_dump(),
    )


@router.get("/projects/{project_id}/ai-conversations/{conversation_id}/messages")
def list_writing_ai_messages(
    project_id: str,
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        _project(project_id)
        return writing_workbench_service.list_messages(
            project_id, _owner_id(user), conversation_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post(
    "/projects/{project_id}/ai-conversations/{conversation_id}/messages",
    status_code=202,
)
def create_writing_ai_message(
    project_id: str,
    conversation_id: str,
    req: WritingAiConversationMessageCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_workbench_service.submit_message(
            _project(project_id),
            _owner_id(user),
            conversation_id,
            req.model_dump(exclude_none=True),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post(
    "/projects/{project_id}/ai-conversations/{conversation_id}/messages/{message_id}/cancel"
)
def cancel_writing_ai_message(
    project_id: str,
    conversation_id: str,
    message_id: str,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_workbench_service.cancel_message(
            _project(project_id), _owner_id(user), conversation_id, message_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects", status_code=201)
def create_writing_project(req: WritingProjectCreate, _user: dict = Depends(require_role("admin"))):
    name = req.name.strip()
    if any(
        str(project.get("name") or "").strip().casefold() == name.casefold()
        for project in project_manager.list_projects()
    ):
        raise HTTPException(status_code=409, detail="已存在同名项目，请使用不同的文档名称")
    if req.product_id and not product_registry_service.get_product(req.product_id):
        raise HTTPException(status_code=400, detail="关联产品不存在")
    chapters = [
        {
            "title": title.strip(),
            "summary": "",
            "main_content": "",
            "status": "planning",
            "assigned_agent": req.owner_agent,
            "order_index": index,
        }
        for index, title in enumerate(req.outline)
        if title.strip()
    ]
    document_spec = {
        "document_type": req.document_type.strip() or "研究报告",
        "writing_goal": req.writing_goal.strip(),
        "target_audience": req.target_audience.strip(),
        "outline": [chapter["title"] for chapter in chapters],
        "chapters": chapters,
        "assets": [],
        "references": [],
        "source_word": {},
        "working_markdown": {},
        "section_links": [],
        "sync_status": {"status": "initialized", "message": "文档项目已创建"},
        "output_format": req.output_format.strip() or "Markdown / Word / PDF",
    }
    project = project_manager.create_project({
        "name": name,
        "description": req.description.strip(),
        "project_type": "document",
        "status": "planning",
        "priority": req.priority,
        "owner_agent": req.owner_agent,
        "current_phase": "outline",
        "enabled_modules": ["writing", "knowledge", "finance", "products"],
        "context": {"project_type": "document", "created_from": "writing-workspace"},
        "product_bindings": ([{
            "product_id": req.product_id,
            "role": "primary",
            "status": "bound",
            "source": "writing-workspace-create",
        }] if req.product_id else []),
        "document_spec": document_spec,
    })
    initialized = document_workspace_service.initialize_project(project, document_spec["outline"])
    document_spec["working_markdown"] = initialized
    document_spec["sync_status"] = {
        "status": "initialized",
        "message": "已创建独立 Markdown 工作稿",
        "heading_count": len(chapters) + 2,
        "section_link_count": 0,
    }
    project = project_manager.update_project(project["id"], {"document_spec": document_spec}) or project
    try:
        workspace = document_workspace_service.workspace(project)
    except DocumentWorkspaceError as exc:
        project_manager.delete_project(project["id"])
        raise _handle(exc) from exc
    return {"project": project, "workspace": workspace}


@router.get("/projects/{project_id}/documents")
def list_project_documents(
    project_id: str,
    include_archived: bool = True,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.list_documents(_project(project_id), include_archived)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents", status_code=201)
def create_project_document(
    project_id: str,
    req: ProjectDocumentCreate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        source_ref_blockers = course_production_service.validate_source_refs(
            _project(project_id), req.source_refs
        ) if req.source_refs else []
        if source_ref_blockers:
            raise DocumentWorkspaceError("；".join(row["message"] for row in source_ref_blockers))
        return multi_document_service.create_document(
            _project(project_id),
            req.title,
            req.kind,
            outline=req.outline,
            source_path=req.source_path,
            is_primary=req.is_primary,
            is_output_product=req.is_output_product,
            output_format=req.output_format,
            data_source_ids=req.data_source_ids,
            product_type=req.product_type,
            course_unit_ids=req.course_unit_ids,
            quality_profile=req.quality_profile,
            required_for_release=req.required_for_release,
            source_refs=req.source_refs,
            print_profile=req.print_profile,
            publication_status=req.publication_status,
            rules_version=req.rules_version,
            data_version=req.data_version,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}")
def get_project_document(project_id: str, document_id: str, _user: dict = Depends(get_current_user)):
    try:
        return multi_document_service.get_document(_project(project_id), document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.patch("/projects/{project_id}/documents/{document_id}")
def update_project_document(
    project_id: str,
    document_id: str,
    req: ProjectDocumentUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        if req.source_refs is not None:
            source_ref_blockers = course_production_service.validate_source_refs(
                _project(project_id), req.source_refs
            )
            if source_ref_blockers:
                raise DocumentWorkspaceError("；".join(row["message"] for row in source_ref_blockers))
        return multi_document_service.update_document(
            _project(project_id),
            document_id,
            req.model_dump(exclude_none=True),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.put("/projects/{project_id}/course-baseline")
def update_course_baseline(
    project_id: str,
    req: CourseBaselineUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return course_production_service.set_baseline(
            _project(project_id), req.model_dump()
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/course-template/apply")
def apply_course_template(
    project_id: str,
    req: CourseTemplateApply,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return course_production_service.apply_template(
            _project(project_id), dry_run=req.dry_run
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/production-status")
def get_course_production_status(
    project_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return course_production_service.production_status(_project(project_id))
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/course-work-plan/apply")
def apply_course_work_plan(
    project_id: str,
    req: CourseWorkPlanApply,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return course_production_service.apply_work_plan(
            _project(project_id), dry_run=req.dry_run
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/course-iterations/run", status_code=202)
def run_course_iteration(
    project_id: str,
    req: CourseIterationRun,
    user: dict = Depends(require_role("admin")),
):
    try:
        return course_production_service.start_iteration(
            _project(project_id),
            rounds=req.rounds,
            parallelism=req.parallelism,
            requested_by=_actor(user),
            dry_run=req.dry_run,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/course-points/{point_id}/review")
def review_course_point(
    project_id: str,
    point_id: str,
    req: CoursePointReview,
    user: dict = Depends(require_role("admin")),
):
    try:
        return course_production_service.review_point(
            _project(project_id),
            point_id,
            decision=req.decision,
            reviewer=_actor(user),
            comment=req.comment,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/import-docx", status_code=201)
async def import_project_docx(
    project_id: str,
    file: UploadFile = File(...),
    title: str = Query(..., min_length=1, max_length=120),
    product_type: str = Query(""),
    course_unit_ids: str = Query(""),
    quality_profile: str = Query(""),
    required_for_release: bool = Query(False),
    actor: str = Query("human-editor"),
    _user: dict = Depends(require_role("admin")),
):
    try:
        data = await file.read()
        return multi_document_service.import_docx(
            _project(project_id),
            title,
            data,
            file.filename or "document.docx",
            product_type=product_type,
            course_unit_ids=[
                value.strip()
                for value in course_unit_ids.split(",")
                if value.strip()
            ],
            quality_profile=quality_profile,
            required_for_release=required_for_release,
            actor=actor,
        )
    except (DocumentWorkspaceError, BadZipFile) as exc:
        error = exc if isinstance(exc, DocumentWorkspaceError) else DocumentWorkspaceError("Word 文件已损坏")
        raise _handle(error) from exc


@router.patch("/projects/{project_id}/documents-order")
def reorder_project_documents(
    project_id: str,
    req: ProjectDocumentOrder,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return {"documents": multi_document_service.reorder_documents(_project(project_id), req.document_ids)}
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
def delete_project_document(
    project_id: str,
    document_id: str,
    _user: dict = Depends(require_role("admin")),
):
    try:
        multi_document_service.delete_document(_project(project_id), document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/content")
async def replace_project_document_content(
    project_id: str,
    document_id: str,
    file: UploadFile = File(...),
    actor: str = Query("human-editor"),
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        data = await file.read()
        result = multi_document_service.replace_content(
            project,
            document_id,
            data,
            file.filename or "document",
            actor,
        )
        _refresh_technical_evaluation(project, document_id)
        return result
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/workspace")
def get_document_workspace(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.rich_workspace(_project(project_id), document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/collaboration")
def get_document_collaboration(
    project_id: str,
    document_id: str,
    section_id: str = Query(default="", max_length=128),
    _user: dict = Depends(get_current_user),
):
    try:
        return writing_collaboration_service.get_state(
            _project(project_id), document_id, section_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/research-workflow")
def get_document_research_workflow(
    project_id: str,
    document_id: str,
    _user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.workspace_summary(project_id, document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/claims", status_code=201)
def create_document_claim(
    project_id: str,
    document_id: str,
    req: WritingClaimCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.create_claim(
            project_id, document_id, req.model_dump(exclude_none=True), _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/evidence-refs", status_code=201)
def create_document_evidence_ref(
    project_id: str,
    document_id: str,
    req: WritingEvidenceRefCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.register_evidence(
            project_id, document_id, req.model_dump(), _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/evidence-bindings", status_code=201)
def create_document_evidence_binding(
    project_id: str,
    document_id: str,
    req: WritingEvidenceBindingCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.bind_evidence(
            project_id, document_id, req.model_dump(), _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post(
    "/projects/{project_id}/documents/{document_id}/evidence-gaps/{gap_id}/dispatch",
    status_code=202,
)
def dispatch_document_evidence_gap(
    project_id: str,
    document_id: str,
    gap_id: str,
    req: WritingEvidenceGapDispatch,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.dispatch_gap(
            project_id,
            document_id,
            gap_id,
            req.model_dump(exclude_none=True),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/jarvis-runs/{run_id}")
def get_document_jarvis_run(
    project_id: str,
    document_id: str,
    run_id: str,
    _user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.get_run(project_id, document_id, run_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/jarvis-runs/{run_id}/decision")
def decide_document_jarvis_run(
    project_id: str,
    document_id: str,
    run_id: str,
    req: WritingJarvisRunDecision,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.decide_run(
            project_id, document_id, run_id, req.decision, _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/jarvis-runs/{run_id}/evidence-ready")
def ingest_document_jarvis_evidence(
    project_id: str,
    document_id: str,
    run_id: str,
    req: WritingEvidenceBundleReady,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.ingest_evidence_bundle(
            project_id,
            document_id,
            run_id,
            req.model_dump(),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/change-sets", status_code=201)
def create_document_change_set(
    project_id: str,
    document_id: str,
    req: WritingChangeSetCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.create_change_set(
            project_id, document_id, req.model_dump(exclude_none=True), _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/change-sets/{change_set_id}/decision")
def decide_document_change_set(
    project_id: str,
    document_id: str,
    change_set_id: str,
    req: WritingChangeSetDecision,
    user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        actor = _actor(user)
        change_set = writing_research_service.get_change_set(project_id, document_id, change_set_id)
        result_revision = 0
        if req.decision == "approve" and not change_set.get("proposal_id"):
            raise DocumentWorkspaceError("该 ChangeSet 尚无可执行块映射，不能标记为已应用")
        if change_set.get("proposal_id"):
            if req.decision == "approve":
                state = writing_collaboration_service.accept_proposal(
                    project, document_id, change_set["proposal_id"], actor
                )
                result_revision = int(state.get("revision") or 0)
            else:
                writing_collaboration_service.reject_proposal(
                    project, document_id, change_set["proposal_id"], actor
                )
        return writing_research_service.decide_change_set(
            project_id,
            document_id,
            change_set_id,
            req.decision,
            actor,
            result_revision=result_revision,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/revisions/{revision}/approval")
def approve_document_revision(
    project_id: str,
    document_id: str,
    revision: int,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.approve_revision(
            project_id, document_id, revision, _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/word-imports", status_code=201)
async def import_document_word_changes(
    project_id: str,
    document_id: str,
    file: UploadFile = File(...),
    base_revision: int = Query(..., ge=1),
    idempotency_key: str = Query(..., min_length=1, max_length=96),
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        content = await file.read()
        if len(content) > 150 * 1024 * 1024:
            raise DocumentWorkspaceError("Word 回流文件超过 150MB 限制")
        return writing_research_service.register_word_import(
            project_id,
            document_id,
            filename=file.filename or "document.docx",
            content=content,
            base_revision=base_revision,
            actor=_actor(user),
            idempotency_key=idempotency_key,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/releases", status_code=201)
def create_document_word_release(
    project_id: str,
    document_id: str,
    req: WritingWordReleaseCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.create_release(
            project_id, document_id, req.model_dump(exclude_none=True), _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.patch("/projects/{project_id}/documents/{document_id}/releases/{release_id}")
def update_document_word_release(
    project_id: str,
    document_id: str,
    release_id: str,
    req: WritingWordReleaseUpdate,
    user: dict = Depends(require_role("admin")),
):
    try:
        _project(project_id)
        return writing_research_service.update_release(
            project_id,
            document_id,
            release_id,
            req.model_dump(exclude_none=True),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/collaboration/initialize")
def initialize_document_collaboration(
    project_id: str,
    document_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Explicitly validate and switch one document to structured authority."""
    try:
        project = _project(project_id)
        writing_collaboration_service.ensure_state(project, document_id)
        return writing_collaboration_service.get_state(project, document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.patch("/projects/{project_id}/documents/{document_id}/collaboration/draft")
def patch_document_collaboration_draft(
    project_id: str,
    document_id: str,
    req: CollaborationDraftPatch,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_collaboration_service.patch_draft(
            _project(project_id),
            document_id,
            req.model_dump(exclude_none=True),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/ai-jobs")
@router.post(
    "/projects/{project_id}/documents/{document_id}/collaboration/ai-jobs",
    include_in_schema=False,
)
def create_document_ai_job(
    project_id: str,
    document_id: str,
    req: CollaborationAiJobCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        job = writing_collaboration_service.submit_ai_job(
            project,
            document_id,
            req.model_dump(exclude_none=True),
            _actor(user),
        )
        return job
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/ai-jobs/{job_id}")
@router.get(
    "/projects/{project_id}/documents/{document_id}/collaboration/ai-jobs/{job_id}",
    include_in_schema=False,
)
def get_document_ai_job(
    project_id: str,
    document_id: str,
    job_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return writing_collaboration_service.get_ai_job(
            _project(project_id), document_id, job_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/ai-jobs/{job_id}/cancel")
def cancel_document_ai_job(
    project_id: str,
    document_id: str,
    job_id: str,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return writing_collaboration_service.cancel_ai_job(
            _project(project_id), document_id, job_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/proposals/{proposal_id}/accept")
@router.post(
    "/projects/{project_id}/documents/{document_id}/collaboration/proposals/{proposal_id}/accept",
    include_in_schema=False,
)
def accept_document_ai_proposal(
    project_id: str,
    document_id: str,
    proposal_id: str,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_collaboration_service.accept_proposal(
            _project(project_id), document_id, proposal_id, _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/proposals/{proposal_id}/reject")
@router.post(
    "/projects/{project_id}/documents/{document_id}/collaboration/proposals/{proposal_id}/reject",
    include_in_schema=False,
)
def reject_document_ai_proposal(
    project_id: str,
    document_id: str,
    proposal_id: str,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_collaboration_service.reject_proposal(
            _project(project_id), document_id, proposal_id, _actor(user)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/versions")
@router.post(
    "/projects/{project_id}/documents/{document_id}/collaboration/versions",
    include_in_schema=False,
)
def create_document_collaboration_version(
    project_id: str,
    document_id: str,
    req: CollaborationVersionCreate,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_collaboration_service.create_version(
            _project(project_id),
            document_id,
            req.model_dump(exclude_none=True),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/projects/{project_id}/documents/{document_id}/collaboration/versions"
)
def list_document_collaboration_versions(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return writing_collaboration_service.list_versions(
            _project(project_id),
            document_id,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post(
    "/projects/{project_id}/documents/{document_id}/collaboration/versions/{version_id}/restore"
)
def restore_document_collaboration_version(
    project_id: str,
    document_id: str,
    version_id: str,
    req: CollaborationVersionRestore,
    user: dict = Depends(require_role("admin")),
):
    try:
        return writing_collaboration_service.restore_version(
            _project(project_id),
            document_id,
            version_id,
            req.model_dump(exclude_none=True),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/sections/{section_id}")
def get_document_section(
    project_id: str,
    document_id: str,
    section_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.rich_call(_project(project_id), document_id, "section", section_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.put("/projects/{project_id}/documents/{document_id}/sections/{section_id}")
def update_document_section(
    project_id: str,
    document_id: str,
    section_id: str,
    req: SectionUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        result = multi_document_service.rich_call(
            project,
            document_id,
            "update_section",
            section_id,
            req.content,
            req.expected_version,
            req.actor,
        )
        _refresh_technical_evaluation(project, document_id)
        return result
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/fulltext")
def get_document_fulltext(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.rich_call(_project(project_id), document_id, "fulltext")
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/references")
def get_document_references(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.rich_call(_project(project_id), document_id, "references")
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/graph")
def get_document_graph(project_id: str, document_id: str, _user: dict = Depends(get_current_user)):
    try:
        return multi_document_service.rich_call(_project(project_id), document_id, "graph")
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/quality")
def get_document_quality(project_id: str, document_id: str, _user: dict = Depends(get_current_user)):
    try:
        return multi_document_service.rich_call(_project(project_id), document_id, "quality")
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/evaluation/profiles")
def get_evaluation_profiles(_user: dict = Depends(get_current_user)):
    return document_evaluation_service.catalog()


@router.get("/projects/{project_id}/documents/{document_id}/evaluation/profile")
def get_document_evaluation_profile(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return document_evaluation_service.resolved_profile(
            _project(project_id), document_id
        )
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.put("/projects/{project_id}/documents/{document_id}/evaluation/profile")
def update_document_evaluation_profile(
    project_id: str,
    document_id: str,
    req: EvaluationPolicyUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return document_evaluation_service.update_policy(
            _project(project_id),
            document_id,
            profile_id=req.profile_id,
            overrides=req.overrides,
            actor=req.actor,
        )
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/evaluation/history")
def get_document_evaluation_history(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return {
            "reports": document_evaluation_service.history(
                _project(project_id), document_id
            )
        }
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/evaluation/jobs/{job_id}")
def get_document_evaluation_job(
    project_id: str,
    document_id: str,
    job_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return document_evaluation_service.get_job(
            _project(project_id), document_id, job_id
        )
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/evaluation")
def get_document_evaluation(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return document_evaluation_service.latest(
            _project(project_id), document_id, create_if_missing=True
        )
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/evaluation/run")
def run_document_evaluation(
    project_id: str,
    document_id: str,
    req: EvaluationRunRequest,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        if req.mode == "technical":
            return {
                "mode": "technical",
                "report": document_evaluation_service.run_technical(
                    project, document_id
                ),
            }
        return document_evaluation_service.run_full(project, document_id)
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/evaluation/confirm")
def confirm_document_evaluation(
    project_id: str,
    document_id: str,
    req: EvaluationConfirmationRequest,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return document_evaluation_service.confirm(
            _project(project_id),
            document_id,
            dimension_scores=req.dimension_scores,
            gate_statuses=req.gate_statuses,
            comment=req.comment,
            actor=req.actor,
        )
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.get("/projects/{project_id}/evaluation/linked-summary")
def get_project_evaluation_linked_summary(
    project_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return document_evaluation_service.linked_summary(_project(project_id))
    except (DocumentWorkspaceError, DocumentEvaluationError) as exc:
        if isinstance(exc, DocumentWorkspaceError):
            raise _handle(exc) from exc
        raise _handle_evaluation(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/versions")
def get_document_versions(project_id: str, document_id: str, _user: dict = Depends(get_current_user)):
    try:
        return {"versions": multi_document_service.versions(_project(project_id), document_id)}
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/structure-binding")
def get_document_structure_binding(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.structure_binding(_project(project_id), document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.put("/projects/{project_id}/documents/{document_id}/structure-binding")
def update_document_structure_binding(
    project_id: str,
    document_id: str,
    req: DocumentStructureBindingUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        payload = req.model_dump()
        manifest = payload.pop("manifest", None)
        return multi_document_service.set_structure_binding(
            _project(project_id),
            document_id,
            payload,
            manifest,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/versions/{version_name}/restore")
def restore_document_version(
    project_id: str,
    document_id: str,
    version_name: str,
    req: VersionRestoreRequest,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        result = multi_document_service.restore_version(
            project,
            document_id,
            version_name,
            req.actor,
        )
        _refresh_technical_evaluation(project, document_id)
        return result
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/assets")
def get_document_asset(
    project_id: str,
    document_id: str,
    path: str = Query(..., min_length=1),
    _user: dict = Depends(get_current_user),
):
    try:
        asset = multi_document_service.rich_call(_project(project_id), document_id, "asset_path", path)
        return FileResponse(asset, filename=asset.name)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/assets", status_code=201)
async def upload_document_asset(
    project_id: str,
    document_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_role("admin")),
):
    try:
        data = await file.read()
        return multi_document_service.upload_rich_text_asset(
            _project(project_id),
            document_id,
            data,
            file.filename or "image",
            file.content_type or "",
            actor=_actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/source-word")
def get_document_source_word(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        manifest = multi_document_service.rich_call(_project(project_id), document_id, "ensure_workspace")
        if not manifest.get("source_word"):
            raise HTTPException(status_code=404, detail="未登记 Word 原文")
        path = Path(manifest["source_word"])
        return FileResponse(path, filename=path.name)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/layout")
def get_document_layout(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        project = _project(project_id)
        context = multi_document_service.rich_project_context(project, document_id)
        return document_layout_service.state(context)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.patch("/projects/{project_id}/documents/{document_id}/layout")
def update_document_layout(
    project_id: str,
    document_id: str,
    req: DocumentLayoutUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        context = multi_document_service.rich_project_context(project, document_id)
        binding = document_layout_service.binding_patch(
            context,
            profile_id=req.profile_id,
            cover=req.cover,
            layout_revision=req.layout_revision,
        )
        multi_document_service.update_document_metadata(
            project,
            document_id,
            {"layout_binding": binding},
        )
        return document_layout_service.state(
            multi_document_service.rich_project_context(project, document_id)
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/layout/sample/{format}")
def get_document_layout_sample(
    project_id: str,
    document_id: str,
    format: str,
    _user: dict = Depends(get_current_user),
):
    try:
        context = multi_document_service.rich_project_context(_project(project_id), document_id)
        state = document_layout_service.state(context)
        key = "pdf_path" if format.lower() == "pdf" else "docx_path"
        path = Path(str(state.get("sample", {}).get(key) or ""))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="模板样张尚未生成")
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(path, filename=path.name, media_type=media_type)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/layout/delivery/{format}")
def get_document_layout_delivery(
    project_id: str,
    document_id: str,
    format: str,
    _user: dict = Depends(get_current_user),
):
    try:
        context = multi_document_service.rich_project_context(_project(project_id), document_id)
        state = document_layout_service.state(context)
        latest = state.get("binding", {}).get("latest_delivery") or {}
        key = "pdf_path" if format.lower() == "pdf" else "docx_path"
        path = Path(str(latest.get(key) or ""))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="当前交付稿尚未生成")
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(path, filename=path.name, media_type=media_type)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/export", include_in_schema=False)
@router.post("/projects/{project_id}/documents/{document_id}/exports")
def export_project_document(
    project_id: str,
    document_id: str,
    req: ExportRequest,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        if req.release_mode == "formal":
            release = writing_research_service.require_formal_release(project_id, document_id, req.format)
            key = "pdf_path" if req.format.lower() == "pdf" else "docx_path"
            path = Path(str(release[key]))
            deliverable = register_document_export(project, path, req.format)
            media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            response = FileResponse(path, filename=path.name, media_type=media_type)
            response.headers["X-Writing-Release-Id"] = str(release["id"])
            if deliverable:
                response.headers["X-Product-Deliverable-Id"] = str(deliverable["id"])
            return response
        writing_collaboration_service.ensure_projection_current(project, document_id)
        path = multi_document_service.rich_call(project, document_id, "export", req.format)
        context = multi_document_service.rich_project_context(project, document_id)
        layout_state = document_layout_service.state(context)
        if layout_state.get("profile"):
            docx_path = path if path.suffix.lower() == ".docx" else path.with_suffix(".docx")
            pdf_path = path if path.suffix.lower() == ".pdf" else None
            binding = document_layout_service.delivery_patch(context, docx_path, pdf_path)
            multi_document_service.update_document_metadata(project, document_id, {"layout_binding": binding})
        deliverable = register_document_export(project, path, req.format)
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        response = FileResponse(path, filename=path.name, media_type=media_type)
        if deliverable:
            response.headers["X-Product-Deliverable-Id"] = str(deliverable["id"])
        return response
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/export-package")
def export_project_document_package(
    project_id: str,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        collection = multi_document_service.list_documents(project, include_archived=False)
        records = [
            document
            for document in collection.get("documents") or []
            if document.get("status") == "active" and bool(document.get("is_output_product"))
        ]
        if not records:
            raise DocumentWorkspaceError("项目没有可交付的正式文档")
        artifacts: list[tuple[Path, str]] = []
        for document in records:
            title = re.sub(r'[\\/:*?"<>|]+', "-", str(document.get("title") or "文档")).strip() or "文档"
            if document.get("publication_status") not in {"approved", "published"}:
                raise DocumentWorkspaceError(f"正式文档尚未批准：{title}")
            if document.get("kind") == "rich_text":
                output_format = str(document.get("output_format") or "docx").lower()
                release = writing_research_service.require_formal_release(
                    project_id,
                    str(document.get("id") or ""),
                    output_format,
                )
                key = "pdf_path" if output_format == "pdf" else "docx_path"
                artifacts.append((Path(str(release[key])), f"{title}.{output_format}"))
            elif document.get("kind") == "presentation" and document.get("output_format") == "pptx":
                path = multi_document_service._content_path(project, document)
                if not path.is_file():
                    raise DocumentWorkspaceError(f"正式课件文件不存在：{title}")
                artifacts.append((path, f"{title}.pptx"))
            else:
                raise DocumentWorkspaceError(f"正式文档输出格式无效：{title}")
        package_dir = artifacts[0][0].parent
        package = package_dir / f"{project_id}-formal-package-{uuid.uuid4().hex[:12]}.zip"
        temporary = package.with_suffix(".tmp")
        names: set[str] = set()
        try:
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
                for artifact, name in artifacts:
                    if name in names:
                        raise DocumentWorkspaceError("正式文档名称重复，无法生成交付包")
                    names.add(name)
                    archive.write(artifact, name)
            temporary.replace(package)
        finally:
            temporary.unlink(missing_ok=True)
        return FileResponse(
            package,
            filename=package.name,
            media_type="application/zip",
            background=BackgroundTask(package.unlink, missing_ok=True),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/workbook")
def get_workbook_metadata(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.workbook_metadata(_project(project_id), document_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/workbook/sheets/{sheet_name}")
def get_workbook_sheet(
    project_id: str,
    document_id: str,
    sheet_name: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.workbook_sheet(_project(project_id), document_id, sheet_name)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.patch("/projects/{project_id}/documents/{document_id}/workbook/sheets/{sheet_name}/cells")
def update_workbook_sheet_cells(
    project_id: str,
    document_id: str,
    sheet_name: str,
    req: WorkbookCellsUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        result = multi_document_service.update_workbook_cells(
            project,
            document_id,
            sheet_name,
            [row.model_dump() for row in req.cells],
            req.expected_revision,
            req.actor,
        )
        _refresh_technical_evaluation(project, document_id)
        return result
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.patch("/projects/{project_id}/documents/{document_id}/workbook/sheets/{sheet_name}")
def rename_workbook_sheet(
    project_id: str,
    document_id: str,
    sheet_name: str,
    req: WorkbookSheetRename,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        result = multi_document_service.rename_workbook_sheet(
            project,
            document_id,
            sheet_name,
            req.new_name,
            req.expected_revision,
        )
        _refresh_technical_evaluation(project, document_id)
        return result
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/source")
def download_project_document_source(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        path = multi_document_service.source_file(_project(project_id), document_id)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if path.suffix.lower() == ".xlsx"
            else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        return FileResponse(path, filename=path.name, media_type=media_type)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/presentation/preview")
def get_presentation_preview(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        path = multi_document_service.presentation_preview(_project(project_id), document_id)
        return FileResponse(path, filename=f"{document_id}.pdf", media_type="application/pdf")
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/presentation/manifest")
def get_presentation_manifest(
    project_id: str,
    document_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.presentation_manifest(
            _project(project_id), document_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/presentation/slide-proposals")
def create_presentation_slide_proposal(
    project_id: str,
    document_id: str,
    req: PresentationSlideProposalCreate,
    _user: dict = Depends(get_current_user),
):
    try:
        return multi_document_service.presentation_slide_proposal(
            _project(project_id),
            document_id,
            req.slide,
            req.draft,
            req.instruction,
            req.agent_id,
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/documents/{document_id}/presentation/slide-jobs")
def create_presentation_slide_job(
    project_id: str,
    document_id: str,
    req: PresentationSlideProposalCreate,
    user: dict = Depends(get_current_user),
):
    try:
        return writing_workbench_service.submit_presentation_job(
            _project(project_id),
            document_id,
            req.model_dump(),
            _actor(user),
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/documents/{document_id}/presentation/slide-jobs/{job_id}")
def get_presentation_slide_job(
    project_id: str,
    document_id: str,
    job_id: str,
    _user: dict = Depends(get_current_user),
):
    try:
        _project(project_id)
        return writing_workbench_service.get_presentation_job(
            project_id, document_id, job_id
        )
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/workspace")
def get_workspace(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        return document_workspace_service.workspace(_project(project_id))
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/sections/{section_id}")
def get_section(project_id: str, section_id: str, _user: dict = Depends(get_current_user)):
    try:
        return document_workspace_service.section(_project(project_id), section_id)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/fulltext")
def get_fulltext(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        return document_workspace_service.fulltext(_project(project_id))
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.put("/projects/{project_id}/sections/{section_id}")
def update_section(
    project_id: str,
    section_id: str,
    req: SectionUpdate,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        result = document_workspace_service.update_section(
            project, section_id, req.content, req.expected_version, req.actor
        )
        index = multi_document_service.ensure_index(project)
        primary = next(
            (
                item
                for item in index.get("documents", [])
                if item.get("kind") == "rich_text" and item.get("is_primary")
            ),
            None,
        )
        if primary:
            _refresh_technical_evaluation(project, str(primary["id"]))
        return result
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/references")
def get_references(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        return document_workspace_service.references(_project(project_id))
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/graph")
def get_graph(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        return document_workspace_service.graph(_project(project_id))
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/quality")
def get_quality(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        return document_workspace_service.quality(_project(project_id))
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/versions")
def get_versions(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        return {"versions": document_workspace_service.versions(_project(project_id))}
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/assets")
def get_asset(
    project_id: str,
    path: str = Query(..., min_length=1),
    _user: dict = Depends(get_current_user),
):
    try:
        asset = document_workspace_service.asset_path(_project(project_id), path)
        return FileResponse(asset, filename=asset.name)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.get("/projects/{project_id}/source-word")
def get_source_word(project_id: str, _user: dict = Depends(get_current_user)):
    try:
        manifest = document_workspace_service.ensure_workspace(_project(project_id))
        if not manifest.get("source_word"):
            raise HTTPException(status_code=404, detail="未登记 Word 原文")
        path = Path(manifest["source_word"])
        return FileResponse(path, filename=path.name)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc


@router.post("/projects/{project_id}/export")
def export_document(
    project_id: str,
    req: ExportRequest,
    _user: dict = Depends(require_role("admin")),
):
    try:
        project = _project(project_id)
        if req.release_mode == "formal":
            raise DocumentWorkspaceError("旧版项目导出不支持正式发布；请从具体文档的 WordRelease 导出")
        path = document_workspace_service.export(project, req.format)
        deliverable = register_document_export(project, path, req.format)
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        response = FileResponse(path, filename=path.name, media_type=media_type)
        if deliverable:
            response.headers["X-Product-Deliverable-Id"] = str(deliverable["id"])
        return response
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc
