"""
RSS 数据清洗与重复检测工具
职责：
  1. HTML 标签清洗（去除 summary/title 中的 HTML）
  2. 空标题过滤
  3. 无效 URL 过滤
  4. 基于 URL + 标题去重
  5. 清洗后流水线（clean → dedup → save）

使用方式：
  from services.dedup_clean import clean_articles, deduplicate_articles, process_rss_pipeline
  clean = clean_articles(raw_entries)
  unique = deduplicate_articles(clean, existing_urls, existing_titles)
  articles = process_rss_pipeline(raw_entries, existing_db)
"""

import re
import hashlib
import logging
from typing import List, Dict, Set, Tuple, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# HTML 清洗
# ──────────────────────────────────────────────

# 匹配 HTML 标签的正则（包括自闭合标签）
_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
# 匹配 HTML 实体
_HTML_ENTITY_PATTERN = re.compile(r'&[a-zA-Z0-9#]+;')

# 常用 HTML 实体映射
_HTML_ENTITIES = {
    '&nbsp;': ' ',
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&apos;': "'",
    '&ndash;': '–',
    '&mdash;': '—',
    '&laquo;': '«',
    '&raquo;': '»',
    '&copy;': '©',
    '&reg;': '®',
    '&trade;': '™',
    '&hellip;': '…',
    '&bull;': '•',
}


def strip_html_tags(text: str) -> str:
    """
    去除字符串中的 HTML 标签，并转换常见 HTML 实体。
    """
    if not text:
        return ""
    # 先处理 HTML 实体
    cleaned = text
    for entity, replacement in _HTML_ENTITIES.items():
        cleaned = cleaned.replace(entity, replacement)
    # 移除剩余的 numeric entities
    cleaned = re.sub(r'&#\d+;', '', cleaned)
    cleaned = re.sub(r'&#[xX][0-9a-fA-F]+;', '', cleaned)
    # 移除 HTML 标签
    cleaned = _HTML_TAG_PATTERN.sub('', cleaned)
    # 清理多余空白
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def clean_title(title: str) -> str:
    """清洗标题：去 HTML、去前后空白"""
    if not title:
        return ""
    return strip_html_tags(title).strip()


def clean_summary(summary: str, max_length: int = 500) -> str:
    """清洗摘要：去 HTML、截断到最大长度"""
    if not summary:
        return ""
    cleaned = strip_html_tags(summary).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip() + "…"
    return cleaned


# ──────────────────────────────────────────────
# 有效性校验
# ──────────────────────────────────────────────

def is_valid_url(url: str) -> bool:
    """
    校验 URL 是否有效。
    要求：非空、包含 scheme (http/https)、有 netloc。
    """
    if not url or not url.strip():
        return False
    url = url.strip()
    try:
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme not in ('http', 'https'):
            return False
        if not parsed.netloc:
            return False
        # 排除明显无效的 URL
        if parsed.netloc in ('localhost', '127.0.0.1'):
            return True  # 本地开发环境允许
        return True
    except Exception:
        return False


def is_valid_title(title: str) -> bool:
    """
    校验标题是否有效。
    要求：非空、清洗后至少有 2 个字符（排除纯空白/单字符标题）。
    """
    if not title:
        return False
    cleaned = clean_title(title)
    return len(cleaned) >= 2


# ──────────────────────────────────────────────
# 去重逻辑
# ──────────────────────────────────────────────

def normalize_title_for_dedup(title: str) -> str:
    """
    将标题标准化为去重比较格式：
    - 去 HTML
    - 转小写
    - 去空白
    - 去标点符号（保留中英文）
    """
    if not title:
        return ""
    cleaned = clean_title(title).lower()
    # 去除标点符号（保留 Unicode 字母和数字）
    cleaned = re.sub(r'[^\w\s]', '', cleaned, flags=re.UNICODE)
    cleaned = re.sub(r'\s+', '', cleaned)
    return cleaned


def title_hash(title: str) -> str:
    """生成标题的相似度 hash"""
    normalized = normalize_title_for_dedup(title)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


def url_canonical(url: str) -> str:
    """
    规范化 URL 用于去重比较：
    - 去 trailing slash
    - 转小写
    - 去 common tracking params
    """
    if not url:
        return ""
    url = url.strip().lower()
    # 去除常见的追踪参数
    try:
        parsed = urlparse(url)
        from urllib.parse import urlencode, parse_qs
        params = parse_qs(parsed.query, keep_blank_values=True)
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term',
                          'utm_content', 'ref', 'fbclid', 'gclid'}
        filtered_params = {k: v for k, v in params.items() if k not in tracking_params}
        new_query = urlencode(filtered_params, doseq=True)
        canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        if new_query:
            canonical += f"?{new_query}"
        if parsed.fragment:
            canonical += f"#{parsed.fragment}"
        return canonical
    except Exception:
        return url.lower().rstrip('/')


def is_duplicate_by_url(url: str, existing_urls: Set[str]) -> bool:
    """基于规范化 URL 判断是否重复"""
    if not url:
        return False
    canonical = url_canonical(url)
    return canonical in existing_urls


def is_duplicate_by_title(title: str, existing_title_hashes: Set[str]) -> bool:
    """基于标题 hash 判断是否重复"""
    if not title:
        return False
    h = title_hash(title)
    return h in existing_title_hashes


# ──────────────────────────────────────────────
# 清洗流水线
# ──────────────────────────────────────────────

def clean_articles(
    entries: List[Dict],
    *,
    skip_empty_title: bool = True,
    skip_invalid_url: bool = True,
    max_summary_length: int = 500,
) -> List[Dict]:
    """
    对 RSS 原始条目进行清洗。

    参数：
      entries: feedparser 解析的原始条目列表
      skip_empty_title: 是否跳过空标题
      skip_invalid_url: 是否跳过无效 URL
      max_summary_length: 摘要最大长度

    返回：
      清洗后的条目列表
    """
    cleaned = []
    skipped_reasons = {"empty_title": 0, "invalid_url": 0}

    for i, entry in enumerate(entries):
        raw_title = entry.get('title', '')
        raw_url = entry.get('link', entry.get('url', ''))
        raw_summary = entry.get('summary', entry.get('description', ''))

        # 1. 清洗标题
        title = clean_title(raw_title)

        # 2. 校验标题
        if skip_empty_title and not is_valid_title(raw_title):
            skipped_reasons["empty_title"] += 1
            logger.debug(f"跳过空标题条目 [{i}]: title='{raw_title[:50]}'")
            continue

        # 3. 校验 URL
        url = raw_url.strip() if raw_url else ''
        if skip_invalid_url and not is_valid_url(url):
            skipped_reasons["invalid_url"] += 1
            logger.debug(f"跳过无效 URL 条目 [{i}]: url='{url[:50]}'")
            continue

        # 4. 清洗摘要
        summary = clean_summary(raw_summary, max_length=max_summary_length)

        # 5. 构建清洗后的条目
        cleaned_entry = {
            'title': title,
            'url': url,
            'summary': summary,
            'source': entry.get('source', entry.get('feed_title', '')),
            'category': entry.get('category', ''),
            'published_at': entry.get('published', entry.get('published_parsed', '')),
            'author': entry.get('author', ''),
            'raw_entry': entry,  # 保留原始数据供调试
        }
        cleaned.append(cleaned_entry)

    if skipped_reasons["empty_title"] or skipped_reasons["invalid_url"]:
        logger.info(
            f"数据清洗：共 {len(entries)} 条，"
            f"清洗后 {len(cleaned)} 条，"
            f"跳过空标题 {skipped_reasons['empty_title']}，"
            f"跳过无效URL {skipped_reasons['invalid_url']}"
        )

    return cleaned


def deduplicate_articles(
    articles: List[Dict],
    existing_urls: Optional[Set[str]] = None,
    existing_title_hashes: Optional[Set[str]] = None,
    *,
    dedup_by_url: bool = True,
    dedup_by_title: bool = True,
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    对清洗后的文章进行去重。

    参数：
      articles: 清洗后的文章列表
      existing_urls: 数据库中已有的规范化 URL 集合
      existing_title_hashes: 数据库中已有的标题 hash 集合
      dedup_by_url: 是否按 URL 去重
      dedup_by_title: 是否按标题去重

    返回：
      (去重后的文章列表, 统计信息)
    """
    if existing_urls is None:
        existing_urls = set()
    if existing_title_hashes is None:
        existing_title_hashes = set()

    # 去重时记录本次新增的 URL/hash，避免同批次内重复
    batch_urls: Set[str] = set()
    batch_hashes: Set[str] = set()

    unique = []
    dup_stats = {"url_dup": 0, "title_dup": 0, "kept": 0}

    for article in articles:
        url = article.get('url', '')
        title = article.get('title', '')

        is_dup = False

        # URL 去重
        if dedup_by_url and url:
            canonical = url_canonical(url)
            if canonical in existing_urls or canonical in batch_urls:
                dup_stats["url_dup"] += 1
                is_dup = True
            else:
                batch_urls.add(canonical)

        # 标题去重
        if not is_dup and dedup_by_title and title:
            h = title_hash(title)
            if h in existing_title_hashes or h in batch_hashes:
                dup_stats["title_dup"] += 1
                is_dup = True
            else:
                batch_hashes.add(h)

        if not is_dup:
            unique.append(article)
            dup_stats["kept"] += 1

    total = len(articles)
    duped = dup_stats["url_dup"] + dup_stats["title_dup"]
    if duped > 0:
        logger.info(
            f"去重：共 {total} 条，"
            f"URL重复 {dup_stats['url_dup']}，"
            f"标题重复 {dup_stats['title_dup']}，"
            f"保留 {dup_stats['kept']}"
        )

    return unique, dup_stats


def process_rss_pipeline(
    entries: List[Dict],
    existing_urls: Optional[Set[str]] = None,
    existing_title_hashes: Optional[Set[str]] = None,
    **kwargs,
) -> Tuple[List[Dict], Dict]:
    """
    完整的 RSS 数据处理流水线：清洗 → 去重。

    参数：
      entries: feedparser 原始条目
      existing_urls: 已有 URL 集合
      existing_title_hashes: 已有标题 hash 集合
      **kwargs: 传递给 clean_articles / deduplicate_articles 的参数

    返回：
      (最终结果列表, 统计信息)
    """
    # Step 1: 清洗
    cleaned = clean_articles(entries, **kwargs)

    # Step 2: 去重
    unique, dup_stats = deduplicate_articles(
        cleaned,
        existing_urls=existing_urls,
        existing_title_hashes=existing_title_hashes,
        **{k: v for k, v in kwargs.items() if k in ('dedup_by_url', 'dedup_by_title')},
    )

    stats = {
        "raw_count": len(entries),
        "cleaned_count": len(cleaned),
        "unique_count": len(unique),
        "dup_stats": dup_stats,
    }

    return unique, stats


def extract_existing_data_from_db(
    articles: List[Dict],
) -> Tuple[Set[str], Set[str]]:
    """
    从已有文章列表中提取 URL 集合和标题 hash 集合。
    用于数据库查询后构建去重索引。
    """
    urls = set()
    title_hashes = set()
    for article in articles:
        if article.get('url'):
            urls.add(url_canonical(article['url']))
        if article.get('title'):
            title_hashes.add(title_hash(article['title']))
    return urls, title_hashes
