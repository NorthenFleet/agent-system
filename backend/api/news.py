"""
新闻资讯 API
任务 007: 新闻资讯热力图地球
"""
from fastapi import APIRouter, Query, Optional
from typing import List, Dict
from services.news_scraper import news_scraper

router = APIRouter(prefix="/api/news", tags=["news"])

@router.get("/list")
async def get_news(category: Optional[str] = Query(None, description="新闻分类")) -> Dict:
    """获取新闻列表"""
    news_list = news_scraper.fetch_news(category)
    return {
        "news": news_list,
        "total": len(news_list)
    }

@router.get("/heatmap")
async def get_heatmap() -> Dict:
    """获取热力图数据"""
    return {
        "heatmap": news_scraper.get_heatmap_data()
    }

@router.get("/stats")
async def get_stats() -> Dict:
    """获取统计信息"""
    return news_scraper.get_stats()

@router.get("/categories")
async def get_categories() -> Dict:
    """获取新闻分类"""
    return {
        "categories": ["科技", "财经", "政治", "体育", "娱乐"]
    }
