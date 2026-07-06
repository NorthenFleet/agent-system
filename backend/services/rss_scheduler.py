"""
RSS 定时抓取调度器
集成 dedup_clean.py（清洗+去重）和 rss_scraper.py（真实抓取）。

职责：
  1. APScheduler 定时触发 RSS 抓取
  2. 调用 rss_scraper 获取原始条目
  3. 调用 dedup_clean 清洗+去重
  4. 持久化到 intelligence_articles 表
  5. 手动触发端点（供前端/管理面板调用）
"""

import logging
from datetime import datetime
from typing import Optional

from services.rss_scraper import rss_scraper
from services.dedup_clean import (
    process_rss_pipeline,
    extract_existing_data_from_db,
)

logger = logging.getLogger(__name__)


class RSSScheduler:
    """
    RSS 定时抓取调度器

    与 APScheduler 集成，每 30 分钟触发一次抓取。
    也可通过 run_once() 手动触发。
    """

    def __init__(self, article_repo=None):
        """
        参数：
          article_repo: IntelligenceArticle repository（可选）。
                        如果提供，去重时会自动查询已有数据；
                        如果未提供，仅做清洗+内存去重。
        """
        self.article_repo = article_repo
        self.last_run_stats = None

    def _get_existing_index(self):
        """从数据库获取已有文章的 URL 和 title hash 索引"""
        if self.article_repo is None:
            return set(), set()
        try:
            articles = self.article_repo.get_all_for_dedup()
            return extract_existing_data_from_db(articles)
        except Exception as e:
            logger.warning(f"获取已有文章索引失败（使用空索引）: {e}")
            return set(), set()

    def run_once(self) -> dict:
        """
        执行一次完整的 RSS 抓取+清洗+去重流程。

        返回：
          {
            "success": bool,
            "stats": { raw_count, cleaned_count, unique_count, dup_stats },
            "saved_count": int,
            "error": str | None,
          }
        """
        logger.info("[RSS Scheduler] 开始执行抓取任务...")
        start = datetime.now()

        try:
            # Step 1: 抓取
            raw_entries = rss_scraper.fetch_all()
            if not raw_entries:
                logger.warning("[RSS Scheduler] 抓取结果为空，跳过后续处理")
                self.last_run_stats = {
                    "raw_count": 0,
                    "cleaned_count": 0,
                    "unique_count": 0,
                    "saved_count": 0,
                    "dup_stats": {"url_dup": 0, "title_dup": 0, "kept": 0},
                    "duration_ms": int((datetime.now() - start).total_seconds() * 1000),
                }
                return {
                    "success": False,
                    "stats": self.last_run_stats,
                    "saved_count": 0,
                    "error": "RSS 抓取结果为空",
                }

            # Step 2: 获取已有数据索引（用于去重）
            existing_urls, existing_hashes = self._get_existing_index()

            # Step 3: 清洗 + 去重
            unique_articles, stats = process_rss_pipeline(
                raw_entries,
                existing_urls=existing_urls,
                existing_title_hashes=existing_hashes,
            )

            # Step 4: 持久化到数据库
            saved_count = 0
            if self.article_repo is not None and unique_articles:
                saved_count = self._save_articles(unique_articles)

            # 组装最终统计
            self.last_run_stats = {
                "raw_count": stats["raw_count"],
                "cleaned_count": stats["cleaned_count"],
                "unique_count": stats["unique_count"],
                "saved_count": saved_count,
                "dup_stats": stats["dup_stats"],
                "duration_ms": int((datetime.now() - start).total_seconds() * 1000),
            }

            logger.info(
                f"[RSS Scheduler] 抓取完成: "
                f"原始 {stats['raw_count']} → 清洗 {stats['cleaned_count']} "
                f"→ 去重 {stats['unique_count']} → 入库 {saved_count} "
                f"({self.last_run_stats['duration_ms']}ms)"
            )

            return {
                "success": True,
                "stats": self.last_run_stats,
                "saved_count": saved_count,
                "error": None,
            }

        except Exception as e:
            logger.error(f"[RSS Scheduler] 执行异常: {e}", exc_info=True)
            self.last_run_stats = {
                "raw_count": 0,
                "cleaned_count": 0,
                "unique_count": 0,
                "saved_count": 0,
                "dup_stats": {"url_dup": 0, "title_dup": 0, "kept": 0},
                "duration_ms": int((datetime.now() - start).total_seconds() * 1000),
            }
            return {
                "success": False,
                "stats": self.last_run_stats,
                "saved_count": 0,
                "error": str(e),
            }

    def _save_articles(self, articles: list) -> int:
        """将清洗去重后的文章入库"""
        saved = 0
        for article in articles:
            try:
                self.article_repo.create_if_not_exists(
                    title=article["title"],
                    url=article["url"],
                    summary=article.get("summary", ""),
                    source=article.get("source", ""),
                    category=article.get("category", ""),
                    published_at=article.get("published") or None,
                    author=article.get("author", ""),
                )
                saved += 1
            except Exception as e:
                logger.warning(f"保存文章失败 (title={article.get('title','')[:50]}): {e}")
        return saved


# ── APScheduler 集成 ──

_rss_scheduler_instance: Optional[RSSScheduler] = None


def get_rss_scheduler(article_repo=None) -> RSSScheduler:
    """获取或创建 RSSScheduler 全局实例"""
    global _rss_scheduler_instance
    if _rss_scheduler_instance is None:
        _rss_scheduler_instance = RSSScheduler(article_repo=article_repo)
    return _rss_scheduler_instance


def scheduled_rss_fetch(article_repo=None):
    """
    APScheduler 回调函数 — 触发一次 RSS 抓取。

    用法：
      scheduler.add_job(scheduled_rss_fetch, 'cron', minute='*/30')
    """
    sched = get_rss_scheduler(article_repo=article_repo)
    return sched.run_once()
