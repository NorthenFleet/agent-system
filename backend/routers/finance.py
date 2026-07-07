"""Finance API backed by the local finance database."""

from fastapi import APIRouter, Body, HTTPException, Query

from services.finance_service import finance_service

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/summary")
def finance_summary(limit: int = Query(120, ge=1, le=500)):
    return finance_service.summary(limit=limit)


@router.get("/sync")
def sync_finance_sources():
    return finance_service.sync_sources()


@router.get("/schema")
def finance_schema():
    return finance_service.schema_summary()


@router.get("/budget")
def finance_budget():
    return finance_service.budget_report()


@router.put("/budget/categories/{project_key}/{category}")
def update_finance_budget_category(
    project_key: str,
    category: str,
    payload: dict = Body(default_factory=dict),
):
    result = finance_service.update_budget_category(
        project_key=project_key,
        category=category,
        budget_amount=float(payload.get("budget_amount") or 0),
        actor=str(payload.get("actor") or "user"),
        reason=str(payload.get("reason") or ""),
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/reimbursements")
def finance_reimbursements(limit: int = Query(100, ge=1, le=500)):
    return finance_service.reimbursements_report(limit=limit)


@router.post("/reimbursements/{reimbursement_key}/status")
def transition_finance_reimbursement(
    reimbursement_key: str,
    payload: dict = Body(default_factory=dict),
):
    result = finance_service.transition_reimbursement_status(
        reimbursement_key=reimbursement_key,
        to_status=str(payload.get("status") or ""),
        actor=str(payload.get("actor") or "user"),
        comment=str(payload.get("comment") or ""),
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/quality")
def finance_quality(limit: int = Query(100, ge=1, le=500)):
    return finance_service.quality_report(limit=limit)


@router.get("/enrichment")
def finance_enrichment(limit: int = Query(100, ge=1, le=500)):
    return finance_service.enrichment_report(limit=limit)


@router.post("/enrichment/run")
def run_finance_enrichment(limit: int = Query(100, ge=1, le=500)):
    return finance_service.run_enrichment(limit=limit)


@router.get("/tables/{table_name}")
def finance_table(
    table_name: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    result = finance_service.table_records(table_name, limit=limit, offset=offset)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result
