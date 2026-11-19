import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import scheduler
from .config import DEFAULT_REGION, REGIONS, Region, Settings, get_region, load_settings
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


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    settings = settings or load_settings()
    storage = Storage(settings.db_path)
    service = SearchService(settings, provider or build_provider(settings), storage)

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

    async def run_search(product: str, region: Region, refresh: bool, client: str | None) -> dict:
        try:
            return await service.search(product, region, refresh=refresh, client=client)
        except RateLimited as exc:
            raise HTTPException(
                status_code=429,
                detail=f"Too many searches. Try again in {exc.retry_after}s.",
                headers={"Retry-After": str(exc.retry_after)},
            )
        except (ProviderNotConfigured, ProviderBlocked) as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except ProviderError as exc:
            logger.warning("Provider failed for %r (%s): %s", product, region.code, exc)
            raise HTTPException(status_code=502, detail="Could not reach the price source. Try again shortly.")
        except Exception:
            logger.exception("Search failed for %r (%s)", product, region.code)
            raise HTTPException(status_code=502, detail="Could not reach the price source. Try again shortly.")

    @app.get("/api/meta")
    def meta():
        return {
            "provider": service.provider.name,
            "default_region": DEFAULT_REGION,
            "refresh_hours": settings.refresh_hours,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
            "regions": [
                {"code": r.code, "label": r.label, "currency": r.currency, "locale": r.locale}
                for r in REGIONS.values()
            ],
        }

    @app.post("/api/search")
    async def search_prices(req: SearchRequest, request: Request):
        product, region = _product_or_422(req.product), _region_or_422(req.country)
        client = request.client.host if request.client else "unknown"
        result = await run_search(product, region, req.refresh, client)
        if not result["results"]:
            detail = "No results found. Try a different product name."
            if result["considered"]:
                detail = (f'Found {result["considered"]} listings, but none matched "{product}" '
                          "closely enough. Try a more specific name.")
            raise HTTPException(status_code=404, detail=detail)
        watch = storage.find_watch(product, region.code)
        return {**result, "watch": watch}

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

