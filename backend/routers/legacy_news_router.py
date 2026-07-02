"""
Legacy News routes extracted from main.py
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from typing import Optional

router = APIRouter(tags=["legacy-news"])

_news_manager = None
_rss_config_manager = None


def set_managers(nm, rm):
    global _news_manager, _rss_config_manager
    _news_manager = nm
    _rss_config_manager = rm


# ─── RSS Config ───

@router.get("/api/news/rss-config")
def get_rss_config():
    feeds = _rss_config_manager.get_feeds()
    return {"feeds": feeds, "total": len(feeds)}


@router.get("/api/news/rss-config/enabled")
def get_enabled_rss_feeds():
    feeds = _rss_config_manager.get_enabled_feeds()
    return {"feeds": feeds, "total": len(feeds)}


@router.get("/api/news/rss-config/{key}")
def get_rss_feed(key: str):
    feed = _rss_config_manager.get_feed(key)
    if not feed:
        raise HTTPException(status_code=404, detail="RSS 源不存在")
    return feed


@router.post("/api/news/rss-config")
def add_rss_feed(feed_data: dict):
    feed = _rss_config_manager.add_feed(feed_data)
    return {"success": True, "feed": feed}


@router.put("/api/news/rss-config/{key}")
def update_rss_feed(key: str, updates: dict):
    feed = _rss_config_manager.update_feed(key, updates)
    if not feed:
        raise HTTPException(status_code=404, detail="RSS 源不存在")
    return {"success": True, "feed": feed}


@router.delete("/api/news/rss-config/{key}")
def delete_rss_feed(key: str):
    success = _rss_config_manager.delete_feed(key)
    if not success:
        raise HTTPException(status_code=404, detail="RSS 源不存在")
    return {"success": True, "message": f"已删除 RSS 源：{key}"}


@router.post("/api/news/rss-config/{key}/toggle")
def toggle_rss_feed(key: str):
    feed = _rss_config_manager.toggle_feed(key)
    if not feed:
        raise HTTPException(status_code=404, detail="RSS 源不存在")
    return {"success": True, "feed": feed, "enabled": feed.get("enabled")}


@router.post("/api/news/rss-config/sync")
def sync_rss_config():
    _rss_config_manager.sync_to_rss_fetcher()
    return {"success": True, "message": "已同步配置到抓取器"}


# ─── News ───

@router.get("/api/news/locations")
def get_news_locations():
    return {"locations": _news_manager.get_locations()}


@router.get("/api/news/categories")
def get_news_categories():
    return {"categories": _news_manager.get_categories()}


@router.get("/api/news/location-news")
def get_location_news():
    return {"data": _news_manager.get_location_news()}


@router.get("/api/news")
def get_news(category: Optional[str] = None, location: Optional[str] = None):
    return {"news": _news_manager.get_all_news(category, location)}


@router.get("/api/news/{news_id}")
def get_news_detail(news_id: str):
    news = _news_manager.get_news_by_id(news_id)
    if not news:
        raise HTTPException(status_code=404, detail="新闻不存在")
    return news


@router.get("/news")
def news_page():
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend")
    return FileResponse(
        os.path.join(frontend_dir, "news.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/api/news/stats")
def get_news_stats():
    return {"stats": _news_manager.get_stats()}


@router.post("/api/news/refresh")
def refresh_news():
    success = _news_manager.refresh_news()
    return {"success": success, "message": "刷新成功" if success else "刷新失败"}
