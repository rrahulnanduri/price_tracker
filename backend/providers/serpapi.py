"""SerpApi Google Shopping API: structured results, no browser, needs SERPAPI_KEY.

More reliable than scraping because the store, price and delivery text arrive
as separate fields instead of being inferred from page layout.
"""

import httpx

from ..config import Region
from ..matching import Offer
from ..pricing import parse_price
from .base import ProviderBlocked, ProviderError, ProviderNotConfigured, parse_shipping, parse_stock

ENDPOINT = "https://serpapi.com/search.json"
TIMEOUT_SECONDS = 30


def parse_results(payload: dict, region: Region) -> list[Offer]:
    offers: list[Offer] = []
    for item in payload.get("shopping_results") or []:
        store = (item.get("source") or "").strip()
        title = (item.get("title") or "").strip()
        price_text = str(item.get("price") or "")
        price = parse_price(price_text, region.currency)
        if price is None and isinstance(item.get("extracted_price"), (int, float)):
            price = parse_price(str(item["extracted_price"]), region.currency)
        if not store or not title or price is None or price.currency != region.currency:
            continue

        extras = " | ".join(str(x) for x in (item.get("extensions") or []))
        delivery = f'{item.get("delivery") or ""} | {extras}'
        offer = Offer(
            store=store.upper(),
            title=title,
            price=price.value,
            price_text=price_text or f"{price.value:g}",
            url=item.get("link") or item.get("product_link") or "",
            shipping_cost=parse_shipping(delivery, region.currency),
            in_stock=parse_stock(delivery),
        )
        if item.get("second_hand_condition"):
            offer.title = f'{title} ({item["second_hand_condition"]})'
        offers.append(offer)
    return offers


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, product: str, region: Region) -> list[Offer]:
        if not self.api_key:
            raise ProviderNotConfigured("Set SERPAPI_KEY to use the SerpApi provider.")
        params = {
            "engine": "google_shopping",
            "q": product,
            "gl": region.gl,
            "hl": region.hl,
            "api_key": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.get(ENDPOINT, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach SerpApi: {type(exc).__name__}") from exc

        if response.status_code in (401, 403):
            raise ProviderNotConfigured("SerpApi rejected the API key.")
        if response.status_code == 429:
            raise ProviderBlocked("SerpApi quota exhausted.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("SerpApi returned a non-JSON response.") from exc

        error = payload.get("error")
        if error and "hasn't returned any results" not in error:
            raise ProviderError(f"SerpApi error: {error}")
        return parse_results(payload, region)
