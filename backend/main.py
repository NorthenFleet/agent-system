"""团队状态看板 API — app init + middleware + routes + lifecycle"""
import os
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from websocket_manager import manager
from routers._slim_helpers import _is_legacy_admin_write, require_admin_request

from core.logging_config import setup_app_logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="团队状态看板 API",
    description="""
## 团队状态看板 API

提供任务管理、智能体监控、用户管理、告警系统等核心功能。

### 主要模块

- **任务管理** (`/api/v2/tasks`) — 任务 CRUD、搜索、分配、统计、甘特图
- **智能体监控** (`/api/v2/agents`) — 智能体状态、心跳监控、WebSocket 实时推送
- **用户管理** (`/api/v2/users`) — 用户 CRUD、角色权限管理
- **告警系统** (`/api/v2/alerts`) — 告警规则、告警事件、统计
- **认证授权** (`/api/v2/auth`) — 登录、刷新 Token、权限验证

### 认证方式

使用 JWT Bearer Token 认证，在请求头中携带：
```
Authorization: Bearer <token>
```

### 错误处理

所有 API 响应遵循统一格式：
- 成功: `{"success": true, "data": {...}}` 或直接返回数据
- 失败: `{"detail": "错误描述"}`
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "v2-tasks", "description": "任务管理 API"},
        {"name": "v2-agents", "description": "智能体监控 API"},
        {"name": "v2-users", "description": "用户管理 API"},
        {"name": "v2-alerts", "description": "告警系统 API"},
        {"name": "v2-auth", "description": "认证授权 API"},
        {"name": "v2-websocket", "description": "WebSocket 实时推送"},
        {"name": "v2-monitoring", "description": "监控数据聚合 API"},
    ],
)

FD = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
FD2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend-v2", "dist")
V2 = os.getenv("USE_FRONTEND_V2", "true").lower() != "false"
_h = lambda: {"Cache-Control": "no-store"}


def _fe():
    if V2 and os.path.isfile(os.path.join(FD2, "index.html")):
        return os.path.join(FD2, "index.html")
    c = os.getenv("FRONTEND_ENTRY", "index-old.html").strip() or "index-old.html"
    p = os.path.join(FD, c)
    return p if os.path.isfile(p) else os.path.join(FD, "complete.html")


def _r(p): return FileResponse(p, headers=_h())


cors = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3020,http://127.0.0.1:3020").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors,
    allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true",
    allow_methods=["*"],
    allow_headers=["*"],
)

from middleware.request_logger import RequestLoggerMiddleware, logger_instance
app.add_middleware(RequestLoggerMiddleware)


@app.middleware("http")
async def _protect_legacy(req: Request, call_next):
    if _is_legacy_admin_write(req):
        try:
            require_admin_request(req)
        except Exception as exc:
            return JSONResponse(
                status_code=getattr(exc, "status_code", 500),
                content={"detail": getattr(exc, "detail", "error")}
            )
    return await call_next(req)


from api.tasks import router as _r0
from api.plans import router as _r1
from routers import (
    loop_queue as _m0, workflow as _m1, openclaw_status as _m2,
    system_status as _m3, projects_v3 as _m4, knowledge as _m5,
    knowledge_stack as _m6, data_admin as _m7, products_router as _m8,
    agent_os as _m9
)
from routers.auth_router import router as _r2
from routers.users_router import router as _r3
from routers.tasks_v2 import router as _r4
from routers.agents_router import router as _r5
from routers.customers_router import router as _r6
from routers.monitoring_router import router as _r7

import routers.legacy_tasks_router as _l7
import routers.legacy_agents_router as _l8
import routers.legacy_bar_router as _l9
import routers.legacy_idle_agents_router as _l10
import routers.legacy_agent_docs_router as _l11
import routers.legacy_community_router as _l12
import routers.legacy_news_router as _l13
import routers.legacy_plans_auto_router as _l14
import routers.legacy_scheduled_tasks_router as _l15

for r in (
    _r0, _r1, _m0.router, _m1.router, _m2.router, _m3.router,
    _m4.router, _m5.router, _m6.router, _m7.router, _m8.router,
    _m9.router, _r2, _r3, _r4, _r5, _r6, _r7,
    _l7.router, _l8.router,
    _l9.router, _l10.router, _l11.router, _l12.router, _l13.router,
    _l14.router, _l15.router
):
    app.include_router(r)


from data_manager import data_manager
from task_queue import task_manager
from device_manager import device_manager
from idle_agent_manager import idle_agent_manager
from document_manager import doc_manager
from community_manager import community_manager
from chat_manager import chat_manager
from forum_api import forum_manager
from news_manager import news_manager
from rss_config_manager import rss_config_manager
from plan_manager import plan_manager
from auto_plan_manager import auto_plan_manager
from openclaw_integration import openclaw_integration

_l7.set_managers(data_manager, task_manager)
_l8.set_managers(data_manager, task_manager, device_manager, openclaw_integration)
_l10.set_managers(data_manager, task_manager, idle_agent_manager)
_l11.set_managers(data_manager, doc_manager)
_l12.set_managers(community_manager, chat_manager, forum_manager)
_l13.set_managers(news_manager, rss_config_manager)
_l14.set_managers(task_manager, plan_manager, auto_plan_manager)


def _legacy_page():
    return _r(os.path.join(FD, os.getenv("FRONTEND_ENTRY", "index-old.html").strip() or "index-old.html"))


app.get("/")(lambda: _r(_fe()))
app.get("/index-old")(lambda: _legacy_page())
app.get("/legacy")(lambda: _legacy_page())
app.get("/modular")(lambda: _legacy_page())
app.get("/mobile")(lambda: _r(os.path.join(FD, "mobile.html")))
app.get("/manifest.json")(lambda: _r(os.path.join(FD, "manifest.json")))
app.get("/sw.js")(lambda: _r(os.path.join(FD, "sw.js")))
app.get("/forum")(lambda: _r(os.path.join(FD, "forum.html")))
app.get("/favicon.ico")(lambda: JSONResponse(status_code=204, content=None))
app.get("/health")(lambda: {"status": "ok", "port": int(os.getenv("API_PORT", "3020"))})
app.mount("/static", StaticFiles(directory=FD), name="static")
app.mount("/js", StaticFiles(directory=os.path.join(FD, "js")), name="js")
app.mount("/views", StaticFiles(directory=os.path.join(FD, "views")), name="views")
app.mount("/icons", StaticFiles(directory=os.path.join(FD, "icons")), name="icons")
if os.path.isdir(FD2):
    app.mount("/assets", StaticFiles(directory=os.path.join(FD2, "assets")), name="v2")


def _raise_404(): raise HTTPException(404)


@app.get("/favicon.svg")
def _favicon_v2():
    return _r(os.path.join(FD2, "favicon.svg")) if V2 and os.path.isfile(os.path.join(FD2, "favicon.svg")) else _raise_404()


@app.get("/{full_path:path}")
def _spa(full_path: str):
    return _r(os.path.join(FD2, "index.html")) if V2 and os.path.isfile(os.path.join(FD2, "index.html")) else _raise_404()


@app.websocket("/ws/status")
async def ws_ep(ws: WebSocket):
    conn_id = await manager.connect(ws)
    try:
        # 连接成功后推送当前状态快照
        await manager.send_to_all({
            "type": "status_update",
            "data": {
                "agents": data_manager.get_agents(),
                "tasks": data_manager.get_merged_tasks(),
                "conn_id": conn_id,
            },
        })
        while True:
            raw = await ws.receive_text()
            # 处理客户端 pong 响应
            try:
                data = json.loads(raw)
                if data.get("type") == "pong":
                    manager.record_pong(ws)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws)
        print(f"[WS] 连接 {conn_id} 已断开")


@app.on_event("startup")
async def startup():
    setup_app_logging()
    logger.info("团队看板 API 启动")
    logger.info(f"日志级别: {logging.getLevelName(logger.getEffectiveLevel())}")
    logger.info(f"前端版本: {'V2' if V2 else 'Legacy'}")

    # 启动 WebSocket 服务端心跳保活循环
    import asyncio
    asyncio.create_task(manager.start_heartbeat_loop(interval=25.0, timeout=60.0))
    logger.info("[WS] 服务端心跳保活已启动 (25s ping / 60s timeout)")

    try:
        interval = int(os.getenv("DEVICE_HEALTH_INTERVAL", "30"))
        await device_manager.start_health_monitoring(interval=interval)
        logger.info(f"设备健康监控启动，间隔: {interval}s")
    except Exception as e:
        logger.error(f"设备健康监控启动失败: {e}")

    if os.getenv("DISABLE_SCHEDULER", "false").lower() == "true":
        logger.info("调度器已禁用（DISABLE_SCHEDULER=true）")
        return

    try:
        from services.scheduler_service import scheduler_service
        scheduler_service.init_scheduler(asyncio.get_event_loop())
        scheduler_service.load_active_tasks()
        logger.info("调度器启动成功")
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("团队看板 API 正在关闭")
    try:
        device_manager.stop_health_monitoring()
        logger.info("设备健康监控已关闭")
    except Exception as e:
        logger.error(f"设备健康监控关闭异常: {e}")

    try:
        from services.scheduler_service import scheduler_service
        scheduler_service.shutdown_scheduler(wait=True)
        logger.info("调度器已关闭")
    except Exception as e:
        logger.error(f"调度器关闭异常: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3020)