"""The search pipeline: cache -> rate limit -> provider -> relevance ranking -> storage."""

import asyncio
import logging
import threading
import time
from collections import OrderedDict, deque

import httpx

from .config import Region, Settings
from .matching import score_offers, select_offers
from .providers import Provider
from .providers.multi import SourceReport
from .storage import Storage, now_iso, query_key

logger = logging.getLogger(__name__)


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Too many searches")
        self.retry_after = retry_after


class RateLimiter:
    """Sliding one-minute window per client. Only live fetches count, not cache hits."""

    WINDOW_SECONDS = 60
    SWEEP_AT = 1000   # clients tracked before idle ones are forgotten

    def __init__(self, per_minute: int, clock=time.monotonic):
        self.per_minute = per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _expire(self, hits: deque[float], now: float) -> None:
        while hits and now - hits[0] >= self.WINDOW_SECONDS:
            hits.popleft()

    def check(self, client: str) -> None:
        if self.per_minute <= 0:
            return
        now = self._clock()
        if len(self._hits) >= self.SWEEP_AT:
            # Drop clients with no hits left in the window, so memory follows active clients only.
            for key in list(self._hits):
                self._expire(self._hits[key], now)
                if not self._hits[key]:
                    del self._hits[key]
        hits = self._hits.setdefault(client, deque())
        self._expire(hits, now)
        if len(hits) >= self.per_minute:
            raise RateLimited(retry_after=max(1, int(self.WINDOW_SECONDS - (now - hits[0])) + 1))
        hits.append(now)

    def tracked_clients(self) -> int:
        return len(self._hits)


class SearchService:
    MAX_CACHED = 500   # search results kept in memory; least recently used go first

    def __init__(self, settings: Settings, provider: Provider, storage: Storage, clock=time.monotonic,
                 llm=None):
        self.settings = settings
        self.provider = provider
        self.storage = storage
        self.llm = llm   # optional backend.llm.LLMHelper for a second opinion on matching
        self._clock = clock
        self._cache: OrderedDict[tuple[str, str], tuple[float, dict]] = OrderedDict()
        self._in_flight: dict[tuple[str, str], asyncio.Lock] = {}
        self._fetch_slots = asyncio.Semaphore(settings.max_concurrent_fetches)
        self._limiter = RateLimiter(settings.rate_limit_per_minute, clock)

    def _cached(self, key: tuple[str, str]) -> dict | None:
        entry = self._cache.get(key)
        if entry and self._clock() - entry[0] < self.settings.cache_ttl_seconds:
            self._cache.move_to_end(key)
            return {**entry[1], "cached": True}
        self._cache.pop(key, None)
        return None

    async def search(self, product: str, region: Region, *, refresh: bool = False,
                     client: str | None = None, on_event=None) -> dict:
        """Ranked offers for a product. `client=None` (the scheduler) skips the rate limit.

        `on_event`, if given, is called with progress events as the search runs:
        {"type": "sources", "names": [...]}, {"type": "source", "name", "ok", "offers", "error"}
        and {"type": "stage", "stage": "matching" | "ai_review"}.
        """
        emit = on_event or (lambda event: None)
        product = " ".join(product.split())
        key = (query_key(product), region.code)

        if not refresh and (hit := self._cached(key)):
            return hit

        # Identical searches arriving together share one fetch instead of racing.
        lock = self._in_flight.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                if not refresh and (hit := self._cached(key)):
                    return hit
                if client is not None:
                    self._limiter.check(client)
                async with self._fetch_slots:
                    if hasattr(self.provider, "search_with_report"):
                        raw, reports = await self.provider.search_with_report(product, region, on_event=emit)
                    else:
                        emit({"type": "sources", "names": [self.provider.name]})
                        try:
                            raw = await self.provider.search(product, region)
                        except Exception as exc:
                            emit({"type": "source", "name": self.provider.name, "ok": False, "offers": 0,
                                  "error": str(exc) or type(exc).__name__})
                            raise
                        emit({"type": "source", "name": self.provider.name, "ok": True, "offers": len(raw),
                              "error": None})
                        reports = None
                result = await self._build_result(product, region, raw, reports, emit)
                if result["results"]:
                    self._remember(key, result)
                return result
        finally:
            if not lock.locked():
                self._in_flight.pop(key, None)

    def _remember(self, key: tuple[str, str], result: dict) -> None:
        self._cache[key] = (self._clock(), result)
        self._cache.move_to_end(key)
        while len(self._cache) > self.MAX_CACHED:
            self._cache.popitem(last=False)

    async def _build_result(self, product: str, region: Region, raw: list, reports=None,
                            emit=lambda event: None) -> dict:
        min_relevance = self.settings.min_relevance
        emit({"type": "stage", "stage": "matching"})
        for offer in raw:
            offer.source = offer.source or self.provider.name
        if reports is None:
            reports = [SourceReport(self.provider.name, ok=True, offers=len(raw))]
        score_offers(product, raw)
        ai_changed = None
        if self.llm is not None and self.llm.options.judge and raw:
            emit({"type": "stage", "stage": "ai_review"})
            ai_changed = await self.llm.review_matches(product, raw, min_relevance)
        ranked, rejected = select_offers(
            product, raw, min_relevance=min_relevance, limit=self.settings.max_results
        )
        results = [offer.to_dict() for offer in ranked]
        fetched_at = now_iso()
        if results:
            self.storage.record_search(product, region.code, region.currency, self.provider.name,
                                       results, fetched_at)
            self._after_observation(product, region, results[0])
        return {
            "product": product,
            "country": region.code,
            "region": region.label,
            "currency": region.currency,
            "locale": region.locale,
            "provider": self.provider.name,
            "fetched_at": fetched_at,
            "cached": False,
            "results": results,
            "considered": len(raw),
            "rejected": len(rejected),
            # How AI was involved: None if it was not asked; otherwise listings it changed.
            "ai_extracted": any(o.extracted_by == "ai" for o in raw),
            "ai_changed": ai_changed,
            # Each source asked, whether it answered, and how many listings it returned.
            "sources": [report.to_dict() for report in reports],
        }

    def _after_observation(self, product: str, region: Region, cheapest: dict) -> None:
        """Keep a matching watchlist entry up to date and fire its alert once per price drop."""
        watch = self.storage.find_watch(product, region.code)
        if not watch:
            return
        updates: dict = {"last_checked_at": now_iso(), "last_error": None}
        if watch["target_hit"] and not watch["alerted_at"]:
            updates["alerted_at"] = now_iso()
            self._notify(watch, cheapest, region)
        elif not watch["target_hit"] and watch["alerted_at"]:
            updates["alerted_at"] = None   # re-arm for the next drop
        self.storage.update_watch(watch["id"], **updates)

    def _notify(self, watch: dict, cheapest: dict, region: Region) -> None:
        logger.info("Price alert: %s at %s %s (target %s)", watch["product"], cheapest["total"],
                    region.currency, watch["target_price"])
        url = self.settings.alert_webhook_url
        if not url:
            return
        payload = {
            "text": (f'Price alert: {watch["product"]} is {cheapest["total"]} {region.currency} at '
                     f'{cheapest["store"]} (target {watch["target_price"]}). {cheapest["url"]}'),
            "product": watch["product"],
            "country": region.code,
            "currency": region.currency,
            "price": cheapest["total"],
            "store": cheapest["store"],
            "url": cheapest["url"],
            "target_price": watch["target_price"],
        }

        def send() -> None:
            try:
                httpx.post(url, json=payload, timeout=10)
            except httpx.HTTPError:
                logger.warning("Alert webhook failed for %s", watch["product"], exc_info=True)

        # Off the event loop: a slow webhook must not stall the search response.
        threading.Thread(target=send, daemon=True).start()
