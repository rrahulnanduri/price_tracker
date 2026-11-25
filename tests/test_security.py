"""Defences from the OWASP audit: trusted hosts, optional API token, resource caps, safe links."""

import asyncio
import dataclasses

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import REGIONS
from backend.matching import Offer, safe_url
from backend.providers.comparison import kieskeurig_products, schema_offers
from backend.providers.google_shopping import _find_link
from backend.search import RateLimiter, SearchService

from .conftest import offer


def test_foreign_host_header_is_refused(client):
    # A DNS-rebinding page reaches the API with its own host name in the Host header.
    assert client.get("/api/watchlist", headers={"Host": "attacker.example:8000"}).status_code == 400
    assert client.get("/api/watchlist", headers={"Host": "localhost:8000"}).status_code == 200


def test_api_token_required_when_set(settings, provider):
    with TestClient(create_app(dataclasses.replace(settings, api_token="s3cret"), provider)) as c:
        assert c.get("/api/watchlist").status_code == 401
        assert c.get("/api/watchlist", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/watchlist", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        assert c.get("/health").status_code == 200   # liveness checks need no token
        # CORS preflight carries no credentials and must still succeed.
        preflight = c.options("/api/watchlist", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type"})
        assert preflight.status_code == 200


def test_watchlist_is_capped(settings, provider):
    with TestClient(create_app(dataclasses.replace(settings, max_watches=2), provider)) as c:
        assert c.post("/api/watchlist", json={"product": "one", "country": "US"}).status_code == 201
        assert c.post("/api/watchlist", json={"product": "two", "country": "US"}).status_code == 201
        assert c.post("/api/watchlist", json={"product": "three", "country": "US"}).status_code == 409
        # Updating an existing entry's target is still allowed when full.
        res = c.post("/api/watchlist", json={"product": "one", "country": "US", "target_price": 5})
        assert res.status_code == 201 and res.json()["target_price"] == 5


def test_history_product_length_is_limited(client):
    assert client.get("/api/history", params={"product": "a" * 201}).status_code == 422


def test_unsafe_offer_urls_are_dropped():
    for bad in ("javascript:alert(1)", " JavaScript:alert(1)", "java\tscript:alert(1)",
                "data:text/html,<script>", "//evil.example/x", "/relative", "https://"):
        assert safe_url(bad) == "", bad
        assert Offer("S", "T", 1, "$1", bad).url == ""
    assert safe_url("https://shop.example/p?id=1") == "https://shop.example/p?id=1"


def test_scraped_javascript_links_never_reach_offers():
    html = ('<script type="application/ld+json">{"@type":"Product","name":"Widget Pro","offers":'
            '{"@type":"Offer","seller":{"name":"Shop"},"price":"10","priceCurrency":"EUR",'
            '"url":"javascript:alert(document.domain)"}}</script>')
    assert schema_offers(html, REGIONS["NL"], base_url="https://www.kieskeurig.nl/x")[0].url == ""


class _Anchor:
    def __init__(self, href):
        self.attrib = {"href": href}


class _Card:
    def __init__(self, *hrefs):
        self._anchors = [_Anchor(h) for h in hrefs]

    def find_all(self, tag):
        return self._anchors


def test_google_card_skips_unsafe_links():
    assert _find_link(_Card("javascript:alert(1)", "https://shop.example/p")) == "https://shop.example/p"
    assert _find_link(_Card("javascript:alert(1)")) == ""


def test_kieskeurig_ignores_links_to_other_hosts():
    html = ('<a href="//evil.example/x/product/1-widget-pro">Widget Pro</a>'
            '<a href="/tv/product/2-widget-pro">Widget Pro</a>'
            '<a href="https://www.kieskeurig.be/tv/product/3-widget-pro">Widget Pro</a>')
    urls = [url for _, url in kieskeurig_products(html, "https://www.kieskeurig.nl/search?q=widget")]
    assert urls == ["https://www.kieskeurig.nl/tv/product/2-widget-pro",
                    "https://www.kieskeurig.be/tv/product/3-widget-pro"]


def test_rate_limiter_forgets_idle_clients():
    now = [0.0]
    limiter = RateLimiter(5, clock=lambda: now[0])
    for i in range(RateLimiter.SWEEP_AT):
        limiter.check(f"10.0.{i // 256}.{i % 256}")
    now[0] += RateLimiter.WINDOW_SECONDS
    limiter.check("fresh")
    assert limiter.tracked_clients() == 1


def test_search_cache_is_bounded(settings, provider, tmp_path, monkeypatch):
    from backend.storage import Storage

    monkeypatch.setattr(SearchService, "MAX_CACHED", 3)
    service = SearchService(settings, provider, Storage(str(tmp_path / "c.db")))

    async def run():
        for i in range(5):
            provider.offers = [offer("Shop A", 20, title=f"Thing {i}")]
            await service.search(f"thing {i}", REGIONS["US"])

    asyncio.run(run())
    assert len(service._cache) == 3
    assert ("thing 4", "US") in service._cache and ("thing 0", "US") not in service._cache
