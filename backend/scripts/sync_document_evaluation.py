"""Create hash-bound technical reports and optionally run one full evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from project_manager import project_manager  # noqa: E402
from services.document_evaluation_service import (  # noqa: E402
    DocumentEvaluationError,
    document_evaluation_service,
)
from services.document_workspace_service import DocumentWorkspaceError  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402


DEFAULT_PROJECT_ID = "proj-10fbeefae5"
DEFAULT_DOCUMENT_ID = "doc-15def56e2401"


def rollout(project_id: str, document_id: str, run_full: bool) -> dict:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"Project not found: {project_id}")
    documents = multi_document_service.list_documents(project)["documents"]
    reports = []
    for document in documents:
        report = document_evaluation_service.run_technical(project, document["id"])
        reports.append(
            {
                "document_id": document["id"],
                "kind": document["kind"],
                "profile_id": report["profile_id"],
                "status": report["status"],
                "technical_score": report["technical_score"],
                "source_sha256": report["source_sha256"],
            }
        )
    academic = None
    if run_full:
        if not any(row["id"] == document_id for row in documents):
            raise RuntimeError(f"Document not found: {document_id}")
        report = document_evaluation_service.run_full_sync(project, document_id)
        academic = {
            key: report.get(key)
            for key in (
                "id",
                "document_id",
                "status",
                "decision",
                "maturity_level",
                "technical_score",
                "provisional_score",
                "confirmed_score",
                "coverage",
                "source_sha256",
                "profile_id",
                "profile_version",
                "model",
            )
        }
    return {
        "project_id": project_id,
        "technical_reports": reports,
        "academic_report": academic,
        "linked_summary": document_evaluation_service.linked_summary(project),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--document-id", default=DEFAULT_DOCUMENT_ID)
    parser.add_argument(
        "--technical-only",
        action="store_true",
        help="Only create automatic technical reports for all current documents.",
    )
    args = parser.parse_args()
    result = rollout(
        args.project_id,
        args.document_id,
        run_full=not args.technical_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DocumentWorkspaceError, DocumentEvaluationError, RuntimeError) as exc:
        raise SystemExit(f"Document evaluation rollout failed: {exc}") from exc
