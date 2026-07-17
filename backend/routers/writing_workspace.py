"""Long-form writing workspace API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from project_manager import project_manager
from services.auth_service import get_current_user, require_role
from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceError,
    document_workspace_service,
)


router = APIRouter(prefix="/api/v3/writing", tags=["writing-workspace"])


class SectionUpdate(BaseModel):
    content: str = Field(min_length=1)
    expected_version: int = Field(ge=1)
    actor: str = "human-editor"


class ExportRequest(BaseModel):
    format: str = "docx"


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


def _project(project_id: str) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if "writing" not in (project.get("enabled_modules") or []):
        raise HTTPException(status_code=400, detail="Project has not enabled the writing module")
    return project


def _handle(error: DocumentWorkspaceError) -> HTTPException:
    if isinstance(error, DocumentVersionConflict):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


@router.post("/projects", status_code=201)
def create_writing_project(req: WritingProjectCreate, _user: dict = Depends(require_role("admin"))):
    name = req.name.strip()
    if any(
        str(project.get("name") or "").strip().casefold() == name.casefold()
        for project in project_manager.list_projects()
    ):
        raise HTTPException(status_code=409, detail="已存在同名项目，请使用不同的文档名称")
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
        return document_workspace_service.update_section(
            _project(project_id), section_id, req.content, req.expected_version, req.actor
        )
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
        path = document_workspace_service.export(_project(project_id), req.format)
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(path, filename=path.name, media_type=media_type)
    except DocumentWorkspaceError as exc:
        raise _handle(exc) from exc
