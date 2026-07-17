from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.web_crawler_service import web_crawler_service


router = APIRouter(prefix="/api/tools/web-crawler", tags=["web-crawler"])


class CrawlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    query: str = Field(default="", max_length=500)


class CrawlerConfigUpdate(BaseModel):
    enabled: bool | None = None
    scope: str | None = None
    module_keys: list[str] | None = None
    agent_ids: list[str] | None = None
    allow_private_network: bool | None = None
    request_timeout_seconds: int | None = Field(default=None, ge=10, le=600)
    max_content_chars: int | None = Field(default=None, ge=1000, le=1000000)


@router.get("/status")
def crawler_status():
    return web_crawler_service.status()


@router.get("/config")
def crawler_config():
    return web_crawler_service.get_config()


@router.put("/config")
def update_crawler_config(req: CrawlerConfigUpdate):
    updates: dict[str, Any] = req.model_dump(exclude_none=True)
    return web_crawler_service.save_config(updates)


@router.post("/crawl")
def crawl(req: CrawlRequest):
    try:
        return web_crawler_service.crawl(req.url, req.query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
