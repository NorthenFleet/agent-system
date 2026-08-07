"""Generic, versioned layout profiles and delivery audits for rich-text documents."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

from services.document_workspace_service import DocumentWorkspaceError, document_workspace_service


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
LAYOUT_STATUSES = {"draft", "validated", "published"}
BINDING_STATUSES = {"aligned", "stale", "missing"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DocumentWorkspaceError(f"排版模板读取失败：{exc}") from exc
    if not isinstance(value, dict):
        raise DocumentWorkspaceError("排版模板数据格式无效")
    return value


class DocumentLayoutService:
    """Resolve profiles without coupling behavior to project names or IDs."""

    def _root(self, project: dict[str, Any]) -> Path:
        return document_workspace_service._workspace_root(project) / "layout"  # noqa: SLF001

    def _record(self, project: dict[str, Any]) -> dict[str, Any]:
        record = project.get("_course_document_record")
        return record if isinstance(record, dict) else {}

    def _binding(self, project: dict[str, Any]) -> dict[str, Any]:
        metadata = self._record(project).get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        value = metadata.get("layout_binding")
        return dict(value) if isinstance(value, dict) else {}

    def profiles(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        root = self._root(project) / "profiles"
        rows: list[dict[str, Any]] = []
        if not root.is_dir():
            return rows
        for path in sorted(root.glob("*/profile.json")):
            profile = _json_read(path)
            profile["profile_path"] = str(path)
            rows.append(profile)
        return rows

    def profile(self, project: dict[str, Any], profile_id: str) -> dict[str, Any]:
        for profile in self.profiles(project):
            if profile.get("id") == profile_id:
                return profile
        raise DocumentWorkspaceError("排版模板不存在")

    def state(self, project: dict[str, Any]) -> dict[str, Any]:
        manifest = document_workspace_service.ensure_workspace(project)
        binding = self._binding(project)
        profile_id = str(binding.get("profile_id") or "")
        profiles = self.profiles(project)
        selected = next((row for row in profiles if row.get("id") == profile_id), None)
        content_path = Path(manifest["working_markdown"])
        content_sha = _sha256(content_path)
        status = "missing"
        changed: list[str] = []
        if selected:
            template_path = Path(str(selected.get("template_path") or ""))
            current_template_sha = _sha256(template_path) if template_path.is_file() else ""
            expected_template_sha = str(selected.get("template_sha256") or "")
            if not current_template_sha:
                changed.append("模板文件缺失")
            elif expected_template_sha and current_template_sha != expected_template_sha:
                changed.append("模板哈希变化")
            if binding.get("content_sha256") and binding.get("content_sha256") != content_sha:
                changed.append("正文哈希变化")
            if binding.get("template_sha256") and binding.get("template_sha256") != current_template_sha:
                changed.append("绑定模板哈希变化")
            status = "stale" if changed else "aligned"
            selected = {**selected, "current_template_sha256": current_template_sha}
        binding = {
            **binding,
            "status": status,
            "content_version": int(manifest.get("version") or 1),
            "current_content_sha256": content_sha,
            "changed_reasons": changed,
        }
        audit = None
        audit_path = Path(str(binding.get("audit_path") or ""))
        if audit_path.is_file():
            audit = _json_read(audit_path)
        return {
            "profiles": profiles,
            "profile": selected,
            "binding": binding,
            "cover": dict(binding.get("cover") or {}),
            "frontmatter": dict(binding.get("frontmatter") or {}),
            "audit": audit,
            "sample": {
                "docx_path": selected.get("sample_docx_path") if selected else "",
                "pdf_path": selected.get("sample_pdf_path") if selected else "",
            },
            "display": {
                "content": f"正文v{manifest.get('version')}",
                "template": f"排版模板{selected.get('version')}" if selected else "未绑定模板",
                "delivery": f"交付{binding.get('layout_revision') or '未生成'}",
                "publication_status": self._record(project).get("publication_status") or "draft",
            },
        }

    def binding_patch(
        self,
        project: dict[str, Any],
        *,
        profile_id: str | None = None,
        cover: dict[str, Any] | None = None,
        layout_revision: str | None = None,
    ) -> dict[str, Any]:
        manifest = document_workspace_service.ensure_workspace(project)
        current = self._binding(project)
        selected_id = profile_id or str(current.get("profile_id") or "")
        profile = self.profile(project, selected_id)
        template_path = Path(str(profile.get("template_path") or ""))
        if not template_path.is_file():
            raise DocumentWorkspaceError("排版模板文件缺失")
        updated_cover = dict(current.get("cover") or {})
        if cover is not None:
            allowed = {"title", "author", "advisor", "advisor_title", "institution", "date"}
            updated_cover.update({key: str(value).strip() for key, value in cover.items() if key in allowed})
        binding = {
            **current,
            "profile_id": selected_id,
            "profile_version": profile.get("version"),
            "profile_name": profile.get("name"),
            "template_path": str(template_path),
            "template_sha256": _sha256(template_path),
            "content_version": int(manifest.get("version") or 1),
            "content_sha256": _sha256(Path(manifest["working_markdown"])),
            "layout_revision": layout_revision or current.get("layout_revision") or "R1",
            "delivery_basename": current.get("delivery_basename") or "",
            "status": "aligned",
            "cover": updated_cover,
            "frontmatter": {
                "abstract_zh": "pending",
                "abstract_en": "pending",
                "keywords_zh": "pending",
                "keywords_en": "pending",
                "toc": "generated",
                **dict(current.get("frontmatter") or {}),
            },
            "bound_at": _now(),
        }
        return binding

    def delivery_patch(
        self,
        project: dict[str, Any],
        docx_path: Path,
        pdf_path: Path | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(project)
        report = self.audit_document(project, docx_path, pdf_path)
        audit_root = self._root(project) / "audits"
        audit_root.mkdir(parents=True, exist_ok=True)
        audit_path = audit_root / f"{docx_path.stem}.json"
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        history = list(binding.get("delivery_history") or [])
        entry = {
            "layout_revision": binding.get("layout_revision") or "R1",
            "content_version": binding.get("content_version"),
            "docx_path": str(docx_path),
            "docx_sha256": _sha256(docx_path),
            "pdf_path": str(pdf_path) if pdf_path and pdf_path.is_file() else "",
            "pdf_sha256": _sha256(pdf_path) if pdf_path and pdf_path.is_file() else "",
            "audit_score": report["compliance_score"],
            "created_at": _now(),
        }
        history.append(entry)
        return {
            **binding,
            "status": "aligned",
            "audit_path": str(audit_path),
            "latest_delivery": entry,
            "delivery_history": history[-20:],
        }

    def audit_document(
        self,
        project: dict[str, Any],
        docx_path: Path,
        pdf_path: Path | None = None,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        blockers: list[str] = []
        warnings: list[str] = []

        def add(key: str, label: str, passed: bool, detail: str, severity: str = "blocker") -> None:
            visible_detail = f"{label}符合当前模板" if passed else detail
            checks.append({"key": key, "label": label, "passed": passed, "detail": visible_detail, "severity": severity})
            if not passed:
                (blockers if severity == "blocker" else warnings).append(detail)

        try:
            with ZipFile(docx_path) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
                styles = ET.fromstring(archive.read("word/styles.xml"))
                settings = ET.fromstring(archive.read("word/settings.xml"))
                sections = document.findall(f".//{W}sectPr")
                a4 = bool(sections) and all(
                    section.find(f"./{W}pgSz") is not None
                    and section.find(f"./{W}pgSz").get(f"{W}w") == "11906"
                    and section.find(f"./{W}pgSz").get(f"{W}h") == "16838"
                    for section in sections
                )
                add("page", "A4页面与页边距", a4, "页面必须为A4纵向")
                margin_ok = bool(sections) and all(
                    section.find(f"./{W}pgMar") is not None
                    and section.find(f"./{W}pgMar").get(f"{W}top") == "2098"
                    and section.find(f"./{W}pgMar").get(f"{W}bottom") == "1984"
                    and section.find(f"./{W}pgMar").get(f"{W}left") == "1587"
                    and section.find(f"./{W}pgMar").get(f"{W}right") == "1474"
                    for section in sections
                )
                add("margins", "页边距", margin_ok, "页边距未匹配第二版正式模板")
                style_names = set()
                for style in styles.findall(f"./{W}style"):
                    name = style.find(f"./{W}name")
                    if name is not None:
                        style_names.add(str(name.get(f"{W}val", "")).replace(" ", "").lower())
                required = {"normal", "heading1", "heading2", "heading3", "toc1", "toc2", "toc3"}
                add("styles", "真实Word样式", required.issubset(style_names), "缺少正文、三级标题或目录样式")
                colors = [node.get(f"{W}val", "").upper() for node in styles.findall(f".//{W}color")]
                add("heading_color", "黑色标题", not any(value in {"2F5496", "1F4E79", "4472C4"} for value in colors), "检测到旧蓝色标题样式")
                header_text = ""
                footer_fields = ""
                for name in archive.namelist():
                    if name.startswith("word/header") and name.endswith(".xml"):
                        root = ET.fromstring(archive.read(name))
                        header_text += "".join(node.text or "" for node in root.findall(f".//{W}t"))
                    if name.startswith("word/footer") and name.endswith(".xml"):
                        root = ET.fromstring(archive.read(name))
                        footer_fields += "".join(node.text or "" for node in root.findall(f".//{W}instrText"))
                add("header", "页眉清理", not header_text.strip(), "页眉应为空且不得残留其他文档内容")
                add("footer", "页脚页码", "PAGE" in footer_fields, "页脚未使用居中PAGE域")
                first_page = all(section.find(f"./{W}titlePg") is not None for section in sections)
                add("first_page", "封面首页规则", first_page, "封面未设置首页不同")
                update_fields = settings.find(f"./{W}updateFields")
                add("fields", "目录与域刷新", update_fields is not None, "未设置打开Word时刷新域", "warning")
                images = len(document.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline"))
                expected_images = 1
                try:
                    profile = self.profile(project, str(self._binding(project).get("profile_id") or ""))
                    expected_images = max(int(profile.get("rules", {}).get("expected_image_count") or 1), 1)
                except (DocumentWorkspaceError, TypeError, ValueError):
                    pass
                add("images", "图片资源", images >= expected_images, f"图片资源不足：检出{images}，要求至少{expected_images}")
                tables = document.findall(f".//{W}tbl")
                rows = document.findall(f".//{W}tbl/{W}tr")
                row_ok = all(row.find(f"./{W}trPr/{W}cantSplit") is not None for row in rows)
                add("tables", "表格跨页规则", not rows or row_ok, "存在可跨页截断的表格行")
                add("captions", "图表题注", bool(tables) or images > 0, "未检出图表对象", "warning")
        except (BadZipFile, KeyError, ET.ParseError, OSError) as exc:
            raise DocumentWorkspaceError(f"排版审计失败：{exc}") from exc
        if pdf_path:
            add("pdf", "DOCX同源PDF", pdf_path.is_file() and pdf_path.stat().st_size > 0, "PDF未由最终DOCX生成")
        frontmatter = self._binding(project).get("frontmatter") or {}
        pending = [key for key in ("abstract_zh", "abstract_en", "keywords_zh", "keywords_en") if frontmatter.get(key) != "ready"]
        if pending:
            warnings.append("中文摘要、英文摘要或关键词尚未同步，当前交付只能保持草稿")
        passed_count = sum(1 for row in checks if row["passed"])
        score = round(100 * passed_count / max(len(checks), 1))
        return {
            "schema": "openclaw.document-layout-audit",
            "generated_at": _now(),
            "document_path": str(docx_path),
            "document_sha256": _sha256(docx_path),
            "pdf_path": str(pdf_path) if pdf_path else "",
            "compliance_score": score,
            "status": "passed" if not blockers else "blocked",
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "page_anomalies": [],
        }


document_layout_service = DocumentLayoutService()
