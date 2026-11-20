import asyncio
import dataclasses
from datetime import date, datetime, timedelta, timezone

import pytest

from backend import scheduler
from backend.config import REGIONS, get_region, load_settings
from backend.matching import Offer, detect_condition, rank_offers, score_relevance
from backend.pricing import parse_price
from backend.providers import build_provider
from backend.providers.base import ProviderBlocked, parse_shipping, parse_stock
from backend.providers.demo import DemoProvider
from backend.providers.google_shopping import (
    build_search_url,
    check_not_blocked,
    extract_offers,
    resolve_link,
)
from backend.providers.serpapi import parse_results
from backend.search import RateLimited, RateLimiter, SearchService
from backend.storage import Storage

from .conftest import offer

US, DE = REGIONS["US"], REGIONS["DE"]


# -- pricing -------------------------------------------------------------------

@pytest.mark.parametrize("text,currency,expected", [
    ("$12.99", "USD", (12.99, "USD")),
    ("1.299,00 €", "EUR", (1299.0, "EUR")),
    ("1.299 €", "EUR", (1299.0, "EUR")),
    ("₹1,50,000", "INR", (150000.0, "INR")),
    ("¥150,000", "JPY", (150000.0, "JPY")),
    ("AED 499", "AED", (499.0, "AED")),
    ("$1,299", "CAD", (1299.0, "CAD")),
    ("S$1,299.00", "USD", (1299.0, "SGD")),
    ("$449 2 offers", "USD", (449.0, "USD")),
    ("$0.10", "USD", None),
    ("", "USD", None),
    (None, "USD", None),
    ("free", "USD", None),
])
def test_parse_price(text, currency, expected):
    price = parse_price(text, currency)
    assert (price and (price.value, price.currency)) == expected


def test_shipping_and_stock_text():
    assert parse_shipping("Free delivery", "USD") == 0
    assert parse_shipping("+ $4.99 shipping", "USD") == 4.99
    assert parse_shipping("Delivery by Fri, Nov 14", "USD") is None
    assert parse_stock("Out of stock") is False
    assert parse_stock("In stock") is True
    assert parse_stock("4.5 stars") is None


# -- matching ------------------------------------------------------------------

@pytest.mark.parametrize("query,title,keep", [
    ("iphone 15", "Apple iPhone 15 128GB Black", True),
    ("iphone 15", "Apple iPhone 14 128GB", False),
    ("iphone 15", "Apple iPhone 15 Pro 128GB", False),
    ("iphone 15", "Spigen Case for iPhone 15", False),
    ("ps5", "Sony PlayStation 5 Slim Console", True),
    ("ps5", "Marvel's Spider-Man 2 - PlayStation 5", False),
    ("lg c4 65 oled", 'LG 65" C3 OLED evo 4K TV', False),
    ("sony wh-1000xm5", "Sony WF-1000XM5 Earbuds", False),
    ("apple watch series 9 45mm", "Apple Watch Series 9 45mm Aluminium Case with Sport Band", True),
    ("iphone 15 case", "Spigen Case for iPhone 15", True),
])
def test_score_relevance(query, title, keep):
    score, flags = score_relevance(query, title)
    assert (score >= 0.7) is keep, (score, flags)


def test_detect_condition():
    assert detect_condition("iPhone 13 (Renewed)") == "refurbished"
    assert detect_condition("PS5 Console - Used") == "used"
    assert detect_condition("PS5 Console") == "new"


def test_rank_offers_one_per_store_and_drops_outliers():
    offers = [
        offer("A", 500), offer("A", 480), offer("B", 510), offer("C", 495),
        offer("D", 40),                                  # far below the rest
        offer("E", 450, title="Acme Widget 3000 (Refurbished)"),
    ]
    ranked, rejected = rank_offers("acme widget 3000", offers)
    assert [(o.store, o.price) for o in ranked] == [("A", 480), ("C", 495), ("B", 510)]
    assert {o.store for o in rejected} == {"D", "E"}

    ranked, _ = rank_offers("refurbished acme widget 3000", offers)
    assert [o.store for o in ranked] == ["E"]


# -- providers -----------------------------------------------------------------

def test_get_region():
    assert get_region("de") is DE
    assert get_region("ZZ") is None and get_region(None) is None


def test_build_provider_selection():
    base = load_settings()
    pick = lambda **kw: build_provider(dataclasses.replace(base, **kw)).name  # noqa: E731
    assert pick(provider="auto", serpapi_key="") == "google+sites"
    assert pick(provider="auto", serpapi_key="k") == "serpapi+sites"
    assert pick(provider="auto", serpapi_key="k", comparison_sites=False) == "serpapi"
    assert pick(provider="sites") == "sites"
    assert pick(provider="demo") == "demo"     # made-up prices are never mixed with real ones
    with pytest.raises(ValueError):
        pick(provider="bing")
    with pytest.raises(ValueError):
        pick(provider="sites", comparison_sites=False)


def test_build_search_url_and_links():
    url = build_search_url("ps5 & controller", DE)
    assert "q=ps5+%26+controller" in url and "gl=de" in url and "hl=de" in url and "tbm=shop" in url
    assert resolve_link("/url?q=x&url=https%3A%2F%2Fshop.com%2Fp") == "https://shop.com/p"
    assert resolve_link("/url?q=https://shop.com/p&sa=U") == "https://shop.com/p"
    assert resolve_link("/shopping/product/1") == "https://www.google.com/shopping/product/1"
    assert resolve_link("https://shop.com/p") == "https://shop.com/p"


RESULTS_PAGE = """
<html><body><div id="rso">
  <div class="mnr-c"><a href="/url?url=https%3A%2F%2Fbestbuy.com%2Fps5"><h3>Sony PlayStation 5 Slim Console</h3></a>
    <div class="UsGWMe">Best Buy</div><span>$499.99</span><span>Free delivery</span></div>
  <div class="mnr-c"><a href="https://walmart.com/ps5"><h3>PlayStation 5 Digital Edition</h3></a>
    <div class="UsGWMe">Walmart</div><span>$449.00</span><span>+ $5.99 shipping</span><span>Out of stock</span></div>
  <div class="mnr-c"><a href="https://shop.de/ps5"><h3>PlayStation 5 Konsole</h3></a>
    <div class="UsGWMe">Shop DE</div><span>499,00 €</span></div>
  <div class="unknown-layout"><div><a href="https://target.com/ps5"><h3>PlayStation 5 Console Bundle</h3></a></div>
    <div><span>Target</span></div><div><span>$559.99</span></div></div>
  <p>Results priced from $1.00 are sponsored</p>
</div></body></html>
"""


def test_extract_offers_from_real_markup():
    pytest.importorskip("scrapling")
    from scrapling.parser import Selector

    offers = extract_offers(Selector(RESULTS_PAGE), US)
    by_store = {o.store: o for o in offers}
    assert set(by_store) == {"BEST BUY", "WALMART", "TARGET"}   # EUR offer and stray text skipped

    best_buy = by_store["BEST BUY"]
    assert best_buy.price == 499.99 and best_buy.url == "https://bestbuy.com/ps5"
    assert best_buy.title == "Sony PlayStation 5 Slim Console" and best_buy.shipping_cost == 0
    assert by_store["WALMART"].shipping_cost == 5.99 and by_store["WALMART"].in_stock is False
    # No known class on this card: found structurally.
    assert by_store["TARGET"].title == "PlayStation 5 Console Bundle" and by_store["TARGET"].price == 559.99


def test_block_pages_are_reported_not_parsed():
    class Page:
        status = 200
        url = "https://www.google.com/sorry/index?continue=..."
        html_content = "<html>Our systems have detected unusual traffic</html>"

    with pytest.raises(ProviderBlocked):
        check_not_blocked(Page())


def test_serpapi_results_are_parsed():
    payload = {"shopping_results": [
        {"title": "Apple iPhone 15", "source": "Apple", "price": "$729.00", "extracted_price": 729.0,
         "product_link": "https://google.com/p/1", "delivery": "Free delivery"},
        {"title": "Apple iPhone 15", "source": "Shop", "price": "", "extracted_price": 699,
         "link": "https://shop.com/p", "extensions": ["Out of stock"]},
        {"title": "No price", "source": "Shop"},
        {"title": "Euro offer", "source": "Shop EU", "price": "€700,00"},
    ]}
    offers = parse_results(payload, US)
    assert [(o.store, o.price, o.shipping_cost, o.in_stock) for o in offers] == [
        ("APPLE", 729.0, 0.0, None), ("SHOP", 699.0, None, False),
    ]
    assert offers[1].url == "https://shop.com/p"
    assert parse_results({}, US) == []


def test_demo_provider_is_deterministic_and_noisy():
    provider = DemoProvider(today=lambda: date(2026, 1, 1))
    first = asyncio.run(provider.search("acme widget 3000", US))
    again = asyncio.run(provider.search("Acme  Widget 3000", US))
    assert [(o.store, o.price) for o in first] == [(o.store, o.price) for o in again]
    ranked, rejected = rank_offers("acme widget 3000", first)
    assert len(ranked) == 6 and len(rejected) == 3     # case, cable and refurbished dropped
    assert asyncio.run(provider.search("nothing", US)) == []


def test_demo_links_are_real_store_searches():
    provider = DemoProvider(today=lambda: date(2026, 1, 1))
    for code, region in REGIONS.items():
        offers = asyncio.run(provider.search("ps5 & controller", region))
        assert offers, code
        for o in offers:
            assert o.url.startswith("https://") and "example.com" not in o.url, (code, o.url)
            assert "ps5" in o.url and " " not in o.url and "&controller" not in o.url, (code, o.url)
    nl = asyncio.run(provider.search("nintendo switch oled", REGIONS["NL"]))
    assert {o.store for o in nl} == {"BOL", "COOLBLUE", "MEDIAMARKT", "AMAZON.NL"}
    assert nl[0].url == "https://www.bol.com/nl/nl/s/?searchtext=nintendo+switch+oled"


# -- service -------------------------------------------------------------------

def test_rate_limiter_window():
    now = [0.0]
    limiter = RateLimiter(2, clock=lambda: now[0])
    limiter.check("a")
    limiter.check("a")
    limiter.check("b")                      # separate client, separate budget
    with pytest.raises(RateLimited) as blocked:
        limiter.check("a")
    assert 1 <= blocked.value.retry_after <= 61
    now[0] = 61
    limiter.check("a")
    RateLimiter(0).check("a")               # 0 disables


def test_cache_expires(settings, provider, tmp_path):
    now = [0.0]
    service = SearchService(settings, provider, Storage(str(tmp_path / "s.db")), clock=lambda: now[0])
    asyncio.run(service.search("acme widget 3000", US))
    now[0] = settings.cache_ttl_seconds - 1
    assert asyncio.run(service.search("acme widget 3000", US))["cached"] is True
    now[0] = settings.cache_ttl_seconds + 1
    assert asyncio.run(service.search("acme widget 3000", US))["cached"] is False
    assert len(provider.calls) == 2


def test_concurrent_identical_searches_share_one_fetch(settings, provider, tmp_path):
    service = SearchService(settings, provider, Storage(str(tmp_path / "s.db")))

    async def both():
        return await asyncio.gather(service.search("acme widget 3000", US),
                                    service.search("Acme Widget 3000", US))

    first, second = asyncio.run(both())
    assert len(provider.calls) == 1
    assert {first["cached"], second["cached"]} == {False, True}


def test_scheduler_rechecks_only_due_products(settings, provider, tmp_path):
    settings = dataclasses.replace(settings, refresh_hours=6)
    storage = Storage(str(tmp_path / "s.db"))
    service = SearchService(settings, provider, storage)
    fresh = storage.add_watch("acme widget 3000", "US", None)
    stale = storage.add_watch("acme widget 3000", "GB", None)
    never = storage.add_watch("other gadget", "US", None)

    recent = datetime.now(timezone.utc).isoformat(timespec="seconds")
    old = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(timespec="seconds")
    storage.update_watch(fresh["id"], last_checked_at=recent)
    storage.update_watch(stale["id"], last_checked_at=old)

    assert asyncio.run(scheduler.refresh_due(service, pause=0)) == 2
    assert sorted(provider.calls) == [("acme widget 3000", "GB"), ("other gadget", "US")]
    # "other gadget" matched nothing: recorded as an error, and not retried immediately.
    assert storage.get_watch(never["id"])["last_error"] == "No matching offers found"
    assert storage.get_watch(stale["id"])["latest_price"] == 20.0
    assert asyncio.run(scheduler.refresh_due(service, pause=0)) == 0


def test_alert_fires_once_per_drop(settings, provider, tmp_path, monkeypatch):
    sent = []
    settings = dataclasses.replace(settings, alert_webhook_url="https://hooks.example/x")
    storage = Storage(str(tmp_path / "s.db"))
    service = SearchService(settings, provider, storage)
    monkeypatch.setattr(service, "_notify", lambda watch, cheapest, region: sent.append(cheapest["total"]))
    storage.add_watch("acme widget 3000", "US", 19)

    def check(price):
        provider.offers = [Offer("SHOP", "Acme Widget 3000", price, f"${price}")]
        asyncio.run(service.search("acme widget 3000", US, refresh=True))

    check(25)
    check(18)      # crosses the target: alert
    check(17)      # still below: no repeat
    check(30)      # back above: re-arms
    check(15)      # crosses again: alert
    assert sent == [18, 15]
