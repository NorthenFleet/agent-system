from fastapi import APIRouter
from auto_plan_manager import auto_plan_manager

router = APIRouter(prefix="/api", tags=["automated_planning"])


@router.get("/auto/tasks")
def get_auto_tasks():
    return {"auto_tasks": []}


@router.get("/auto/logs")
def get_auto_logs(limit: int = 50):
    return {"logs": auto_plan_manager.get_auto_logs(limit)}


@router.post("/auto/leonardo/generate")
def trigger_leonardo_generate():
    try:
        result = auto_plan_manager.leonardo_auto_generate()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/auto/optimus/review")
def trigger_optimus_review():
    try:
        result = auto_plan_manager.optimus_auto_review(auto_approve=True)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/auto/status")
def get_auto_status():
    return {
        "running": False,
        "leonardo_interval": 900,
        "optimus_interval": 600,
        "leonardo_interval_min": 15,
        "optimus_interval_min": 10,
    }


@router.put("/auto/leonardo/interval")
def update_leonardo_interval(minutes: int = 15):
    return {"message": "Leonardo interval updated", "interval_minutes": minutes}


@router.put("/auto/optimus/interval")
def update_optimus_interval(minutes: int = 10):
    return {"message": "Optimus interval updated", "interval_minutes": minutes}


@router.post("/auto/start")
def start_auto_tasks():
    return {"message": "Auto tasks started"}


@router.post("/auto/stop")
def stop_auto_tasks():
    return {"message": "Auto tasks stopped"}
