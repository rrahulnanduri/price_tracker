"""Wider coverage: comparison sites, the every-seller lookup, and pooling sources."""

import asyncio
import dataclasses
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import REGIONS
from backend.matching import Offer, rank_offers, store_key
from backend.providers import comparison
from backend.providers.base import ProviderBlocked, ProviderError, ProviderNotConfigured
from backend.providers.comparison import (
    SiteProvider,
    kieskeurig_products,
    schema_offers,
    sites_for,
    staticice_offers,
)
from backend.providers.multi import MultiProvider
from backend.providers.serpapi import SerpApiProvider, parse_stores

from .conftest import offer

FIXTURES = Path(__file__).parent / "fixtures"
NL, AU, US = REGIONS["NL"], REGIONS["AU"], REGIONS["US"]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# -- generic schema.org offers ---------------------------------------------------

def test_schema_offers_reads_every_seller_from_a_real_product_page():
    offers = schema_offers(fixture("kieskeurig_product.html"), NL,
                           base_url="https://www.kieskeurig.nl/consoles/product/13733869", source="kieskeurig")
    assert [(o.store, o.price) for o in offers] == [
        ("NEDGAME", 318.0), ("AMAZON", 319.07), ("ALIEXPRESS.COM", 321.52), ("COOLBLUE.NL", 324.0),
        ("MEDIAMARKT.NL", 324.0), ("BOL.", 334.0), ("NINTENDO STORE", 349.99), ("KAUFLAND", 411.22),
    ]
    first = offers[0]
    assert first.title == "Nintendo Switch OLED Wit" and first.shipping_cost == 0 and first.in_stock is True
    assert first.url == "https://www.kieskeurig.nl/product-clickout/13733869/4611" and first.source == "kieskeurig"


def test_schema_offers_handles_other_shapes():
    page = """<script type="application/ld+json">{"@graph": [{"@type": ["Product"], "name": "Widget 3000",
      "offers": {"@type": "Offer", "price": "19.99", "priceCurrency": "EUR", "seller": "Shop A",
                 "availability": "https://schema.org/OutOfStock", "itemCondition": "https://schema.org/UsedCondition"}}]}
      </script><script type="application/ld+json">{"@type": "Product", "name": "Widget 3000",
      "offers": {"@type": "Offer", "price": 25, "priceCurrency": "USD", "seller": {"name": "Wrong currency"}}}</script>
      <script type="application/ld+json">not json</script>"""
    offers = schema_offers(page, NL)
    assert [(o.store, o.price, o.in_stock, o.title) for o in offers] == [
        ("SHOP A", 19.99, False, "Widget 3000 (used)"),
    ]


# -- sites ---------------------------------------------------------------------

def test_kieskeurig_products_titles_from_slugs():
    products = kieskeurig_products(fixture("kieskeurig_search.html"), "https://www.kieskeurig.nl/search?q=x")
    titles = {title for title, _ in products}
    assert "nintendo switch oled wit" in titles and "Bekijk product" not in titles
    assert all(url.startswith("https://www.kieskeurig.nl/") for _, url in products)


def test_staticice_rows_link_straight_to_shops():
    offers = staticice_offers(fixture("staticice_search.html"), "", "nintendo switch oled", AU)
    assert len(offers) == 8
    officeworks = next(o for o in offers if o.store == "OFFICEWORKS")
    assert officeworks.price == 538.0 and officeworks.title == "Nintendo Switch OLED Model White"
    assert officeworks.url.startswith("https://www.officeworks.com.au/") and "redirect.cgi" not in officeworks.url
    ranked, _ = rank_offers("nintendo switch oled", offers)
    assert {o.store for o in ranked} == {"MWAVE AUSTRALIA", "OFFICEWORKS", "JB HI-FI"}   # cases dropped


def test_sites_cover_nl_be_au_only():
    assert {s.name for s in sites_for(NL)} == {"kieskeurig"}
    assert sites_for(REGIONS["BE"])[0].search_url.startswith("https://www.kieskeurig.be/")
    assert {s.name for s in sites_for(AU)} == {"staticice"}
    assert sites_for(US) == []


def mock_client(routes: dict[str, tuple[int, str]], seen: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.headers["User-Agent"].startswith("PriceTracker/")
        for prefix, (status, body) in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(status, text=body)
        return httpx.Response(404, text="")

    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     headers={"User-Agent": comparison.USER_AGENT})


def test_site_provider_opens_best_matching_product_pages(monkeypatch):
    monkeypatch.setattr(comparison, "POLITE_DELAY_SECONDS", 0)
    seen: list[str] = []
    routes = {
        "https://www.kieskeurig.nl/search": (200, fixture("kieskeurig_search.html")),
        "https://www.kieskeurig.nl/consoles/product/13733869": (200, fixture("kieskeurig_product.html")),
        "https://www.kieskeurig.nl/consoles/product/": (200, "<html></html>"),
    }
    provider = SiteProvider(sites_for(NL)[0], client_factory=mock_client(routes, seen))
    offers = asyncio.run(provider.search("nintendo switch oled", NL))

    assert seen[0] == "https://www.kieskeurig.nl/search?q=nintendo+switch+oled"
    assert len(seen) == 1 + comparison.PRODUCT_PAGES_PER_SITE
    assert all("/product/" in url and "case" not in url and "hoesje" not in url for url in seen[1:])
    assert {o.store for o in offers} >= {"NEDGAME", "COOLBLUE.NL"}


def test_site_provider_reports_refusals(monkeypatch):
    provider = SiteProvider(sites_for(NL)[0], client_factory=mock_client(
        {"https://www.kieskeurig.nl/": (403, "no")}, []))
    with pytest.raises(ProviderBlocked):
        asyncio.run(provider.search("x", NL))


# -- every seller via SerpApi ----------------------------------------------------

STORES_PAYLOAD = {"product_results": {"stores": [
    {"name": "Walmart", "title": "PlayStation 5 Slim", "price": "$449.00", "extracted_price": 449.0,
     "shipping": "+ $6.99", "shipping_extracted": 6.99, "link": "https://walmart.com/p",
     "details_and_offers": ["In stock online"]},
    {"name": "GameStop", "price": "$459.99", "link": "https://gamestop.com/p", "shipping": "Free shipping"},
    {"name": "No price"},
]}}


def test_parse_stores():
    offers = parse_stores(STORES_PAYLOAD, US, "PlayStation 5")
    assert [(o.store, o.price, o.shipping_cost, o.in_stock, o.title) for o in offers] == [
        ("WALMART", 449.0, 6.99, True, "PlayStation 5 Slim"),
        ("GAMESTOP", 459.99, 0.0, None, "PlayStation 5"),
    ]


def test_seller_lookup_opens_best_matching_product_pages(monkeypatch):
    calls = []

    async def fake_call(self, client, params):
        calls.append(params)
        if params["engine"] == "google_shopping":
            return {"shopping_results": [
                {"title": "PS5 DualSense Controller", "source": "Amazon", "price": "$69.00",
                 "immersive_product_page_token": "controller"},
                {"title": "Sony PlayStation 5 Slim Console", "source": "Best Buy", "price": "$499.99",
                 "immersive_product_page_token": "console"},
            ]}
        return STORES_PAYLOAD

    monkeypatch.setattr(SerpApiProvider, "_call", fake_call)
    offers = asyncio.run(SerpApiProvider("key", seller_lookups=2).search("playstation 5 console", US))
    assert [c["page_token"] for c in calls if c["engine"] == "google_immersive_product"] == ["console"]
    assert {o.store for o in offers} == {"AMAZON", "BEST BUY", "WALMART", "GAMESTOP"}

    calls.clear()
    asyncio.run(SerpApiProvider("key", seller_lookups=0).search("playstation 5 console", US))
    assert [c["engine"] for c in calls] == ["google_shopping"]


# -- pooling sources -------------------------------------------------------------

class Source:
    def __init__(self, name, offers=None, error=None):
        self.name, self.offers, self.error = name, offers or [], error

    async def search(self, product, region):
        if self.error:
            raise self.error
        return [dataclasses.replace(o) for o in self.offers]


def test_multi_provider_pools_sources_and_reports_failures():
    multi = MultiProvider(
        Source("google", error=ProviderBlocked("Google is rate-limiting this address.")),
        lambda region: [Source("kieskeurig", [offer("Nedgame.nl", 318), offer("Coolblue", 324)]),
                        Source("other", error=RuntimeError("boom"))],
    )
    offers, reports = asyncio.run(multi.search_with_report("acme widget 3000", NL))
    assert [o.source for o in offers] == ["kieskeurig", "kieskeurig"]
    assert [r.to_dict() for r in reports] == [
        {"name": "google", "ok": False, "offers": 0, "error": "Google is rate-limiting this address."},
        {"name": "kieskeurig", "ok": True, "offers": 2, "error": None},
        {"name": "other", "ok": False, "offers": 0, "error": "failed"},
    ]


def test_multi_provider_fails_only_when_every_source_fails():
    multi = MultiProvider(Source("google", error=ProviderError("x")),
                          lambda region: [Source("site", error=ProviderBlocked("blocked"))])
    with pytest.raises(ProviderBlocked):
        asyncio.run(multi.search("x", NL))
    with pytest.raises(ProviderNotConfigured):
        asyncio.run(MultiProvider(None, lambda region: []).search("x", US))


def test_same_shop_from_two_sources_is_listed_once_at_its_cheapest():
    assert store_key("Nedgame.nl") == store_key("NEDGAME") == store_key("www.nedgame.nl") == "nedgame"
    offers = [offer("Nedgame.nl", 320), offer("NEDGAME", 318), offer("Coolblue", 324)]
    ranked, _ = rank_offers("acme widget 3000", offers)
    assert [(o.store, o.price) for o in ranked] == [("NEDGAME", 318), ("COOLBLUE", 324)]


def test_search_api_lists_sources(settings):
    multi = MultiProvider(Source("google", error=ProviderBlocked("blocked")),
                          lambda region: [Source("kieskeurig", [offer("Shop A", 20)])])
    with TestClient(create_app(settings, multi)) as client:
        body = client.post("/api/search", json={"product": "acme widget 3000", "country": "NL"}).json()
    assert [(s["name"], s["ok"]) for s in body["sources"]] == [("google", False), ("kieskeurig", True)]
    assert body["results"][0]["source"] == "kieskeurig"


def test_search_api_single_source_reports_itself(client):
    body = client.post("/api/search", json={"product": "acme widget 3000"}).json()
    assert body["sources"] == [{"name": "fake", "ok": True, "offers": 3, "error": None}]
    assert {r["source"] for r in body["results"]} == {"fake"}


def test_results_are_not_capped_at_eight(settings, provider):
    provider.offers = [offer(f"Shop {i}", 100 + i) for i in range(12)]
    with TestClient(create_app(dataclasses.replace(settings, max_results=50), provider)) as client:
        body = client.post("/api/search", json={"product": "acme widget 3000"}).json()
    assert len(body["results"]) == 12


def test_offer_dict_includes_source():
    assert Offer("A", "t", 1.0, "$1", source="kieskeurig").to_dict()["source"] == "kieskeurig"
