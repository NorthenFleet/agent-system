"""Structured diagram authority, versions, AI proposals, and references."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from agent_messenger import OpenClawEmptyResponseError, agent_messenger
from database import SessionLocal
from models.writing_collaboration import (
    WritingChangeEvent,
    WritingDiagramAiJob,
    WritingDiagramAiProposal,
    WritingDiagramReference,
    WritingDiagramState,
    WritingDiagramVersion,
)
from services.document_workspace_service import (
    DocumentVersionConflict,
    DocumentWorkspaceError,
)
from services.multi_document_service import MultiDocumentService, multi_document_service
from services.writing_collaboration_service import (
    WritingCollaborationService,
    writing_collaboration_service,
)


AgentRequester = Callable[[str, str], Awaitable[str]]
ALLOWED_CELL_TYPES = {"node", "edge", "group", "text", "image"}
ALLOWED_OPERATIONS = {
    "add_cell",
    "update_cell",
    "delete_cell",
    "move_cell",
    "connect_cells",
    "group_cells",
    "apply_style",
    "apply_layout",
}
ALLOWED_EXPORT_FORMATS = {"svg", "png", "pdf", "json"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _cell_body(cell: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in cell.items() if key != "cell_revision"}


def _default_page() -> dict[str, Any]:
    return {"width": 1600, "height": 900, "background": "#ffffff", "grid_size": 8}


def _node(
    cell_id: str,
    label: str,
    x: int,
    y: int,
    *,
    shape: str = "rect",
    fill: str = "#f8fafc",
    stroke: str = "#64748b",
    width: int = 190,
    height: int = 64,
) -> dict[str, Any]:
    return {
        "id": cell_id,
        "cell_revision": 1,
        "type": "node",
        "shape": shape,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "label": label,
        "attrs": {
            "body": {"fill": fill, "stroke": stroke, "strokeWidth": 1.5, "rx": 6, "ry": 6},
            "label": {"fill": "#172033", "fontSize": 15, "fontWeight": 600},
        },
    }


def _edge(cell_id: str, source: str, target: str, label: str = "") -> dict[str, Any]:
    return {
        "id": cell_id,
        "cell_revision": 1,
        "type": "edge",
        "shape": "edge",
        "source": source,
        "target": target,
        "label": label,
        "attrs": {
            "line": {
                "stroke": "#64748b",
                "strokeWidth": 1.5,
                "targetMarker": {"name": "block", "width": 10, "height": 8},
            }
        },
    }


def _template(template_id: str) -> list[dict[str, Any]]:
    templates: dict[str, list[dict[str, Any]]] = {
        "blank": [],
        "thesis-roadmap": [
            _node("problem", "科学问题", 90, 160, fill="#fff7ed", stroke="#d97706"),
            _node("model", "统一建模", 370, 80, fill="#eff6ff", stroke="#2563eb"),
            _node("planning", "任务规划", 370, 240, fill="#eefbf3", stroke="#15803d"),
            _node("validation", "仿真验证", 650, 160, fill="#faf5ff", stroke="#7e22ce"),
            _node("evidence", "结论与证据", 930, 160, fill="#f8fafc", stroke="#475569"),
            _edge("e1", "problem", "model"),
            _edge("e2", "problem", "planning"),
            _edge("e3", "model", "validation"),
            _edge("e4", "planning", "validation"),
            _edge("e5", "validation", "evidence"),
        ],
        "system-architecture": [
            _node("input", "任务与数据输入", 80, 180, fill="#f8fafc"),
            _node("agent", "智能体协同层", 360, 80, fill="#eff6ff", stroke="#2563eb"),
            _node("planning", "规划与决策层", 360, 260, fill="#eefbf3", stroke="#15803d"),
            _node("runtime", "执行与仿真层", 650, 170, fill="#fff7ed", stroke="#d97706"),
            _node("evidence", "记录与评价", 940, 170, fill="#faf5ff", stroke="#7e22ce"),
            _edge("e1", "input", "agent"),
            _edge("e2", "input", "planning"),
            _edge("e3", "agent", "runtime"),
            _edge("e4", "planning", "runtime"),
            _edge("e5", "runtime", "evidence"),
        ],
        "ooda": [
            _node("observe", "观察 Observe", 180, 80, shape="ellipse", fill="#eff6ff", stroke="#2563eb"),
            _node("orient", "判断 Orient", 520, 80, shape="ellipse", fill="#eefbf3", stroke="#15803d"),
            _node("decide", "决策 Decide", 520, 300, shape="ellipse", fill="#fff7ed", stroke="#d97706"),
            _node("act", "行动 Act", 180, 300, shape="ellipse", fill="#faf5ff", stroke="#7e22ce"),
            _edge("e1", "observe", "orient"),
            _edge("e2", "orient", "decide"),
            _edge("e3", "decide", "act"),
            _edge("e4", "act", "observe", "反馈"),
        ],
    }
    return copy.deepcopy(templates.get(template_id, templates["blank"]))


class DiagramService:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        documents_service: MultiDocumentService = multi_document_service,
        collaboration_service: WritingCollaborationService = writing_collaboration_service,
        ai_requester: AgentRequester | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.documents_service = documents_service
        self.collaboration_service = collaboration_service
        self.ai_requester = ai_requester or agent_messenger.request_agent

    def _document(self, project: dict[str, Any], document_id: str) -> dict[str, Any]:
        record = self.documents_service.get_document(project, document_id)
        if record.get("kind") != "diagram":
            raise DocumentWorkspaceError("目标资源不是图表")
        return record

    def _state(self, session, project_id: str, document_id: str, *, lock: bool = False) -> WritingDiagramState:
        query = select(WritingDiagramState).where(
            WritingDiagramState.project_id == project_id,
            WritingDiagramState.document_id == document_id,
        )
        if lock:
            query = query.with_for_update()
        row = session.execute(query).scalar_one_or_none()
        if not row:
            raise DocumentWorkspaceError("图表结构化状态不存在")
        return row

    def _state_dict(self, row: WritingDiagramState) -> dict[str, Any]:
        return {
            "schema_version": row.schema_version,
            "project_id": row.project_id,
            "document_id": row.document_id,
            "revision": row.diagram_revision,
            "title": row.title,
            "diagram_type": row.diagram_type,
            "theme_id": row.theme_id,
            "page_settings": copy.deepcopy(row.page_settings or {}),
            "cells": copy.deepcopy(row.cells or []),
            "content_sha256": row.content_sha256,
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    def _validate_cells(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise DocumentWorkspaceError("图表 cells 必须是数组")
        if len(value) > 1000:
            raise DocumentWorkspaceError("单个图表最多支持 1000 个元素")
        cells: list[dict[str, Any]] = []
        ids: set[str] = set()
        for raw in value:
            if not isinstance(raw, dict):
                raise DocumentWorkspaceError("图表元素必须是对象")
            cell = copy.deepcopy(raw)
            cell_id = str(cell.get("id") or "").strip()
            if not cell_id or len(cell_id) > 96 or cell_id in ids:
                raise DocumentWorkspaceError("图表元素 ID 缺失、重复或过长")
            ids.add(cell_id)
            cell_type = str(cell.get("type") or ("edge" if cell.get("source") else "node"))
            if cell_type not in ALLOWED_CELL_TYPES:
                raise DocumentWorkspaceError(f"不支持的图表元素类型：{cell_type}")
            cell["id"] = cell_id
            cell["type"] = cell_type
            cells.append(cell)
        node_ids = {cell["id"] for cell in cells if cell["type"] != "edge"}
        for cell in cells:
            if cell["type"] != "edge":
                continue
            source = self._endpoint_id(cell.get("source"))
            target = self._endpoint_id(cell.get("target"))
            if source not in node_ids or target not in node_ids:
                raise DocumentWorkspaceError(f"连线 {cell['id']} 引用了不存在的节点")
        return cells

    @staticmethod
    def _endpoint_id(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("cell") or value.get("cell_id") or value.get("id") or "")
        return str(value or "")

    def _with_cell_revisions(
        self,
        previous: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        old = {str(cell.get("id")): cell for cell in previous}
        result = []
        for cell in incoming:
            prior = old.get(cell["id"])
            if not prior:
                revision = 1
            elif _cell_body(prior) == _cell_body(cell):
                revision = int(prior.get("cell_revision") or 1)
            else:
                revision = int(prior.get("cell_revision") or 1) + 1
            result.append({**cell, "cell_revision": revision})
        return result

    def create(
        self,
        project: dict[str, Any],
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        title = str(payload.get("title") or "新建图表").strip()
        template_id = str(payload.get("template_id") or "blank")
        cells = self._validate_cells(payload.get("cells") if "cells" in payload else _template(template_id))
        cells = self._with_cell_revisions([], cells)
        record = self.documents_service.create_document(
            project,
            title,
            "diagram",
            is_output_product=False,
            publication_status="internal",
            product_type="diagram_asset",
            edit_policy="editable",
            delivery_role="candidate",
        )
        snapshot = {
            "schema_version": 1,
            "title": title,
            "diagram_type": str(payload.get("diagram_type") or "flowchart"),
            "theme_id": str(payload.get("theme_id") or "academic"),
            "page_settings": {**_default_page(), **copy.deepcopy(payload.get("page_settings") or {})},
            "cells": cells,
        }
        with self.session_factory() as session:
            state = WritingDiagramState(
                id=_uuid("diagram"),
                project_id=str(project.get("id") or ""),
                document_id=str(record["id"]),
                schema_version=1,
                diagram_revision=1,
                title=title,
                diagram_type=snapshot["diagram_type"],
                theme_id=snapshot["theme_id"],
                page_settings=snapshot["page_settings"],
                cells=cells,
                content_sha256=_sha(snapshot),
            )
            session.add(state)
            session.add(self._version_row(state, label="初始版本", reason="create", actor_type="human", actor_id=actor))
            session.commit()
            session.refresh(state)
            return {"document": record, "diagram": self._state_dict(state)}

    def list(self, project: dict[str, Any]) -> dict[str, Any]:
        project_id = str(project.get("id") or "")
        records = [
            row
            for row in self.documents_service.list_documents(project, include_archived=True).get("documents", [])
            if row.get("kind") == "diagram"
        ]
        with self.session_factory() as session:
            states = {
                row.document_id: row
                for row in session.execute(
                    select(WritingDiagramState).where(WritingDiagramState.project_id == project_id)
                ).scalars()
            }
        return {
            "diagrams": [
                {**record, "diagram": self._state_dict(states[record["id"]]) if record["id"] in states else None}
                for record in records
            ]
        }

    def get(self, project: dict[str, Any], document_id: str) -> dict[str, Any]:
        record = self._document(project, document_id)
        with self.session_factory() as session:
            return {"document": record, "diagram": self._state_dict(self._state(session, str(project["id"]), document_id))}

    def update_draft(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self.documents_service.assert_writable(project, document_id)
        self._document(project, document_id)
        expected = int(payload.get("expected_revision") or 0)
        incoming = payload.get("document") or payload
        project_id = str(project.get("id") or "")
        with self.session_factory() as session:
            state = self._state(session, project_id, document_id, lock=True)
            if expected != state.diagram_revision:
                raise DocumentVersionConflict(f"图表已更新：当前修订 {state.diagram_revision}")
            cells = self._with_cell_revisions(
                copy.deepcopy(state.cells or []),
                self._validate_cells(incoming.get("cells") or []),
            )
            state.diagram_revision += 1
            state.title = str(incoming.get("title") or state.title)[:200]
            state.diagram_type = str(incoming.get("diagram_type") or state.diagram_type)[:48]
            state.theme_id = str(incoming.get("theme_id") or state.theme_id)[:48]
            state.page_settings = {**_default_page(), **copy.deepcopy(incoming.get("page_settings") or state.page_settings or {})}
            state.cells = cells
            snapshot = self._state_snapshot(state)
            state.content_sha256 = _sha(snapshot)
            state.updated_at = _now()
            session.execute(
                update(WritingDiagramReference)
                .where(
                    WritingDiagramReference.project_id == project_id,
                    WritingDiagramReference.diagram_document_id == document_id,
                    WritingDiagramReference.diagram_revision < state.diagram_revision,
                )
                .values(status="update_available", updated_at=_now())
            )
            session.commit()
            session.refresh(state)
            return self._state_dict(state)

    def _state_snapshot(self, state: WritingDiagramState) -> dict[str, Any]:
        return {
            "schema_version": state.schema_version,
            "title": state.title,
            "diagram_type": state.diagram_type,
            "theme_id": state.theme_id,
            "page_settings": copy.deepcopy(state.page_settings or {}),
            "cells": copy.deepcopy(state.cells or []),
        }

    def _version_row(
        self,
        state: WritingDiagramState,
        *,
        label: str,
        reason: str,
        actor_type: str,
        actor_id: str,
    ) -> WritingDiagramVersion:
        snapshot = self._state_snapshot(state)
        return WritingDiagramVersion(
            id=_uuid("diagram-version"),
            project_id=state.project_id,
            document_id=state.document_id,
            diagram_revision=state.diagram_revision,
            label=label[:160],
            reason=reason[:40],
            snapshot_json=snapshot,
            content_sha256=_sha(snapshot),
            actor_type=actor_type[:16],
            actor_id=actor_id[:64],
        )

    def create_version(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._document(project, document_id)
        with self.session_factory() as session:
            state = self._state(session, str(project["id"]), document_id)
            existing = session.execute(select(WritingDiagramVersion).where(
                WritingDiagramVersion.project_id == state.project_id,
                WritingDiagramVersion.document_id == document_id,
                WritingDiagramVersion.diagram_revision == state.diagram_revision,
            )).scalar_one_or_none()
            if not existing:
                existing = self._version_row(
                    state,
                    label=str(payload.get("label") or f"修订 {state.diagram_revision}"),
                    reason=str(payload.get("reason") or "manual"),
                    actor_type="human",
                    actor_id=actor,
                )
                session.add(existing)
                session.commit()
            return self._version_dict(existing)

    @staticmethod
    def _version_dict(row: WritingDiagramVersion) -> dict[str, Any]:
        return {
            "id": row.id,
            "revision": row.diagram_revision,
            "label": row.label,
            "reason": row.reason,
            "content_sha256": row.content_sha256,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    def list_versions(self, project: dict[str, Any], document_id: str) -> list[dict[str, Any]]:
        self._document(project, document_id)
        with self.session_factory() as session:
            rows = session.execute(
                select(WritingDiagramVersion)
                .where(
                    WritingDiagramVersion.project_id == str(project["id"]),
                    WritingDiagramVersion.document_id == document_id,
                )
                .order_by(WritingDiagramVersion.diagram_revision.desc())
            ).scalars()
            return [self._version_dict(row) for row in rows]

    def _svg(self, state: WritingDiagramState) -> str:
        page = {**_default_page(), **(state.page_settings or {})}
        width = max(320, int(page.get("width") or 1600))
        height = max(240, int(page.get("height") or 900))
        background = html.escape(str(page.get("background") or "#ffffff"), quote=True)
        cells = copy.deepcopy(state.cells or [])
        nodes = {cell["id"]: cell for cell in cells if cell.get("type") != "edge"}
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#64748b"/></marker></defs>',
            f'<rect width="100%" height="100%" fill="{background}"/>',
        ]
        for cell in cells:
            if cell.get("type") != "edge":
                continue
            source = nodes.get(self._endpoint_id(cell.get("source")))
            target = nodes.get(self._endpoint_id(cell.get("target")))
            if not source or not target:
                continue
            source_x = float(source.get("x") or 0)
            source_y = float(source.get("y") or 0)
            source_width = float(source.get("width") or 160)
            source_height = float(source.get("height") or 56)
            target_x = float(target.get("x") or 0)
            target_y = float(target.get("y") or 0)
            target_width = float(target.get("width") or 160)
            target_height = float(target.get("height") or 56)
            source_cx = source_x + source_width / 2
            source_cy = source_y + source_height / 2
            target_cx = target_x + target_width / 2
            target_cy = target_y + target_height / 2
            vertical = abs(target_cy - source_cy) >= abs(target_cx - source_cx)
            if vertical:
                downward = target_cy >= source_cy
                sx, sy = source_cx, source_y + source_height if downward else source_y
                tx, ty = target_cx, target_y if downward else target_y + target_height
            else:
                rightward = target_cx >= source_cx
                sx, sy = source_x + source_width if rightward else source_x, source_cy
                tx, ty = target_x if rightward else target_x + target_width, target_cy
            line = ((cell.get("attrs") or {}).get("line") or {})
            stroke = html.escape(str(line.get("stroke") or "#64748b"), quote=True)
            stroke_width = float(line.get("strokeWidth") or 1.5)
            if vertical:
                middle = (sy + ty) / 2
                path = f"M {sx:.1f} {sy:.1f} L {sx:.1f} {middle:.1f} L {tx:.1f} {middle:.1f} L {tx:.1f} {ty:.1f}"
                label_x, label_y = (sx + tx) / 2, middle - 6
            else:
                middle = (sx + tx) / 2
                path = f"M {sx:.1f} {sy:.1f} L {middle:.1f} {sy:.1f} L {middle:.1f} {ty:.1f} L {tx:.1f} {ty:.1f}"
                label_x, label_y = middle, (sy + ty) / 2 - 6
            parts.append(
                f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" marker-end="url(#arrow)"/>'
            )
            label = str(cell.get("label") or "")
            if label:
                parts.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="13" fill="#475569">{html.escape(label)}</text>')
        for cell in cells:
            if cell.get("type") == "edge":
                continue
            x = float(cell.get("x") or 0)
            y = float(cell.get("y") or 0)
            width_value = float(cell.get("width") or 160)
            height_value = float(cell.get("height") or 56)
            attrs = cell.get("attrs") or {}
            body = attrs.get("body") or {}
            label_style = attrs.get("label") or {}
            fill = html.escape(str(body.get("fill") or "#f8fafc"), quote=True)
            stroke = html.escape(str(body.get("stroke") or "#64748b"), quote=True)
            stroke_width = float(body.get("strokeWidth") or 1.5)
            shape = str(cell.get("shape") or "rect")
            if shape in {"ellipse", "circle"}:
                parts.append(f'<ellipse cx="{x + width_value / 2:.1f}" cy="{y + height_value / 2:.1f}" rx="{width_value / 2:.1f}" ry="{height_value / 2:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>')
            elif shape in {"polygon", "diamond"}:
                points = f"{x + width_value / 2:.1f},{y:.1f} {x + width_value:.1f},{y + height_value / 2:.1f} {x + width_value / 2:.1f},{y + height_value:.1f} {x:.1f},{y + height_value / 2:.1f}"
                parts.append(f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>')
            else:
                radius = float(body.get("rx") or 6)
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{width_value:.1f}" height="{height_value:.1f}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>')
            label = str(cell.get("label") or "")
            color = html.escape(str(label_style.get("fill") or "#172033"), quote=True)
            font_size = float(label_style.get("fontSize") or 15)
            lines = label.splitlines() or [""]
            line_height = font_size * 1.35
            first_y = y + height_value / 2 - (len(lines) - 1) * line_height / 2 + font_size / 3
            tspans = "".join(
                f'<tspan x="{x + width_value / 2:.1f}" y="{first_y + index * line_height:.1f}">{html.escape(line)}</tspan>'
                for index, line in enumerate(lines)
            )
            parts.append(f'<text text-anchor="middle" font-family="Arial, PingFang SC, sans-serif" font-size="{font_size}" fill="{color}">{tspans}</text>')
        parts.append("</svg>")
        return "".join(parts)

    def export(
        self,
        project: dict[str, Any],
        document_id: str,
        export_format: str,
        actor: str,
    ) -> Path:
        export_format = export_format.lower()
        if export_format not in ALLOWED_EXPORT_FORMATS:
            raise DocumentWorkspaceError("图表仅支持 SVG、PNG、PDF 或 JSON 导出")
        record = self._document(project, document_id)
        with self.session_factory() as session:
            state = self._state(session, str(project["id"]), document_id)
            existing = session.execute(select(WritingDiagramVersion).where(
                WritingDiagramVersion.project_id == state.project_id,
                WritingDiagramVersion.document_id == document_id,
                WritingDiagramVersion.diagram_revision == state.diagram_revision,
            )).scalar_one_or_none()
            if not existing:
                session.add(self._version_row(state, label="导出检查点", reason="export", actor_type="human", actor_id=actor))
                session.commit()
            root = self.documents_service._document_root(project, record["id"]) / "exports"  # noqa: SLF001
            root.mkdir(parents=True, exist_ok=True)
            target = root / f"diagram-r{state.diagram_revision}.{export_format}"
            if export_format == "json":
                target.write_text(json.dumps(self._state_snapshot(state), ensure_ascii=False, indent=2), encoding="utf-8")
                return target
            svg = self._svg(state)
            svg_target = root / f"diagram-r{state.diagram_revision}.svg"
            svg_target.write_text(svg, encoding="utf-8")
            if export_format == "svg":
                return svg_target
            converter = shutil.which("convert") or shutil.which("magick")
            if not converter:
                raise DocumentWorkspaceError("服务器缺少图表 PNG/PDF 转换器")
            command = [converter, "-density", "192", str(svg_target), str(target)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
            if completed.returncode != 0 or not target.is_file():
                raise DocumentWorkspaceError(completed.stderr.strip() or "图表导出失败")
            return target

    @staticmethod
    def _parse_ai_payload(response: str) -> dict[str, Any]:
        value = response.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", value, flags=re.S)
        if fenced:
            value = fenced.group(1)
        else:
            start = value.find("{")
            end = value.rfind("}")
            if start >= 0 and end > start:
                value = value[start : end + 1]
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise DocumentWorkspaceError("AI 未返回有效的图表操作 JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("operations"), list):
            raise DocumentWorkspaceError("AI 图表建议缺少 operations")
        return payload

    def _ai_prompt(self, state: WritingDiagramState, job: WritingDiagramAiJob) -> str:
        return "\n".join([
            "你是结构化图表编辑智能体。只返回 JSON，不返回 Markdown 说明。",
            "这是用户显式发起的任务，禁止返回 NO_REPLY、HEARTBEAT_OK 或空内容。",
            "允许操作：" + ", ".join(sorted(ALLOWED_OPERATIONS)) + "。",
            "返回格式：{\"summary\":\"...\",\"rationale\":\"...\",\"risk_level\":\"low|medium|high\",\"operations\":[...]}。",
            "每个操作必须包含 action；修改已有元素时包含 cell_id；新增元素时包含 cell。",
            "新增节点 cell 的 type 只能是 node、text、group 或 image；矩形节点必须写 type=node、shape=rect。",
            "新增连线 cell 必须写 type=edge，并使用现有或本次新增节点 ID 作为 source 和 target。",
            "每个 add_cell 只能包含一个 cell，不得重复 JSON 键；节点文字写在 label 字段。",
            "不要删除或改写未授权元素；不要输出整图覆盖。",
            f"用户指令：{job.instruction}",
            f"当前修订：{state.diagram_revision}",
            "授权元素：" + json.dumps(job.target_snapshot, ensure_ascii=False),
            "页面设置：" + json.dumps(state.page_settings or {}, ensure_ascii=False),
        ])

    def _ai_retry_prompt(self, state: WritingDiagramState, job: WritingDiagramAiJob) -> str:
        return "\n".join([
            "上一次响应为空。请立即完成这次用户显式请求。",
            "禁止返回 NO_REPLY、HEARTBEAT_OK、Markdown 或解释性前言。",
            "只返回一个紧凑 JSON 对象，operations 至少包含一项可执行操作。",
            self._ai_prompt(state, job),
        ])

    def _job_dict(self, row: WritingDiagramAiJob, proposal: WritingDiagramAiProposal | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "document_id": row.document_id,
            "status": row.status,
            "base_revision": row.base_diagram_revision,
            "target_cell_ids": copy.deepcopy(row.target_cell_ids or []),
            "error": row.error,
            "proposal": self._proposal_dict(proposal) if proposal else None,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    @staticmethod
    def _proposal_dict(row: WritingDiagramAiProposal) -> dict[str, Any]:
        return {
            "id": row.id,
            "job_id": row.job_id,
            "status": row.status,
            "base_revision": row.base_diagram_revision,
            "operations": copy.deepcopy(row.operations or []),
            "summary": row.summary,
            "rationale": row.rationale,
            "risk_level": row.risk_level,
            "conflicts": copy.deepcopy(row.conflicts or []),
        }

    async def submit_ai_job(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self.documents_service.assert_writable(project, document_id)
        self._document(project, document_id)
        project_id = str(project["id"])
        client_id = str(payload.get("client_request_id") or _uuid("diagram-request"))[:96]
        with self.session_factory() as session:
            existing = session.execute(select(WritingDiagramAiJob).where(
                WritingDiagramAiJob.project_id == project_id,
                WritingDiagramAiJob.document_id == document_id,
                WritingDiagramAiJob.client_request_id == client_id,
            )).scalar_one_or_none()
            if existing:
                proposal = session.execute(select(WritingDiagramAiProposal).where(WritingDiagramAiProposal.job_id == existing.id)).scalar_one_or_none()
                return self._job_dict(existing, proposal)
            state = self._state(session, project_id, document_id)
            cells = {str(cell.get("id")): cell for cell in state.cells or []}
            target_ids = list(dict.fromkeys(str(value) for value in payload.get("target_cell_ids") or [] if str(value)))
            if any(cell_id not in cells for cell_id in target_ids):
                raise DocumentWorkspaceError("AI目标包含不存在的图表元素")
            selected = target_ids or list(cells)
            snapshot = {cell_id: copy.deepcopy(cells[cell_id]) for cell_id in selected}
            row = WritingDiagramAiJob(
                id=_uuid("diagram-job"),
                project_id=project_id,
                document_id=document_id,
                client_request_id=client_id,
                agent_id=str(payload.get("agent_id") or "ultra-magnus")[:64],
                instruction=str(payload.get("instruction") or "").strip(),
                base_diagram_revision=state.diagram_revision,
                target_cell_ids=target_ids,
                target_snapshot=snapshot,
                status="running",
                requested_by=actor,
                started_at=_now(),
            )
            session.add(row)
            session.commit()
            job_id = row.id
            prompt = self._ai_prompt(state, row)
            retry_prompt = self._ai_retry_prompt(state, row)
            agent_id = row.agent_id
        try:
            try:
                response = await self.ai_requester(agent_id, prompt)
            except OpenClawEmptyResponseError:
                response = await self.ai_requester(agent_id, retry_prompt)
            result = self._parse_ai_payload(response)
            operations = []
            for operation in result.get("operations") or []:
                if not isinstance(operation, dict) or operation.get("action") not in ALLOWED_OPERATIONS:
                    raise DocumentWorkspaceError("AI返回了不允许的图表操作")
                operations.append(copy.deepcopy(operation))
            with self.session_factory() as session:
                job = session.get(WritingDiagramAiJob, job_id)
                proposal = WritingDiagramAiProposal(
                    id=_uuid("diagram-proposal"),
                    job_id=job_id,
                    project_id=project_id,
                    document_id=document_id,
                    base_diagram_revision=job.base_diagram_revision,
                    base_cell_revisions={
                        cell_id: int((cell or {}).get("cell_revision") or 1)
                        for cell_id, cell in (job.target_snapshot or {}).items()
                    },
                    operations=operations,
                    summary=str(result.get("summary") or "已生成图表修改建议")[:4000],
                    rationale=str(result.get("rationale") or "")[:8000],
                    risk_level=str(result.get("risk_level") or "medium") if str(result.get("risk_level") or "medium") in {"low", "medium", "high"} else "medium",
                    status="pending",
                )
                session.add(proposal)
                job.status = "succeeded"
                job.finished_at = _now()
                session.commit()
                session.refresh(proposal)
                return self._job_dict(job, proposal)
        except Exception as exc:
            with self.session_factory() as session:
                job = session.get(WritingDiagramAiJob, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(exc)[:4000]
                    job.finished_at = _now()
                    session.commit()
            raise

    def get_ai_job(self, project: dict[str, Any], document_id: str, job_id: str) -> dict[str, Any]:
        self._document(project, document_id)
        with self.session_factory() as session:
            row = session.get(WritingDiagramAiJob, job_id)
            if not row or row.project_id != str(project["id"]) or row.document_id != document_id:
                raise DocumentWorkspaceError("图表AI任务不存在")
            proposal = session.execute(select(WritingDiagramAiProposal).where(WritingDiagramAiProposal.job_id == row.id)).scalar_one_or_none()
            return self._job_dict(row, proposal)

    def _apply_operation(self, cells: dict[str, dict[str, Any]], operation: dict[str, Any]) -> None:
        action = str(operation.get("action") or "")
        cell_id = str(operation.get("cell_id") or "")
        if action == "add_cell":
            cell = self._validate_cells([operation.get("cell") or {}])[0]
            if cell["id"] in cells:
                raise DocumentWorkspaceError(f"新增元素已存在：{cell['id']}")
            cells[cell["id"]] = cell
        elif action == "update_cell":
            patch = copy.deepcopy(operation.get("patch") or {})
            patch.pop("id", None)
            cells[cell_id] = {**cells[cell_id], **patch}
        elif action == "delete_cell":
            cells.pop(cell_id, None)
            for edge_id in [key for key, cell in cells.items() if cell.get("type") == "edge" and cell_id in {self._endpoint_id(cell.get("source")), self._endpoint_id(cell.get("target"))}]:
                cells.pop(edge_id, None)
        elif action == "move_cell":
            cells[cell_id]["x"] = float(operation.get("x") or 0)
            cells[cell_id]["y"] = float(operation.get("y") or 0)
        elif action == "apply_style":
            attrs = copy.deepcopy(cells[cell_id].get("attrs") or {})
            for key, value in (operation.get("attrs") or {}).items():
                attrs[key] = {**(attrs.get(key) or {}), **value} if isinstance(value, dict) else value
            cells[cell_id]["attrs"] = attrs
        elif action == "connect_cells":
            edge_id = str(operation.get("edge_id") or _uuid("edge"))[:96]
            cells[edge_id] = _edge(edge_id, str(operation.get("source_id") or ""), str(operation.get("target_id") or ""), str(operation.get("label") or ""))
        elif action == "group_cells":
            parent_id = str(operation.get("group_id") or "")
            for target_id in operation.get("cell_ids") or []:
                if str(target_id) in cells:
                    cells[str(target_id)]["parent"] = parent_id
        elif action == "apply_layout":
            for target_id, position in (operation.get("positions") or {}).items():
                if target_id in cells and isinstance(position, dict):
                    cells[target_id]["x"] = float(position.get("x") or 0)
                    cells[target_id]["y"] = float(position.get("y") or 0)

    def accept_proposal(
        self,
        project: dict[str, Any],
        document_id: str,
        proposal_id: str,
        actor: str,
    ) -> dict[str, Any]:
        self.documents_service.assert_writable(project, document_id)
        project_id = str(project["id"])
        with self.session_factory() as session:
            proposal = session.execute(select(WritingDiagramAiProposal).where(
                WritingDiagramAiProposal.id == proposal_id,
                WritingDiagramAiProposal.project_id == project_id,
                WritingDiagramAiProposal.document_id == document_id,
            ).with_for_update()).scalar_one_or_none()
            if not proposal:
                raise DocumentWorkspaceError("图表AI建议不存在")
            if proposal.status not in {"pending", "conflicted", "partially_applied"}:
                return self._proposal_dict(proposal)
            state = self._state(session, project_id, document_id, lock=True)
            current = {str(cell.get("id")): copy.deepcopy(cell) for cell in state.cells or []}
            before = copy.deepcopy(list(current.values()))
            conflicts = []
            applied = 0
            for operation in proposal.operations or []:
                action = str(operation.get("action") or "")
                target_ids = []
                if operation.get("cell_id"):
                    target_ids.append(str(operation["cell_id"]))
                target_ids.extend(str(value) for value in operation.get("cell_ids") or [])
                target_ids.extend(str(value) for value in (operation.get("positions") or {}).keys())
                conflict = next((cell_id for cell_id in target_ids if cell_id in proposal.base_cell_revisions and int((current.get(cell_id) or {}).get("cell_revision") or 0) != int(proposal.base_cell_revisions[cell_id])), None)
                if conflict:
                    conflicts.append({"cell_id": conflict, "reason": "目标元素已由人工或其他任务更新"})
                    continue
                if action not in ALLOWED_OPERATIONS:
                    conflicts.append({"cell_id": "", "reason": f"不支持的操作：{action}"})
                    continue
                try:
                    self._apply_operation(current, operation)
                    applied += 1
                except (KeyError, TypeError, ValueError, DocumentWorkspaceError) as exc:
                    conflicts.append({"cell_id": target_ids[0] if target_ids else "", "reason": str(exc)})
            cells = self._with_cell_revisions(before, self._validate_cells(list(current.values())))
            if applied:
                state.cells = cells
                state.diagram_revision += 1
                state.content_sha256 = _sha(self._state_snapshot(state))
                state.updated_at = _now()
                session.add(self._version_row(state, label="AI建议应用", reason="ai_apply", actor_type="ai", actor_id=actor))
                session.execute(
                    update(WritingDiagramReference)
                    .where(
                        WritingDiagramReference.project_id == project_id,
                        WritingDiagramReference.diagram_document_id == document_id,
                        WritingDiagramReference.diagram_revision < state.diagram_revision,
                    )
                    .values(status="update_available", updated_at=_now())
                )
            proposal.conflicts = conflicts
            proposal.status = "partially_applied" if applied and conflicts else "conflicted" if conflicts else "applied"
            proposal.decided_by = actor[:64]
            proposal.decided_at = _now()
            session.commit()
            session.refresh(proposal)
            return {"proposal": self._proposal_dict(proposal), "diagram": self._state_dict(state)}

    def reject_proposal(self, project: dict[str, Any], document_id: str, proposal_id: str, actor: str) -> dict[str, Any]:
        self._document(project, document_id)
        with self.session_factory() as session:
            row = session.get(WritingDiagramAiProposal, proposal_id)
            if not row or row.project_id != str(project["id"]) or row.document_id != document_id:
                raise DocumentWorkspaceError("图表AI建议不存在")
            if row.status == "pending":
                row.status = "rejected"
                row.decided_by = actor[:64]
                row.decided_at = _now()
                session.commit()
            return self._proposal_dict(row)

    def create_reference(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        self._document(project, document_id)
        target_id = str(payload.get("target_document_id") or "")
        target = self.documents_service.get_document(project, target_id)
        target_kind = str(payload.get("target_kind") or target.get("kind") or "")
        if target_kind not in {"rich_text", "presentation"} or target.get("kind") != target_kind:
            raise DocumentWorkspaceError("图表只能引用到正文或PPT")
        with self.session_factory() as session:
            state = self._state(session, str(project["id"]), document_id)
            requested_revision = int(payload.get("diagram_version") or state.diagram_revision)
            if requested_revision != state.diagram_revision:
                version = session.execute(select(WritingDiagramVersion).where(
                    WritingDiagramVersion.project_id == str(project["id"]),
                    WritingDiagramVersion.document_id == document_id,
                    WritingDiagramVersion.diagram_revision == requested_revision,
                )).scalar_one_or_none()
                if not version:
                    raise DocumentWorkspaceError("指定的图表版本不存在")
            row = WritingDiagramReference(
                id=_uuid("diagram-ref"),
                project_id=str(project["id"]),
                diagram_document_id=document_id,
                diagram_revision=requested_revision,
                target_document_id=target_id,
                target_kind=target_kind,
                target_section_id=str(payload.get("target_section_id") or "")[:128],
                target_slide=int(payload["target_slide"]) if payload.get("target_slide") else None,
                export_format=str(payload.get("export_format") or "svg")[:16],
                crop_or_viewbox=copy.deepcopy(payload.get("crop_or_viewbox") or {}),
                caption=str(payload.get("caption") or state.title)[:500],
                status="current" if requested_revision == state.diagram_revision else "update_available",
                created_by=actor[:64],
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(select(WritingDiagramReference).where(
                    WritingDiagramReference.diagram_document_id == document_id,
                    WritingDiagramReference.diagram_revision == requested_revision,
                    WritingDiagramReference.target_document_id == target_id,
                    WritingDiagramReference.target_section_id == row.target_section_id,
                    WritingDiagramReference.target_slide == row.target_slide,
                )).scalar_one()
                row = existing
            return self._reference_dict(row)

    def publish_to_document(
        self,
        project: dict[str, Any],
        document_id: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        """Publish a fixed diagram revision into structured document authority."""
        self._document(project, document_id)
        target_id = str(payload.get("target_document_id") or "")
        target = self.documents_service.assert_writable(project, target_id)
        if target.get("kind") != "rich_text":
            raise DocumentWorkspaceError("图表正文发布仅支持可编辑正文文档")

        expected_diagram_revision = int(payload.get("expected_diagram_revision") or 0)
        expected_document_revision = int(payload.get("expected_document_revision") or 0)
        section_id = str(payload.get("target_section_id") or "")
        client_change_id = str(payload.get("client_change_id") or _uuid("diagram-publish"))[:96]
        project_id = str(project.get("id") or "")

        with self.session_factory() as session:
            replay = session.execute(select(WritingChangeEvent).where(
                WritingChangeEvent.project_id == project_id,
                WritingChangeEvent.document_id == target_id,
                WritingChangeEvent.client_change_id == client_change_id,
            )).scalar_one_or_none()
        if replay:
            references = [
                row for row in self.list_references(project, document_id)
                if row.get("target_document_id") == target_id
                and row.get("target_section_id", "") == section_id
            ]
            return {
                "idempotent_replay": True,
                "document": self.collaboration_service.get_state(project, target_id, section_id),
                "reference": references[0] if references else None,
            }

        with self.session_factory() as session:
            state = self._state(session, project_id, document_id)
            if expected_diagram_revision != state.diagram_revision:
                raise DocumentVersionConflict(
                    f"图表已更新：当前修订 {state.diagram_revision}"
                )
            svg_bytes = self._svg(state).encode("utf-8")
            diagram_revision = state.diagram_revision
            diagram_title = state.title

        collaboration = self.collaboration_service.get_state(project, target_id, section_id)
        current_document_revision = int(collaboration.get("document_revision") or 0)
        if expected_document_revision != current_document_revision:
            raise DocumentVersionConflict(
                f"正文修订不匹配，当前为 {current_document_revision}"
            )

        section_blocks = (collaboration.get("document") or {}).get("content") or []
        block_revisions = {
            str((block.get("attrs") or {}).get("blockId") or ""): int(
                (block.get("attrs") or {}).get("blockRevision") or 1
            )
            for block in section_blocks
        }
        anchor_id = str(payload.get("anchor_block_id") or "")
        if not anchor_id and section_blocks:
            anchor_id = str((section_blocks[-1].get("attrs") or {}).get("blockId") or "")
        if not anchor_id or anchor_id not in block_revisions:
            raise DocumentWorkspaceError("图表插入锚点不存在，请刷新正文后重试")

        replacement_ids = [str(value) for value in payload.get("replace_block_ids") or []]
        missing = [value for value in replacement_ids if value not in block_revisions]
        if missing:
            raise DocumentWorkspaceError("待替换的正文块不存在，请刷新正文后重试")

        asset = self.documents_service.upload_rich_text_asset(
            project,
            target_id,
            svg_bytes,
            f"{document_id}-r{diagram_revision}.svg",
            "image/svg+xml",
            actor=actor,
        )
        figure_label = str(payload.get("figure_label") or "").strip()
        caption = str(payload.get("caption") or diagram_title).strip()
        full_caption = " ".join(value for value in (figure_label, caption) if value)
        id_seed = hashlib.sha256(client_change_id.encode("utf-8")).hexdigest()[:20]
        image_block_id = f"block-diagram-{id_seed}"
        caption_block_id = f"block-diagram-caption-{id_seed}"
        image_node = {
            "type": "image",
            "attrs": {
                "src": asset["path"],
                "alt": full_caption,
                "title": full_caption,
                "width": str(payload.get("width") or "145mm"),
                "artifactKind": "figure",
                "artifactLabel": figure_label,
                "artifactTitle": caption,
            },
        }
        caption_node = {
            "type": "paragraph",
            "attrs": {
                "textAlign": "center",
                "artifactKind": "figure-caption",
                "artifactLabel": figure_label,
            },
            "content": [{"type": "text", "text": full_caption}],
        }
        operations = [
            {
                "op": "delete",
                "block_id": block_id,
                "expected_block_revision": block_revisions[block_id],
            }
            for block_id in replacement_ids
        ]
        operations.extend([
            {
                "op": "insert_after",
                "block_id": image_block_id,
                "after_block_id": anchor_id,
                "node": image_node,
            },
            {
                "op": "insert_after",
                "block_id": caption_block_id,
                "after_block_id": image_block_id,
                "node": caption_node,
            },
        ])

        reference = self.create_reference(
            project,
            document_id,
            {
                "diagram_version": diagram_revision,
                "target_kind": "rich_text",
                "target_document_id": target_id,
                "target_section_id": section_id,
                "export_format": str(payload.get("export_format") or "svg"),
                "caption": full_caption,
            },
            actor,
        )
        with self.session_factory() as session:
            row = session.get(WritingDiagramReference, reference["id"])
            if row:
                row.status = "publishing"
                session.commit()
        try:
            updated_document = self.collaboration_service.patch_draft(
                project,
                target_id,
                {
                    "section_id": section_id,
                    "expected_revision": expected_document_revision,
                    "client_change_id": client_change_id,
                    "operations": operations,
                },
                actor,
            )
        except Exception:
            with self.session_factory() as session:
                row = session.get(WritingDiagramReference, reference["id"])
                if row:
                    row.status = "failed"
                    session.commit()
            raise
        with self.session_factory() as session:
            row = session.get(WritingDiagramReference, reference["id"])
            if row:
                row.status = "current"
                session.commit()
                reference = self._reference_dict(row)
        return {
            "idempotent_replay": False,
            "diagram_revision": diagram_revision,
            "document_revision": updated_document.get("document_revision"),
            "inserted_block_ids": [image_block_id, caption_block_id],
            "asset": asset,
            "reference": reference,
            "document": updated_document,
        }

    @staticmethod
    def _reference_dict(row: WritingDiagramReference) -> dict[str, Any]:
        return {
            "id": row.id,
            "diagram_document_id": row.diagram_document_id,
            "diagram_revision": row.diagram_revision,
            "target_document_id": row.target_document_id,
            "target_kind": row.target_kind,
            "target_section_id": row.target_section_id,
            "target_slide": row.target_slide,
            "export_format": row.export_format,
            "crop_or_viewbox": copy.deepcopy(row.crop_or_viewbox or {}),
            "caption": row.caption,
            "status": row.status,
        }

    def list_references(self, project: dict[str, Any], document_id: str) -> list[dict[str, Any]]:
        self._document(project, document_id)
        with self.session_factory() as session:
            rows = session.execute(select(WritingDiagramReference).where(
                WritingDiagramReference.project_id == str(project["id"]),
                WritingDiagramReference.diagram_document_id == document_id,
            ).order_by(WritingDiagramReference.created_at.desc())).scalars()
            return [self._reference_dict(row) for row in rows]


diagram_service = DiagramService()
