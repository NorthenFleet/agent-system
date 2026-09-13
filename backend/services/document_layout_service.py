"""Generic, versioned layout profiles and delivery audits for rich-text documents."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
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
REFERENCE_TEMPLATE_MAX_BYTES = 150 * 1024 * 1024


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


def _safe_profile_id(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized[:80] or "current-word-template"


def _reference_contract(path: Path) -> dict[str, Any]:
    """Capture layout facts from a user-approved DOCX without changing it."""
    try:
        with ZipFile(path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            styles = ET.fromstring(archive.read("word/styles.xml"))
            sections = document.findall(f".//{W}sectPr")
            first = sections[0] if sections else None
            page = first.find(f"./{W}pgSz") if first is not None else None
            margins = first.find(f"./{W}pgMar") if first is not None else None
            style_names = sorted({
                str(node.get(f"{W}val", "")).replace(" ", "").lower()
                for style in styles.findall(f"./{W}style")
                if style.find(f"./{W}name") is not None
                for node in [style.find(f"./{W}name")]
            })
            headers = any(name.startswith("word/header") and name.endswith(".xml") for name in archive.namelist())
            footers = any(name.startswith("word/footer") and name.endswith(".xml") for name in archive.namelist())
    except (BadZipFile, KeyError, ET.ParseError, OSError) as exc:
        raise DocumentWorkspaceError("当前 Word 模板无效或已损坏") from exc
    if page is None:
        raise DocumentWorkspaceError("当前 Word 模板缺少页面设置")
    return {
        "page_size": {key: str(page.get(f"{W}{key}") or "") for key in ("w", "h", "orient")},
        "margins": (
            {key: str(margins.get(f"{W}{key}") or "") for key in ("top", "bottom", "left", "right", "header", "footer", "gutter")}
            if margins is not None else {}
        ),
        "style_names": style_names,
        "section_count": len(sections),
        "has_headers": headers,
        "has_footers": footers,
    }


class DocumentLayoutService:
    """Resolve profiles without coupling behavior to project names or IDs."""

    def _root(self, project: dict[str, Any]) -> Path:
        return document_workspace_service._workspace_root(project) / "layout"  # noqa: SLF001

    def _library_root(self, project: dict[str, Any]) -> Path:
        """One immutable template library shared by documents in this workspace."""
        # A document workspace lives at .../documents/<document-id>; its parent is
        # the stable course-document collection, unlike an individual document's
        # private layout directory.
        return document_workspace_service._workspace_root(project).parent / "template-library"  # noqa: SLF001

    def _record(self, project: dict[str, Any]) -> dict[str, Any]:
        record = project.get("_course_document_record")
        return record if isinstance(record, dict) else {}

    def _binding(self, project: dict[str, Any]) -> dict[str, Any]:
        metadata = self._record(project).get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        value = metadata.get("layout_binding")
        return dict(value) if isinstance(value, dict) else {}

    def _document_type(self, project: dict[str, Any]) -> str:
        record = self._record(project)
        return str(record.get("product_type") or record.get("kind") or "document")

    def _render_template_preview(self, root: Path, template_path: Path) -> dict[str, Any]:
        """Create browser-safe derivatives; the reference DOCX is never edited."""
        preview_pdf = root / "preview.pdf"
        preview_dir = root / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        if not preview_pdf.is_file():
            with tempfile.TemporaryDirectory(prefix="openclaw-template-preview-", dir="/private/tmp") as profile:
                result = subprocess.run(
                    [
                        "/opt/homebrew/bin/soffice", "--headless",
                        f"-env:UserInstallation=file://{Path(profile).as_posix()}",
                        "--convert-to", "pdf", "--outdir", str(root), str(template_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            generated = root / f"{template_path.stem}.pdf"
            if result.returncode != 0 or not generated.is_file() or generated.stat().st_size == 0:
                raise DocumentWorkspaceError(f"Word 模板预览生成失败：{result.stderr[-300:]}")
            generated.replace(preview_pdf)
        # PDFKit renders actual PDF pages without weakening ImageMagick's
        # Ghostscript policy. A short document simply has fewer cards.
        existing = sorted(preview_dir.glob("page-*.png"))
        if not existing:
            renderer = Path(__file__).resolve().parents[1] / "scripts" / "render_pdf_pages.swift"
            result = subprocess.run(
                ["/usr/bin/swift", str(renderer), str(preview_pdf), str(preview_dir)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            existing = sorted(preview_dir.glob("page-*.png"))
            if result.returncode != 0 or not existing:
                raise DocumentWorkspaceError(f"Word 模板缩略图生成失败：{result.stderr[-300:]}")
        # These are unmodified source pages. Do not call a page a cover,
        # table of contents, or body sample until a reviewer has explicitly
        # labelled it as such for this template.
        labels = tuple(("page", f"模板第 {index + 1} 页") for index in range(3))
        showcase = [
            {"kind": kind, "label": label, "page": index + 1}
            for index, (kind, label) in enumerate(labels)
            if index < len(existing)
        ]
        return {"pdf_path": str(preview_pdf), "page_count": len(existing), "showcase_pages": showcase}

    def profiles(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        roots = (self._library_root(project), self._root(project) / "profiles")
        rows: list[dict[str, Any]] = []
        ids: set[str] = set()
        template_hashes: set[str] = set()
        for root_index, root in enumerate(roots):
            if not root.is_dir():
                continue
            for path in sorted(root.glob("**/profile.json")):
                profile = _json_read(path)
                profile_id = str(profile.get("id") or "")
                if not profile_id or profile_id in ids:
                    continue
                template_sha = str(profile.get("template_sha256") or "")
                if root_index and profile.get("rules", {}).get("template_mode") == "reference_docx" and template_sha in template_hashes:
                    continue
                ids.add(profile_id)
                if template_sha:
                    template_hashes.add(template_sha)
                profile["profile_path"] = str(path)
                rows.append(profile)
        document_type = self._document_type(project)
        return sorted(rows, key=lambda row: (document_type not in row.get("applies_to", {}).get("document_types", []), str(row.get("name") or "")))

    def profile(self, project: dict[str, Any], profile_id: str) -> dict[str, Any]:
        for profile in self.profiles(project):
            if profile.get("id") == profile_id:
                return profile
        raise DocumentWorkspaceError("排版模板不存在")

    def register_reference_template(
        self,
        project: dict[str, Any],
        *,
        data: bytes,
        filename: str,
        profile_name: str = "",
    ) -> dict[str, Any]:
        """Store an explicitly supplied current Word file as this document's layout authority."""
        if not data or len(data) > REFERENCE_TEMPLATE_MAX_BYTES:
            raise DocumentWorkspaceError("当前 Word 模板为空或超过 150MB 限制")
        if not filename.lower().endswith(".docx"):
            raise DocumentWorkspaceError("排版模板仅支持 .docx 格式")
        record = self._record(project)
        product_type = self._document_type(project)
        content_sha = hashlib.sha256(data).hexdigest()
        profile_id = _safe_profile_id(f"{product_type}-word-{content_sha[:12]}")
        root = self._library_root(project) / _safe_profile_id(product_type) / profile_id
        root.mkdir(parents=True, exist_ok=True)
        template_path = root / "reference.docx"
        if not template_path.is_file():
            temporary = template_path.with_suffix(".uploading")
            temporary.write_bytes(data)
            try:
                contract = _reference_contract(temporary)
                temporary.replace(template_path)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            contract = _reference_contract(template_path)
        preview = self._render_template_preview(root, template_path)
        label = profile_name.strip() or f"{record.get('title') or '文档'}·当前 Word 模板"
        profile = {
            "id": profile_id,
            "name": label,
            "version": f"sha-{content_sha[:12]}",
            "applies_to": {"kind": "rich_text", "document_types": [product_type]},
            "authority_source": {
                "sha256": content_sha,
                "filename": filename,
                "role": "current_word_reference",
                "document_id": str(record.get("id") or ""),
                "document_title": str(record.get("title") or ""),
            },
            "template_path": str(template_path),
            "template_sha256": _sha256(template_path),
            "status": "validated",
            "page": {
                "size": "reference_docx",
                "margin_top_twips": contract["margins"].get("top", ""),
                "margin_bottom_twips": contract["margins"].get("bottom", ""),
                "margin_left_twips": contract["margins"].get("left", ""),
                "margin_right_twips": contract["margins"].get("right", ""),
            },
            "styles": {},
            "rules": {
                "template_mode": "reference_docx",
                "reference_contract": contract,
                "postprocess": "preserve_reference",
            },
            "preview": preview,
            "created_at": _now(),
        }
        (root / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return profile

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
        document_type = self._document_type(project)
        same_type = [row for row in profiles if document_type in row.get("applies_to", {}).get("document_types", [])]
        return {
            "profiles": profiles,
            "template_catalog": {"document_type": document_type, "same_type_count": len(same_type), "total_count": len(profiles)},
            "profile": selected,
            "binding": binding,
            "cover": dict(binding.get("cover") or {}),
            "frontmatter": dict(binding.get("frontmatter") or {}),
            "audit": audit,
            "sample": {
                "docx_path": selected.get("template_path") if selected else "",
                "pdf_path": (selected.get("preview") or {}).get("pdf_path", "") if selected else "",
            },
            "display": {
                "content": f"正文v{manifest.get('version')}",
                "template": f"排版模板{selected.get('version')}" if selected else "未绑定模板",
                "delivery": f"交付{binding.get('layout_revision') or '未生成'}",
                "publication_status": self._record(project).get("publication_status") or "draft",
            },
        }

    def preview_path(self, project: dict[str, Any], profile_id: str, format: str, page: int | None = None) -> Path:
        profile = self.profile(project, profile_id)
        if format == "docx":
            path = Path(str(profile.get("template_path") or ""))
        elif format == "pdf":
            path = Path(str((profile.get("preview") or {}).get("pdf_path") or ""))
        elif format == "png" and page:
            path = Path(str((profile.get("preview") or {}).get("pdf_path") or "")).parent / "preview" / f"page-{page - 1:03d}.png"
        else:
            raise DocumentWorkspaceError("模板预览格式无效")
        if not path.is_file():
            raise DocumentWorkspaceError("模板预览尚未生成")
        return path

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
            "postprocess": str(profile.get("rules", {}).get("postprocess") or "formal"),
            "content_version": int(manifest.get("version") or 1),
            "content_sha256": _sha256(Path(manifest["working_markdown"])),
            "layout_revision": layout_revision or current.get("layout_revision") or "R1",
            "delivery_basename": current.get("delivery_basename") or f"{_safe_profile_id(str(self._record(project).get('title') or 'document'))}-layout-r1",
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
            profile = None
            try:
                profile = self.profile(project, str(self._binding(project).get("profile_id") or ""))
            except DocumentWorkspaceError:
                pass
            with ZipFile(docx_path) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
                styles = ET.fromstring(archive.read("word/styles.xml"))
                settings = ET.fromstring(archive.read("word/settings.xml"))
                sections = document.findall(f".//{W}sectPr")
                style_names = {
                    str(node.get(f"{W}val", "")).replace(" ", "").lower()
                    for style in styles.findall(f"./{W}style")
                    if style.find(f"./{W}name") is not None
                    for node in [style.find(f"./{W}name")]
                }
                reference_contract = (profile or {}).get("rules", {}).get("reference_contract")
                if isinstance(reference_contract, dict):
                    page = sections[0].find(f"./{W}pgSz") if sections else None
                    margins = sections[0].find(f"./{W}pgMar") if sections else None
                    actual_size = {key: str(page.get(f"{W}{key}") or "") for key in ("w", "h", "orient")} if page is not None else {}
                    actual_margins = {key: str(margins.get(f"{W}{key}") or "") for key in ("top", "bottom", "left", "right", "header", "footer", "gutter")} if margins is not None else {}
                    add("page", "页面设置", actual_size == (reference_contract.get("page_size") or {}), "页面尺寸未匹配当前 Word 模板")
                    add("margins", "页边距", actual_margins == (reference_contract.get("margins") or {}), "页边距未匹配当前 Word 模板")
                    required = set(reference_contract.get("style_names") or [])
                    add("styles", "Word样式", required.issubset(style_names), "导出稿缺少当前 Word 模板样式")
                else:
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
                    required = {"normal", "heading1", "heading2", "heading3", "toc1", "toc2", "toc3"}
                    add("styles", "真实Word样式", required.issubset(style_names), "缺少正文、三级标题或目录样式")
                    colors = [node.get(f"{W}val", "").upper() for node in styles.findall(f".//{W}color")]
                    add("heading_color", "黑色标题", not any(value in {"2F5496", "1F4E79", "4472C4"} for value in colors), "检测到旧蓝色标题样式")
                update_fields = settings.find(f"./{W}updateFields")
                add("fields", "目录与域刷新", update_fields is not None, "未设置打开Word时刷新域", "warning")
                if not isinstance(reference_contract, dict):
                    rows = document.findall(f".//{W}tbl/{W}tr")
                    row_ok = all(row.find(f"./{W}trPr/{W}cantSplit") is not None for row in rows)
                    add("tables", "表格跨页规则", not rows or row_ok, "存在可跨页截断的表格行")
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
