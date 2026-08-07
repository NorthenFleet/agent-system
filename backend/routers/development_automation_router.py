from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.auth_router import get_current_user, require_role
from services.development_automation_service import development_automation_service


router = APIRouter(prefix="/api/v3/development", tags=["development-automation"])


class DevelopmentPlanCreate(BaseModel):
    project_id: str
    target_kind: str
    target_id: str
    instruction: str
    task_type: Optional[str] = None
    developer_agent_id: Optional[str] = None
    planner_agent_id: Optional[str] = None
    evaluator_agent_id: Optional[str] = None
    max_rounds: int = 2
    repo: Optional[str] = None


class DevelopmentPlanDecision(BaseModel):
    action: str
    comment: str = ""
    auto_execute: bool = True


class DevelopmentPlanExecute(BaseModel):
    comment: str = ""


def _actor(user: dict) -> str:
    return str(user.get("sub") or user.get("username") or user.get("id") or "unknown")


@router.get("/task-types")
def list_task_types(_user: dict = Depends(get_current_user)):
    return {"task_types": development_automation_service.list_task_types()}


@router.get("/plans")
def list_plans(
    project_id: Optional[str] = Query(None),
    target_kind: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    return {"plans": development_automation_service.list_plans(project_id, target_kind, target_id)}


@router.post("/plans", status_code=201)
def create_plan(request: DevelopmentPlanCreate, user: dict = Depends(require_role("admin", "agent"))):
    try:
        plan = development_automation_service.create_plan(
            **request.model_dump(), created_by=_actor(user)
        )
        return {"plan": plan}
    except KeyError as exc:
        raise HTTPException(404, "项目或开发任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, _user: dict = Depends(get_current_user)):
    plan = development_automation_service.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "开发计划不存在")
    return {"plan": plan}


@router.post("/plans/{plan_id}/decision")
def decide_plan(
    plan_id: str,
    request: DevelopmentPlanDecision,
    user: dict = Depends(require_role("admin")),
):
    try:
        return {"plan": development_automation_service.decide_plan(
            plan_id, request.action, _actor(user), str(user.get("role") or ""),
            request.comment, request.auto_execute,
        )}
    except KeyError as exc:
        raise HTTPException(404, "开发计划不存在") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Codex Loop 启动失败：{exc}") from exc


@router.post("/plans/{plan_id}/execute")
def execute_plan(
    plan_id: str,
    _request: DevelopmentPlanExecute,
    user: dict = Depends(require_role("admin")),
):
    try:
        return {"plan": development_automation_service.execute_plan(plan_id, _actor(user))}
    except KeyError as exc:
        raise HTTPException(404, "开发计划不存在") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Codex Loop 启动失败：{exc}") from exc


@router.post("/plans/{plan_id}/retry-integration")
def retry_plan_integration(plan_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return {"plan": development_automation_service.retry_integration(plan_id, _actor(user))}
    except KeyError as exc:
        raise HTTPException(404, "开发计划不存在") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(409, f"集成分支仍存在冲突：{exc}") from exc


@router.post("/plans/{plan_id}/redispatch")
def redispatch_plan_execution(plan_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return {"plan": development_automation_service.redispatch_execution(plan_id, _actor(user))}
    except KeyError as exc:
        raise HTTPException(404, "开发计划不存在") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Codex Loop 重新派发失败：{exc}") from exc
