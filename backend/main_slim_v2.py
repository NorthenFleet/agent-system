"""Slim main.py — app init + middleware + routes + lifecycle (< 100 lines)."""
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from api_registry import (
    data_manager,
    device_manager,
    register_api_routes,
    start_elastic_agent_runner,
    start_mission_planning_monitor,
    stop_elastic_agent_runner,
    stop_mission_planning_monitor,
)
from websocket_manager import manager
from routers._slim_helpers import _is_legacy_admin_write, require_admin_request

app = FastAPI(title="团队状态看板 API")
FD2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend-v2", "dist")
V2 = os.getenv("USE_FRONTEND_V2", "true").lower() != "false"
_h = lambda: {"Cache-Control": "no-store"}


def _fe():
    index_path = os.path.join(FD2, "index.html")
    if V2 and os.path.isfile(index_path):
        return index_path
    raise HTTPException(503, "frontend-v2/dist/index.html not built")


def _r(p): return FileResponse(p, headers=_h())

# Middleware
default_cors = "http://localhost:3021,http://127.0.0.1:3021"
cors = [o.strip() for o in os.getenv("CORS_ORIGINS", default_cors).split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=cors, allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true", allow_methods=["*"], allow_headers=["*"])

from middleware.request_logger import RequestLoggerMiddleware
app.add_middleware(RequestLoggerMiddleware)


@app.middleware("http")
async def _protect_legacy(req: Request, call_next):
    if _is_legacy_admin_write(req):
        try: require_admin_request(req)
        except Exception as exc: return JSONResponse(status_code=getattr(exc, "status_code", 500), content={"detail": getattr(exc, "detail", "error")})
    blocked = _check_module_access(req)
    if blocked is not None:
        return blocked
    return await call_next(req)


def _module_for_path(path: str):
    if not path.startswith("/api/"):
        return None
    if path.startswith("/api/v2/auth") or path == "/api/v2/modules/me":
        return None
    mapping = [
        (("/api/v3/writing",), "writing"),
        (("/api/v2/users", "/api/v2/modules"), "user-admin"),
        (("/api/v3/projects", "/api/v2/projects"), "projects"),
        (("/api/v2/tasks", "/api/tasks", "/api/v2/task-recommend"), "tasks"),
        (("/api/admin/data", "/api/v2/data", "/api/v3/data"), "data-admin"),
        (("/api/v3/agents", "/api/v2/agents", "/api/agents", "/api/v2/agent-health"), "agents"),
        (("/api/v2/codex", "/api/v2/codex-jobs"), "development"),
        (("/api/v2/chat", "/api/chat"), "agents"),
        (("/api/knowledge", "/api/v3/knowledge"), "knowledge"),
        (("/api/finance",), "finance"),
        (("/api/skills",), "skills"),
        (("/api/scheduled",), "scheduled"),
        (("/api/devices",), "monitoring"),
        (("/api/community", "/api/forum", "/api/bar"), "community"),
        (("/api/news",), "news-center"),
        (("/api/intelligence",), "intelligence"),
        (("/api/tools",), "tools"),
        (("/api/products", "/api/v2/products"), "products"),
        (("/api/v2/monitoring",), "monitoring"),
    ]
    for prefixes, module_key in mapping:
        if any(path.startswith(prefix) for prefix in prefixes):
            return module_key
    return None


def _check_module_access(req: Request):
    if os.getenv("DISABLE_MODULE_AUTH_FOR_TESTS", "false").lower() == "true":
        return None
    module_key = _module_for_path(req.url.path)
    if not module_key:
        return None
    auth = req.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    try:
        from services.auth_service import decode_access_token
        from services.user_service import UserService
        from services.module_permission_service import user_has_module
        from database import SessionLocal

        payload = decode_access_token(auth[7:])
        if not payload:
            return JSONResponse(status_code=401, content={"detail": "Token 无效或已过期"})
        db = SessionLocal()
        try:
            user = UserService(db).get_active_user_by_id(int(payload["sub"]))
            if not user_has_module(db, user, module_key):
                return JSONResponse(status_code=403, content={"detail": f"无权访问模块: {module_key}"})
        finally:
            db.close()
    except Exception:
        return JSONResponse(status_code=403, content={"detail": "模块权限校验失败"})
    return None

# API routes
register_api_routes(app)

# Pages
app.get("/")(lambda: _r(_fe()))
app.get("/login")(lambda: _r(_fe()))
app.get("/favicon.ico")(lambda: JSONResponse(status_code=204, content=None))
app.get("/health")(lambda: {"status": "ok", "port": int(os.getenv("API_PORT", os.getenv("PORT", "3021")))})
if os.path.isdir(FD2): app.mount("/assets", StaticFiles(directory=os.path.join(FD2, "assets")), name="v2")


def _raise_404(): raise HTTPException(404)
for _legacy_page in ("/index-old", "/legacy", "/modular", "/mobile", "/forum", "/manifest.json", "/sw.js"):
    app.get(_legacy_page)(_raise_404)
for _legacy_prefix in ("/static/{path:path}", "/js/{path:path}", "/views/{path:path}", "/icons/{path:path}"):
    app.get(_legacy_prefix)(_raise_404)


@app.get("/favicon.svg")
def _favicon_v2(): return _r(os.path.join(FD2, "favicon.svg")) if V2 and os.path.isfile(os.path.join(FD2, "favicon.svg")) else _raise_404()


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def _unknown_api(path: str):
    raise HTTPException(status_code=404, detail=f"API not found: /api/{path}")


@app.api_route("/ws/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def _unknown_ws(path: str):
    raise HTTPException(status_code=404, detail=f"WebSocket endpoint not found: /ws/{path}")


@app.get("/{full_path:path}")
def _spa(full_path: str): return _r(os.path.join(FD2, "index.html")) if V2 and os.path.isfile(os.path.join(FD2, "index.html")) else _raise_404()


@app.websocket("/ws/status")
async def ws_ep(ws: WebSocket):
    try:
        await manager.connect(ws)
        await manager.push_status_update(data_manager.get_agents(), data_manager.get_merged_tasks())
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        manager.disconnect(ws)
        print(f"[WS] 连接异常: {e}")

@app.on_event("startup")
async def startup():
    print("=" * 50 + "\n团队看板 API 启动 (Slim)\n" + "=" * 50)
    try:
        from database import init_db, SessionLocal
        from services.module_permission_service import ensure_default_modules
        init_db()
        db = SessionLocal()
        try: ensure_default_modules(db)
        finally: db.close()
    except Exception as e:
        print(f"[Permissions] 初始化失败: {e}")
    try:
        from project_manager import project_manager
        migrated = project_manager.migrate_composition_model()
        print(f"[ProjectComposition] migrated={migrated}")
    except Exception as e:
        print(f"[ProjectComposition] 迁移失败: {e}")
    try:
        interval = int(os.getenv("DEVICE_HEALTH_INTERVAL", "30"))
        await device_manager.start_health_monitoring(interval=interval)
    except Exception as e:
        print(f"[DeviceManager] 健康监控启动失败: {e}")

    try:
        start_elastic_agent_runner()
    except Exception as e:
        print(f"[ElasticAgentRunner] 启动失败: {e}")
    try:
        start_mission_planning_monitor()
    except Exception as e:
        print(f"[MissionPlanningMonitor] 启动失败: {e}")

    if os.getenv("DISABLE_SCHEDULER", "false").lower() == "true":
        print("[Scheduler] 已禁用（DISABLE_SCHEDULER=true）")
        return
    try:
        from services.scheduler_service import scheduler_service; import asyncio
        scheduler_service.init_scheduler(asyncio.get_event_loop()); scheduler_service.load_active_tasks()
    except Exception as e: print(f"[Scheduler] 启动失败: {e}")


@app.on_event("shutdown")
async def shutdown():
    try:
        device_manager.stop_health_monitoring()
    except Exception as e: print(f"[DeviceManager] 健康监控关闭异常: {e}")
    try:
        await stop_elastic_agent_runner()
    except Exception as e: print(f"[ElasticAgentRunner] 关闭异常: {e}")
    try:
        await stop_mission_planning_monitor()
    except Exception as e: print(f"[MissionPlanningMonitor] 关闭异常: {e}")
    try:
        from services.scheduler_service import scheduler_service; scheduler_service.shutdown_scheduler(wait=True)
    except Exception as e: print(f"[Scheduler] 关闭异常: {e}")


if __name__ == "__main__": import uvicorn; uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", os.getenv("PORT", "3021"))))
