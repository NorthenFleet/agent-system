"""
Legacy Plans & Auto routes extracted from main.py
"""
import asyncio
import os
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["legacy-plans-auto"])

_task_manager = None
_plan_manager = None
_auto_plan_manager = None


def set_managers(tm, pm, apm):
    global _task_manager, _plan_manager, _auto_plan_manager
    _task_manager = tm
    _plan_manager = pm
    _auto_plan_manager = apm


# ─── Plans ───

@router.post("/api/plans/generate-all")
def generate_all_plans():
    tasks = _task_manager.get_all_tasks()
    generated, skipped = [], []
    for task in tasks:
        if task["status"] in ["pending", "in_progress"]:
            existing = _plan_manager.get_plan_by_task(task["id"])
            if not existing:
                template = _plan_manager.generate_plan_template(task)
                plan = _plan_manager.create_plan(task["id"], template, "李奥纳多")
                generated.append({"task_id": task["id"], "plan_id": plan["id"]})
            else:
                skipped.append({"task_id": task["id"], "reason": "计划已存在"})
    return {"success": True, "generated": generated, "skipped": skipped}


@router.post("/api/plans/generate/{task_id}")
def generate_plan(task_id: str):
    tasks = _task_manager.get_all_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    existing = _plan_manager.get_plan_by_task(task_id)
    if existing:
        raise HTTPException(status_code=400, detail="计划已存在")
    template = _plan_manager.generate_plan_template(task)
    plan = _plan_manager.create_plan(task_id, template, "李奥纳多")
    return {"success": True, "plan": plan}


@router.get("/api/plans/pending")
def get_pending_plans():
    return {"plans": _plan_manager.get_pending_plans()}


@router.get("/api/plans/task/{task_id}")
def get_task_plan(task_id: str):
    plan = _plan_manager.get_plan_by_task(task_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    return plan


@router.post("/api/plans/{plan_id}/review")
def review_plan_endpoint(plan_id: str, approved: bool, comment: str = ""):
    success = _plan_manager.review_plan(plan_id, approved, "擎天柱", comment)
    if not success:
        raise HTTPException(status_code=404, detail="计划不存在")
    return {"success": True, "approved": approved}


@router.post("/api/plans/{plan_id}/execute/{step_index}")
def execute_plan_step_endpoint(plan_id: str, step_index: int):
    result = _plan_manager.execute_plan_step(plan_id, step_index)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/plans/{plan_id}/execute-all")
def execute_all_steps_endpoint(plan_id: str):
    plan = _plan_manager.plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    if plan["status"] != "approved":
        raise HTTPException(status_code=400, detail="计划未通过审核")
    results = []
    for i in range(len(plan.get("steps", []))):
        results.append(_plan_manager.execute_plan_step(plan_id, i))
    return {"success": True, "results": results}


@router.get("/api/plans")
def get_all_plans():
    return {"plans": list(_plan_manager.plans.values())}


@router.get("/plans")
def plans_page():
    from fastapi.responses import FileResponse
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend")
    return FileResponse(
        os.path.join(frontend_dir, "plans.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


# ─── Auto ───

@router.get("/api/auto/logs")
def get_auto_logs(limit: int = 50):
    return {"logs": _auto_plan_manager.get_auto_logs(limit)}


@router.post("/api/auto/leonardo/generate")
def trigger_leonardo_generate():
    return _auto_plan_manager.leonardo_auto_generate()


@router.post("/api/auto/optimus/review")
def trigger_optimus_review():
    return _auto_plan_manager.optimus_auto_review(auto_approve=True)


# ─── Scheduler ───

@router.get("/api/scheduler/status")
def get_scheduler_status():
    from services.scheduler_service import scheduler_service
    return scheduler_service.get_scheduler_status()


@router.post("/api/scheduler/reload")
def reload_scheduler():
    from services.scheduler_service import scheduler_service
    try:
        scheduler_service.load_active_tasks()
        return {"success": True, "message": "已重新加载 active 任务"}
    except Exception as e:
        return {"success": False, "error": str(e)}
