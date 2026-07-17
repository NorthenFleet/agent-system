"""Shared Crawl4AI adapter and configuration for dashboard agents."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_FILE = DATA_DIR / "web-crawler.json"
DEFAULT_CONFIG = {
    "enabled": True,
    "provider": "Crawl4AI",
    "repository": "https://github.com/unclecode/crawl4ai",
    "base_url": "http://127.0.0.1:11235",
    "scope": "global",
    "module_keys": ["*"],
    "agent_ids": ["*"],
    "allow_private_network": False,
    "request_timeout_seconds": 120,
    "max_content_chars": 250000,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WebCrawlerService:
    def get_config(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        config = {**DEFAULT_CONFIG, **data}
        config["base_url"] = os.getenv("CRAWL4AI_BASE_URL", config["base_url"]).rstrip("/")
        config["token_configured"] = bool(os.getenv("CRAWL4AI_TOKEN"))
        return config

    def save_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "enabled", "base_url", "scope", "module_keys", "agent_ids",
            "allow_private_network", "request_timeout_seconds", "max_content_chars",
        }
        current = self.get_config()
        for key in allowed:
            if key in updates:
                current[key] = updates[key]
        current.pop("token_configured", None)
        current["updated_at"] = _now()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get_config()

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = os.getenv("CRAWL4AI_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def status(self) -> dict[str, Any]:
        config = self.get_config()
        result = {
            "provider": config["provider"],
            "repository": config["repository"],
            "enabled": bool(config["enabled"]),
            "ready": False,
            "base_url": config["base_url"],
            "scope": config["scope"],
            "module_keys": config["module_keys"],
            "agent_ids": config["agent_ids"],
            "checked_at": _now(),
        }
        if not config["enabled"]:
            result["message"] = "网络采集工具已停用"
            return result
        try:
            response = requests.get(
                f"{config['base_url']}/health",
                headers=self._headers(),
                timeout=8,
            )
            result["ready"] = response.status_code < 400
            result["http_status"] = response.status_code
            result["message"] = "Crawl4AI 服务就绪" if result["ready"] else "Crawl4AI 服务异常"
        except requests.RequestException as exc:
            result["message"] = f"Crawl4AI 未连接: {exc}"
        return result

    def _validate_target(self, url: str, allow_private: bool) -> str:
        value = (url or "").strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("仅支持有效的 HTTP/HTTPS 地址")
        if allow_private:
            return value
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        except socket.gaierror as exc:
            raise ValueError(f"域名无法解析: {parsed.hostname}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("默认禁止抓取本机或内网地址")
        return value

    def crawl(self, url: str, query: str = "") -> dict[str, Any]:
        config = self.get_config()
        if not config["enabled"]:
            raise RuntimeError("网络采集工具已停用")
        target = self._validate_target(url, bool(config["allow_private_network"]))
        payload: dict[str, Any] = {"urls": [target]}
        if query.strip():
            payload["crawler_config"] = {
                "type": "CrawlerRunConfig",
                "params": {
                    "word_count_threshold": 10,
                    "markdown_generator": {
                        "type": "DefaultMarkdownGenerator",
                        "params": {
                            "content_filter": {
                                "type": "BM25ContentFilter",
                                "params": {"user_query": query.strip(), "bm25_threshold": 1.0},
                            }
                        },
                    },
                },
            }
        response = requests.post(
            f"{config['base_url']}/crawl",
            headers=self._headers(),
            json=payload,
            timeout=max(10, min(int(config["request_timeout_seconds"]), 600)),
        )
        if response.status_code >= 400:
            detail = response.text[:1200]
            raise RuntimeError(f"Crawl4AI 返回 {response.status_code}: {detail}")
        body = response.json()
        rows = body.get("results") if isinstance(body, dict) else None
        if not rows or not isinstance(rows, list):
            raise RuntimeError("Crawl4AI 未返回抓取结果")
        row = rows[0]
        markdown = row.get("markdown", "")
        if isinstance(markdown, dict):
            markdown = markdown.get("fit_markdown") or markdown.get("raw_markdown") or ""
        content = str(markdown or row.get("cleaned_html") or "")
        max_chars = max(1000, int(config["max_content_chars"]))
        return {
            "success": bool(row.get("success", True)),
            "url": row.get("url") or target,
            "title": (row.get("metadata") or {}).get("title", ""),
            "content": content[:max_chars],
            "content_length": len(content),
            "truncated": len(content) > max_chars,
            "links": row.get("links") or {},
            "media": row.get("media") or {},
            "status_code": row.get("status_code"),
            "error_message": row.get("error_message") or "",
            "provider": config["provider"],
            "crawled_at": _now(),
        }


web_crawler_service = WebCrawlerService()
