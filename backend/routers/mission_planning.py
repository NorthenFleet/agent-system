"""Project-scoped integration API for the AI Planning product on port 5130."""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from project_manager import project_manager
from services.auth_service import get_current_user, require_role
from services.mission_planning_adapter import (
    MissionPlanningError,
    mission_planning_adapter,
)
from services.mission_planning_automation import evaluate_signals
from services.mission_run_protocol import (
    create_run,
    current_run,
    ensure_mission_protocol,
    protocol_summary,
    record_artifact,
    record_command,
    record_event,
    transition_run,
    update_binding,
)
from services.project_composition import upsert_product_binding
from unified_data_manager import unified_data_manager


router = APIRouter(prefix="/api/v3/mission-planning", tags=["mission-planning"])


class MissionPlanningBindRequest(BaseModel):
    scenario_id: str
    side: str = "red"


class MissionPlanningAgentToolRequest(BaseModel):
    agent_id: str
    tool_name: str
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class MissionPlanningApprovalDecision(BaseModel):
    approved: bool
    comment: str = ""


class MissionPlanningAutomationUpdate(BaseModel):
    enabled: bool


TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "inspect_status": {
        "name": "读取规划状态",
        "description": "读取5130监督器状态并同步项目摘要",
        "approval_required": False,
        "payload_fields": [],
    },
    "bind_scenario": {
        "name": "绑定任务想定",
        "description": "将项目绑定到指定5130想定和规划方",
        "approval_required": True,
        "payload_fields": ["scenario_id", "side"],
    },
    "start_run": {
        "name": "启动规划与推演",
        "description": "加载已绑定想定、生成计划并启动闭环监督",
        "approval_required": True,
        "payload_fields": [],
    },
    "stop_run": {
        "name": "停止规划与推演",
        "description": "停止5130闭环监督器",
        "approval_required": True,
        "payload_fields": [],
    },
    "replan": {
        "name": "触发重新规划",
        "description": "根据当前态势触发一次人工原因标记的重规划",
        "approval_required": True,
        "payload_fields": ["reason"],
    },
}


_MONITOR_TASK: asyncio.Task | None = None
_MONITOR_STOP: asyncio.Event | None = None
_MONITOR_EVALUATION_LOCK = asyncio.Lock()
_MONITOR_STATE: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "last_tick_at": "",
    "last_error": "",
    "projects_checked": 0,
    "suggestions_created": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_epoch(value: Any) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _project(project_id: str) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _integration(project: dict[str, Any]) -> dict[str, Any]:
    context = project.get("context") if isinstance(project.get("context"), dict) else {}
    value = context.get("mission_planning")
    return dict(value) if isinstance(value, dict) else {}


def _save(project: dict[str, Any], integration: dict[str, Any]) -> dict[str, Any]:
    context = dict(project.get("context") or {})
    context["mission_planning"] = integration
    project["context"] = context
    if integration.get("scenario_id"):
        common_config = {
            "scenario_id": integration.get("scenario_id"),
            "scenario_name": integration.get("scenario_name"),
            "scenario_type": integration.get("scenario_type"),
        }
        upsert_product_binding(
            project,
            "ai-planning-5130",
            role="planner",
            status="running" if integration.get("status") == "running" else "bound",
            config={**common_config, "side": integration.get("side")},
            source="mission-planning",
        )
        upsert_product_binding(
            project,
            "one-sim",
            role="simulator",
            status="running" if integration.get("status") == "running" else "bound",
            config={**common_config, "mode": "embedded-planning-situation"},
            source="mission-planning",
        )
    updated = project_manager.update_project(project["id"], {
        "context": context,
        "enabled_modules": project.get("enabled_modules") or [],
        "product_bindings": project.get("product_bindings") or [],
    })
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


def _ensure_protocol(project: dict[str, Any], integration: dict[str, Any]) -> bool:
    return ensure_mission_protocol(
        project,
        integration,
        product_url=mission_planning_adapter.public_url,
    )


def _actor(user: dict[str, Any]) -> str:
    return f"human:{user.get('username') or user.get('sub') or 'unknown'}"


def _sanitize_agent_id(agent_id: str) -> str:
    value = str(agent_id or "").strip()
    if not re.fullmatch(r"[\w.\-\u4e00-\u9fff]{1,64}", value):
        raise HTTPException(status_code=400, detail="agent_id 格式无效")
    return value


def _sanitize_tool_payload(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = set(TOOL_CATALOG[tool_name]["payload_fields"])
    clean = {key: value for key, value in payload.items() if key in allowed}
    if tool_name == "bind_scenario":
        scenario_id = str(clean.get("scenario_id") or "").strip()
        side = str(clean.get("side") or "red").strip().lower()
        if not scenario_id:
            raise HTTPException(status_code=400, detail="bind_scenario 需要 scenario_id")
        if side not in {"red", "blue"}:
            raise HTTPException(status_code=400, detail="side must be red or blue")
        return {"scenario_id": scenario_id, "side": side}
    if tool_name == "replan":
        return {"reason": str(clean.get("reason") or "智能体请求重新规划").strip()[:200]}
    return {}


def _approval_requests(integration: dict[str, Any]) -> list[dict[str, Any]]:
    rows = integration.get("approval_requests")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _save_approval_request(project_id: str, request_id: str, updates: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    project = _project(project_id)
    integration = _integration(project)
    rows = _approval_requests(integration)
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    row.update(updates)
    integration["approval_requests"] = rows[-100:]
    updated = _save(project, integration)
    return updated, row


def _audit_request(action: str, row: dict[str, Any], actor: str, before: Any = None) -> None:
    unified_data_manager.record_audit(
        action,
        "mission_planning_approval",
        str(row.get("id") or "unknown"),
        actor=actor,
        before_state=before,
        after_state=row,
        metadata={
            "project_id": row.get("project_id"),
            "agent_id": row.get("agent_id"),
            "tool_name": row.get("tool_name"),
        },
    )


def _log_request(project_id: str, row: dict[str, Any], action: str, content: str, actor: str | None = None) -> None:
    project_manager.add_log(
        project_id,
        None,
        actor or str(row.get("agent_id") or "system"),
        action,
        content,
    )


def _create_tool_request(
    project_id: str,
    *,
    agent_id: str,
    tool_name: str,
    reason: str,
    payload: dict[str, Any] | None,
    requested_by: str,
    source: str = "manual",
    trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = _project(project_id)
    if tool_name not in TOOL_CATALOG:
        raise HTTPException(status_code=400, detail="不支持的智能体工具")
    clean_agent_id = _sanitize_agent_id(agent_id)
    clean_payload = _sanitize_tool_payload(tool_name, payload or {})
    spec = TOOL_CATALOG[tool_name]
    trigger = dict(trigger or {})
    row = {
        "id": f"mpapproval-{uuid.uuid4().hex[:12]}",
        "project_id": project_id,
        "agent_id": clean_agent_id,
        "tool_name": tool_name,
        "tool_label": spec["name"],
        "payload": clean_payload,
        "reason": str(reason or "").strip()[:500],
        "approval_required": bool(spec["approval_required"]),
        "status": "pending" if spec["approval_required"] else "queued",
        "source": source,
        "severity": trigger.get("severity"),
        "rule_id": trigger.get("rule_id"),
        "trigger_key": trigger.get("trigger_key"),
        "evidence": trigger.get("evidence") if isinstance(trigger.get("evidence"), dict) else {},
        "requested_by": requested_by,
        "requested_at": _now(),
    }
    integration = _integration(project)
    rows = _approval_requests(integration)
    rows.append(row)
    integration["approval_requests"] = rows[-100:]
    _save(project, integration)
    source_label = "态势监控器" if source == "automation" else clean_agent_id
    _log_request(
        project_id,
        row,
        "mission_planning_agent_tool_requested",
        f"{source_label} 提议{spec['name']}：{row['reason'] or '未填写原因'}",
    )
    _audit_request("mission_planning_tool_requested", row, requested_by)
    return row


def _execution_summary(payload: dict[str, Any]) -> dict[str, Any]:
    integration = payload.get("integration") if isinstance(payload.get("integration"), dict) else {}
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    return {
        "integration_status": integration.get("status"),
        "run_id": integration.get("run_id"),
        "result_summary": integration.get("result_summary"),
        "product_state": status.get("state"),
        "product_running": status.get("running"),
    }


async def _execute_agent_tool(project_id: str, row: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(row.get("tool_name") or "")
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if tool_name == "inspect_status":
        return await refresh_project_mission_planning(project_id)
    if tool_name == "bind_scenario":
        return await bind_project_mission_planning(
            project_id,
            MissionPlanningBindRequest(
                scenario_id=str(payload.get("scenario_id") or ""),
                side=str(payload.get("side") or "red"),
            ),
        )
    if tool_name == "start_run":
        return await start_project_mission_planning(project_id)
    if tool_name == "stop_run":
        return await stop_project_mission_planning(project_id)
    if tool_name == "replan":
        project = _project(project_id)
        integration = _integration(project)
        _ensure_protocol(project, integration)
        if not integration.get("scenario_id"):
            raise HTTPException(status_code=400, detail="项目尚未绑定5130想定")
        try:
            result = await mission_planning_adapter.replan(str(payload.get("reason") or row.get("reason") or "智能体请求重新规划"))
        except MissionPlanningError as exc:
            _raise_product_error(project, exc)
        reason = str(payload.get("reason") or row.get("reason") or "")
        record_command(integration, "replan", target="ai-planning", detail=reason)
        record_event(
            integration,
            "planning.replan.requested",
            source="openclaw",
            summary=reason or "已提交重新规划请求",
        )
        integration.update({
            "last_synced_at": _now(),
            "last_replan_at": _now(),
            "last_replan_reason": reason,
            "result_summary": "已向5130提交重新规划请求",
        })
        updated = _save(project, integration)
        return {"project": updated, "integration": integration, "product_result": result}
    raise HTTPException(status_code=400, detail="不支持的智能体工具")


async def _run_approval_request(project_id: str, row: dict[str, Any], actor: str) -> dict[str, Any]:
    request_id = str(row["id"])
    _, running = _save_approval_request(project_id, request_id, {
        "status": "executing",
        "execution_started_at": _now(),
    })
    try:
        payload = await _execute_agent_tool(project_id, running)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        _, failed = _save_approval_request(project_id, request_id, {
            "status": "failed",
            "failed_at": _now(),
            "error": str(detail),
        })
        _log_request(
            project_id,
            failed,
            "mission_planning_agent_tool_failed",
            f"{failed.get('tool_label')} 执行失败：{detail}",
            actor,
        )
        _audit_request("mission_planning_tool_failed", failed, actor, running)
        raise
    summary = _execution_summary(payload)
    _, executed = _save_approval_request(project_id, request_id, {
        "status": "executed",
        "executed_at": _now(),
        "result": summary,
        "error": "",
    })
    _log_request(
        project_id,
        executed,
        "mission_planning_agent_tool_executed",
        f"{executed.get('tool_label')} 已执行：{summary.get('result_summary') or summary.get('integration_status') or '完成'}",
        actor,
    )
    _audit_request("mission_planning_tool_executed", executed, actor, running)
    return {"request": executed, "execution": payload}


def _raise_product_error(project: dict[str, Any] | None, exc: MissionPlanningError) -> None:
    if project:
        integration = _integration(project)
        integration.update({"status": "error", "last_error": str(exc), "last_synced_at": _now()})
        _save(project, integration)
    raise HTTPException(status_code=exc.status_code, detail=f"[{exc.code}] {exc}") from exc


def _status_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("plan_summary") if isinstance(payload.get("plan_summary"), dict) else {}
    total = int(summary.get("total") or 0)
    done = int(summary.get("done") or 0)
    tasks = payload.get("plan_tasks") if isinstance(payload.get("plan_tasks"), list) else []
    recent_events = payload.get("recent_events") if isinstance(payload.get("recent_events"), list) else []
    return {
        "state": str(payload.get("state") or "unknown"),
        "running": bool(payload.get("running")),
        "tick_count": int(payload.get("tick_count") or 0),
        "total_replans": int(payload.get("total_replans") or 0),
        "eval_score": payload.get("eval_score"),
        "last_eval_status": payload.get("last_eval_status"),
        "consecutive_urgent": int(payload.get("consecutive_urgent") or 0),
        "progress": round(done * 100 / total, 1) if total else 0,
        "plan_summary": {
            "total": total,
            "active": int(summary.get("active") or 0),
            "done": done,
            "pending": int(summary.get("pending") or 0),
        },
        "tasks": [
            {
                "id": task.get("id"),
                "name": task.get("display_name") or task.get("name_cn") or task.get("name"),
                "status": task.get("status"),
                "assigned_units": task.get("assigned_units") or [],
            }
            for task in tasks
            if isinstance(task, dict)
        ],
        "recent_events": recent_events[-8:],
        "last_diagnosis": payload.get("last_diagnosis"),
        "last_tick": payload.get("last_tick") if isinstance(payload.get("last_tick"), dict) else {},
    }


def _apply_snapshot_to_integration(integration: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    total = int((snapshot.get("plan_summary") or {}).get("total") or 0)
    done = int((snapshot.get("plan_summary") or {}).get("done") or 0)
    if snapshot.get("running"):
        status = "running"
    elif total and done >= total:
        status = "completed"
    elif integration.get("status") in {"running", "stopping"}:
        status = "stopped"
    else:
        status = integration.get("status") or "bound"
    integration.update({
        "status": status,
        "last_synced_at": _now(),
        "product_status": snapshot,
        "result_summary": (
            f"任务 {done}/{total}，评估 {snapshot.get('last_eval_status') or '暂无'}，"
            f"重规划 {snapshot.get('total_replans', 0)} 次"
        ),
    })
    if status == "completed" and not integration.get("completed_at"):
        integration["completed_at"] = _now()
    run = current_run(integration)
    if run:
        transition_run(
            integration,
            status,
            planning={
                "state": snapshot.get("state"),
                "running": snapshot.get("running"),
                "tick_count": snapshot.get("tick_count"),
                "progress": snapshot.get("progress"),
                "plan_summary": snapshot.get("plan_summary"),
            },
        )
        record_event(
            integration,
            "planning.status",
            source="ai-planning",
            summary=integration["result_summary"],
            data={
                "state": snapshot.get("state"),
                "running": snapshot.get("running"),
                "tick_count": snapshot.get("tick_count"),
                "progress": snapshot.get("progress"),
                "total_replans": snapshot.get("total_replans"),
            },
        )
    return integration


def _apply_simulation_snapshot(integration: dict[str, Any], snapshot: dict[str, Any]) -> None:
    if not snapshot:
        return
    integration["simulation_status"] = snapshot
    run = current_run(integration)
    if run:
        run["simulation"] = snapshot
        record_event(
            integration,
            "simulation.snapshot",
            source="one-sim",
            summary=(
                f"仿真帧 {snapshot.get('frame', 0)}，阶段 {snapshot.get('phase') or 'unknown'}，"
                f"实体 {snapshot.get('unit_count', 0)}"
            ),
            data={
                "frame": snapshot.get("frame"),
                "turn": snapshot.get("turn"),
                "phase": snapshot.get("phase"),
                "unit_count": snapshot.get("unit_count"),
                "destroyed_count": snapshot.get("destroyed_count"),
            },
        )
        record_artifact(
            integration,
            "simulation-state-summary",
            source="one-sim",
            title=f"one-sim 帧 {snapshot.get('frame', 0)} 状态摘要",
            metadata={
                "scenario_name": snapshot.get("scenario_name"),
                "frame": snapshot.get("frame"),
                "turn": snapshot.get("turn"),
                "phase": snapshot.get("phase"),
                "unit_count": snapshot.get("unit_count"),
            },
        )


def _automation_config(integration: dict[str, Any]) -> dict[str, Any]:
    value = integration.get("automation")
    config = dict(value) if isinstance(value, dict) else {}
    config.setdefault("enabled", True)
    config.setdefault("health", "waiting")
    config.setdefault("monitor_state", {})
    return config


async def _evaluate_project_automation_unlocked(project_id: str, *, force: bool = False) -> dict[str, Any]:
    project = _project(project_id)
    integration = _integration(project)
    automation = _automation_config(integration)
    if not automation.get("enabled") and not force:
        return {"project_id": project_id, "status": "disabled", "suggestions": []}
    if not integration.get("scenario_id"):
        return {"project_id": project_id, "status": "unbound", "suggestions": []}
    if integration.get("status") != "running" and not force:
        automation.update({"health": "waiting", "last_skip_reason": "project_not_running"})
        integration["automation"] = automation
        _save(project, integration)
        return {"project_id": project_id, "status": "waiting", "suggestions": []}
    try:
        payload = await mission_planning_adapter.supervisor_status()
    except MissionPlanningError as exc:
        automation.update({"health": "error", "last_error": str(exc), "last_checked_at": _now()})
        integration["automation"] = automation
        integration.update({"last_error": str(exc), "last_synced_at": _now()})
        _save(project, integration)
        raise

    snapshot = _status_snapshot(payload)
    integration = _apply_snapshot_to_integration(integration, snapshot)
    if not snapshot.get("running"):
        automation.update({
            "health": "waiting",
            "last_error": "",
            "last_checked_at": _now(),
            "last_skip_reason": "product_not_running",
        })
        integration["automation"] = automation
        _save(project, integration)
        return {
            "project_id": project_id,
            "status": "waiting",
            "snapshot": snapshot,
            "suggestions": [],
            "automation": automation,
        }
    suggestions, monitor_state = evaluate_signals(
        snapshot,
        automation.get("monitor_state") if isinstance(automation.get("monitor_state"), dict) else {},
        run_id=str(integration.get("run_id") or ""),
        run_started_epoch=_iso_epoch(integration.get("started_at")),
        now_epoch=time.time(),
        cooldown_seconds=int(os.getenv("MISSION_MONITOR_COOLDOWN_SECONDS", "300")),
    )
    automation.update({
        "health": monitor_state.get("health") or "healthy",
        "last_error": "",
        "last_checked_at": _now(),
        "monitor_state": monitor_state,
    })
    integration["automation"] = automation
    _save(project, integration)

    created: list[dict[str, Any]] = []
    for suggestion in suggestions:
        fresh = _project(project_id)
        pending = _approval_requests(_integration(fresh))
        duplicate = any(
            row.get("status") == "pending"
            and row.get("source") == "automation"
            and row.get("tool_name") == suggestion.get("tool_name")
            for row in pending
        )
        if duplicate:
            continue
        agent_id = str(fresh.get("owner_agent") or "optimus")
        try:
            agent_id = _sanitize_agent_id(agent_id)
        except HTTPException:
            agent_id = "optimus"
        tool_name = str(suggestion["tool_name"])
        tool_payload = {"reason": suggestion["reason"]} if tool_name == "replan" else {}
        row = _create_tool_request(
            project_id,
            agent_id=agent_id,
            tool_name=tool_name,
            reason=str(suggestion["reason"]),
            payload=tool_payload,
            requested_by="system:mission-monitor",
            source="automation",
            trigger=suggestion,
        )
        created.append(row)
    if created:
        project = _project(project_id)
        integration = _integration(project)
        automation = _automation_config(integration)
        automation.update({"health": "attention", "last_suggestion_at": _now()})
        integration["automation"] = automation
        _save(project, integration)
    return {
        "project_id": project_id,
        "status": "evaluated",
        "snapshot": snapshot,
        "suggestions": created,
        "automation": automation,
    }


async def evaluate_project_automation(project_id: str, *, force: bool = False) -> dict[str, Any]:
    async with _MONITOR_EVALUATION_LOCK:
        return await _evaluate_project_automation_unlocked(project_id, force=force)


async def _monitor_loop(interval_seconds: int) -> None:
    assert _MONITOR_STOP is not None
    _MONITOR_STATE.update({"enabled": True, "running": True, "last_error": ""})
    while not _MONITOR_STOP.is_set():
        _MONITOR_STATE["last_tick_at"] = _now()
        checked = 0
        created = 0
        tick_errors: list[str] = []
        try:
            for project in project_manager.list_projects():
                integration = _integration(project)
                if integration.get("status") != "running" or not _automation_config(integration).get("enabled"):
                    continue
                checked += 1
                try:
                    result = await evaluate_project_automation(str(project["id"]))
                    created += len(result.get("suggestions") or [])
                except Exception as exc:
                    tick_errors.append(str(exc))
                    print(f"[MissionPlanningMonitor] project={project.get('id')} failed: {exc}")
            _MONITOR_STATE.update({
                "projects_checked": checked,
                "suggestions_created": created,
                "last_error": "; ".join(tick_errors[:3]),
            })
        except Exception as exc:
            _MONITOR_STATE["last_error"] = str(exc)
            print(f"[MissionPlanningMonitor] tick failed: {exc}")
        try:
            await asyncio.wait_for(_MONITOR_STOP.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    _MONITOR_STATE["running"] = False


def start_mission_planning_monitor() -> None:
    global _MONITOR_TASK, _MONITOR_STOP
    if os.getenv("MISSION_MONITOR_ENABLED", "true").lower() == "false":
        _MONITOR_STATE.update({"enabled": False, "running": False, "last_error": "disabled"})
        print("[MissionPlanningMonitor] disabled")
        return
    if _MONITOR_TASK and not _MONITOR_TASK.done():
        return
    interval = max(int(os.getenv("MISSION_MONITOR_INTERVAL_SECONDS", "15")), 5)
    _MONITOR_STOP = asyncio.Event()
    _MONITOR_TASK = asyncio.create_task(_monitor_loop(interval))
    print(f"[MissionPlanningMonitor] started interval={interval}s")


async def stop_mission_planning_monitor() -> None:
    global _MONITOR_TASK, _MONITOR_STOP
    if not _MONITOR_TASK:
        return
    if _MONITOR_STOP:
        _MONITOR_STOP.set()
    try:
        await asyncio.wait_for(_MONITOR_TASK, timeout=5)
    except asyncio.TimeoutError:
        _MONITOR_TASK.cancel()
    _MONITOR_TASK = None
    _MONITOR_STOP = None


@router.get("/health")
async def mission_planning_health():
    try:
        return await mission_planning_adapter.health()
    except MissionPlanningError as exc:
        return {
            "online": False,
            "base_url": mission_planning_adapter.public_url,
            "product": "无人集群任务规划系统",
            "error": str(exc),
            "error_code": exc.code,
        }


@router.get("/scenarios")
async def mission_planning_scenarios():
    try:
        scenarios = await mission_planning_adapter.list_scenarios()
        return {"scenarios": scenarios, "total": len(scenarios)}
    except MissionPlanningError as exc:
        _raise_product_error(None, exc)


@router.get("/projects/{project_id}")
async def get_project_mission_planning(project_id: str):
    project = _project(project_id)
    integration = _integration(project)
    if _ensure_protocol(project, integration):
        project = _save(project, integration)
    return {
        "project_id": project_id,
        "integration": integration,
        "protocol": protocol_summary(integration),
        "product_url": mission_planning_adapter.public_url,
    }


@router.put("/projects/{project_id}/binding")
async def bind_project_mission_planning(project_id: str, req: MissionPlanningBindRequest):
    project = _project(project_id)
    side = req.side.strip().lower()
    if side not in {"red", "blue"}:
        raise HTTPException(status_code=400, detail="side must be red or blue")
    try:
        scenarios = await mission_planning_adapter.list_scenarios()
    except MissionPlanningError as exc:
        _raise_product_error(project, exc)
    scenario = next((row for row in scenarios if row["id"] == req.scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"5130 想定不存在：{req.scenario_id}")
    current = _integration(project)
    _ensure_protocol(project, current)
    current.update({
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "scenario_type": scenario["type"],
        "side": side,
        "status": "bound",
        "bound_at": _now(),
        "last_error": "",
        "product_url": mission_planning_adapter.public_url,
    })
    update_binding(current)
    record_event(
        current,
        "mission.binding.updated",
        source="openclaw",
        summary=f"项目绑定想定 {scenario['name']}，{side} 方规划",
        data={"scenario_id": scenario["id"], "side": side},
    )
    updated = _save(project, current)
    return {"project": updated, "integration": current, "protocol": protocol_summary(current)}


@router.post("/projects/{project_id}/start")
async def start_project_mission_planning(project_id: str):
    project = _project(project_id)
    integration = _integration(project)
    _ensure_protocol(project, integration)
    if not integration.get("scenario_id"):
        raise HTTPException(status_code=400, detail="请先绑定5130想定")

    conflicting = next(
        (
            row for row in project_manager.list_projects()
            if row.get("id") != project_id and _integration(row).get("status") == "running"
        ),
        None,
    )
    if conflicting:
        raise HTTPException(status_code=409, detail=f"5130 当前由项目“{conflicting.get('name')}”占用")

    try:
        product_status = await mission_planning_adapter.supervisor_status()
    except MissionPlanningError as exc:
        _raise_product_error(project, exc)
    if product_status.get("running") and integration.get("status") != "running":
        raise HTTPException(status_code=409, detail="5130 已有一个未纳入3021管理的运行任务，请先在产品侧停止")

    run = create_run(integration, actor="human:project-console")
    integration.update({
        "status": "starting",
        "run_id": run["id"],
        "started_at": _now(),
        "last_error": "",
        "result_summary": "正在加载想定并建立规划/仿真运行链",
    })
    project = _save(project, integration)

    try:
        load_result = await mission_planning_adapter.load_scenario(
            str(integration["scenario_id"]),
            str(integration.get("scenario_type") or "wargame"),
            str(integration.get("side") or "red"),
        )
        record_command(
            integration,
            "load_scenario",
            target="ai-planning",
            detail=f"加载想定 {integration['scenario_id']}",
        )
        plan_result = await mission_planning_adapter.generate_plan()
        record_command(integration, "generate_plan", target="ai-planning", detail="生成任务计划")
        start_result = await mission_planning_adapter.start_supervisor()
        record_command(integration, "start_supervisor", target="ai-planning", detail="启动闭环监督器")
        simulation_snapshot = await mission_planning_adapter.simulation_snapshot()
    except MissionPlanningError as exc:
        failed_project = _project(project_id)
        failed_integration = _integration(failed_project)
        transition_run(failed_integration, "failed", error=str(exc))
        record_command(
            failed_integration,
            "start_pipeline",
            target="ai-planning/one-sim",
            status="failed",
            detail=str(exc),
        )
        record_event(
            failed_integration,
            "run.failed",
            source="openclaw",
            summary=str(exc),
            data={"error_code": exc.code},
        )
        failed_integration.update({"status": "error", "last_error": str(exc), "last_synced_at": _now()})
        _save(failed_project, failed_integration)
        raise HTTPException(status_code=exc.status_code, detail=f"[{exc.code}] {exc}") from exc

    plan = plan_result.get("plan") if isinstance(plan_result, dict) else {}
    plan_tasks = plan.get("tasks") if isinstance(plan, dict) else []
    transition_run(
        integration,
        "running",
        planning={"task_count": len(plan_tasks or []), "supervisor": start_result},
    )
    record_event(
        integration,
        "run.started",
        source="openclaw",
        summary=f"规划与仿真运行已启动，共 {len(plan_tasks or [])} 个规划任务",
        data={"scenario_id": integration.get("scenario_id"), "side": integration.get("side")},
    )
    record_artifact(
        integration,
        "generated-plan",
        source="ai-planning",
        title="5130生成任务计划",
        metadata={"task_count": len(plan_tasks or []), "side": integration.get("side")},
    )
    _apply_simulation_snapshot(integration, simulation_snapshot)
    integration.update({
        "status": "running",
        "started_at": _now(),
        "last_synced_at": _now(),
        "last_error": "",
        "result_summary": f"想定已加载，生成 {len(plan_tasks or [])} 个任务，闭环监督已启动",
        "load_summary": {
            "mission_type": (load_result.get("planning") or {}).get("mission_type"),
            "plan_tasks_count": (load_result.get("planning") or {}).get("plan_tasks_count"),
        },
        "start_result": start_result,
    })
    updated = _save(project, integration)
    return {"project": updated, "integration": integration, "protocol": protocol_summary(integration)}


@router.get("/projects/{project_id}/status")
async def refresh_project_mission_planning(project_id: str):
    project = _project(project_id)
    integration = _integration(project)
    _ensure_protocol(project, integration)
    if not integration.get("scenario_id"):
        raise HTTPException(status_code=400, detail="项目尚未绑定5130想定")
    try:
        payload, simulation_snapshot = await asyncio.gather(
            mission_planning_adapter.supervisor_status(),
            mission_planning_adapter.simulation_snapshot(),
        )
    except MissionPlanningError as exc:
        _raise_product_error(project, exc)
    snapshot = _status_snapshot(payload)
    integration = _apply_snapshot_to_integration(integration, snapshot)
    _apply_simulation_snapshot(integration, simulation_snapshot)
    updated = _save(project, integration)
    return {
        "project": updated,
        "integration": integration,
        "status": snapshot,
        "protocol": protocol_summary(integration),
    }


@router.post("/projects/{project_id}/stop")
async def stop_project_mission_planning(project_id: str):
    project = _project(project_id)
    integration = _integration(project)
    _ensure_protocol(project, integration)
    try:
        result = await mission_planning_adapter.stop_supervisor()
    except MissionPlanningError as exc:
        _raise_product_error(project, exc)
    record_command(integration, "stop_supervisor", target="ai-planning", detail="停止闭环监督器")
    transition_run(integration, "stopped")
    record_event(
        integration,
        "run.stopped",
        source="openclaw",
        summary="规划与仿真运行已停止",
    )
    integration.update({
        "status": "stopped",
        "stopped_at": _now(),
        "last_synced_at": _now(),
        "result_summary": "闭环监督已停止",
        "stop_result": result,
    })
    updated = _save(project, integration)
    return {"project": updated, "integration": integration, "protocol": protocol_summary(integration)}


@router.get("/tools")
async def mission_planning_tools(_user: dict = Depends(get_current_user)):
    tools = [
        {"id": tool_id, **{key: value for key, value in spec.items() if key != "payload_fields"}}
        for tool_id, spec in TOOL_CATALOG.items()
    ]
    return {"tools": tools, "total": len(tools)}


@router.get("/automation/status")
async def mission_planning_automation_status(_user: dict = Depends(get_current_user)):
    return {
        **_MONITOR_STATE,
        "task_active": bool(_MONITOR_TASK and not _MONITOR_TASK.done()),
        "interval_seconds": max(int(os.getenv("MISSION_MONITOR_INTERVAL_SECONDS", "15")), 5),
    }


@router.put("/projects/{project_id}/automation")
async def update_mission_planning_automation(
    project_id: str,
    req: MissionPlanningAutomationUpdate,
    user: dict = Depends(require_role("admin")),
):
    project = _project(project_id)
    integration = _integration(project)
    automation = _automation_config(integration)
    before = dict(automation)
    automation.update({
        "enabled": req.enabled,
        "health": "waiting" if req.enabled else "disabled",
        "updated_at": _now(),
        "updated_by": _actor(user),
    })
    integration["automation"] = automation
    updated = _save(project, integration)
    unified_data_manager.record_audit(
        "mission_planning_automation_updated",
        "mission_planning_automation",
        project_id,
        actor=_actor(user),
        before_state=before,
        after_state=automation,
    )
    return {"project": updated, "integration": integration, "automation": automation}


@router.post("/projects/{project_id}/automation/evaluate")
async def run_mission_planning_automation(
    project_id: str,
    _user: dict = Depends(require_role("admin")),
):
    try:
        return await evaluate_project_automation(project_id, force=True)
    except MissionPlanningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=f"[{exc.code}] {exc}") from exc


@router.get("/projects/{project_id}/approvals")
async def list_mission_planning_approvals(project_id: str, _user: dict = Depends(get_current_user)):
    project = _project(project_id)
    rows = list(reversed(_approval_requests(_integration(project))))
    return {
        "project_id": project_id,
        "requests": rows,
        "pending_count": sum(1 for row in rows if row.get("status") == "pending"),
    }


@router.post("/projects/{project_id}/agent-tools/invoke")
async def invoke_mission_planning_agent_tool(
    project_id: str,
    req: MissionPlanningAgentToolRequest,
    user: dict = Depends(get_current_user),
):
    tool_name = str(req.tool_name or "").strip()
    actor = _actor(user)
    row = _create_tool_request(
        project_id,
        agent_id=req.agent_id,
        tool_name=tool_name,
        reason=req.reason,
        payload=req.payload,
        requested_by=actor,
    )
    if row["approval_required"]:
        return {"request": row, "dispatch_status": "pending_approval"}
    result = await _run_approval_request(project_id, row, actor)
    return {**result, "dispatch_status": "executed"}


@router.post("/projects/{project_id}/approvals/{request_id}/decision")
async def decide_mission_planning_approval(
    project_id: str,
    request_id: str,
    req: MissionPlanningApprovalDecision,
    user: dict = Depends(require_role("admin")),
):
    project = _project(project_id)
    row = next(
        (item for item in _approval_requests(_integration(project)) if item.get("id") == request_id),
        None,
    )
    if not row:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    if row.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"审批请求当前状态为 {row.get('status')}")
    actor = _actor(user)
    before = dict(row)
    decision = {
        "reviewer": actor,
        "reviewed_at": _now(),
        "review_comment": str(req.comment or "").strip()[:500],
    }
    if not req.approved:
        _, rejected = _save_approval_request(project_id, request_id, {**decision, "status": "rejected"})
        _log_request(
            project_id,
            rejected,
            "mission_planning_agent_tool_rejected",
            f"{rejected.get('tool_label')} 已驳回：{decision['review_comment'] or '未填写意见'}",
            actor,
        )
        _audit_request("mission_planning_tool_rejected", rejected, actor, before)
        return {"request": rejected, "dispatch_status": "rejected"}
    _, approved = _save_approval_request(project_id, request_id, {**decision, "status": "approved"})
    _log_request(
        project_id,
        approved,
        "mission_planning_agent_tool_approved",
        f"{approved.get('tool_label')} 已批准，准备执行",
        actor,
    )
    _audit_request("mission_planning_tool_approved", approved, actor, before)
    result = await _run_approval_request(project_id, approved, actor)
    return {**result, "dispatch_status": "executed"}
