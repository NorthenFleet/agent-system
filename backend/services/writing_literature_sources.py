"""External scholarly metadata adapters with cache, throttling, and fail-soft health."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx


SUPPORTED_PROVIDERS = {"semantic_scholar", "crossref"}


class LiteratureSourceError(RuntimeError):
    pass


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _title(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _year_from_parts(value: Any) -> int | None:
    try:
        parts = value.get("date-parts") or []
        return int(parts[0][0]) if parts and parts[0] else None
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def _canonical_key(doi: str, title: str, year: int | None) -> str:
    normalized_doi = doi.strip().lower()
    if normalized_doi:
        return f"doi:{normalized_doi}"
    normalized_title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())
    return f"title:{normalized_title}:{year or 0}"


class ExternalLiteratureRegistry:
    def __init__(
        self,
        *,
        cache_root: str | Path | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        cache_ttl_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self.cache_root = Path(cache_root or os.getenv(
            "WRITING_LITERATURE_CACHE_ROOT",
            str(Path(__file__).resolve().parents[1] / "data" / "writing_literature_cache"),
        ))
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
        self.sleep = sleep
        self.clock = clock
        self.cache_ttl_seconds = max(60, int(cache_ttl_seconds))
        self._lock = threading.Lock()
        self._last_request_at: dict[str, float] = {}

    def _cache_path(self, provider: str, fingerprint: str) -> Path:
        return self.cache_root / provider / f"{fingerprint}.json"

    def _read_cache(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(cached.get("fetched_at_epoch") or 0)
            if self.clock() - fetched_at > self.cache_ttl_seconds:
                return None
            return cached
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _throttle(self, provider: str, minimum_interval: float) -> None:
        with self._lock:
            now = self.clock()
            wait = max(0.0, minimum_interval - (now - self._last_request_at.get(provider, 0.0)))
            if wait:
                self.sleep(wait)
                now = self.clock()
            self._last_request_at[provider] = now

    def _request_json(
        self,
        provider: str,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        minimum_interval: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        request_identity = {"provider": provider, "url": url, "params": params}
        request_fingerprint = _fingerprint(request_identity)
        cache_path = self._cache_path(provider, request_fingerprint)
        cached = self._read_cache(cache_path)
        if cached:
            return dict(cached.get("response") or {}), {
                "cache_hit": True,
                "request_fingerprint": request_fingerprint,
                "cache_path": str(cache_path.resolve()),
            }

        last_error = ""
        for attempt in range(3):
            self._throttle(provider, minimum_interval)
            try:
                response = self.client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                if attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                break
            if response.status_code == 200:
                payload = response.json()
                self._write_cache(cache_path, {
                    "schema": "writing.external_literature_cache.v1",
                    "provider": provider,
                    "request": request_identity,
                    "request_fingerprint": request_fingerprint,
                    "fetched_at_epoch": self.clock(),
                    "response_sha256": _fingerprint(payload),
                    "response": payload,
                })
                return payload, {
                    "cache_hit": False,
                    "request_fingerprint": request_fingerprint,
                    "cache_path": str(cache_path.resolve()),
                    "rate_limit_limit": response.headers.get("x-rate-limit-limit", ""),
                    "rate_limit_interval": response.headers.get("x-rate-limit-interval", ""),
                }
            last_error = f"HTTP {response.status_code}"
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            retry_after = response.headers.get("retry-after", "")
            try:
                wait = min(float(retry_after), 30.0) if retry_after else float(2 ** attempt)
            except ValueError:
                wait = float(2 ** attempt)
            self.sleep(wait)
        raise LiteratureSourceError(f"{provider} 请求失败：{last_error or 'unknown error'}")

    def _semantic_scholar(
        self,
        query: str,
        *,
        limit: int,
        year_from: int,
        year_to: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fields = "paperId,title,authors,year,venue,abstract,url,externalIds,openAccessPdf,publicationTypes"
        headers = {"User-Agent": "3021-literature-research/1.0"}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        if api_key:
            headers["x-api-key"] = api_key
        payload, request_meta = self._request_json(
            "semantic_scholar",
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": limit,
                "offset": 0,
                "year": f"{year_from}-{year_to}",
                "fields": fields,
            },
            headers=headers,
            minimum_interval=1.0,
        )
        candidates = []
        for rank, item in enumerate(payload.get("data") or [], start=1):
            title = _title(item.get("title"))
            paper_id = str(item.get("paperId") or "").strip()
            if not title or not paper_id:
                continue
            external_ids = item.get("externalIds") or {}
            doi = str(external_ids.get("DOI") or "").strip().lower()
            abstract = str(item.get("abstract") or "")
            year = int(item["year"]) if item.get("year") else None
            candidates.append({
                "provider": "semantic_scholar",
                "provider_record_id": paper_id,
                "title": title,
                "authors": [str(author.get("name") or "") for author in item.get("authors") or [] if author.get("name")],
                "year": year,
                "venue": str(item.get("venue") or ""),
                "doi": doi,
                "url": str(item.get("url") or ""),
                "abstract_snapshot": abstract,
                "access_status": "abstract" if abstract else "metadata_only",
                "retrieval_score": round(max(0.0, 1.0 - (rank - 1) * 0.03), 4),
                "rank": rank,
                "canonical_key": _canonical_key(doi, title, year),
                "metadata_snapshot": {
                    "provider_payload": item,
                    "request_fingerprint": request_meta["request_fingerprint"],
                    "cache_path": request_meta["cache_path"],
                },
            })
        return candidates, {**request_meta, "status": "ready", "results": len(candidates)}

    def _crossref(
        self,
        query: str,
        *,
        limit: int,
        year_from: int,
        year_to: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        mailto = os.getenv("CROSSREF_MAILTO", "").strip()
        user_agent = "3021-literature-research/1.0"
        if mailto:
            user_agent += f" (mailto:{mailto})"
        params: dict[str, Any] = {
            "query.bibliographic": query,
            "rows": limit,
            "filter": f"from-pub-date:{year_from}-01-01,until-pub-date:{year_to}-12-31",
        }
        if mailto:
            params["mailto"] = mailto
        payload, request_meta = self._request_json(
            "crossref",
            "https://api.crossref.org/v1/works",
            params=params,
            headers={"User-Agent": user_agent},
            minimum_interval=0.12 if mailto else 0.22,
        )
        candidates = []
        for rank, item in enumerate((payload.get("message") or {}).get("items") or [], start=1):
            title = _title(item.get("title"))
            doi = str(item.get("DOI") or "").strip().lower()
            if not title or not doi:
                continue
            year = (
                _year_from_parts(item.get("published-print"))
                or _year_from_parts(item.get("published-online"))
                or _year_from_parts(item.get("published"))
                or _year_from_parts(item.get("issued"))
            )
            authors = []
            for author in item.get("author") or []:
                name = " ".join(part for part in (
                    str(author.get("given") or "").strip(),
                    str(author.get("family") or "").strip(),
                ) if part)
                if name:
                    authors.append(name)
            abstract = str(item.get("abstract") or "")
            candidates.append({
                "provider": "crossref",
                "provider_record_id": doi,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": _title(item.get("container-title")),
                "doi": doi,
                "url": str(item.get("URL") or ""),
                "abstract_snapshot": abstract,
                "access_status": "abstract" if abstract else "metadata_only",
                "retrieval_score": round(max(0.0, 1.0 - (rank - 1) * 0.03), 4),
                "rank": rank,
                "canonical_key": _canonical_key(doi, title, year),
                "metadata_snapshot": {
                    "provider_payload": item,
                    "request_fingerprint": request_meta["request_fingerprint"],
                    "cache_path": request_meta["cache_path"],
                },
            })
        return candidates, {**request_meta, "status": "ready", "results": len(candidates)}

    def search(
        self,
        *,
        providers: list[str],
        query: str,
        limit: int,
        year_from: int,
        year_to: int,
        request_budget: int = 2,
    ) -> dict[str, Any]:
        selected = [provider for provider in providers if provider in SUPPORTED_PROVIDERS]
        candidates: list[dict[str, Any]] = []
        health: dict[str, Any] = {}
        remaining = max(0, int(request_budget))
        for provider in selected:
            if remaining <= 0:
                health[provider] = {"status": "budget_exhausted", "results": 0}
                continue
            remaining -= 1
            try:
                if provider == "semantic_scholar":
                    provider_candidates, provider_health = self._semantic_scholar(
                        query, limit=limit, year_from=year_from, year_to=year_to
                    )
                else:
                    provider_candidates, provider_health = self._crossref(
                        query, limit=limit, year_from=year_from, year_to=year_to
                    )
                candidates.extend(provider_candidates)
                health[provider] = provider_health
            except (LiteratureSourceError, httpx.HTTPError, ValueError, TypeError) as exc:
                health[provider] = {
                    "status": "degraded",
                    "results": 0,
                    "reason": str(exc)[:500],
                }
        return {
            "candidates": candidates,
            "health": health,
            "request_budget": int(request_budget),
            "requests_used": int(request_budget) - remaining,
        }


external_literature_registry = ExternalLiteratureRegistry()
