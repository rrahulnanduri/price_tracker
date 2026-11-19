import dataclasses

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.providers import ProviderBlocked, ProviderError, ProviderNotConfigured

from .conftest import offer

WIDGET = {"product": "acme widget 3000", "country": "US"}


def test_search_ranks_cheapest_first(client, provider):
    res = client.post("/api/search", json={"product": "  acme   widget 3000 ", "country": "us"})
    assert res.status_code == 200
    body = res.json()
    assert [r["store"] for r in body["results"]] == ["SHOP A", "SHOP C", "SHOP B"]
    assert body["currency"] == "USD" and body["provider"] == "fake" and body["cached"] is False
    assert provider.calls == [("acme widget 3000", "US")]


def test_search_ranks_by_total_including_shipping(client, provider):
    provider.offers = [offer("Cheap", 20, shipping_cost=15), offer("Fair", 25, shipping_cost=0)]
    results = client.post("/api/search", json=WIDGET).json()["results"]
    assert [(r["store"], r["total"]) for r in results] == [("FAIR", 25.0), ("CHEAP", 35.0)]


def test_search_puts_out_of_stock_last(client, provider):
    provider.offers = [offer("Gone", 10, in_stock=False), offer("Here", 20, in_stock=True)]
    results = client.post("/api/search", json=WIDGET).json()["results"]
    assert [r["store"] for r in results] == ["HERE", "GONE"]


def test_search_drops_accessories(client, provider):
    provider.offers += [offer("Shop D", 2, title="Case for Acme Widget 3000")]
    body = client.post("/api/search", json=WIDGET).json()
    assert "SHOP D" not in [r["store"] for r in body["results"]]
    assert body["considered"] == 4 and body["rejected"] == 1


def test_second_search_is_served_from_cache(client, provider):
    client.post("/api/search", json=WIDGET)
    again = client.post("/api/search", json={"product": "ACME Widget 3000", "country": "US"})
    assert again.json()["cached"] is True
    assert len(provider.calls) == 1


def test_refresh_bypasses_cache(client, provider):
    client.post("/api/search", json=WIDGET)
    client.post("/api/search", json={**WIDGET, "refresh": True})
    assert len(provider.calls) == 2


def test_regions_do_not_share_cache(client, provider):
    client.post("/api/search", json=WIDGET)
    client.post("/api/search", json={**WIDGET, "country": "GB"})
    assert [c[1] for c in provider.calls] == ["US", "GB"]


def test_search_errors(client, provider):
    assert client.post("/api/search", json={"product": "   "}).status_code == 422
    assert client.post("/api/search", json={"product": ""}).status_code == 422
    assert client.post("/api/search", json={"product": "x", "country": "ZZ"}).status_code == 422

    provider.offers = []
    assert client.post("/api/search", json=WIDGET).status_code == 404

    provider.offers = [offer("Shop", 5, title="Something unrelated entirely")]
    res = client.post("/api/search", json=WIDGET)
    assert res.status_code == 404 and "none matched" in res.json()["detail"]

    provider.error = ProviderBlocked("Google is rate-limiting this address.")
    res = client.post("/api/search", json=WIDGET)
    assert res.status_code == 503 and "rate-limiting" in res.json()["detail"]

    provider.error = ProviderNotConfigured("Set SERPAPI_KEY")
    assert client.post("/api/search", json=WIDGET).status_code == 503

    provider.error = ProviderError("secret internals")
    res = client.post("/api/search", json=WIDGET)
    assert res.status_code == 502 and "secret" not in res.json()["detail"]

    provider.error = RuntimeError("secret internals")
    res = client.post("/api/search", json=WIDGET)
    assert res.status_code == 502 and "secret" not in res.json()["detail"]


def test_rate_limit_counts_only_live_fetches(settings, provider):
    limited = dataclasses.replace(settings, rate_limit_per_minute=2)
    with TestClient(create_app(limited, provider)) as client:
        for name in ("acme widget 3000", "acme widget 3000", "acme widget 3000 blue"):
            provider.offers = [offer("Shop", 10, title=name)]
            assert client.post("/api/search", json={"product": name}).status_code == 200
        provider.offers = [offer("Shop", 10, title="acme widget 3000 red")]
        res = client.post("/api/search", json={"product": "acme widget 3000 red"})
        assert res.status_code == 429 and int(res.headers["Retry-After"]) >= 1


def test_meta_lists_regions(client):
    body = client.get("/api/meta").json()
    codes = [r["code"] for r in body["regions"]]
    assert {"US", "NL", "JP", "AE"} <= set(codes)
    assert body["provider"] == "fake" and body["default_region"] == "US"


def test_history_accumulates_one_point_per_live_fetch(client, provider):
    client.post("/api/search", json=WIDGET)
    provider.offers = [offer("Shop A", 18), offer("Shop B", 30)]
    client.post("/api/search", json={**WIDGET, "refresh": True})
    client.post("/api/search", json=WIDGET)   # cache hit: no new point

    points = client.get("/api/history", params=WIDGET).json()["points"]
    assert [p["lowest"] for p in points] == [20.0, 18.0]
    assert points[1]["stores"] == {"SHOP A": 18.0, "SHOP B": 30.0}
    assert client.get("/api/history", params={"product": "never searched"}).json()["points"] == []


def test_watchlist_lifecycle(client, provider):
    assert client.get("/api/watchlist").json()["items"] == []

    created = client.post("/api/watchlist", json={**WIDGET, "target_price": 19})
    assert created.status_code == 201
    watch = created.json()
    assert watch["latest_price"] is None and watch["target_hit"] is False

    # Adding the same product again (any casing) updates rather than duplicates.
    client.post("/api/watchlist", json={"product": "ACME widget 3000", "country": "US"})
    assert len(client.get("/api/watchlist").json()["items"]) == 1

    body = client.post("/api/search", json=WIDGET).json()
    assert body["watch"]["id"] == watch["id"]
    item = client.get("/api/watchlist").json()["items"][0]
    assert item["latest_price"] == 20.0 and item["latest_store"] == "SHOP A"
    assert item["target_hit"] is False and item["last_checked_at"]

    provider.offers = [offer("Shop A", 18)]
    client.post("/api/search", json={**WIDGET, "refresh": True})
    item = client.get("/api/watchlist").json()["items"][0]
    assert item["target_hit"] is True and item["alerted_at"]
    assert item["previous_price"] == 20.0 and item["lowest_ever"] == 18.0

    patched = client.patch(f'/api/watchlist/{watch["id"]}', json={"target_price": None}).json()
    assert patched["target_price"] is None and patched["target_hit"] is False

    assert client.delete(f'/api/watchlist/{watch["id"]}').status_code == 204
    assert client.delete(f'/api/watchlist/{watch["id"]}').status_code == 404
    assert client.patch("/api/watchlist/999", json={"target_price": 5}).status_code == 404
    assert client.post("/api/watchlist", json={"product": "x", "target_price": -1}).status_code == 422
