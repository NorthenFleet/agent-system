#!/usr/bin/env python3
"""Run the approved Phase G1 read-only GenOffice gold checks.

This intentionally reads each manifest DOCX into memory, uploads it to the
localhost Sidecar, and performs only docs_read, docs_check, and page-1 render.
It never supplies an original filesystem path to GenOffice and never writes a
candidate or modifies a gold source. The Sidecar's HTTP FileStore retains an
uploaded source for its documented short TTL; launcher privacy controls apply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from services.genoffice_readonly_service import (  # noqa: E402
    GenOfficeMcpClient,
    GenOfficeReadOnlyError,
    GenOfficeSettings,
    GenOfficeSource,
    _first_render_url,
    _public_check,
    _public_read,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read gold manifest: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ValueError("gold manifest does not contain a documents list")
    return payload


def _audit_document(settings: GenOfficeSettings, item: dict[str, Any]) -> dict[str, Any]:
    document_id = str(item.get("id") or "")
    stage = "source_preflight"
    stage_started_at = monotonic()
    try:
        source_path = Path(str(item.get("path") or ""))
        expected_sha256 = str(item.get("expected_sha256") or "").lower()
        if not document_id or not source_path.is_file() or len(expected_sha256) != 64:
            raise ValueError("gold manifest document entry is invalid")

        source_data = source_path.read_bytes()
        source_sha256 = hashlib.sha256(source_data).hexdigest()
        if source_sha256 != expected_sha256:
            raise ValueError("gold source SHA-256 does not match the approved manifest")

        source = GenOfficeSource(data=source_data, sha256=source_sha256, name="original.docx")
        stage = "mcp_initialize"
        stage_started_at = monotonic()
        with GenOfficeMcpClient(settings, settings.load_token()) as client:
            stage = "tools_list"
            stage_started_at = monotonic()
            tools = client.list_tools()
            if not {"docs_read", "docs_check", "render"}.issubset(tools):
                raise ValueError("Sidecar is missing an approved read-only tool")
            stage = "upload_source"
            stage_started_at = monotonic()
            remote_file = client.upload_docx(source)
            try:
                stage = "docs_read"
                stage_started_at = monotonic()
                read = client.call_tool("docs_read", {"file": remote_file, "range": "0", "max_chars": 200})
                stage = "docs_check"
                stage_started_at = monotonic()
                check = client.call_tool("docs_check", {"file": remote_file})
                stage = "render_page_1"
                stage_started_at = monotonic()
                rendered = client.call_tool("render", {"file": remote_file, "page": 1, "scale": 1})
                stage = "download_page_1"
                stage_started_at = monotonic()
                png = client.download_png(_first_render_url(rendered), max_bytes=settings.max_render_bytes)
            finally:
                settings.cleanup_headless_source(source.sha256)

            public_read = _public_read(read)
            public_check = _public_check(check)
            return {
                "id": document_id,
                "source_sha256": source_sha256,
                "source_bytes": len(source_data),
                "release_version": settings.release_version(),
                "mcp_version": client.mcp_version,
                "read": {
                    "blocks": public_read["blocks"],
                    "range": public_read["range"],
                    "item_count": len(public_read["items"]),
                },
                "check": {
                    "counts": public_check["counts"],
                    "issue_count": len(public_check["issues"]),
                    "truncated": public_check["truncated"],
                },
                "render_page_1": {
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "bytes": len(png),
                },
                "status": "passed",
            }
    except (GenOfficeReadOnlyError, OSError, ValueError) as exc:
        return {
            "id": document_id,
            "stage": stage,
            "elapsed_ms": round((monotonic() - stage_started_at) * 1000),
            "status": "failed",
            "reason": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "specs/active/word-cowriting-phase0-gold-documents.json",
    )
    parser.add_argument(
        "--document-id",
        action="append",
        dest="document_ids",
        help="audit only a named manifest document; repeatable",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    try:
        manifest = _load_manifest(manifest_path)
        settings = GenOfficeSettings.from_env()
        if not settings.enabled:
            raise ValueError("GenOffice G1 is disabled")
        settings.validate_url()
        documents = [item for item in manifest["documents"] if isinstance(item, dict)]
        if len(documents) != len(manifest["documents"]):
            raise ValueError("gold manifest contains an invalid document entry")
        requested_ids = set(args.document_ids or [])
        if requested_ids:
            documents = [item for item in documents if str(item.get("id") or "") in requested_ids]
            if len(documents) != len(requested_ids):
                raise ValueError("requested gold manifest document is unavailable")
        results = []
        for item in documents:
            results.append(_audit_document(settings, item))
        report: dict[str, Any] = {
            "schema": "openclaw.genoffice-phase-g1-readonly-gold.v1",
            "created_at": _utc_now(),
            "manifest_path": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "scope": "docs_read/docs_check/render page 1 only; no source or candidate write",
            "uploaded_source_retention": "GenOffice HTTP FileStore retains uploads for its vendor-defined short TTL (currently about one hour); the isolated Electron original copy is removed after each proof",
            "status": "passed" if all(item["status"] == "passed" for item in results) else "failed",
            "documents": results,
        }
    except (GenOfficeReadOnlyError, OSError, ValueError) as exc:
        report = {
            "schema": "openclaw.genoffice-phase-g1-readonly-gold.v1",
            "created_at": _utc_now(),
            "manifest_path": str(manifest_path),
            "status": "failed",
            "reason": str(exc),
        }

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output_path)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
