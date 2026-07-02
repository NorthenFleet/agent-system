# -*- coding: utf-8 -*-
"""
RSS 新闻抓取器 - 从 RSS 源和 API 获取实时新闻
支持：36Kr、虎嗅、GitHub Trending、知乎热榜
"""
import sys
import os

# 添加多个可能的 site-packages 路径
for path in [
    '/opt/homebrew/lib/python3.14/site-packages',
    '/opt/homebrew/lib/python3.11/site-packages',
    '/Users/apple/Library/Python/3.14/lib/python/site-packages',
]:
    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

import feedparser
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import hashlib
import json

# RSS 订阅源配置
RSS_FEEDS = {
    "36kr": {
        "name": "36Kr",
        "url": "https://www.36kr.com/feed",
        "category": "科技",
        "location": "beijing",
        "priority": "high"
    },
    "huxiu": {
        "name": "虎嗅",
        "url": "https://www.huxiu.com/rss/1.xml",
        "category": "财经",
        "location": "beijing",
        "priority": "medium"
    },
    "github_trending": {
        "name": "GitHub Trending",
        "url": "https://github-trends.com/rss",
        "category": "科技",
        "location": "sanfrancisco",
        "priority": "high"
    },
    "zhihu_hot": {
        "name": "知乎热榜",
        "url": "https://www.zhihu.com/rss",
        "category": "科技",
        "location": "beijing",
        "priority": "medium"
    }
}

# NewsAPI 配置（备用）
NEWSAPI_CONFIG = {
    "endpoint": "https://newsapi.org/v2/top-headlines",
    "countries": ["cn", "us"],
    "categories": ["technology", "business", "science"]
}


class RSSNewsFetcher:
    """RSS 新闻抓取器"""
    
    def __init__(self, cache_file: str = None):
        self.cache_file = cache_file or os.path.join(
            os.path.dirname(__file__), 
            "../data/news_cache.json"
        )
        self.cache = self._load_cache()
        self.session = None
    
    def _load_cache(self) -> Dict:
        """加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"news": [], "last_update": None}
    
    def _save_cache(self):
        """保存缓存"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def _generate_id(self, title: str, url: str) -> str:
        """生成唯一 ID"""
        return hashlib.md5(f"{title}:{url}".encode()).hexdigest()[:12]
    
    async def fetch_feed(self, feed_key: str, feed_config: Dict) -> List[Dict]:
        """抓取单个 RSS 源"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(feed_config["url"], timeout=10) as response:
                if response.status != 200:
                    print(f"[RSS] {feed_config['name']} 请求失败：{response.status}")
                    return []
                
                content = await response.text()
                feed = feedparser.parse(content)
                
                news_list = []
                for entry in feed.entries[:20]:  # 每个源最多 20 条
                    published = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6]).isoformat()
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published = datetime(*entry.updated_parsed[:6]).isoformat()
                    else:
                        published = datetime.now().isoformat()
                    
                    news_item = {
                        "id": self._generate_id(entry.title, entry.get('link', '')),
                        "title": entry.title,
                        "summary": entry.get('summary', entry.get('description', ''))[:200],
                        "category": feed_config.get("category", "科技"),
                        "location": feed_config.get("location", "beijing"),
                        "source": feed_config["name"],
                        "url": entry.get('link', ''),
                        "published_at": published,
                        "priority": feed_config.get("priority", "medium"),
                        "fetched_at": datetime.now().isoformat()
                    }
                    news_list.append(news_item)
                
                print(f"[RSS] {feed_config['name']} 抓取成功：{len(news_list)}条")
                return news_list
                
        except Exception as e:
            print(f"[RSS] {feed_config['name']} 抓取失败：{e}")
            return []
    
    async def fetch_all_feeds(self) -> List[Dict]:
        """抓取所有 RSS 源"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        tasks = [
            self.fetch_feed(key, config) 
            for key, config in RSS_FEEDS.items()
        ]
        results = await asyncio.gather(*tasks)
        
        # 合并所有新闻
        all_news = []
        for news_list in results:
            all_news.extend(news_list)
        
        # 去重（按 ID）
        seen = set()
        unique_news = []
        for news in all_news:
            if news["id"] not in seen:
                seen.add(news["id"])
                unique_news.append(news)
        
        # 按时间排序
        unique_news.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        
        # 更新缓存
        self.cache["news"] = unique_news[:100]  # 最多保留 100 条
        self.cache["last_update"] = datetime.now().isoformat()
        self._save_cache()
        
        if self.session:
            await self.session.close()
            self.session = None
        
        return unique_news
    
    def get_cached_news(self, max_age_minutes: int = 30) -> List[Dict]:
        """获取缓存的新闻"""
        if not self.cache.get("last_update"):
            return []
        
        last_update = datetime.fromisoformat(self.cache["last_update"])
        if datetime.now() - last_update > timedelta(minutes=max_age_minutes):
            return []  # 缓存过期
        
        return self.cache.get("news", [])
    
    def get_all_news(self) -> List[Dict]:
        """获取所有新闻（缓存 + 实时）"""
        return self.cache.get("news", [])


# 同步包装器（用于 FastAPI）
def fetch_news_sync() -> List[Dict]:
    """同步方式抓取新闻"""
    fetcher = RSSNewsFetcher()
    return asyncio.run(fetcher.fetch_all_feeds())


def get_cached_news_sync(max_age_minutes: int = 30) -> List[Dict]:
    """同步方式获取缓存新闻"""
    fetcher = RSSNewsFetcher()
    cached = fetcher.get_cached_news(max_age_minutes)
    
    # 如果缓存过期，触发更新
    if not cached:
        print("[RSS] 缓存过期，开始更新...")
        return asyncio.run(fetcher.fetch_all_feeds())
    
    return cached


if __name__ == "__main__":
    # 测试
    print("开始抓取新闻...")
    news = fetch_news_sync()
    print(f"抓取完成，共{len(news)}条新闻")
    for n in news[:5]:
        print(f"  - {n['title']} ({n['source']})")
