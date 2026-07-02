# -*- coding: utf-8 -*-
"""
新闻管理器 - 管理全球新闻资讯
集成 RSS 实时抓取 + 缓存机制
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os
from rss_fetcher import get_cached_news_sync, fetch_news_sync

# 新闻分类与地理位置映射
NEWS_LOCATIONS = {
    "beijing": {"lat": 39.9042, "lng": 116.4074, "name": "北京", "country": "中国"},
    "shanghai": {"lat": 31.2304, "lng": 121.4737, "name": "上海", "country": "中国"},
    "shenzhen": {"lat": 22.5431, "lng": 114.0579, "name": "深圳", "country": "中国"},
    "tokyo": {"lat": 35.6762, "lng": 139.6503, "name": "东京", "country": "日本"},
    "seoul": {"lat": 37.5665, "lng": 126.9780, "name": "首尔", "country": "韩国"},
    "singapore": {"lat": 1.3521, "lng": 103.8198, "name": "新加坡", "country": "新加坡"},
    "london": {"lat": 51.5074, "lng": -0.1278, "name": "伦敦", "country": "英国"},
    "paris": {"lat": 48.8566, "lng": 2.3522, "name": "巴黎", "country": "法国"},
    "berlin": {"lat": 52.5200, "lng": 13.4050, "name": "柏林", "country": "德国"},
    "newyork": {"lat": 40.7128, "lng": -74.0060, "name": "纽约", "country": "美国"},
    "sanfrancisco": {"lat": 37.7749, "lng": -122.4194, "name": "旧金山", "country": "美国"},
    "washington": {"lat": 38.9072, "lng": -77.0369, "name": "华盛顿", "country": "美国"},
}

# 备用示例新闻（当 RSS 抓取失败时使用）
SAMPLE_NEWS = [
    {"id": "1", "title": "中国发布新一代人工智能发展规划", "summary": "国务院发布新一代人工智能发展规划，提出到 2030 年人工智能核心产业规模超过 1 万亿元", "category": "科技", "location": "beijing", "source": "新华网", "url": "https://example.com/news/1", "published_at": "2026-04-06T09:00:00Z", "priority": "high"},
    {"id": "2", "title": "上海科创板迎来新突破", "summary": "上海证券交易所科创板今日新增 5 家企业上市，总市值超过 500 亿元", "category": "财经", "location": "shanghai", "source": "财新网", "url": "https://example.com/news/2", "published_at": "2026-04-06T08:30:00Z", "priority": "medium"},
    {"id": "3", "title": "深圳科技创新成果展开幕", "summary": "2026 深圳科技创新成果展今日开幕，展示多项前沿科技成果", "category": "科技", "location": "shenzhen", "source": "南方日报", "url": "https://example.com/news/3", "published_at": "2026-04-06T07:00:00Z", "priority": "medium"},
]


class NewsManager:
    """新闻管理器 - 支持 RSS 实时抓取"""
    
    def __init__(self, cache_file: str = None):
        self.cache_file = cache_file or os.path.join(
            os.path.dirname(__file__), 
            "../data/news_cache.json"
        )
        self.locations = NEWS_LOCATIONS
        self._last_fetch_time = None
        self._fetch_interval_minutes = 30  # 30 分钟刷新一次
    
    def _load_cache(self) -> List[Dict]:
        """加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("news", [])
            except:
                pass
        return []
    
    def _save_cache(self, news: List[Dict]):
        """保存缓存"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "news": news,
                "last_update": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def _should_fetch(self) -> bool:
        """判断是否需要重新抓取"""
        if not self._last_fetch_time:
            return True
        
        return datetime.now() - self._last_fetch_time > timedelta(minutes=self._fetch_interval_minutes)
    
    def refresh_news(self) -> bool:
        """刷新新闻（手动触发）"""
        try:
            print("[News] 开始刷新新闻...")
            news = fetch_news_sync()
            if news:
                self._save_cache(news)
                self._last_fetch_time = datetime.now()
                print(f"[News] 刷新成功：{len(news)}条")
                return True
            else:
                print("[News] 刷新失败：无数据")
                return False
        except Exception as e:
            print(f"[News] 刷新异常：{e}")
            return False
    
    def get_all_news(self, category=None, location=None, use_cache=True):
        """获取所有新闻，支持分类和位置过滤"""
        # 尝试从 RSS 获取
        if use_cache:
            news = get_cached_news_sync(max_age_minutes=self._fetch_interval_minutes)
            if news:
                self._last_fetch_time = datetime.now()
        else:
            news = self._load_cache()
        
        # 如果没有数据，使用备用示例
        if not news:
            news = SAMPLE_NEWS
        
        # 过滤
        if category:
            news = [n for n in news if n.get("category") == category]
        if location:
            news = [n for n in news if n.get("location") == location]
        
        # 排序
        news = sorted(news, key=lambda x: x.get("published_at", ""), reverse=True)
        return news
    
    def get_news_by_id(self, news_id):
        """根据 ID 获取新闻"""
        news = self.get_all_news()
        for item in news:
            if item.get("id") == news_id:
                return item
        return None
    
    def get_news_by_location(self, location):
        """根据位置获取新闻"""
        return [n for n in self.get_all_news() if n.get("location") == location]
    
    def get_locations(self):
        """获取所有位置信息"""
        return self.locations
    
    def get_location_news(self):
        """获取带位置信息的新闻列表"""
        news = self.get_all_news()
        result = []
        for item in news:
            loc_key = item.get("location")
            if loc_key and loc_key in self.locations:
                loc_info = self.locations[loc_key].copy()
                loc_info["news"] = item
                result.append(loc_info)
        return result
    
    def get_categories(self):
        """获取所有新闻分类"""
        news = self.get_all_news()
        categories = set()
        for item in news:
            if item.get("category"):
                categories.add(item["category"])
        return sorted(list(categories)) if categories else ["科技", "财经", "能源", "政治"]
    
    def get_stats(self):
        """获取新闻统计信息"""
        news = self.get_all_news()
        categories = {}
        sources = {}
        
        for item in news:
            cat = item.get("category", "其他")
            src = item.get("source", "未知")
            categories[cat] = categories.get(cat, 0) + 1
            sources[src] = sources.get(src, 0) + 1
        
        return {
            "total": len(news),
            "categories": categories,
            "sources": sources,
            "last_update": self._last_fetch_time.isoformat() if self._last_fetch_time else None
        }


news_manager = NewsManager()
