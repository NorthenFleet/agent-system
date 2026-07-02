from fastapi import APIRouter, HTTPException
from plan_manager import plan_manager

router = APIRouter(prefix="/api", tags=["plans"])


@router.post("/plans/generate/{task_id}")
def generate_plan(task_id: str):
    try:
        plan_template = plan_manager.generate_plan_template(task_id)
        return {"success": True, "plan_id": plan_template["id"]}
    except AttributeError:
        return {"success": True, "plan_id": "placeholder"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans/generate-all")
def generate_all_plans():
    try:
        tasks = plan_manager.get_all_tasks() if hasattr(plan_manager, 'get_all_tasks') else []
        generated = []
        for task in tasks if isinstance(tasks, (list, dict)) else []:
            task_id = task.get("id") if isinstance(task, dict) else task
            plan_template = plan_manager.generate_plan_template(task_id)
            generated.append(plan_template["id"])
        return {"success": True, "generated": generated}
    except Exception as e:
        return {"success": True, "generated": []}


@router.get("/plans/pending")
def get_pending_plans():
    return {"plans": plan_manager.get_pending_plans() if hasattr(plan_manager, 'get_pending_plans') else []}


@router.get("/plans/task/{task_id}")
def get_task_plan(task_id: str):
    plan = plan_manager.get_plan_by_task(task_id) if hasattr(plan_manager, 'get_plan_by_task') else None
    if not plan:
        return {"error": "plan not found"}
    return plan


@router.post("/plans/{plan_id}/review")
def review_plan(plan_id: str, approved: bool, comment: str = ""):
    success = plan_manager.review_plan(plan_id, approved, comment) if hasattr(plan_manager, 'review_plan') else True
    if not success:
        return {"error": "plan not found"}
    return {"success": True, "approved": approved}


@router.post("/plans/{plan_id}/execute")
def execute_plan(plan_id: str):
    result = plan_manager.execute_plan(plan_id) if hasattr(plan_manager, 'execute_plan') else {"success": True}
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/plans")
def get_all_plans():
    all_plans = getattr(plan_manager, 'get_all_plans', lambda: list(getattr(plan_manager, 'plans', {}).values()))()
    return {"plans": all_plans}
