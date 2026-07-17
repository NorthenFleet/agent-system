"""API router registration for the unified 3021 OpenClaw service.

The current service still exposes several legacy API surfaces for compatibility,
but the FastAPI application entrypoint should not own those wiring details.
"""
from __future__ import annotations

from fastapi import FastAPI

from routers import (
    agent_os,
    data_admin,
    finance,
    intelligence,
    knowledge,
    knowledge_stack,
    loop_queue,
    mission_planning,
    openclaw_status,
    products_router,
    projects_v3,
    system_status,
    workflow,
    web_crawler,
    writing_workspace,
)
from routers.agent_health_router import router as agent_health_router
from routers.agents_router import router as agents_router
from routers.auth_router import router as auth_router
from routers.codex_jobs_router import router as codex_jobs_router
from routers.customers_router import router as customers_router
from routers.modules_router import router as modules_router
from routers.monitoring_router import router as monitoring_router
from routers.notification_router import router as notification_router
from routers.task_recommend_router import router as task_recommend_router
from routers.task_webhook_router import router as task_webhook_router
from routers.tasks_v2 import router as tasks_v2_router
from routers.automation_router import router as automation_router
from routers.templates_router import router as templates_router
from routers.users_router import router as users_router
from routers.v2_chat_router import router as v2_chat_router
from routers.analytics_router import router as analytics_router

# Legacy compatibility managers. Keep these imports centralized so their
# compatibility surface is visible and can be removed in one place later.
from auto_plan_manager import auto_plan_manager
from chat_manager import chat_manager
from community_manager import community_manager
from data_manager import data_manager
from device_manager import device_manager
from document_manager import doc_manager
from forum_api import forum_manager
from idle_agent_manager import idle_agent_manager
from news_manager import news_manager
from openclaw_integration import openclaw_integration
from plan_manager import plan_manager
from rss_config_manager import rss_config_manager
from task_queue import task_manager

import routers.legacy_agent_docs_router as legacy_agent_docs_router
import routers.legacy_agents_router as legacy_agents_router
import routers.legacy_bar_router as legacy_bar_router
import routers.legacy_community_router as legacy_community_router
import routers.legacy_idle_agents_router as legacy_idle_agents_router
import routers.legacy_news_router as legacy_news_router
import routers.legacy_plans_auto_router as legacy_plans_auto_router
import routers.legacy_scheduled_tasks_router as legacy_scheduled_tasks_router
import routers.legacy_tasks_router as legacy_tasks_router


ACTIVE_ROUTERS = (
    loop_queue.router,
    workflow.router,
    openclaw_status.router,
    system_status.router,
    projects_v3.router,
    writing_workspace.router,
    mission_planning.router,
    knowledge.router,
    knowledge_stack.router,
    data_admin.router,
    products_router.router,
    agent_os.router,
    finance.router,
    intelligence.router,
    web_crawler.router,
    auth_router,
    users_router,
    tasks_v2_router,
    agents_router,
    customers_router,
    v2_chat_router,
    codex_jobs_router,
    task_recommend_router,
    agent_health_router,
    monitoring_router,
    modules_router,
    task_webhook_router,
    templates_router,
    notification_router,
    automation_router,
    analytics_router,
)


def _wire_legacy_managers() -> None:
    legacy_tasks_router.set_managers(data_manager, task_manager)
    legacy_agents_router.set_managers(data_manager, task_manager, device_manager, openclaw_integration)
    legacy_idle_agents_router.set_managers(data_manager, task_manager, idle_agent_manager)
    legacy_agent_docs_router.set_managers(data_manager, doc_manager)
    legacy_community_router.set_managers(community_manager, chat_manager, forum_manager)
    legacy_news_router.set_managers(news_manager, rss_config_manager)
    legacy_plans_auto_router.set_managers(task_manager, plan_manager, auto_plan_manager)


def legacy_routers():
    _wire_legacy_managers()
    return (
        legacy_tasks_router.router,
        legacy_agents_router.router,
        legacy_bar_router.router,
        legacy_idle_agents_router.router,
        legacy_agent_docs_router.router,
        legacy_community_router.router,
        legacy_news_router.router,
        legacy_plans_auto_router.router,
        legacy_scheduled_tasks_router.router,
    )


def register_api_routes(app: FastAPI) -> None:
    for router in (*ACTIVE_ROUTERS, *legacy_routers()):
        app.include_router(router)


def start_elastic_agent_runner() -> None:
    projects_v3.start_elastic_agent_runner()


async def stop_elastic_agent_runner() -> None:
    await projects_v3.stop_elastic_agent_runner()


def start_mission_planning_monitor() -> None:
    mission_planning.start_mission_planning_monitor()


async def stop_mission_planning_monitor() -> None:
    await mission_planning.stop_mission_planning_monitor()
