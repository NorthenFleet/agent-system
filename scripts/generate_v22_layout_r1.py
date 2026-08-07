"""Generate, audit and register the v22/R1 doctoral delivery from the bound profile."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REPO = Path("/Users/apple/工作桌面/Workspace/agent-system")
sys.path.insert(0, str(REPO / "backend"))

from project_manager import project_manager  # noqa: E402
from services.document_layout_service import document_layout_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402


PROJECT_ID = "proj-10fbeefae5"
DOCUMENT_ID = "doc-15def56e2401"
CONTENT_SHA = "40f5c0f6dc3423406c5731749b7ea08b1c79b163b922e85c68c6d8a465b9193a"
AUTHORITY_SHA = "cce0e6ebb84f23f17b34c97cb57c59abcfc89ce5b191c98fecdb573a5b2b8a4c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("project missing")
    context = multi_document_service.rich_project_context(project, DOCUMENT_ID)
    state = document_layout_service.state(context)
    profile = state.get("profile") or {}
    binding = state.get("binding") or {}
    if binding.get("current_content_sha256") != CONTENT_SHA:
        raise SystemExit("v22 Markdown hash mismatch")
    authority = Path(str(profile.get("authority_source", {}).get("path") or ""))
    if not authority.is_file() or sha256(authority) != AUTHORITY_SHA:
        raise SystemExit("second-edition authority hash mismatch")
    if binding.get("status") != "aligned":
        raise SystemExit(f"layout binding is not aligned: {binding.get('changed_reasons')}")

    pdf_path = multi_document_service.rich_call(project, DOCUMENT_ID, "export", "pdf")
    docx_path = pdf_path.with_suffix(".docx")
    if not docx_path.is_file():
        raise SystemExit("DOCX was not generated")
    context = multi_document_service.rich_project_context(project, DOCUMENT_ID)
    updated_binding = document_layout_service.delivery_patch(context, docx_path, pdf_path)
    multi_document_service.update_document_metadata(project, DOCUMENT_ID, {"layout_binding": updated_binding})
    report = json.loads(Path(updated_binding["audit_path"]).read_text(encoding="utf-8"))
    result = {
        "docx": {"path": str(docx_path), "sha256": sha256(docx_path), "size_bytes": docx_path.stat().st_size},
        "pdf": {"path": str(pdf_path), "sha256": sha256(pdf_path), "size_bytes": pdf_path.stat().st_size},
        "audit": report,
        "content_source_unchanged": binding.get("current_content_sha256") == CONTENT_SHA,
        "authority_source_unchanged": sha256(authority) == AUTHORITY_SHA,
        "publication_status": "draft",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
