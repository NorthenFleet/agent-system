import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from task_queue import task_manager

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _get_plan_manager():
    from plan_manager import plan_manager
    return plan_manager


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@router.post("/generate-all")
def generate_plans_for_all():
    """李奥纳多为所有空闲任务生成计划"""
    plan_mgr = _get_plan_manager()
    tasks = task_manager.get_all_tasks()
    generated = []
    skipped = []

    for task in tasks:
        if task["status"] in ["pending", "in_progress"]:
            existing_plan = plan_mgr.get_plan_by_task(task["id"])
            if not existing_plan:
                plan_template = plan_mgr.generate_plan_template(task)
                plan = plan_mgr.create_plan(task["id"], plan_template, "李奥纳多")
                generated.append({"task_id": task["id"], "plan_id": plan["id"]})
            else:
                skipped.append({"task_id": task["id"], "reason": "计划已存在"})

    return {"success": True, "generated": generated, "skipped": skipped}


@router.post("/generate/{task_id}")
def generate_plan_for_task(task_id: str):
    """李奥纳多为任务生成计划"""
    plan_mgr = _get_plan_manager()
    tasks = task_manager.get_all_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    existing_plan = plan_mgr.get_plan_by_task(task_id)
    if existing_plan:
        raise HTTPException(status_code=400, detail="计划已存在")

    plan_template = plan_mgr.generate_plan_template(task)
    plan = plan_mgr.create_plan(task_id, plan_template, "李奥纳多")

    return {"success": True, "plan": plan}


@router.get("/pending")
def get_pending_plans():
    """获取待审核计划"""
    plan_mgr = _get_plan_manager()
    return {"plans": plan_mgr.get_pending_plans()}


@router.get("/task/{task_id}")
def get_plans_for_task(task_id: str):
    """获取任务的计划"""
    plan_mgr = _get_plan_manager()
    plan = plan_mgr.get_plan_by_task(task_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    return plan


@router.post("/{plan_id}/review")
def review_plan(plan_id: str, approved: bool, comment: str = ""):
    """擎天柱审核计划"""
    plan_mgr = _get_plan_manager()
    success = plan_mgr.review_plan(plan_id, approved, "擎天柱", comment)
    if not success:
        raise HTTPException(status_code=404, detail="计划不存在")
    return {"success": True, "approved": approved}


@router.post("/{plan_id}/execute/{step_index}")
def execute_plan_step(plan_id: str, step_index: int):
    """执行计划步骤"""
    plan_mgr = _get_plan_manager()
    result = plan_mgr.execute_plan_step(plan_id, step_index)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{plan_id}/execute-all")
def execute_all_plan_steps(plan_id: str):
    """执行计划所有步骤"""
    plan_mgr = _get_plan_manager()
    plan = plan_mgr.plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    if plan["status"] != "approved":
        raise HTTPException(status_code=400, detail="计划未通过审核")

    results = []
    for i in range(len(plan.get("steps", []))):
        result = plan_mgr.execute_plan_step(plan_id, i)
        results.append(result)

    return {"success": True, "results": results}


@router.get("")
def get_all_plans():
    """获取所有计划"""
    plan_mgr = _get_plan_manager()
    return {"plans": list(plan_mgr.plans.values())}


# Jinja2 模板渲染的路由需要单独注册到 app 上
def register_templates(app):
    """注册模板渲染路由"""
    @app.get("/plans")
    async def plans_page(request):
        """任务计划页面"""
        from fastapi.requests import Request
        return FileResponse(
            os.path.join(FRONTEND_DIR, "plans.html"),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )
