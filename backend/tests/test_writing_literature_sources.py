import httpx

from services.writing_literature_sources import ExternalLiteratureRegistry


def test_external_registry_normalizes_and_caches_provider_results(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "api.semanticscholar.org":
            return httpx.Response(200, json={
                "total": 1,
                "data": [{
                    "paperId": "paper-1",
                    "title": "Dynamic Authority Allocation",
                    "authors": [{"name": "Researcher A"}],
                    "year": 2025,
                    "venue": "Systems",
                    "abstract": "Authority changes with workload and communications.",
                    "url": "https://www.semanticscholar.org/paper/paper-1",
                    "externalIds": {"DOI": "10.1000/example.1"},
                    "openAccessPdf": None,
                    "publicationTypes": ["JournalArticle"],
                }],
            })
        return httpx.Response(200, json={
            "status": "ok",
            "message": {
                "items": [{
                    "DOI": "10.1000/example.1",
                    "title": ["Dynamic Authority Allocation"],
                    "author": [{"given": "Researcher", "family": "A"}],
                    "published": {"date-parts": [[2025, 2, 1]]},
                    "container-title": ["Systems"],
                    "URL": "https://doi.org/10.1000/example.1",
                    "type": "journal-article",
                }]
            },
        })

    registry = ExternalLiteratureRegistry(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=lambda: 1000.0,
    )
    payload = {
        "providers": ["semantic_scholar", "crossref"],
        "query": "dynamic authority allocation",
        "limit": 5,
        "year_from": 2020,
        "year_to": 2026,
        "request_budget": 2,
    }
    result = registry.search(**payload)

    assert len(result["candidates"]) == 2
    assert {item["provider"] for item in result["candidates"]} == {
        "semantic_scholar", "crossref"
    }
    assert {item["canonical_key"] for item in result["candidates"]} == {
        "doi:10.1000/example.1"
    }
    assert result["health"]["semantic_scholar"]["status"] == "ready"
    assert result["health"]["crossref"]["status"] == "ready"
    assert len(calls) == 2

    cached = registry.search(**payload)
    assert len(cached["candidates"]) == 2
    assert cached["health"]["semantic_scholar"]["cache_hit"] is True
    assert cached["health"]["crossref"]["cache_hit"] is True
    assert len(calls) == 2


def test_external_registry_degrades_one_provider_without_raising(tmp_path):
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"})

    registry = ExternalLiteratureRegistry(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=lambda: 1000.0,
    )
    result = registry.search(
        providers=["semantic_scholar"],
        query="mission command",
        limit=5,
        year_from=2020,
        year_to=2026,
        request_budget=1,
    )

    assert result["candidates"] == []
    assert result["health"]["semantic_scholar"]["status"] == "degraded"
    assert attempts == 3


def test_external_registry_respects_request_budget(tmp_path):
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"total": 0, "data": []})

    registry = ExternalLiteratureRegistry(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=lambda: 1000.0,
    )
    result = registry.search(
        providers=["semantic_scholar", "crossref"],
        query="mission command",
        limit=5,
        year_from=2020,
        year_to=2026,
        request_budget=1,
    )

    assert calls == 1
    assert result["health"]["crossref"]["status"] == "budget_exhausted"
