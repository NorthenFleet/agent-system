"""Authenticated, side-effect-free cluster monitoring projection."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from routers.auth_router import get_current_user
from services.cluster_inventory_service import ClusterInventoryService
from services.auth_settings_service import is_login_enabled
from services.cluster_execution import execution_preparation


router = APIRouter(prefix="/api/v2/monitoring", tags=["v2-monitoring"])


@router.get("/cluster")
def get_cluster_inventory(
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    snapshot = ClusterInventoryService(db).snapshot()
    snapshot["execution"] = execution_preparation(snapshot, login_required=is_login_enabled(db))
    return snapshot
