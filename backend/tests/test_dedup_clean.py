"""
测试: dedup_clean.py — 数据清洗 + 重复检测
"""
import pytest
from services.dedup_clean import (
    strip_html_tags,
    clean_title,
    clean_summary,
    is_valid_url,
    is_valid_title,
    normalize_title_for_dedup,
    title_hash,
    url_canonical,
    is_duplicate_by_url,
    is_duplicate_by_title,
    clean_articles,
    deduplicate_articles,
    process_rss_pipeline,
    extract_existing_data_from_db,
)


# ──────────────────────────────────────────────
# HTML 清洗
# ──────────────────────────────────────────────

class TestStripHtmlTags:
    def test_plain_text(self):
        assert strip_html_tags("Hello World") == "Hello World"

    def test_remove_simple_tags(self):
        assert strip_html_tags("<b>Hello</b>") == "Hello"

    def test_remove_nested_tags(self):
        result = strip_html_tags("<div><p>Hello <b>World</b></p></div>")
        assert "Hello" in result
        assert "World" in result
        assert "<" not in result

    def test_remove_self_closing(self):
        result = strip_html_tags("Line<br/>break")
        assert "Line" in result
        assert "break" in result
        assert "<br" not in result

    def test_html_entities(self):
        assert strip_html_tags("A &amp; B") == "A & B"
        assert strip_html_tags("It&rsquo;s") == "It's" or "It" in strip_html_tags("It&rsquo;s")

    def test_empty_string(self):
        assert strip_html_tags("") == ""
        assert strip_html_tags(None) == ""

    def test_only_tags(self):
        result = strip_html_tags("<p></p><br/>")
        assert result == ""

    def test_whitespace_cleanup(self):
        result = strip_html_tags("  Hello   World  ")
        assert result == "Hello World"


class TestCleanTitle:
    def test_basic(self):
        assert clean_title("  Hello World  ") == "Hello World"

    def test_html_in_title(self):
        assert clean_title("<b>Breaking News</b>") == "Breaking News"

    def test_empty(self):
        assert clean_title("") == ""
        assert clean_title(None) == ""


class TestCleanSummary:
    def test_truncation(self):
        long_text = "A" * 600
        result = clean_summary(long_text, max_length=100)
        assert len(result) <= 101  # 100 + "…"
        assert result.endswith("…")

    def test_short_summary(self):
        assert clean_summary("Short", max_length=100) == "Short"

    def test_html_in_summary(self):
        result = clean_summary("<p>Summary text</p>", max_length=100)
        assert "<" not in result


# ──────────────────────────────────────────────
# 有效性校验
# ──────────────────────────────────────────────

class TestIsValidUrl:
    def test_valid_http(self):
        assert is_valid_url("http://example.com") is True

    def test_valid_https(self):
        assert is_valid_url("https://example.com/article") is True

    def test_empty(self):
        assert is_valid_url("") is False
        assert is_valid_url(None) is False

    def test_no_scheme(self):
        assert is_valid_url("example.com") is False

    def test_ftp(self):
        assert is_valid_url("ftp://example.com") is False

    def test_localhost(self):
        assert is_valid_url("http://localhost:8080") is True


class TestIsValidTitle:
    def test_valid(self):
        assert is_valid_title("Hello") is True

    def test_too_short(self):
        assert is_valid_title("A") is False

    def test_empty(self):
        assert is_valid_title("") is False
        assert is_valid_title(None) is False

    def test_whitespace_only(self):
        assert is_valid_title("   ") is False


# ──────────────────────────────────────────────
# 去重逻辑
# ──────────────────────────────────────────────

class TestNormalizeTitleForDedup:
    def test_lowercase(self):
        assert normalize_title_for_dedup("Hello World") == "helloworld"

    def test_remove_punctuation(self):
        assert normalize_title_for_dedup("Hello, World!") == "helloworld"

    def test_remove_html(self):
        assert normalize_title_for_dedup("<b>Hello</b>") == "hello"

    def test_similar_titles(self):
        t1 = normalize_title_for_dedup("AI技术新突破！")
        t2 = normalize_title_for_dedup("AI技术新突破")
        assert t1 == t2


class TestTitleHash:
    def test_same_title_same_hash(self):
        h1 = title_hash("Hello")
        h2 = title_hash("Hello")
        assert h1 == h2

    def test_different_titles_different_hash(self):
        h1 = title_hash("Hello")
        h2 = title_hash("World")
        assert h1 != h2

    def test_similar_titles_same_hash(self):
        h1 = title_hash("AI突破!")
        h2 = title_hash("AI突破")
        assert h1 == h2


class TestUrlCanonical:
    def test_lowercase(self):
        assert url_canonical("https://Example.COM/Path") == "https://example.com/path"

    def test_trailing_slash(self):
        assert url_canonical("https://example.com/path/") == "https://example.com/path"

    def test_remove_tracking_params(self):
        result = url_canonical("https://example.com/page?utm_source=foo&id=1")
        assert "utm_source" not in result
        assert "id=1" in result

    def test_empty(self):
        assert url_canonical("") == ""
        assert url_canonical(None) == ""


class TestIsDuplicateByUrl:
    def test_not_duplicate(self):
        assert is_duplicate_by_url("https://example.com/new", {"https://example.com/old"}) is False

    def test_duplicate(self):
        assert is_duplicate_by_url("https://example.com/", {"https://example.com"}) is True

    def test_empty_url(self):
        assert is_duplicate_by_url("", {"https://example.com"}) is False


class TestIsDuplicateByTitle:
    def test_not_duplicate(self):
        existing = {title_hash("Old Title")}
        assert is_duplicate_by_title("New Title", existing) is False

    def test_duplicate(self):
        existing = {title_hash("Same Title")}
        assert is_duplicate_by_title("Same Title", existing) is True

    def test_empty_title(self):
        assert is_duplicate_by_title("", {"abc"}) is False


# ──────────────────────────────────────────────
# 清洗流水线
# ──────────────────────────────────────────────

class TestCleanArticles:
    def test_clean_valid_entries(self):
        entries = [
            {
                "title": "Valid Article",
                "link": "https://example.com/1",
                "summary": "A good summary",
            },
        ]
        result = clean_articles(entries)
        assert len(result) == 1
        assert result[0]["title"] == "Valid Article"
        assert result[0]["url"] == "https://example.com/1"

    def test_skip_empty_title(self):
        entries = [
            {"title": "", "link": "https://example.com/1"},
            {"title": "Valid", "link": "https://example.com/2"},
        ]
        result = clean_articles(entries)
        assert len(result) == 1

    def test_skip_invalid_url(self):
        entries = [
            {"title": "No URL", "link": ""},
            {"title": "Bad URL", "link": "not-a-url"},
            {"title": "Good", "link": "https://example.com"},
        ]
        result = clean_articles(entries)
        assert len(result) == 1

    def test_html_in_title_cleaned(self):
        entries = [
            {"title": "<b>Bold Title</b>", "link": "https://example.com/1", "summary": ""},
        ]
        result = clean_articles(entries)
        assert result[0]["title"] == "Bold Title"

    def test_summary_html_cleaned(self):
        entries = [
            {"title": "Test", "link": "https://example.com/1", "summary": "<p>Summary</p>"},
        ]
        result = clean_articles(entries)
        assert "<" not in result[0]["summary"]


class TestDeduplicateArticles:
    def test_no_duplicates(self):
        articles = [
            {"title": "A", "url": "https://example.com/a"},
            {"title": "B", "url": "https://example.com/b"},
        ]
        unique, stats = deduplicate_articles(articles)
        assert len(unique) == 2
        assert stats["kept"] == 2

    def test_url_duplicate(self):
        articles = [
            {"title": "A", "url": "https://example.com/same"},
            {"title": "B", "url": "https://example.com/same"},
        ]
        unique, stats = deduplicate_articles(articles)
        assert len(unique) == 1
        assert stats["url_dup"] == 1

    def test_title_duplicate(self):
        articles = [
            {"title": "Same Title", "url": "https://example.com/a"},
            {"title": "Same Title", "url": "https://example.com/b"},
        ]
        unique, stats = deduplicate_articles(articles)
        assert len(unique) == 1
        assert stats["title_dup"] == 1

    def test_existing_urls(self):
        articles = [
            {"title": "New", "url": "https://example.com/new"},
        ]
        existing_urls = {"https://example.com/new"}
        unique, stats = deduplicate_articles(articles, existing_urls=existing_urls)
        assert len(unique) == 0
        assert stats["url_dup"] == 1

    def test_existing_hashes(self):
        articles = [
            {"title": "Old Title", "url": "https://example.com/new"},
        ]
        existing_hashes = {title_hash("Old Title")}
        unique, stats = deduplicate_articles(articles, existing_title_hashes=existing_hashes)
        assert len(unique) == 0
        assert stats["title_dup"] == 1


class TestProcessRssPipeline:
    def test_full_pipeline(self):
        entries = [
            {
                "title": "Good Article",
                "link": "https://example.com/1",
                "summary": "Summary text",
            },
            {
                "title": "Good Article",  # duplicate title
                "link": "https://example.com/2",
                "summary": "Another summary",
            },
            {
                "title": "",  # empty title
                "link": "https://example.com/3",
                "summary": "",
            },
        ]
        articles, stats = process_rss_pipeline(entries)
        assert stats["raw_count"] == 3
        assert stats["cleaned_count"] == 2  # empty title skipped
        assert stats["unique_count"] == 1   # one title duplicate removed
        assert len(articles) == 1


class TestExtractExistingDataFromDb:
    def test_extraction(self):
        articles = [
            {"title": "Article 1", "url": "https://example.com/1"},
            {"title": "Article 2", "url": "https://example.com/2"},
        ]
        urls, hashes = extract_existing_data_from_db(articles)
        assert len(urls) == 2
        assert len(hashes) == 2
        assert title_hash("Article 1") in hashes
