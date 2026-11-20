"""SerpApi Google Shopping API: structured results, no browser, needs SERPAPI_KEY.

More reliable than scraping because the store, price and delivery text arrive
as separate fields instead of being inferred from page layout.
"""

import logging

import httpx

from ..config import Region
from ..matching import Offer, score_relevance
from ..pricing import parse_price
from .base import ProviderBlocked, ProviderError, ProviderNotConfigured, parse_shipping, parse_stock

logger = logging.getLogger(__name__)

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


def parse_stores(payload: dict, region: Region, title: str) -> list[Offer]:
    """Every seller from a google_immersive_product response (product_results.stores)."""
    offers: list[Offer] = []
    for store in (payload.get("product_results") or {}).get("stores") or []:
        name = (store.get("name") or "").strip()
        price_text = str(store.get("price") or "")
        price = parse_price(price_text, region.currency)
        if price is None and isinstance(store.get("extracted_price"), (int, float)):
            price = parse_price(str(store["extracted_price"]), region.currency)
        if not name or price is None or price.currency != region.currency:
            continue
        shipping = store.get("shipping_extracted")
        if not isinstance(shipping, (int, float)):
            shipping = parse_shipping(str(store.get("shipping") or ""), region.currency)
        details = " | ".join(str(d) for d in store.get("details_and_offers") or [])
        offers.append(Offer(
            store=name.upper(),
            title=(store.get("title") or title).strip(),
            price=price.value,
            price_text=price_text or f"{price.value:g}",
            url=store.get("link") or "",
            shipping_cost=float(shipping) if isinstance(shipping, (int, float)) else None,
            in_stock=parse_stock(details),
            source="serpapi",
        ))
    return offers


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, api_key: str, seller_lookups: int = 0):
        self.api_key = api_key
        # Product pages to open for their full seller list. Each costs one extra SerpApi search.
        self.seller_lookups = seller_lookups

    async def _call(self, client: httpx.AsyncClient, params: dict) -> dict:
        try:
            response = await client.get(ENDPOINT, params={**params, "api_key": self.api_key})
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
        return payload

    async def search(self, product: str, region: Region) -> list[Offer]:
        if not self.api_key:
            raise ProviderNotConfigured("Set SERPAPI_KEY to use the SerpApi provider.")
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            payload = await self._call(client, {
                "engine": "google_shopping", "q": product, "gl": region.gl, "hl": region.hl,
            })
            offers = parse_results(payload, region)
            if self.seller_lookups <= 0:
                return offers

            # Open the product pages of the best-matching results for every seller of that exact item.
            ranked = sorted(
                (item for item in payload.get("shopping_results") or [] if item.get("immersive_product_page_token")),
                key=lambda item: -score_relevance(product, item.get("title") or "")[0],
            )
            picks = [item for item in ranked if score_relevance(product, item.get("title") or "")[0] >= 0.7]
            for item in picks[: self.seller_lookups]:
                try:
                    detail = await self._call(client, {
                        "engine": "google_immersive_product",
                        "page_token": item["immersive_product_page_token"],
                        "more_stores": "true",
                        "gl": region.gl, "hl": region.hl,
                    })
                except ProviderError as exc:
                    logger.info("Seller lookup failed for %r: %s", item.get("title"), exc)
                    continue
                offers.extend(parse_stores(detail, region, item.get("title") or product))
            return offers
