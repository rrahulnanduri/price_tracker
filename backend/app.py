import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import scheduler
from .config import DEFAULT_REGION, REGIONS, Region, Settings, get_region, load_settings
from .llm import build_llm_helper
from .providers import (
    Provider,
    ProviderBlocked,
    ProviderError,
    ProviderNotConfigured,
    build_provider,
)
from .search import RateLimited, SearchService
from .storage import Storage

logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    product: str = Field(min_length=1, max_length=200)
    country: str = DEFAULT_REGION
    refresh: bool = False


class WatchRequest(BaseModel):
    product: str = Field(min_length=1, max_length=200)
    country: str = DEFAULT_REGION
    target_price: float | None = Field(default=None, gt=0)


class WatchUpdate(BaseModel):
    target_price: float | None = Field(default=None, gt=0)


def _region_or_422(country: str) -> Region:
    region = get_region(country)
    if region is None:
        raise HTTPException(status_code=422, detail=f"Unsupported region: {country}")
    return region


def _product_or_422(product: str) -> str:
    product = " ".join(product.split())
    if not product:
        raise HTTPException(status_code=422, detail="Product name is required.")
    return product


def create_app(settings: Settings | None = None, provider: Provider | None = None, llm=None) -> FastAPI:
    settings = settings or load_settings()
    storage = Storage(settings.db_path)
    if llm is None:
        llm = build_llm_helper(settings)
    service = SearchService(settings, provider or build_provider(settings, llm), storage, llm=llm)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if settings.refresh_hours > 0:
            task = asyncio.create_task(scheduler.run_forever(service))
        yield
        if task:
            task.cancel()
        storage.close()

    app = FastAPI(title="Price Tracker", lifespan=lifespan)
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def search_error(exc: Exception, product: str, region: Region) -> HTTPException:
        """The HTTP error a failed search should produce."""
        if isinstance(exc, HTTPException):
            return exc
        if isinstance(exc, RateLimited):
            return HTTPException(
                status_code=429,
                detail=f"Too many searches. Try again in {exc.retry_after}s.",
                headers={"Retry-After": str(exc.retry_after)},
            )
        if isinstance(exc, (ProviderNotConfigured, ProviderBlocked)):
            return HTTPException(status_code=503, detail=str(exc))
        if isinstance(exc, ProviderError):
            logger.warning("Provider failed for %r (%s): %s", product, region.code, exc)
        else:
            logger.error("Search failed for %r (%s)", product, region.code, exc_info=exc)
        return HTTPException(status_code=502, detail="Could not reach the price source. Try again shortly.")

    def finish(product: str, region: Region, result: dict) -> dict:
        """The response for a completed search; no matching offers is a 404."""
        if not result["results"]:
            detail = "No results found. Try a different product name."
            if result["considered"]:
                detail = (f'Found {result["considered"]} listings, but none matched "{product}" '
                          "closely enough. Try a more specific name.")
            raise HTTPException(status_code=404, detail=detail)
        return {**result, "watch": storage.find_watch(product, region.code)}

    async def run_search(product: str, region: Region, refresh: bool, client: str | None,
                         on_event=None) -> dict:
        try:
            result = await service.search(product, region, refresh=refresh, client=client, on_event=on_event)
            return finish(product, region, result)
        except Exception as exc:
            raise search_error(exc, product, region) from exc

    @app.get("/api/meta")
    def meta():
        return {
            "provider": service.provider.name,
            "default_region": DEFAULT_REGION,
            "refresh_hours": settings.refresh_hours,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
            "ai": {
                "model": llm.model if llm else None,
                "fallback": bool(llm and llm.options.fallback),
                "judge": bool(llm and llm.options.judge),
            },
            "regions": [
                {"code": r.code, "label": r.label, "currency": r.currency, "locale": r.locale}
                for r in REGIONS.values()
            ],
        }

    @app.post("/api/search")
    async def search_prices(req: SearchRequest, request: Request):
        product, region = _product_or_422(req.product), _region_or_422(req.country)
        client = request.client.host if request.client else "unknown"
        return await run_search(product, region, req.refresh, client)

    @app.post("/api/search/stream")
    async def search_prices_stream(req: SearchRequest, request: Request):
        """The same search, sent as newline-delimited JSON: progress events, then one result or error."""
        product, region = _product_or_422(req.product), _region_or_422(req.country)
        client = request.client.host if request.client else "unknown"
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def work() -> None:
            try:
                result = await run_search(product, region, req.refresh, client, on_event=queue.put_nowait)
                queue.put_nowait({"type": "result", "data": result})
            except HTTPException as exc:
                queue.put_nowait({"type": "error", "status": exc.status_code, "detail": exc.detail})

        async def lines():
            task = asyncio.create_task(work())
            try:
                while True:
                    event = await queue.get()
                    yield json.dumps(event, ensure_ascii=False) + "\n"
                    if event["type"] in ("result", "error"):
                        break
            finally:
                if not task.done():
                    task.cancel()   # the browser went away: stop the search

        return StreamingResponse(lines(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/history")
    def history(product: str, country: str = DEFAULT_REGION):
        region = _region_or_422(country)
        return {"product": product, "country": region.code, "currency": region.currency,
                "points": storage.history(_product_or_422(product), region.code)}

    @app.get("/api/watchlist")
    def list_watches():
        return {"items": storage.list_watches()}

    @app.post("/api/watchlist", status_code=201)
    def add_watch(req: WatchRequest):
        product, region = _product_or_422(req.product), _region_or_422(req.country)
        return storage.add_watch(product, region.code, req.target_price)

    @app.patch("/api/watchlist/{watch_id}")
    def update_watch(watch_id: int, req: WatchUpdate):
        # Changing the target re-arms the alert.
        if not storage.update_watch(watch_id, target_price=req.target_price, alerted_at=None):
            raise HTTPException(status_code=404, detail="Not on the watchlist.")
        return storage.get_watch(watch_id)

    @app.delete("/api/watchlist/{watch_id}", status_code=204)
    def delete_watch(watch_id: int):
        if not storage.delete_watch(watch_id):
            raise HTTPException(status_code=404, detail="Not on the watchlist.")

    @app.get("/health")
    def health():
        return {"status": "ok", "provider": service.provider.name}

    return app

