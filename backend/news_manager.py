# -*- coding: utf-8 -*-
"""
新闻管理器 - 管理全球新闻资讯
"""
from datetime import datetime
from typing import List, Dict, Optional

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

# 示例新闻数据
SAMPLE_NEWS = [
    {"id": "1", "title": "中国发布新一代人工智能发展规划", "summary": "国务院发布新一代人工智能发展规划，提出到 2030 年人工智能核心产业规模超过 1 万亿元", "category": "科技", "location": "beijing", "source": "新华网", "url": "https://example.com/news/1", "published_at": "2026-04-06T09:00:00Z", "priority": "high"},
    {"id": "2", "title": "上海科创板迎来新突破", "summary": "上海证券交易所科创板今日新增 5 家企业上市，总市值超过 500 亿元", "category": "财经", "location": "shanghai", "source": "财新网", "url": "https://example.com/news/2", "published_at": "2026-04-06T08:30:00Z", "priority": "medium"},
    {"id": "3", "title": "深圳科技创新成果展开幕", "summary": "2026 深圳科技创新成果展今日开幕，展示多项前沿科技成果", "category": "科技", "location": "shenzhen", "source": "南方日报", "url": "https://example.com/news/3", "published_at": "2026-04-06T07:00:00Z", "priority": "medium"},
    {"id": "4", "title": "日本发布新型机器人技术", "summary": "东京大学研究团队发布新型人形机器人，具备更强大的学习能力", "category": "科技", "location": "tokyo", "source": "日经新闻", "url": "https://example.com/news/4", "published_at": "2026-04-06T06:00:00Z", "priority": "medium"},
    {"id": "5", "title": "韩国半导体产业新投资", "summary": "三星电子宣布将在首尔投资 100 亿美元建设新半导体工厂", "category": "财经", "location": "seoul", "source": "韩联社", "url": "https://example.com/news/5", "published_at": "2026-04-06T05:30:00Z", "priority": "high"},
    {"id": "6", "title": "新加坡金融科技峰会召开", "summary": "2026 新加坡金融科技峰会今日开幕，全球超过 500 家金融机构参会", "category": "财经", "location": "singapore", "source": "海峡时报", "url": "https://example.com/news/6", "published_at": "2026-04-06T04:00:00Z", "priority": "medium"},
    {"id": "7", "title": "英国发布新能源政策", "summary": "英国政府发布新能源政策，计划 2030 年前实现 80% 可再生能源发电", "category": "能源", "location": "london", "source": "BBC", "url": "https://example.com/news/7", "published_at": "2026-04-06T03:00:00Z", "priority": "high"},
    {"id": "8", "title": "法国 AI 研究中心成立", "summary": "巴黎成立新的人工智能研究中心，投资规模达 5 亿欧元", "category": "科技", "location": "paris", "source": "法新社", "url": "https://example.com/news/8", "published_at": "2026-04-06T02:30:00Z", "priority": "medium"},
    {"id": "9", "title": "德国汽车工业转型加速", "summary": "德国三大汽车制造商宣布加速电动化转型，投资总额超过 1000 亿欧元", "category": "汽车", "location": "berlin", "source": "德新社", "url": "https://example.com/news/9", "published_at": "2026-04-06T01:00:00Z", "priority": "high"},
    {"id": "10", "title": "纽约股市创新高", "summary": "道琼斯指数今日收盘创新高，科技股领涨", "category": "财经", "location": "newyork", "source": "华尔街日报", "url": "https://example.com/news/10", "published_at": "2026-04-05T23:00:00Z", "priority": "medium"},
    {"id": "11", "title": "旧金山科技巨头发布新产品", "summary": "某科技巨头在旧金山发布新一代 AI 产品，引发市场关注", "category": "科技", "location": "sanfrancisco", "source": "TechCrunch", "url": "https://example.com/news/11", "published_at": "2026-04-05T22:00:00Z", "priority": "high"},
    {"id": "12", "title": "华盛顿发布新贸易政策", "summary": "美国政府发布新贸易政策，影响全球贸易格局", "category": "政治", "location": "washington", "source": "路透社", "url": "https://example.com/news/12", "published_at": "2026-04-05T21:00:00Z", "priority": "high"},
]


class NewsManager:
    """新闻管理器"""
    
    def __init__(self):
        self.news_data = SAMPLE_NEWS.copy()
        self.locations = NEWS_LOCATIONS
    
    def get_all_news(self, category=None, location=None):
        """获取所有新闻，支持分类和位置过滤"""
        news = self.news_data
        if category:
            news = [n for n in news if n.get("category") == category]
        if location:
            news = [n for n in news if n.get("location") == location]
        news = sorted(news, key=lambda x: x.get("published_at", ""), reverse=True)
        return news
    
    def get_news_by_id(self, news_id):
        """根据 ID 获取新闻"""
        for news in self.news_data:
            if news["id"] == news_id:
                return news
        return None
    
    def get_news_by_location(self, location):
        """根据位置获取新闻"""
        return [n for n in self.news_data if n.get("location") == location]
    
    def get_locations(self):
        """获取所有位置信息"""
        return self.locations
    
    def get_location_news(self):
        """获取带位置信息的新闻列表"""
        result = []
        for news in self.news_data:
            loc_key = news.get("location")
            if loc_key and loc_key in self.locations:
                loc_info = self.locations[loc_key].copy()
                loc_info["news"] = news
                result.append(loc_info)
        return result
    
    def get_categories(self):
        """获取所有新闻分类"""
        categories = set()
        for news in self.news_data:
            if news.get("category"):
                categories.add(news["category"])
        return sorted(list(categories))


news_manager = NewsManager()
