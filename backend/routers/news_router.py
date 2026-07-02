import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/api/news", tags=["news"])

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


def _get_news_manager():
    from news_manager import news_manager
    return news_manager


@router.get("/locations")
def get_news_locations():
    """获取新闻位置信息"""
    news_mgr = _get_news_manager()
    return {"locations": news_mgr.get_locations()}


@router.get("/categories")
def get_news_categories():
    """获取新闻分类"""
    news_mgr = _get_news_manager()
    return {"categories": news_mgr.get_categories()}


@router.get("/location-news")
def get_location_news():
    """获取带位置的新闻"""
    news_mgr = _get_news_manager()
    return {"data": news_mgr.get_location_news()}


@router.get("")
def get_live_news(category: str = None, location: str = None, force_refresh: bool = False):
    """获取新闻列表"""
    news_mgr = _get_news_manager()
    return {
        "news": news_mgr.get_all_news(category, location, force_refresh=force_refresh),
        "meta": news_mgr.get_meta(),
    }


@router.post("/refresh")
def refresh_news():
    """强制刷新国际新闻缓存"""
    news_mgr = _get_news_manager()
    return news_mgr.refresh_now()


@router.get("/{news_id}")
def get_individual_news(news_id: str):
    """获取新闻详情"""
    news_mgr = _get_news_manager()
    news = news_mgr.get_news_by_id(news_id)
    if not news:
        return FileResponse(
            os.path.join(FRONTEND_DIR, "not-found.html"),
            media_type="text/html",
        )
    return news


# Jinja2 模板渲染的路由需要单独注册到 app 上
def register_templates(app):
    """注册模板渲染路由"""
    templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

    @app.get("/news")
    async def news_page(request):
        """新闻资讯页面"""
        from fastapi.requests import Request
        return templates.TemplateResponse("news.html", {"request": request})
