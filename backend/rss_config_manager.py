"""
RSS 源配置管理器

功能：
- 读取/保存 RSS 订阅源配置
- 添加、编辑、删除、启用/禁用订阅源
- 配置持久化到 rss_config.json

@author 拉斐尔 (🟥 后端开发)
@created 2026-06-25
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "rss_config.json")


class RSSConfigManager:
    """RSS 源配置管理器"""

    DEFAULT_CONFIG = {
        "feeds": [
            {
                "key": "36kr",
                "name": "36Kr",
                "url": "https://www.36kr.com/feed",
                "category": "科技",
                "location": "beijing",
                "priority": "high",
                "enabled": True,
            },
            {
                "key": "huxiu",
                "name": "虎嗅",
                "url": "https://www.huxiu.com/rss/1.xml",
                "category": "财经",
                "location": "beijing",
                "priority": "medium",
                "enabled": True,
            },
            {
                "key": "github_trending",
                "name": "GitHub Trending",
                "url": "https://github-trends.com/rss",
                "category": "科技",
                "location": "sanfrancisco",
                "priority": "high",
                "enabled": True,
            },
            {
                "key": "zhihu_hot",
                "name": "知乎热榜",
                "url": "https://www.zhihu.com/rss",
                "category": "科技",
                "location": "beijing",
                "priority": "medium",
                "enabled": True,
            },
        ]
    }

    def __init__(self):
        self._config = self._load()

    def _load(self) -> dict:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return self.DEFAULT_CONFIG.copy()

    def _save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def get_feeds(self) -> List[dict]:
        return self._config.get("feeds", [])

    def get_enabled_feeds(self) -> List[dict]:
        return [f for f in self._config.get("feeds", []) if f.get("enabled", True)]

    def get_feed(self, key: str) -> Optional[dict]:
        for feed in self.get_feeds():
            if feed.get("key") == key:
                return feed
        return None

    def add_feed(self, feed: dict) -> dict:
        feeds = self._config.setdefault("feeds", [])
        feed.setdefault("enabled", True)
        feed.setdefault("priority", "medium")
        feed.setdefault("created_at", datetime.now().isoformat())
        feed.setdefault("updated_at", datetime.now().isoformat())
        feeds.append(feed)
        self._save()
        return feed

    def update_feed(self, key: str, updates: dict) -> Optional[dict]:
        for feed in self.get_feeds():
            if feed.get("key") == key:
                feed.update(updates)
                feed["updated_at"] = datetime.now().isoformat()
                self._save()
                return feed
        return None

    def delete_feed(self, key: str) -> bool:
        feeds = self._config.get("feeds", [])
        new_feeds = [f for f in feeds if f.get("key") != key]
        if len(new_feeds) < len(feeds):
            self._config["feeds"] = new_feeds
            self._save()
            return True
        return False

    def toggle_feed(self, key: str) -> Optional[dict]:
        feed = self.get_feed(key)
        if feed:
            feed["enabled"] = not feed.get("enabled", True)
            feed["updated_at"] = datetime.now().isoformat()
            self._save()
        return feed

    def sync_to_rss_fetcher(self):
        """将当前配置同步到 rss_fetcher 的 RSS_FEEDS 字典，使其在运行时生效。"""
        try:
            import rss_fetcher
            feeds = {}
            for feed in self.get_enabled_feeds():
                feeds[feed["key"]] = {
                    "name": feed["name"],
                    "url": feed["url"],
                    "category": feed.get("category", "科技"),
                    "location": feed.get("location", "beijing"),
                    "priority": feed.get("priority", "medium"),
                }
            rss_fetcher.RSS_FEEDS = feeds
            print(f"[RSS-Config] 已同步 {len(feeds)} 个订阅源到抓取器")
        except ImportError:
            pass


rss_config_manager = RSSConfigManager()
