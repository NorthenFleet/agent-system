from __future__ import annotations
"""团队看板 V3 — FastAPI 主入口 (< 100 行)"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import init_db

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app = FastAPI(title="团队看板 V3 API", version="3.0.0")

# CORS
cors_origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:3020,http://127.0.0.1:3020"
).split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins,
    allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true",
    allow_methods=["*"], allow_headers=["*"])

# ── 路由注册 ──
from routers.tasks_router import router as v2_tasks_router
from routers.agents_router import router as v2_agents_router
from routers.devices_router import router as v2_devices_router
from routers.auth_router import router as v2_auth_router
from routers.users_router import router as v2_users_router
from routers.products_router import router as v2_products_router
from routers.sprints_router import router as v2_sprints_router
from routers.alerts_router import router as v2_alerts_router
from routers.health_router import router as v2_health_router
from routers.health_router import health_router as v2_agent_health_router
from routers.websocket_router import router as v2_ws_router
from routers.intelligence_router import router as v2_intelligence_router
from routers.scheduled_tasks_router import router as v2_scheduled_tasks_router
from routers.knowledge import router as knowledge_router
from routers.task_recommend_router import router as v2_task_recommend_router
from routers.task_webhook_router import router as v2_task_webhook_router

for _r in (v2_tasks_router, v2_agents_router, v2_devices_router, v2_auth_router,
           v2_users_router, v2_products_router, v2_sprints_router, v2_alerts_router,
           v2_health_router, v2_agent_health_router, v2_ws_router, v2_intelligence_router,
           v2_scheduled_tasks_router, knowledge_router, v2_task_recommend_router,
           v2_task_webhook_router):
    app.include_router(_r)

# 旧路由向后兼容（逐步迁移）
from routers import loop_queue, workflow, system_status, projects_v3
for _r in (loop_queue, workflow, system_status, projects_v3):
    app.include_router(_r.router)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# ── 前端 SPA (v2) ──
V2_DIR = os.path.join(FRONTEND_DIR, "v2", "dist")
app.mount("/assets", StaticFiles(directory=os.path.join(V2_DIR, "assets")), name="v2-assets")
DEFAULT_ENTRY = os.path.join(V2_DIR, "index.html")

def _resolve_entry() -> str:
    name = os.getenv("FRONTEND_ENTRY", DEFAULT_ENTRY).strip() or DEFAULT_ENTRY
    path = os.path.join(FRONTEND_DIR, name) if not os.path.isabs(name) else name
    if os.path.isfile(path): return path
    if os.path.isfile(DEFAULT_ENTRY): return DEFAULT_ENTRY
    fb = os.path.join(FRONTEND_DIR, "complete.html")
    return fb if os.path.isfile(fb) else path

# ── 快捷健康检查 ──
@app.get("/health")
def health_check():
    return {"status": "ok", "port": 3020}

@app.get("/")
def root():
    return FileResponse(_resolve_entry(),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

# ── SPA catch-all: 所有非 API 路径返回 index.html ──
@app.get("/{path:path}")
def spa_fallback(path: str):
    # 跳过 API 路由、静态文件路由、已知文件扩展名
    if path.startswith("api/") or path.startswith("static/") or path.startswith("assets/"):
        raise HTTPException(status_code=404)
    ext = os.path.splitext(path)[1]
    if ext in (".js", ".css", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".json"):
        raise HTTPException(status_code=404)
    return FileResponse(_resolve_entry(),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

@app.on_event("startup")
async def startup():
    init_db()
    # 启动 RSS 定时抓取调度器（每 30 分钟）
    try:
        from services.rss_scheduler import start_rss_scheduler
        start_rss_scheduler(interval_minutes=30)
    except Exception as e:
        print(f"[V3] RSS 定时抓取调度器启动失败: {e}")
    print("=" * 50 + "\n团队看板 V3 API 启动\n" + "=" * 50)

@app.on_event("shutdown")
async def shutdown():
    # 关闭 RSS 调度器
    try:
        from services.rss_scheduler import stop_rss_scheduler
        stop_rss_scheduler()
    except Exception:
        pass
    print("[V3] API 已关闭")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3020)
