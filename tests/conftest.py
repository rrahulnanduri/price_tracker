import dataclasses

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import load_settings
from backend.matching import Offer


class FakeProvider:
    """A provider whose answers a test sets directly."""

    name = "fake"

    def __init__(self):
        self.offers: list[Offer] = []
        self.error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    async def search(self, product, region):
        self.calls.append((product, region.code))
        if self.error:
            raise self.error
        return [dataclasses.replace(o) for o in self.offers]


def offer(store, price, title="Acme Widget 3000", **extra) -> Offer:
    return Offer(store.upper(), title, price, f"${price:.2f}", f"https://{store.lower()}.example/p", **extra)


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(
        load_settings(), provider="demo", db_path=str(tmp_path / "test.db"),
        refresh_hours=0, rate_limit_per_minute=0, alert_webhook_url="",
        cache_ttl_seconds=900, min_relevance=0.7, max_results=8,
    )


@pytest.fixture
def provider():
    fake = FakeProvider()
    fake.offers = [offer("Shop B", 30), offer("Shop A", 20), offer("Shop C", 25)]
    return fake


@pytest.fixture
def client(settings, provider):
    with TestClient(create_app(settings, provider)) as test_client:
        yield test_client
