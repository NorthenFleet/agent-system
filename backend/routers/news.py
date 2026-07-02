from fastapi import APIRouter
from news_manager import news_manager

router = APIRouter(prefix="/api", tags=["news"])


@router.get("/news")
def get_news(category: str = None, location: str = None):
    return {"news": news_manager.get_all_news(category, location)}


@router.get("/news/location-news")
def get_location_news():
    return {"data": news_manager.get_location_news()}


@router.get("/news/categories")
def get_news_categories():
    return {"categories": news_manager.get_categories()}


@router.post("/news/refresh")
def refresh_news():
    return news_manager.refresh_news()
