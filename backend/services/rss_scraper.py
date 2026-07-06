"""
RSS 真实抓取器
职责：
  1. 从配置的 RSS 源抓取文章
  2. 返回原始 feedparser 条目供清洗流水线处理
  3. 与 dedup_clean.py 配合使用

使用方式：
  from services.rss_scraper import rss_scraper
  entries = rss_scraper.fetch_all()
  articles, stats = process_rss_pipeline(entries, existing_urls, existing_hashes)
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional

import feedparser
import requests

from services.dedup_clean import (
    clean_title, clean_summary, is_valid_url, is_valid_title,
)

logger = logging.getLogger(__name__)

# RSS 订阅源配置
RSS_FEEDS = [
    {
        "key": "36kr",
        "name": "36Kr",
        "url": "https://www.36kr.com/feed",
        "category": "科技",
    },
    {
        "key": "huxiu",
        "name": "虎嗅",
        "url": "https://www.huxiu.com/rss/0.xml",
        "category": "财经",
    },
    {
        "key": "github_trending",
        "name": "GitHub Trending",
        "url": "https://github-trends.com/rss",
        "category": "科技",
    },
    {
        "key": "infoq",
        "name": "InfoQ",
        "url": "https://www.infoq.cn/feed",
        "category": "科技",
    },
    {
        "key": "solidot",
        "name": "Solidot",
        "url": "https://www.solidot.org/index.rss",
        "category": "科技",
    },
]

REQUEST_TIMEOUT = 15  # 秒
MAX_ENTRIES_PER_FEED = 50


class RSSScraper:
    """RSS 抓取器 — 同步模式（适用于 APScheduler 后台任务）"""

    def __init__(self, feeds: Optional[List[Dict]] = None):
        self.feeds = feeds or RSS_FEEDS
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Team Dashboard RSS Bot/1.0)"
        })

    def _fetch_one(self, feed_config: Dict) -> List[Dict]:
        """抓取单个 RSS 源，返回原始 feedparser entries"""
        url = feed_config["url"]
        name = feed_config.get("name", url)
        category = feed_config.get("category", "")
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            entries = []
            for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
                raw_title = entry.get("title", "")
                title = clean_title(raw_title)
                if not is_valid_title(raw_title):
                    continue

                link = entry.get("link", entry.get("url", ""))
                if not is_valid_url(link):
                    continue

                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).isoformat()
                    except Exception:
                        pass
                if not published and hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    try:
                        published = datetime(*entry.updated_parsed[:6]).isoformat()
                    except Exception:
                        pass

                summary = entry.get("summary", entry.get("description", ""))

                entries.append({
                    "title": title,
                    "raw_title": raw_title,
                    "url": link.strip(),
                    "summary": summary,
                    "source": name,
                    "category": category,
                    "published": published,
                    "author": entry.get("author", ""),
                    "feed_key": feed_config.get("key", ""),
                })

            logger.info(f"[RSS] {name} 抓取成功: {len(entries)} 条有效条目")
            return entries

        except Exception as e:
            logger.warning(f"[RSS] {name} 抓取失败: {e}")
            return []

    def fetch_all(self) -> List[Dict]:
        """抓取所有 RSS 源，返回原始条目列表"""
        all_entries = []
        for feed_config in self.feeds:
            entries = self._fetch_one(feed_config)
            all_entries.extend(entries)

        logger.info(f"[RSS] 全部抓取完成，共 {len(all_entries)} 条原始条目")
        return all_entries

    def fetch_one(self, key: str) -> List[Dict]:
        """按 key 抓取单个 RSS 源"""
        for feed_config in self.feeds:
            if feed_config["key"] == key:
                return self._fetch_one(feed_config)
        logger.warning(f"[RSS] 未找到 key={key} 的 RSS 源")
        return []

    def get_feed_config(self) -> List[Dict]:
        """返回 RSS 源配置列表"""
        return [
            {"key": f["key"], "name": f["name"], "url": f["url"], "category": f["category"]}
            for f in self.feeds
        ]


# 全局单例
rss_scraper = RSSScraper()
