"""Audited content-fidelity checks and reversible rich-text migrations."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.document_workspace_service import DocumentWorkspaceError, document_workspace_service
from services.multi_document_service import MultiDocumentService, multi_document_service
from services.pandoc_document_importer import PandocDocxImporter, pandoc_docx_importer
from services.structured_document_service import StructuredDocumentCodec, structured_document_codec
from services.writing_collaboration_service import WritingCollaborationService, writing_collaboration_service


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(data: bytes | str) -> str:
    value = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(value).hexdigest()


class DocumentFidelityService:
    metric_keys = (
        "table_count", "table_cell_count", "image_count",
        "math_block_count", "math_inline_count", "replacement_character_count",
    )

    def __init__(
        self,
        documents: MultiDocumentService = multi_document_service,
        collaboration: WritingCollaborationService = writing_collaboration_service,
        codec: StructuredDocumentCodec = structured_document_codec,
        docx_importer: PandocDocxImporter = pandoc_docx_importer,
    ) -> None:
        self.documents = documents
        self.collaboration = collaboration
        self.codec = codec
        self.docx_importer = docx_importer

    def audit(self, project: dict[str, Any], document_id: str, *, persist: bool = True) -> dict[str, Any]:
        record = self.documents.get_document(project, document_id)
        if record.get("kind") != "rich_text":
            raise DocumentWorkspaceError("内容保真审计仅支持正文文档")
        context = self.documents.rich_project_context(project, document_id)
        fulltext = document_workspace_service.fulltext(context)
        markdown = str(fulltext.get("content") or "")
        root = self.documents._document_root(project, document_id)  # noqa: SLF001
        original = root / "source" / "original.docx"

        source_kind = "docx" if original.is_file() else "markdown"
        if source_kind == "docx":
            imported = self.docx_importer.convert(original.read_bytes(), str(record.get("title") or "正文"))
            expected_document = imported["document"]
            expected_markdown = imported["markdown"]
            expected_assets = imported["assets"]
            importer_status = str(imported["stats"].get("fidelity_status") or "degraded")
            warnings = list(imported.get("warnings") or [])
        else:
            expected_document = self.codec.from_markdown(markdown, namespace=f"{project.get('id')}/{document_id}/fidelity-audit")
            expected_markdown = markdown
            expected_assets = {}
            importer_status = "passed"
            warnings = []

        expected = self.codec.metrics(expected_document)
        current_document: dict[str, Any] | None = None
        current_revision = 0
        try:
            with self.collaboration.session_factory() as session:
                state = self.collaboration._load_state(session, str(project.get("id") or ""), document_id)  # noqa: SLF001
                if state:
                    current_document = copy.deepcopy(state.content_json)
                    current_revision = int(state.document_revision)
        except Exception as exc:
            warnings.append(f"无法读取结构化正文状态：{exc}")
        current = self.codec.metrics(current_document) if current_document else {key: 0 for key in expected}

        unresolved: list[str] = []
        for node in self.codec._walk_nodes(expected_document):
            if node.get("type") != "image":
                continue
            path = str((node.get("attrs") or {}).get("src") or "")
            if path.startswith("assets/") and Path(path).name in expected_assets:
                continue
            try:
                self.documents.rich_call(project, document_id, "asset_path", path)
            except Exception:
                unresolved.append(path)
        empty_math = [
            str((node.get("attrs") or {}).get("suffix") or "")
            for node in self.codec._walk_nodes(expected_document)
            if node.get("type") in {"mathInline", "mathBlock"}
            and not str((node.get("attrs") or {}).get("latex") or "").strip()
        ]
        differences = {
            key: {"source": int(expected.get(key) or 0), "structured": int(current.get(key) or 0)}
            for key in self.metric_keys
            if int(expected.get(key) or 0) != int(current.get(key) or 0)
        }
        migration_safe = (
            importer_status == "passed"
            and not empty_math
            and int(expected.get("replacement_character_count") or 0) == 0
            and not unresolved
        )
        if not migration_safe:
            status = "blocked"
        elif differences or not current_document or str((current_document.get("attrs") or {}).get("schemaVersion")) != self.codec.schema_version:
            status = "stale"
        else:
            status = "passed"
        report = {
            "schema": "openclaw.document-content-fidelity.v1",
            "project_id": str(project.get("id") or ""),
            "document_id": document_id,
            "document_title": str(record.get("title") or ""),
            "source_kind": source_kind,
            "source_sha256": _sha(original.read_bytes()) if source_kind == "docx" else _sha(markdown),
            "structured_revision": current_revision,
            "structured_sha256": self.codec.document_sha256(current_document) if current_document else "",
            "status": status,
            "migration_safe": migration_safe,
            "source_metrics": expected,
            "structured_metrics": current,
            "differences": differences,
            "unresolved_assets": unresolved,
            "empty_formulas": empty_math,
            "warnings": warnings,
            "audited_at": _now(),
        }
        if persist:
            target = root / "fidelity" / "latest.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.documents.update_document_metadata(project, document_id, {"content_fidelity": report})
        report["_candidate_document"] = expected_document
        report["_candidate_markdown"] = expected_markdown
        report["_candidate_assets"] = expected_assets
        return report

    def latest(self, project: dict[str, Any], document_id: str) -> dict[str, Any]:
        path = self.documents._document_root(project, document_id) / "fidelity" / "latest.json"  # noqa: SLF001
        if not path.is_file():
            return self._public(self.audit(project, document_id))
        return json.loads(path.read_text(encoding="utf-8"))

    def migrate(self, project: dict[str, Any], document_id: str, *, actor: str) -> dict[str, Any]:
        report = self.audit(project, document_id, persist=False)
        if not report["migration_safe"]:
            raise DocumentWorkspaceError("内容保真审计未通过，已阻止迁移")
        document = report.pop("_candidate_document")
        markdown = str(report.pop("_candidate_markdown"))
        assets: dict[str, bytes] = report.pop("_candidate_assets")
        root = self.documents._document_root(project, document_id)  # noqa: SLF001
        self._snapshot(project, document_id, root)

        source = root / "source" / "document.md"
        working = root / "working" / "document.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        working.parent.mkdir(parents=True, exist_ok=True)
        if report["source_kind"] == "docx":
            assets_dir = root / "source" / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            for name, data in assets.items():
                (assets_dir / name).write_bytes(data)
            source.write_text(markdown, encoding="utf-8")
            working.write_text(markdown, encoding="utf-8")
            (root / "source" / "structured.json").write_text(
                json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        try:
            self.collaboration.ensure_state(project, document_id)
        except Exception:
            # An existing state is expected for migrated production documents;
            # ensure_state creates it for newly imported documents.
            with self.collaboration.session_factory() as session:
                if not self.collaboration._load_state(session, str(project.get("id") or ""), document_id):  # noqa: SLF001
                    raise
        state = self.collaboration.replace_authority_from_document(
            project, document_id, document, markdown,
            label="内容高保真结构迁移", actor=actor,
        )
        final = self.audit(project, document_id, persist=True)
        final = self._public(final)
        final["collaboration_revision"] = int(state.get("revision") or 0)
        return final

    def preview_pdf(self, project: dict[str, Any], document_id: str) -> Path:
        """Return a read-only WPS-compatible PDF without publishing a delivery."""
        record = self.documents.get_document(project, document_id)
        if record.get("kind") != "rich_text":
            raise DocumentWorkspaceError("WPS 预览仅支持正文文档")
        root = self.documents._document_root(project, document_id)  # noqa: SLF001
        original = root / "source" / "original.docx"
        source_path = Path(str(record.get("source_path") or ""))
        source_word = original if original.is_file() else source_path if source_path.suffix.lower() == ".docx" and source_path.is_file() else None
        if source_word is not None:
            return self._render_source_word_preview(root, source_word)

        # Markdown documents only expose the latest user-generated format proof.
        # Reading this pointer never creates or promotes a formal delivery.
        from services.document_layout_service import document_layout_service

        context = self.documents.rich_project_context(project, document_id)
        latest = document_layout_service.state(context).get("binding", {}).get("latest_delivery") or {}
        preview = Path(str(latest.get("pdf_path") or ""))
        if not preview.is_file():
            raise DocumentWorkspaceError("当前正文尚无格式校样，请在“排版与交付”中生成 PDF 后预览")
        return preview

    def _render_source_word_preview(self, root: Path, source_word: Path) -> Path:
        source_sha = _sha(source_word.read_bytes())
        cache_dir = root / "fidelity" / "preview" / source_sha
        target = cache_dir / "wps-preview.pdf"
        if target.is_file() and target.stat().st_size:
            return target
        soffice = Path(os.environ.get("LIBREOFFICE_BIN") or "/opt/homebrew/bin/soffice")
        if not soffice.is_file():
            raise DocumentWorkspaceError("LibreOffice 不可用，无法生成 WPS 预览")
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="writing-fidelity-lo-") as profile:
            result = subprocess.run(
                [
                    str(soffice),
                    f"-env:UserInstallation=file://{profile}",
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(cache_dir),
                    str(source_word),
                ],
                capture_output=True,
                text=True,
                timeout=240,
            )
        generated = cache_dir / f"{source_word.stem}.pdf"
        if result.returncode != 0 or not generated.is_file() or not generated.stat().st_size:
            raise DocumentWorkspaceError((result.stderr or result.stdout or "Word 预览转换失败")[-500:])
        generated.replace(target)
        return target

    def _snapshot(self, project: dict[str, Any], document_id: str, root: Path) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = root / "fidelity" / "backups" / f"{stamp}-before-migration"
        target.mkdir(parents=True, exist_ok=False)
        for relative in ("source/document.md", "source/structured.json", "working/document.md", "manifest.json"):
            source = root / relative
            if source.is_file():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        assets = root / "source" / "assets"
        if assets.is_dir():
            shutil.copytree(assets, target / "source" / "assets")
        with self.collaboration.session_factory() as session:
            state = self.collaboration._load_state(session, str(project.get("id") or ""), document_id)  # noqa: SLF001
            if state:
                (target / "structured-state.json").write_text(
                    json.dumps({
                        "schema_version": state.schema_version,
                        "revision": state.document_revision,
                        "content_json": state.content_json,
                        "content_sha256": state.content_sha256,
                        "source_markdown_sha256": state.source_markdown_sha256,
                    }, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        return target

    @staticmethod
    def _public(report: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in report.items() if not key.startswith("_candidate_")}


document_fidelity_service = DocumentFidelityService()
