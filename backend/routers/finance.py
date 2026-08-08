"""Production project-finance API and one-release compatibility surface."""
from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from database import get_db
from models.finance_models import BudgetLine, BudgetVersion, FinanceProject, Reimbursement
from routers.auth_router import get_current_user
from schemas.finance import (
    ApprovalAction,
    BudgetAdjustmentCreate,
    BudgetApprove,
    BudgetCreate,
    BudgetLinesReplace,
    FundAllocationCreate,
    ImportRequest,
    InvoiceBatchCreate,
    InvoiceCreate,
    PaymentConfirm,
    PaymentCreate,
    ProjectCreate,
    ProjectUpdate,
    ReconciliationConfirm,
    ReimbursementCreate,
    ReimbursementItemCreate,
    ReimbursementItemUpdate,
    ReimbursementSubmit,
    ReimbursementUpdate,
    RoleGrant,
    WorkflowCreate,
)
from services.finance_v2_service import FinanceError, FinanceNotFound, FinanceServiceV2, row_dict
from services.finance_intake_service import FinanceIntakeError, FinanceIntakeService
from services.finance_invoice_batch_service import FinanceInvoiceBatchService, process_invoice_batch_job


router = APIRouter(prefix="/api/finance", tags=["finance"])
health_router = APIRouter(tags=["health"])


class FinanceEnvelope(BaseModel):
    status: str = "ok"
    data: Any
    meta: dict[str, Any] = Field(default_factory=dict)


def service(request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> FinanceServiceV2:
    return FinanceServiceV2(
        db,
        user,
        request_id=request.headers.get("x-request-id", ""),
        ip_address=request.client.host if request.client else "",
    )


def call(callback: Callable[[], Any]) -> Any:
    try:
        return callback()
    except FinanceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        ) from exc


def call_intake(callback: Callable[[], Any]) -> Any:
    try:
        return callback()
    except FinanceIntakeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def envelope(data: Any, **meta: Any) -> dict[str, Any]:
    return {"status": "ok", "data": data, "meta": meta}


def idempotent(
    svc: FinanceServiceV2,
    endpoint: str,
    key: str | None,
    payload: dict[str, Any],
    callback: Callable[[], dict[str, Any]],
    response: Response,
) -> dict[str, Any]:
    result, replayed = call(lambda: svc.idempotent(endpoint, key or "", payload, callback))
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return envelope(result)


@health_router.get("/health/live")
def health_live():
    return {"status": "ok"}


@health_router.get("/health/ready")
def health_ready(response: Response, db: Session = Depends(get_db)):
    try:
        result = FinanceServiceV2.readiness(db)
    except Exception as exc:
        response.status_code = 503
        return {"status": "not_ready", "error": type(exc).__name__}
    if result["status"] != "ready":
        response.status_code = 503
    return result


@router.get("/dashboard", response_model=FinanceEnvelope)
def dashboard(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.dashboard))


@router.get("/control-readiness", response_model=FinanceEnvelope)
def control_readiness(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.control_readiness))


@router.get("/intake-jobs", response_model=FinanceEnvelope)
def intake_jobs(
    status: str = Query("", pattern="^(|received|shadow_read|awaiting_extraction|extracted|needs_review|validated|approved|committed|rejected|failed|cancelled)$"),
    operation_type: str = Query("", pattern="^(|reimbursement|invoice|budget|payment|reconciliation|query|unknown)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    service = FinanceIntakeService(db)
    jobs = call_intake(
        lambda: service.list_jobs(
            user_id=int(user["sub"]),
            system_role=str(user.get("role") or ""),
            status=status,
            operation_type=operation_type,
            limit=limit,
        )
    )
    return envelope(jobs, total=len(jobs), mode="shadow")


@router.get("/intake-jobs/{job_id}", response_model=FinanceEnvelope)
def intake_job_detail(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    service = FinanceIntakeService(db)
    return envelope(
        call_intake(
            lambda: service.get_job(
                job_id,
                user_id=int(user["sub"]),
                system_role=str(user.get("role") or ""),
            )
        )
    )


# ---------- roles and projects ----------
@router.get("/roles", response_model=FinanceEnvelope)
def roles(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_role_assignments))


@router.post("/roles", response_model=FinanceEnvelope)
def grant_role(payload: RoleGrant, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/roles", idempotency_key, payload.model_dump(mode="json"), lambda: svc.grant_role(payload), response)


@router.get("/projects", response_model=FinanceEnvelope)
def projects(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_projects))


@router.post("/projects", response_model=FinanceEnvelope)
def create_project(payload: ProjectCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/projects", idempotency_key, payload.model_dump(mode="json"), lambda: svc.create_project(payload), response)


@router.patch("/projects/{project_id}", response_model=FinanceEnvelope)
def update_project(project_id: str, payload: ProjectUpdate, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.update_project(project_id, payload)))


@router.get("/fund-allocations", response_model=FinanceEnvelope)
def allocations(project_id: str | None = None, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.list_allocations(project_id)))


@router.post("/fund-allocations", response_model=FinanceEnvelope)
def create_allocation(payload: FundAllocationCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/fund-allocations", idempotency_key, payload.model_dump(mode="json"), lambda: svc.create_allocation(payload), response)


# ---------- budgets ----------
@router.get("/budgets", response_model=FinanceEnvelope)
def budgets(project_id: str | None = None, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.list_budgets(project_id)))


@router.post("/budgets", response_model=FinanceEnvelope)
def create_budget(payload: BudgetCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/budgets", idempotency_key, payload.model_dump(mode="json"), lambda: svc.create_budget(payload), response)


@router.get("/budgets/{budget_id}", response_model=FinanceEnvelope)
def budget_detail(budget_id: str, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.get_budget(budget_id)))


@router.put("/budgets/{budget_id}/lines", response_model=FinanceEnvelope)
def replace_budget_lines(budget_id: str, payload: BudgetLinesReplace, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.replace_budget_lines(budget_id, payload)))


@router.post("/budgets/{budget_id}/approve", response_model=FinanceEnvelope)
def approve_budget(budget_id: str, payload: BudgetApprove, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/budgets/{budget_id}/approve", idempotency_key, payload.model_dump(), lambda: svc.approve_budget(budget_id, payload.version), response)


@router.post("/budgets/lines/{line_id}/adjustments", response_model=FinanceEnvelope)
def adjust_budget(line_id: str, payload: BudgetAdjustmentCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/budgets/lines/{line_id}/adjustments", idempotency_key, payload.model_dump(mode="json"), lambda: svc.adjust_budget_line(line_id, payload), response)


# ---------- reimbursements and approvals ----------
@router.get("/reimbursements", response_model=FinanceEnvelope)
def reimbursements(status: str | None = None, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.list_reimbursements(status)))


@router.post("/reimbursements", response_model=FinanceEnvelope)
def create_reimbursement(payload: ReimbursementCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/reimbursements", idempotency_key, payload.model_dump(), lambda: svc.create_reimbursement(payload), response)


@router.get("/reimbursements/{reimbursement_id}", response_model=FinanceEnvelope)
def reimbursement_detail(reimbursement_id: str, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.get_reimbursement(reimbursement_id)))


@router.patch("/reimbursements/{reimbursement_id}", response_model=FinanceEnvelope)
def update_reimbursement(reimbursement_id: str, payload: ReimbursementUpdate, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.update_reimbursement(reimbursement_id, payload)))


@router.post("/reimbursements/{reimbursement_id}/items", response_model=FinanceEnvelope)
def add_reimbursement_item(reimbursement_id: str, payload: ReimbursementItemCreate, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.add_reimbursement_item(reimbursement_id, payload)))


@router.patch("/reimbursements/{reimbursement_id}/items/{item_id}", response_model=FinanceEnvelope)
def update_reimbursement_item(reimbursement_id: str, item_id: str, payload: ReimbursementItemUpdate, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.update_reimbursement_item(reimbursement_id, item_id, payload)))


@router.delete("/reimbursements/{reimbursement_id}/items/{item_id}", response_model=FinanceEnvelope)
def delete_reimbursement_item(reimbursement_id: str, item_id: str, version: int = Query(..., ge=1), svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.delete_reimbursement_item(reimbursement_id, item_id, version)))


@router.post("/reimbursements/{reimbursement_id}/submit", response_model=FinanceEnvelope)
def submit_reimbursement(reimbursement_id: str, payload: ReimbursementSubmit, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/reimbursements/{reimbursement_id}/submit", idempotency_key, payload.model_dump(), lambda: svc.submit_reimbursement(reimbursement_id, payload.version), response)


@router.post("/reimbursements/{reimbursement_id}/redraft", response_model=FinanceEnvelope)
def redraft_reimbursement(reimbursement_id: str, payload: ReimbursementSubmit, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.return_to_draft(reimbursement_id, payload.version)))


@router.post("/reimbursements/{reimbursement_id}/archive", response_model=FinanceEnvelope)
def archive_reimbursement(reimbursement_id: str, payload: ReimbursementSubmit, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/reimbursements/{reimbursement_id}/archive", idempotency_key, payload.model_dump(), lambda: svc.archive_reimbursement(reimbursement_id, payload.version), response)


@router.get("/approval-workflows", response_model=FinanceEnvelope)
def workflows(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_workflows))


@router.post("/approval-workflows", response_model=FinanceEnvelope)
def create_workflow(payload: WorkflowCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/approval-workflows", idempotency_key, payload.model_dump(mode="json"), lambda: svc.create_workflow(payload), response)


@router.get("/approval-tasks/me", response_model=FinanceEnvelope)
def approval_tasks(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_my_approval_tasks))


def approval_action(task_id: str, action: str, payload: ApprovalAction, response: Response, key: str | None, svc: FinanceServiceV2):
    return idempotent(svc, f"POST:/approval-tasks/{task_id}/{action}", key, payload.model_dump(), lambda: svc.act_approval(task_id, action, payload.comment), response)


@router.post("/approval-tasks/{task_id}/approve", response_model=FinanceEnvelope)
def approve_task(task_id: str, payload: ApprovalAction, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return approval_action(task_id, "approve", payload, response, idempotency_key, svc)


@router.post("/approval-tasks/{task_id}/return", response_model=FinanceEnvelope)
def return_task(task_id: str, payload: ApprovalAction, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return approval_action(task_id, "return", payload, response, idempotency_key, svc)


@router.post("/approval-tasks/{task_id}/reject", response_model=FinanceEnvelope)
def reject_task(task_id: str, payload: ApprovalAction, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return approval_action(task_id, "reject", payload, response, idempotency_key, svc)


# ---------- invoices ----------
@router.get("/invoice-batches", response_model=FinanceEnvelope)
def invoice_batches(
    project_id: str = Query(""),
    status: str = Query("", pattern="^(|received|processing|review_required|completed|failed|cancelled)$"),
    limit: int = Query(100, ge=1, le=500),
    svc: FinanceServiceV2 = Depends(service),
):
    records = call(
        lambda: FinanceInvoiceBatchService(svc).list_batches(
            project_id=project_id,
            status=status,
            limit=limit,
        )
    )
    return envelope(records, total=len(records))


@router.post("/invoice-batches", response_model=FinanceEnvelope)
def create_invoice_batch(
    payload: InvoiceBatchCreate,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    svc: FinanceServiceV2 = Depends(service),
):
    return idempotent(
        svc,
        "POST:/invoice-batches",
        idempotency_key,
        payload.model_dump(mode="json"),
        lambda: FinanceInvoiceBatchService(svc).create_batch(payload),
        response,
    )


@router.get("/invoice-batches/{batch_id}", response_model=FinanceEnvelope)
def invoice_batch_detail(batch_id: str, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: FinanceInvoiceBatchService(svc).get_batch(batch_id)))


@router.post("/invoice-batches/{batch_id}/files", response_model=FinanceEnvelope)
async def upload_invoice_batch_file(
    batch_id: str,
    response: Response,
    request: Request,
    filename: str = Header(..., alias="X-Filename"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    svc: FinanceServiceV2 = Depends(service),
):
    content = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    payload = {
        "batch_id": batch_id,
        "filename": filename,
        "content_type": content_type,
        "sha256": __import__("hashlib").sha256(content).hexdigest(),
    }
    return idempotent(
        svc,
        f"POST:/invoice-batches/{batch_id}/files",
        idempotency_key,
        payload,
        lambda: FinanceInvoiceBatchService(svc).add_file(batch_id, filename, content_type, content),
        response,
    )


@router.post("/invoice-batches/{batch_id}/start", response_model=FinanceEnvelope)
def start_invoice_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    svc: FinanceServiceV2 = Depends(service),
):
    result = idempotent(
        svc,
        f"POST:/invoice-batches/{batch_id}/start",
        idempotency_key,
        {},
        lambda: FinanceInvoiceBatchService(svc).start_batch(batch_id),
        response,
    )
    if response.headers.get("Idempotency-Replayed") == "false" and result["data"].get("queued"):
        background_tasks.add_task(process_invoice_batch_job, batch_id)
    return result


@router.post("/invoice-batches/{batch_id}/retry", response_model=FinanceEnvelope)
def retry_invoice_batch(
    batch_id: str,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    svc: FinanceServiceV2 = Depends(service),
):
    return idempotent(
        svc,
        f"POST:/invoice-batches/{batch_id}/retry",
        idempotency_key,
        {},
        lambda: FinanceInvoiceBatchService(svc).retry_failed(batch_id),
        response,
    )


@router.get("/invoices", response_model=FinanceEnvelope)
def invoices(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_invoices))


@router.post("/invoices", response_model=FinanceEnvelope)
def create_invoice(payload: InvoiceCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/invoices", idempotency_key, payload.model_dump(mode="json"), lambda: svc.create_invoice(payload), response)


@router.post("/invoices/{invoice_id}/attachments", response_model=FinanceEnvelope)
async def upload_invoice_attachment(
    invoice_id: str,
    response: Response,
    request: Request,
    filename: str = Header(..., alias="X-Filename"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    svc: FinanceServiceV2 = Depends(service),
):
    content = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    payload = {"invoice_id": invoice_id, "filename": filename, "content_type": content_type, "sha256": __import__("hashlib").sha256(content).hexdigest()}
    return idempotent(svc, f"POST:/invoices/{invoice_id}/attachments", idempotency_key, payload, lambda: svc.attach_invoice(invoice_id, filename, content_type, content), response)


@router.get("/attachments/{attachment_id}/download-url", response_model=FinanceEnvelope)
def attachment_download_url(attachment_id: str, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.attachment_url(attachment_id)))


@router.get("/attachments/{attachment_id}/content")
def attachment_content(attachment_id: str, svc: FinanceServiceV2 = Depends(service)):
    content, content_type, filename = call(lambda: svc.attachment_content(attachment_id))
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": disposition, "Cache-Control": "private, no-store"},
    )


@router.post("/invoices/{invoice_id}/ocr", response_model=FinanceEnvelope)
def run_invoice_ocr(invoice_id: str, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/invoices/{invoice_id}/ocr", idempotency_key, {}, lambda: svc.run_ocr(invoice_id), response)


@router.post("/invoices/{invoice_id}/verify", response_model=FinanceEnvelope)
def verify_invoice(invoice_id: str, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/invoices/{invoice_id}/verify", idempotency_key, {}, lambda: svc.verify_invoice(invoice_id), response)


# ---------- payments and reconciliation ----------
@router.get("/payments", response_model=FinanceEnvelope)
def payments(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_payments))


@router.post("/payments", response_model=FinanceEnvelope)
def create_payment(payload: PaymentCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/payments", idempotency_key, payload.model_dump(mode="json"), lambda: svc.create_payment(payload), response)


@router.post("/payments/{payment_id}/confirm", response_model=FinanceEnvelope)
def confirm_payment(payment_id: str, payload: PaymentConfirm, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, f"POST:/payments/{payment_id}/confirm", idempotency_key, payload.model_dump(mode="json"), lambda: svc.confirm_payment(payment_id, payload), response)


@router.post("/bank-statements/import", response_model=FinanceEnvelope)
async def import_bank_statement(
    response: Response,
    request: Request,
    filename: str = Header(..., alias="X-Filename"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    svc: FinanceServiceV2 = Depends(service),
):
    content = await request.body()
    payload = {"filename": filename, "sha256": __import__("hashlib").sha256(content).hexdigest()}
    return idempotent(svc, "POST:/bank-statements/import", idempotency_key, payload, lambda: svc.import_statement(filename, content), response)


@router.get("/reconciliations", response_model=FinanceEnvelope)
def reconciliations(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.list_reconciliations))


@router.post("/reconciliations/confirm", response_model=FinanceEnvelope)
def confirm_reconciliations(payload: ReconciliationConfirm, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(
        svc,
        "POST:/reconciliations/confirm",
        idempotency_key,
        payload.model_dump(),
        lambda: {
            "records": svc.confirm_reconciliations(
                payload.matches,
                human_confirmed=payload.human_confirmed,
                confirmation_note=payload.confirmation_note,
            )
        },
        response,
    )


# ---------- reports and explicit imports ----------
@router.get("/reports/budget-execution", response_model=FinanceEnvelope)
def budget_report(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.budget_execution_report))


@router.get("/reports/expenses", response_model=FinanceEnvelope)
def expense_report(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.expense_report))


@router.get("/reports/payments", response_model=FinanceEnvelope)
def payment_report(svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(svc.payment_report))


@router.get("/reports/audit", response_model=FinanceEnvelope)
def audit_report(limit: int = Query(200, ge=1, le=1000), svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.audit_report(limit)))


@router.post("/imports", response_model=FinanceEnvelope)
def create_import(payload: ImportRequest, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), svc: FinanceServiceV2 = Depends(service)):
    return idempotent(svc, "POST:/imports", idempotency_key, payload.model_dump(), lambda: svc.create_import_job(payload.source_type, payload.dry_run), response)


@router.get("/imports/{job_id}", response_model=FinanceEnvelope)
def import_detail(job_id: str, svc: FinanceServiceV2 = Depends(service)):
    return envelope(call(lambda: svc.get_import_job(job_id)))


# ---------- one-release legacy compatibility ----------
@router.get("/summary", deprecated=True)
def legacy_summary(response: Response, svc: FinanceServiceV2 = Depends(service)):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-10-01"
    return call(svc.compatibility_summary)


@router.get("/sync", deprecated=True)
def legacy_sync_removed():
    raise HTTPException(410, detail={"code": "sync_moved", "message": "数据导入已迁移到 POST /api/finance/imports"})


@router.get("/budget", deprecated=True)
def legacy_budget(response: Response, svc: FinanceServiceV2 = Depends(service)):
    response.headers["Deprecation"] = "true"
    return call(svc.budget_execution_report)


@router.put("/budget/categories/{project_key}/{category}", deprecated=True)
def legacy_budget_update(project_key: str, category: str, response: Response, payload: dict = Body(default_factory=dict), svc: FinanceServiceV2 = Depends(service)):
    response.headers["Deprecation"] = "true"
    project = svc.db.query(FinanceProject).filter_by(project_key=project_key).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    line = svc.db.query(BudgetLine).join(BudgetVersion).filter(
        BudgetVersion.project_id == project.id,
        BudgetVersion.status == "approved",
        BudgetLine.category == category,
    ).first()
    if not line:
        raise HTTPException(404, "预算科目不存在")
    request = BudgetAdjustmentCreate(version=line.lock_version, amount=payload.get("budget_amount", 0), reason=payload.get("reason") or "兼容接口预算调整")
    return call(lambda: svc.adjust_budget_line(line.id, request))


@router.post("/reimbursements/{reimbursement_key}/status", deprecated=True)
def legacy_status_transition(reimbursement_key: str):
    raise HTTPException(410, detail={"code": "approval_required", "message": "状态直改已禁用，请使用提交、审批、付款和归档接口"})


@router.get("/quality", deprecated=True)
def legacy_quality(svc: FinanceServiceV2 = Depends(service)):
    invoices = svc.list_invoices()
    review = [item for item in invoices if item["status"] == "manual_review"]
    return {"status": "ready", "summary": {"records": len(invoices), "complete": len(invoices) - len(review), "needs_review": len(review), "missing_amount": 0, "missing_date": 0}, "issues": [], "records": review}


@router.get("/enrichment", deprecated=True)
def legacy_enrichment():
    return {"status": "ready", "summary": {"suggestions": 0, "pending": 0, "applied": 0, "high_confidence": 0}, "fields": [], "suggestions": []}


@router.post("/enrichment/run", deprecated=True)
def legacy_enrichment_run():
    return {"status": "manual_review", "scanned": 0, "suggestions_upserted": 0}


@router.get("/schema", deprecated=True)
def finance_schema(response: Response, svc: FinanceServiceV2 = Depends(service)):
    call(lambda: svc.require("finance_admin"))
    response.headers["Deprecation"] = "true"
    inspector = inspect(svc.db.bind)
    names = [name for name in inspector.get_table_names() if name.startswith(("finance_", "budget_", "reimbursement", "invoice", "approval_", "payment", "bank_", "reconciliation", "expense_", "fund_"))]
    return {"status": "ready", "tables": [{"name": name, "table": name, "columns": inspector.get_columns(name)} for name in sorted(names)]}


@router.get("/tables/{table_name}", deprecated=True)
def finance_table(table_name: str, limit: int = Query(100, ge=1, le=500), svc: FinanceServiceV2 = Depends(service)):
    call(lambda: svc.require("finance_admin"))
    allowed = {mapper.local_table.name: mapper.class_ for mapper in __import__("models.finance_models", fromlist=["Base"]).Base.registry.mappers if mapper.local_table.name == table_name}
    model = allowed.get(table_name)
    if not model:
        raise HTTPException(404, "财务表不存在")
    rows = svc.db.query(model).limit(limit).all()
    return {"status": "ready", "name": table_name, "table": table_name, "total": svc.db.query(model).count(), "rows": [row_dict(row) for row in rows]}
