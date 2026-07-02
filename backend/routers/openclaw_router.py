from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["openclaw"])


@router.get("/openclaw/stats")
def get_openclaw_stats():
    from openclaw_integration import openclaw_integration
    return openclaw_integration.sync_data()


@router.get("/email/stats")
def get_email_stats():
    from openclaw_integration import openclaw_integration
    return openclaw_integration.get_email_stats()


@router.get("/codex/tasks")
def get_codex_tasks():
    from openclaw_integration import openclaw_integration
    tasks = openclaw_integration.get_codex_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/heartbeat/state")
def get_heartbeat_state():
    from openclaw_integration import openclaw_integration
    return openclaw_integration.get_heartbeat_state()
